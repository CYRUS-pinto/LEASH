"""Protected Tool Server for LEASH.

This server manages execution of protected actions (refunds, emails, SQL)
and strictly enforces that NO protected action is executed without a valid,
unexpired, non-replayed gateway HMAC receipt.
"""

import sqlite3
import time
from typing import Any, Dict, Optional, Set
from fastapi import FastAPI, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field

from leash.config import BUSINESS_DB_PATH, GATEWAY_HMAC_SECRET
from leash.db import get_db_connection, init_db
from leash.receipt import verify_receipt

app = FastAPI(title="LEASH Protected Tool Server", version="0.1.0")

# Store used nonces in memory (and persistable) for replay prevention
_SEEN_NONCES: Set[str] = set()


class ExecuteToolRequest(BaseModel):
    tool: str
    args: Dict[str, Any] = Field(default_factory=dict)
    receipt: Optional[Dict[str, Any]] = None


class RefundArgs(BaseModel):
    order_id: str
    amount: float
    recipient_email: str
    receipt: Optional[Dict[str, Any]] = None


class EmailArgs(BaseModel):
    recipient: str
    subject: str
    body: str
    receipt: Optional[Dict[str, Any]] = None


class SqlArgs(BaseModel):
    query: str
    receipt: Optional[Dict[str, Any]] = None


def execute_action(tool: str, args: Dict[str, Any], db_path: Optional[str] = None) -> Dict[str, Any]:
    """Executes the protected action on the business system of record."""
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        if tool == "issue_refund":
            order_id = args.get("order_id")
            amount = float(args.get("amount", 0.0))
            recipient_email = args.get("recipient_email")

            cur.execute("SELECT id, refundable_amount FROM orders WHERE id = ?", (order_id,))
            order = cur.fetchone()
            if not order:
                raise HTTPException(status_code=404, detail=f"Order {order_id} not found")

            new_refundable = order["refundable_amount"] - amount
            cur.execute(
                "UPDATE orders SET refundable_amount = ? WHERE id = ?",
                (new_refundable, order_id),
            )
            cur.execute(
                "INSERT INTO refunds (order_id, amount, recipient_email) VALUES (?, ?, ?)",
                (order_id, amount, recipient_email),
            )
            refund_id = cur.lastrowid
            conn.commit()

            return {
                "status": "success",
                "tool": "issue_refund",
                "refund_id": refund_id,
                "order_id": order_id,
                "amount": amount,
                "recipient_email": recipient_email,
                "remaining_refundable": new_refundable,
            }

        elif tool == "send_email":
            recipient = args.get("recipient")
            subject = args.get("subject", "")
            body = args.get("body", "")

            cur.execute(
                "INSERT INTO emails (recipient, subject, body) VALUES (?, ?, ?)",
                (recipient, subject, body),
            )
            email_id = cur.lastrowid
            conn.commit()

            return {
                "status": "success",
                "tool": "send_email",
                "email_id": email_id,
                "recipient": recipient,
                "subject": subject,
            }

        elif tool == "run_sql":
            query = args.get("query", "").strip()
            cur.execute(
                "INSERT INTO sql_audit (query, statement_type) VALUES (?, ?)",
                (query, "SELECT"),
            )
            cur.execute(query)
            rows = [dict(r) for r in cur.fetchall()[:100]]
            conn.commit()

            return {
                "status": "success",
                "tool": "run_sql",
                "row_count": len(rows),
                "rows": rows,
            }

        else:
            raise HTTPException(status_code=400, detail=f"Unsupported tool: {tool}")

    finally:
        conn.close()


def validate_and_record_receipt(
    tool: str, args: Dict[str, Any], receipt: Optional[Dict[str, Any]], secret: str = GATEWAY_HMAC_SECRET
):
    if not receipt:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: Direct tool execution rejected. Valid gateway receipt required.",
        )

    is_valid, reason = verify_receipt(
        receipt=receipt,
        tool=tool,
        args=args,
        seen_nonces=_SEEN_NONCES,
        secret=secret,
    )

    if not is_valid:
        if "signature" in reason.lower():
            raise HTTPException(status_code=403, detail=f"Forbidden: {reason}")
        elif "expired" in reason.lower() or "replay" in reason.lower() or "not match" in reason.lower():
            raise HTTPException(status_code=400, detail=f"Bad Request: {reason}")
        else:
            raise HTTPException(status_code=400, detail=f"Receipt validation failed: {reason}")

    # Mark nonce as consumed
    _SEEN_NONCES.add(receipt["nonce"])


@app.on_event("startup")
def startup_event():
    init_db()


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "protected_tool_server"}


@app.post("/tools/execute")
def execute_tool(req: ExecuteToolRequest):
    validate_and_record_receipt(req.tool, req.args, req.receipt)
    result = execute_action(req.tool, req.args)
    return result


@app.post("/tools/issue_refund")
def direct_refund(req: RefundArgs):
    args = {"order_id": req.order_id, "amount": req.amount, "recipient_email": req.recipient_email}
    validate_and_record_receipt("issue_refund", args, req.receipt)
    return execute_action("issue_refund", args)


@app.post("/tools/send_email")
def direct_email(req: EmailArgs):
    args = {"recipient": req.recipient, "subject": req.subject, "body": req.body}
    validate_and_record_receipt("send_email", args, req.receipt)
    return execute_action("send_email", args)


@app.post("/tools/run_sql")
def direct_sql(req: SqlArgs):
    args = {"query": req.query}
    validate_and_record_receipt("run_sql", args, req.receipt)
    return execute_action("run_sql", args)


# Helper for testing to clear used nonces
def clear_seen_nonces():
    _SEEN_NONCES.clear()
