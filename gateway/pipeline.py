"""Deterministic 8-Stage Decision Pipeline for LEASH Gateway."""

import time
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel

from leash.audit import append_audit_entry
from leash.config import GATEWAY_HMAC_SECRET, POLICY_FILE_PATH
from leash.db import get_db_connection
from leash.receipt import compute_action_hash, create_receipt
from gateway.policy import (
    PolicyError,
    check_and_redact_dlp,
    check_email_effect,
    check_parameter_constraints,
    check_provenance_taint,
    check_refund_effect,
    check_role_scope,
    check_sql_statement_effect,
    load_policy,
)


class CircuitBreakerState:
    """In-memory state tracker for caps, rolling spend, rate limits, and quarantines."""

    def __init__(self):
        # agent_id -> list of float timestamps
        self.request_history: Dict[str, List[float]] = {}
        # agent_id -> list of float timestamps of BLOCKs
        self.block_history: Dict[str, List[float]] = {}
        # agent_id -> quarantine_expiry_timestamp
        self.quarantined_until: Dict[str, float] = {}

    def is_quarantined(self, agent_id: str, now: Optional[float] = None) -> Tuple[bool, float]:
        t = now or time.time()
        expiry = self.quarantined_until.get(agent_id, 0.0)
        if t < expiry:
            return True, expiry - t
        return False, 0.0

    def record_request(self, agent_id: str, now: Optional[float] = None) -> int:
        t = now or time.time()
        if agent_id not in self.request_history:
            self.request_history[agent_id] = []
        # Keep within last 60 seconds
        self.request_history[agent_id] = [ts for ts in self.request_history[agent_id] if t - ts <= 60.0]
        self.request_history[agent_id].append(t)
        return len(self.request_history[agent_id])

    def record_block(
        self, agent_id: str, threshold: int = 3, window: float = 300.0, duration: float = 600.0, now: Optional[float] = None
    ) -> bool:
        t = now or time.time()
        if agent_id not in self.block_history:
            self.block_history[agent_id] = []
        self.block_history[agent_id] = [ts for ts in self.block_history[agent_id] if t - ts <= window]
        self.block_history[agent_id].append(t)

        if len(self.block_history[agent_id]) >= threshold:
            self.quarantined_until[agent_id] = t + duration
            return True
        return False

    def reset(self):
        self.request_history.clear()
        self.block_history.clear()
        self.quarantined_until.clear()


BREAKER_STATE = CircuitBreakerState()


class PipelineResult(BaseModel):
    verdict: str  # ALLOW | REDACT | ESCALATE | BLOCK
    reason: str
    action_hash: str
    tool: str
    args: Dict[str, Any]
    agent_id: str
    role: str
    stage_trace: List[Dict[str, Any]]
    receipt: Optional[Dict[str, Any]] = None
    approval_id: Optional[str] = None


