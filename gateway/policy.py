"""Policy and System-of-Record Effect Validation Engine for LEASH Gateway."""

import json
import re
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import sqlparse
from sqlparse.sql import Statement
from sqlparse.tokens import DDL, DML, Keyword

from leash.config import BUSINESS_DB_PATH, POLICY_FILE_PATH
from leash.db import get_db_connection


class PolicyError(Exception):
    """Raised when policy file is missing, unreadable, or invalid."""
    pass


def load_policy(policy_path: Optional[Path] = None) -> Dict[str, Any]:
    path = policy_path or POLICY_FILE_PATH
    if not path.exists():
        raise PolicyError(f"Policy file not found: {path}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            policy = json.load(f)
    except Exception as e:
        raise PolicyError(f"Failed to load/parse policy file: {e}")

    # Validate essential schema
    if "roles" not in policy or "policy_version" not in policy:
        raise PolicyError("Policy missing 'roles' or 'policy_version' schema definition")

    return policy


# -------------------------------------------------------------
# Stage 1: Role Scope Checks
# -------------------------------------------------------------
def check_role_scope(
    role: str, tool: str, policy: Dict[str, Any]
) -> Tuple[bool, str]:
    roles = policy.get("roles", {})
    if role not in roles:
        return False, f"Role '{role}' is not recognized in policy (default-deny)"

    allowed_tools = roles[role].get("allowed_tools", [])
    if tool not in allowed_tools:
        return False, f"Tool '{tool}' is not permitted for role '{role}' (default-deny)"

    return True, f"Tool '{tool}' permitted for role '{role}'"


# -------------------------------------------------------------
# Stage 2: Parameter Constraints (Schema & basic bounds)
# -------------------------------------------------------------
def check_parameter_constraints(
    tool: str, args: Dict[str, Any]
) -> Tuple[bool, str]:
    if not isinstance(args, dict):
        return False, "Tool arguments must be a JSON dictionary"

    if tool == "issue_refund":
        order_id = args.get("order_id")
        amount = args.get("amount")
        recipient_email = args.get("recipient_email")

        if not order_id or not isinstance(order_id, str):
            return False, "Parameter 'order_id' must be a non-empty string"
        if amount is None or not isinstance(amount, (int, float)):
            return False, "Parameter 'amount' must be a valid number"
        if amount <= 0:
            return False, f"Parameter 'amount' must be positive (received: {amount})"
        if not recipient_email or not isinstance(recipient_email, str) or "@" not in recipient_email:
            return False, "Parameter 'recipient_email' must be a valid email address"

    elif tool == "send_email":
        recipient = args.get("recipient")
        subject = args.get("subject")
        body = args.get("body")

        if not recipient or not isinstance(recipient, str) or "@" not in recipient:
            return False, "Parameter 'recipient' must be a valid email address"
        if subject is None or not isinstance(subject, str):
            return False, "Parameter 'subject' must be a string"
        if body is None or not isinstance(body, str):
            return False, "Parameter 'body' must be a string"

    elif tool == "run_sql":
        query = args.get("query")
        if not query or not isinstance(query, str) or not query.strip():
            return False, "Parameter 'query' must be a non-empty string"

    else:
        return False, f"Unknown tool '{tool}'"

    return True, "Parameter constraints satisfied"


# -------------------------------------------------------------
# Stage 3: Effect Checks against System of Record (SoR)
# -------------------------------------------------------------
def check_sql_statement_effect(
    query: str, policy: Dict[str, Any]
) -> Tuple[str, str]:
    """
    Parses SQL and strictly verifies it is a single read-only SELECT statement.
    Does NOT rely on naive regex alone.
    Returns: (verdict: 'ALLOW' | 'BLOCK', reason: str)
    """
    cleaned = query.strip()
    statements = sqlparse.parse(cleaned)

    if not statements or len(statements) == 0:
        return "BLOCK", "SQL query could not be parsed"

    if len(statements) > 1:
        return "BLOCK", "Multiple SQL statements detected (batch execution prohibited)"

    stmt: Statement = statements[0]
    stmt_type = stmt.get_type()

    allowed_types = policy.get("sql_rules", {}).get("allowed_statements", ["SELECT"])
    if stmt_type not in allowed_types:
        return "BLOCK", f"SQL statement type '{stmt_type}' prohibited (only {allowed_types} permitted)"

    # Thorough check against DDL or DML tokens in statement tree
    prohibited_keywords = set(
        policy.get("sql_rules", {}).get("prohibited_keywords", [])
    )
    for token in stmt.flatten():
        token_val = token.value.upper()
        if token_val in prohibited_keywords:
            return "BLOCK", f"Prohibited SQL keyword detected: '{token_val}'"

    # Block DELETE/DROP patterns even if disguised
    upper_query = cleaned.upper()
    if any(k in upper_query for k in ["DROP TABLE", "DELETE FROM", "TRUNCATE TABLE", "ALTER TABLE"]):
        return "BLOCK", "Forbidden DDL/DML operation detected in SQL text"

    return "ALLOW", f"SQL statement parsed as read-only {stmt_type}"


def check_refund_effect(
    order_id: str,
    amount: float,
    recipient_email: str,
    role: str,
    policy: Dict[str, Any],
    db_path: Optional[Path] = None,
) -> Tuple[str, str]:
    """
    Effect check for refund against SQLite SoR:
    1. Order exists
    2. Recipient matches original payer of that order
    3. Amount <= remaining refundable balance
    4. Amount <= role limits; triggers ESCALATE if above threshold
    """
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, customer_id, original_payer_email, amount, status, refundable_amount FROM orders WHERE id = ?",
        (order_id,),
    )
    order = cur.fetchone()
    conn.close()

    if not order:
        return "BLOCK", f"Order '{order_id}' does not exist in system of record"

    if order["status"] != "completed":
        return "BLOCK", f"Order '{order_id}' status is '{order['status']}', not eligible for refund"

    # CRITICAL EFFECT CHECK: Recipient must be original payer
    orig_payer = order["original_payer_email"].strip().lower()
    proposed_recipient = recipient_email.strip().lower()

    if orig_payer != proposed_recipient:
        return (
            "BLOCK",
            f"Laundered/Redirected refund blocked: recipient '{proposed_recipient}' does not match original payer '{orig_payer}' in system of record",
        )

    # Check remaining refundable balance
    refundable = order["refundable_amount"]
    if amount > refundable:
        return (
            "BLOCK",
            f"Refund amount ${amount:.2f} exceeds remaining refundable balance ${refundable:.2f} for order {order_id}",
        )

    # Role limits and thresholds
    role_cfg = policy.get("roles", {}).get(role, {})
    max_limit = role_cfg.get("max_single_refund", 500.0)
    escalate_thresh = role_cfg.get("escalate_refund_threshold", 300.0)

    if amount > max_limit:
        return "BLOCK", f"Refund amount ${amount:.2f} exceeds maximum allowed limit for role '{role}' (${max_limit:.2f})"

    if amount > escalate_thresh:
        return (
            "ESCALATE",
            f"Refund amount ${amount:.2f} exceeds automatic approval threshold (${escalate_thresh:.2f}) for role '{role}'; human approval required",
        )

    return "ALLOW", f"Refund effect verified against order {order_id} (original payer: {orig_payer})"