def check_rolling_refund_budget(proposed_amount: float, max_budget: float = 3000.0) -> Tuple[bool, float]:
    """Checks sum of refunds processed in the last 1 hour + proposed amount."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT SUM(amount) FROM refunds WHERE timestamp >= datetime('now', '-1 hour') AND status = 'processed'"
    )
    row = cur.fetchone()
    conn.close()

    current_sum = float(row[0] or 0.0) if row else 0.0
    projected = current_sum + proposed_amount
    return (projected <= max_budget), projected


def evaluate_action(
    agent_id: str,
    role: str,
    tool: str,
    args: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None,
    current_time: Optional[float] = None,
    secret: str = GATEWAY_HMAC_SECRET,
) -> PipelineResult:
    """
    Executes the 8-stage deterministic decision pipeline.
    Fail-closed: Any unhandled exception or policy error produces BLOCK/ESCALATE.
    """
    now = current_time or time.time()
    ctx = context or {}
    stage_trace: List[Dict[str, Any]] = []
    action_args = dict(args)
    action_hash = compute_action_hash(tool, action_args)

    try:
        # Load policy
        try:
            policy = load_policy()
        except Exception as e:
            # Fail closed: cannot evaluate without policy
            stage_trace.append({"stage": -1, "name": "policy_load", "verdict": "BLOCK", "reason": str(e)})
            final_reason = f"Fail closed: Policy load failed: {e}"
            append_audit_entry(agent_id, role, tool, action_args, action_hash, "BLOCK", final_reason)
            return PipelineResult(
                verdict="BLOCK",
                reason=final_reason,
                action_hash=action_hash,
                tool=tool,
                args=action_args,
                agent_id=agent_id,
                role=role,
                stage_trace=stage_trace,
            )

        policy_ver = policy.get("policy_version", "1.0.0")

        # -------------------------------------------------------------
        # Stage 0: Quarantine Check
        # -------------------------------------------------------------
        is_q, remaining = BREAKER_STATE.is_quarantined(agent_id, now)
        if is_q:
            reason = f"Agent '{agent_id}' is quarantined due to repeated violations ({int(remaining)}s remaining)"
            stage_trace.append({"stage": 0, "name": "quarantine_check", "verdict": "BLOCK", "reason": reason})
            append_audit_entry(agent_id, role, tool, action_args, action_hash, "BLOCK", reason)
            return PipelineResult(
                verdict="BLOCK",
                reason=reason,
                action_hash=action_hash,
                tool=tool,
                args=action_args,
                agent_id=agent_id,
                role=role,
                stage_trace=stage_trace,
            )
        stage_trace.append({"stage": 0, "name": "quarantine_check", "verdict": "PASS", "reason": "Agent not quarantined"})

        # -------------------------------------------------------------
        # Stage 1: Role Scope (Default-Deny)
        # -------------------------------------------------------------
        role_ok, role_reason = check_role_scope(role, tool, policy)
        if not role_ok:
            stage_trace.append({"stage": 1, "name": "role_scope", "verdict": "BLOCK", "reason": role_reason})
            BREAKER_STATE.record_block(agent_id, now=now)
            append_audit_entry(agent_id, role, tool, action_args, action_hash, "BLOCK", role_reason)
            return PipelineResult(
                verdict="BLOCK",
                reason=role_reason,
                action_hash=action_hash,
                tool=tool,
                args=action_args,
                agent_id=agent_id,
                role=role,
                stage_trace=stage_trace,
            )
        stage_trace.append({"stage": 1, "name": "role_scope", "verdict": "PASS", "reason": role_reason})

        # -------------------------------------------------------------
        # Stage 2: Parameter Constraints (Schema & Basic Bounds)
        # -------------------------------------------------------------
        param_ok, param_reason = check_parameter_constraints(tool, action_args)
        if not param_ok:
            stage_trace.append({"stage": 2, "name": "parameter_constraints", "verdict": "BLOCK", "reason": param_reason})
            BREAKER_STATE.record_block(agent_id, now=now)
            append_audit_entry(agent_id, role, tool, action_args, action_hash, "BLOCK", param_reason)
            return PipelineResult(
                verdict="BLOCK",
                reason=param_reason,
                action_hash=action_hash,
                tool=tool,
                args=action_args,
                agent_id=agent_id,
                role=role,
                stage_trace=stage_trace,
            )
        stage_trace.append({"stage": 2, "name": "parameter_constraints", "verdict": "PASS", "reason": param_reason})

        # -------------------------------------------------------------
        # Stage 3: Effect Checks against System of Record (SoR)
        # -------------------------------------------------------------
        effect_verdict = "ALLOW"
        effect_reason = "Effect checks passed"

        if tool == "issue_refund":
            effect_verdict, effect_reason = check_refund_effect(
                order_id=action_args["order_id"],
                amount=float(action_args["amount"]),
                recipient_email=action_args["recipient_email"],
                role=role,
                policy=policy,
            )
        elif tool == "send_email":
            ticket_id = ctx.get("ticket_id") or action_args.get("ticket_id")
            effect_verdict, effect_reason = check_email_effect(
                recipient=action_args["recipient"],
                subject=action_args["subject"],
                body=action_args["body"],
                ticket_id=ticket_id,
                policy=policy,
            )
        elif tool == "run_sql":
            effect_verdict, effect_reason = check_sql_statement_effect(
                query=action_args["query"],
                policy=policy,
            )

        if effect_verdict == "BLOCK":
            stage_trace.append({"stage": 3, "name": "effect_checks", "verdict": "BLOCK", "reason": effect_reason})
            BREAKER_STATE.record_block(agent_id, now=now)
            append_audit_entry(agent_id, role, tool, action_args, action_hash, "BLOCK", effect_reason)
            return PipelineResult(
                verdict="BLOCK",
                reason=effect_reason,
                action_hash=action_hash,
                tool=tool,
                args=action_args,
                agent_id=agent_id,
                role=role,
                stage_trace=stage_trace,
            )
        stage_trace.append({"stage": 3, "name": "effect_checks", "verdict": effect_verdict, "reason": effect_reason})

        # -------------------------------------------------------------
        # Stage 4: Provenance / Taint Analysis (Risk Signal)
        # -------------------------------------------------------------
        taint_verdict, taint_reason = check_provenance_taint(tool, action_args, ctx)
        stage_trace.append({"stage": 4, "name": "provenance_taint", "verdict": taint_verdict, "reason": taint_reason})

        # -------------------------------------------------------------
        # Stage 5: DLP / Redaction
        # -------------------------------------------------------------
        dlp_verdict, dlp_reason, sanitized_args = check_and_redact_dlp(tool, action_args)
        stage_trace.append({"stage": 5, "name": "dlp_redaction", "verdict": dlp_verdict, "reason": dlp_reason})
        if dlp_verdict == "REDACT":
            action_args = sanitized_args
            # Update action_hash for sanitized args
            action_hash = compute_action_hash(tool, action_args)

        # -------------------------------------------------------------
        # Stage 6: Caps & Circuit Breakers (Budget, Rate Limits)
        # -------------------------------------------------------------
        req_count = BREAKER_STATE.record_request(agent_id, now)
        rate_limit = policy.get("limits", {}).get("rate_limit_per_minute", 60)
        if req_count > rate_limit:
            cap_reason = f"Rate limit exceeded: {req_count} requests in 60s (max {rate_limit})"
            stage_trace.append({"stage": 6, "name": "caps_breakers", "verdict": "BLOCK", "reason": cap_reason})
            BREAKER_STATE.record_block(agent_id, now=now)
            append_audit_entry(agent_id, role, tool, action_args, action_hash, "BLOCK", cap_reason)
            return PipelineResult(
                verdict="BLOCK",
                reason=cap_reason,
                action_hash=action_hash,
                tool=tool,
                args=action_args,
                agent_id=agent_id,
                role=role,
                stage_trace=stage_trace,
            )

        if tool == "issue_refund":
            budget_limit = policy.get("limits", {}).get("rolling_refund_budget_1h", 3000.0)
            budget_ok, projected = check_rolling_refund_budget(float(action_args["amount"]), budget_limit)
            if not budget_ok:
                budget_reason = f"Rolling 1-hour refund budget limit (${budget_limit:.2f}) exceeded: projected total ${projected:.2f}"
                stage_trace.append({"stage": 6, "name": "caps_breakers", "verdict": "BLOCK", "reason": budget_reason})
                BREAKER_STATE.record_block(agent_id, now=now)
                append_audit_entry(agent_id, role, tool, action_args, action_hash, "BLOCK", budget_reason)
                return PipelineResult(
                    verdict="BLOCK",
                    reason=budget_reason,
                    action_hash=action_hash,
                    tool=tool,
                    args=action_args,
                    agent_id=agent_id,
                    role=role,
                    stage_trace=stage_trace,
                )

        stage_trace.append({"stage": 6, "name": "caps_breakers", "verdict": "PASS", "reason": "Limits and caps satisfied"})

        # -------------------------------------------------------------
        # Stage 7: Final Verdict Assembly
        # -------------------------------------------------------------
        # Hard invariants: If effect_verdict == ESCALATE or taint_verdict == ESCALATE -> ESCALATE
        final_verdict = "ALLOW"
        final_reason = "Action approved by policy and system of record verification"

        if effect_verdict == "ESCALATE":
            final_verdict = "ESCALATE"
            final_reason = effect_reason
        elif taint_verdict == "ESCALATE":
            final_verdict = "ESCALATE"
            final_reason = taint_reason
        elif dlp_verdict == "REDACT":
            final_verdict = "REDACT"
            final_reason = dlp_reason

        # Log to hash-chained audit
        append_audit_entry(agent_id, role, tool, action_args, action_hash, final_verdict, final_reason)

        receipt = None
        if final_verdict in ("ALLOW", "REDACT"):
            receipt = create_receipt(
                tool=tool,
                args=action_args,
                decision="ALLOW",
                policy_version=policy_ver,
                secret=secret,
            )

        stage_trace.append({"stage": 7, "name": "final_verdict", "verdict": final_verdict, "reason": final_reason})

        return PipelineResult(
            verdict=final_verdict,
            reason=final_reason,
            action_hash=action_hash,
            tool=tool,
            args=action_args,
            agent_id=agent_id,
            role=role,
            stage_trace=stage_trace,
            receipt=receipt,
        )

    except Exception as exc:
        # Ultimate fail-closed catch
        fail_reason = f"Fail closed: Unexpected gateway exception: {exc}"
        try:
            append_audit_entry(agent_id, role, tool, action_args, action_hash, "BLOCK", fail_reason)
        except Exception:
            pass
        stage_trace.append({"stage": 7, "name": "fail_closed_exception", "verdict": "BLOCK", "reason": fail_reason})
        return PipelineResult(
            verdict="BLOCK",
            reason=fail_reason,
            action_hash=action_hash,
            tool=tool,
            args=action_args,
            agent_id=agent_id,
            role=role,
            stage_trace=stage_trace,
        )