def check_email_effect(
    recipient: str,
    subject: str,
    body: str,
    ticket_id: Optional[str],
    policy: Dict[str, Any],
    db_path: Optional[Path] = None,
) -> Tuple[str, str]:
    """
    Effect check for email against SQLite SoR:
    Recipient must be a registered contact of the ticket's customer or in trusted domain.
    """
    proposed = recipient.strip().lower()
    trusted_domains = policy.get("email_rules", {}).get("trusted_domains", [])

    for domain in trusted_domains:
        if proposed.endswith(domain.lower()):
            return "ALLOW", f"Recipient domain '{domain}' is in trusted internal domains allow-list"

    conn = get_db_connection(db_path)
    cur = conn.cursor()

    if ticket_id:
        cur.execute("SELECT customer_id FROM tickets WHERE id = ?", (ticket_id,))
        tkt = cur.fetchone()
        if tkt:
            cust_id = tkt["customer_id"]
            cur.execute("SELECT email FROM contacts WHERE customer_id = ?", (cust_id,))
            valid_contacts = [r["email"].strip().lower() for r in cur.fetchall()]
            conn.close()

            if proposed in valid_contacts:
                return "ALLOW", f"Recipient '{proposed}' is a registered contact for customer '{cust_id}' on ticket '{ticket_id}'"
            else:
                return (
                    "BLOCK",
                    f"Email exfiltration blocked: recipient '{proposed}' is not a registered contact for customer '{cust_id}' on ticket '{ticket_id}'",
                )

    # If no ticket_id provided, check if recipient is a registered contact of ANY customer
    cur.execute("SELECT email, customer_id FROM contacts WHERE lower(email) = ?", (proposed,))
    match = cur.fetchone()
    conn.close()

    if match:
        return "ALLOW", f"Recipient '{proposed}' is a registered contact of customer '{match['customer_id']}'"

    return (
        "BLOCK",
        f"Email exfiltration/forwarding blocked: recipient '{proposed}' is neither a registered customer contact nor a trusted domain",
    )


# -------------------------------------------------------------
# Stage 4: Provenance / Taint Analysis (as Risk Signal)
# -------------------------------------------------------------
def check_provenance_taint(
    tool: str, args: Dict[str, Any], context: Dict[str, Any]
) -> Tuple[str, str]:
    """
    Inspects tainted strings from untrusted sources (prompts, ticket text, emails).
    Serves as an additional risk signal.
    """
    tainted = context.get("taint_sources", [])
    if not tainted:
        return "ALLOW", "No tainted provenance tags present"

    # Check for direct flow of attacker-injected strings into tool arguments
    dangerous_signatures = [
        "evil", "attacker", "hacker", "drop table", "delete from",
        "1=1", "bypass", "exfiltrate", "admin=1", "chariot"
    ]

    args_str = json.dumps(args).lower()
    for item in tainted:
        item_lower = str(item).lower()
        for sig in dangerous_signatures:
            if sig in item_lower and sig in args_str:
                return "ESCALATE", f"Taint provenance signal: suspicious pattern '{sig}' flowed from untrusted source into arguments"

    return "ALLOW", "Taint inspection passed without triggering elevation"


# -------------------------------------------------------------
# Stage 5: DLP / Data Loss Prevention (PII & Secret Redaction)
# -------------------------------------------------------------
# Luhn algorithm for credit card detection
def luhn_checksum_valid(card_num: str) -> bool:
    digits = [int(c) for c in card_num if c.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False
    checksum = 0
    reverse_digits = digits[::-1]
    for i, d in enumerate(reverse_digits):
        if i % 2 == 1:
            doubled = d * 2
            checksum += (doubled - 9) if doubled > 9 else doubled
        else:
            checksum += d
    return checksum % 10 == 0


CC_REGEX = re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b|\b\d{15,16}\b")
SSN_REGEX = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
API_KEY_REGEX = re.compile(r"\b(?:sk-[a-zA-Z0-9]{20,}|ghp_[a-zA-Z0-9]{20,}|[A-Za-z0-9+/]{40}=)\b")


def check_and_redact_dlp(
    tool: str, args: Dict[str, Any]
) -> Tuple[str, str, Dict[str, Any]]:
    """
    Inspects outbound text for sensitive PII / secrets.
    If found in email body, redacts in-place and issues REDACT verdict.
    """
    redacted_args = dict(args)
    findings = []

    if tool == "send_email":
        body = args.get("body", "")
        modified_body = body

        # Check SSNs
        if SSN_REGEX.search(body):
            modified_body = SSN_REGEX.sub("[REDACTED_SSN]", modified_body)
            findings.append("SSN")

        # Check Credit Cards
        for match in CC_REGEX.finditer(body):
            raw_match = match.group(0)
            cleaned = re.sub(r"[-\s]", "", raw_match)
            if luhn_checksum_valid(cleaned):
                masked = f"[REDACTED_CC: ****-****-****-{cleaned[-4:]}]"
                modified_body = modified_body.replace(raw_match, masked)
                findings.append("CreditCard")

        # Check API keys
        if API_KEY_REGEX.search(body):
            modified_body = API_KEY_REGEX.sub("[REDACTED_SECRET_KEY]", modified_body)
            findings.append("APIKey")

        if findings:
            redacted_args["body"] = modified_body
            return (
                "REDACT",
                f"DLP active: detected and redacted sensitive items ({', '.join(set(findings))}) in outbound body",
                redacted_args,
            )

    return "ALLOW", "No sensitive PII/secrets detected in outbound arguments", redacted_args
