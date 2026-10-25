"""LEASH Action-Control Gateway FastAPI Server."""

import time
import uuid
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import httpx

from leash.audit import append_audit_entry, get_audit_connection, init_audit_db, verify_audit_chain
from leash.db import init_db
from leash.config import AUDIT_DB_PATH, BASE_DIR, GATEWAY_HMAC_SECRET, POLICY_FILE_PATH, TOOLS_HOST, TOOLS_PORT
from leash.receipt import compute_action_hash, create_receipt, verify_receipt
from gateway.pipeline import PipelineResult, evaluate_action

app = FastAPI(title="LEASH Gateway", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# In-memory storage for action-bound pending approvals
# approval_id -> { "approval_id", "agent_id", "role", "tool", "args", "action_hash", "reason", "created_at", "expires_at", "status", "used" }
PENDING_APPROVALS: Dict[str, Dict[str, Any]] = {}


class ProposeActionRequest(BaseModel):
    agent_id: str = "agent_01"
    role: str = "support_agent"
    tool: str
    args: Dict[str, Any] = Field(default_factory=dict)
    context: Optional[Dict[str, Any]] = None


class ApproveRequest(BaseModel):
    tool: Optional[str] = None
    args: Optional[Dict[str, Any]] = None
    approver: str = "security_lead"


class RejectRequest(BaseModel):
    reason: Optional[str] = "Rejected by human supervisor"
    approver: str = "security_lead"


@app.on_event("startup")
def startup():
    init_db(seed=True)
    init_audit_db()


@app.get("/health")
def health():
    return {"status": "ok", "service": "leash_gateway"}


@app.post("/gateway/propose")
def propose_action(req: ProposeActionRequest):
    result: PipelineResult = evaluate_action(
        agent_id=req.agent_id,
        role=req.role,
        tool=req.tool,
        args=req.args,
        context=req.context,
    )

    resp = {
        "verdict": result.verdict,
        "reason": result.reason,
        "action_hash": result.action_hash,
        "tool": result.tool,
        "args": result.args,
        "agent_id": result.agent_id,
        "role": result.role,
        "stage_trace": result.stage_trace,
    }

    if result.verdict in ("ALLOW", "REDACT"):
        resp["receipt"] = result.receipt

    elif result.verdict == "ESCALATE":
        approval_id = f"appr_{uuid.uuid4().hex[:12]}"
        now = time.time()
        PENDING_APPROVALS[approval_id] = {
            "approval_id": approval_id,
            "agent_id": req.agent_id,
            "role": req.role,
            "tool": result.tool,
            "args": result.args,
            "action_hash": result.action_hash,
            "reason": result.reason,
            "created_at": now,
            "expires_at": now + 300.0,  # 5 minutes expiry
            "status": "PENDING",
            "used": False,
        }
        resp["approval_id"] = approval_id
        resp["expires_in_seconds"] = 300

    return resp


@app.post("/gateway/execute")
async def execute_via_gateway(req: ProposeActionRequest):
    """Convenience endpoint: evaluates action, and if allowed, invokes protected tool server."""
    res = propose_action(req)
    verdict = res.get("verdict")

    if verdict not in ("ALLOW", "REDACT"):
        return {
            "status": "blocked_or_escalated",
            "gateway_result": res,
            "tool_executed": False,
        }

    receipt = res.get("receipt")
    tools_url = f"http://{TOOLS_HOST}:{TOOLS_PORT}/tools/execute"

    async with httpx.AsyncClient() as client:
        try:
            tool_res = await client.post(
                tools_url,
                json={"tool": res["tool"], "args": res["args"], "receipt": receipt},
                timeout=5.0,
            )
            return {
                "status": "executed",
                "gateway_result": res,
                "tool_executed": True,
                "tool_response": tool_res.json(),
                "tool_status_code": tool_res.status_code,
            }
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Failed to communicate with tools server: {e}")


@app.get("/gateway/approvals")
def list_approvals():
    now = time.time()
    active = []
    for app_id, data in list(PENDING_APPROVALS.items()):
        if data["status"] == "PENDING" and now > data["expires_at"]:
            data["status"] = "EXPIRED"
        active.append(data)
    return {"approvals": active}


@app.post("/gateway/approvals/{approval_id}/approve")
def approve_action(approval_id: str, req: ApproveRequest):
    """
    Approves an escalated action.
    Action-bound: Verifies that if tool/args are provided, they match the exact action_hash.
    Single-use: Cannot be approved twice.
    Expires in 5 minutes.
    """
    now = time.time()
    approval = PENDING_APPROVALS.get(approval_id)

    if not approval:
        raise HTTPException(status_code=404, detail=f"Approval '{approval_id}' not found")

    if approval["used"] or approval["status"] != "PENDING":
        raise HTTPException(
            status_code=400,
            detail=f"Approval '{approval_id}' cannot be processed (status: {approval['status']}, used: {approval['used']})",
        )

    if now > approval["expires_at"]:
        approval["status"] = "EXPIRED"
        raise HTTPException(status_code=400, detail="Approval expired (valid for 5 minutes)")

    # ACTION-BOUND CHECK:
    # If caller provided tool/args to execute with this approval, verify against the approval's action_hash!
    target_tool = req.tool or approval["tool"]
    target_args = req.args if req.args is not None else approval["args"]
    target_hash = compute_action_hash(target_tool, target_args)

    if target_hash != approval["action_hash"]:
        raise HTTPException(
            status_code=403,
            detail=f"Action mismatch: Approval '{approval_id}' is bound to action_hash {approval['action_hash']}, but attempted for {target_hash}",
        )

    # Mark as approved and consumed (single-use)
    approval["status"] = "APPROVED"
    approval["used"] = True
    approval["approved_by"] = req.approver
    approval["approved_at"] = now

    # Mint receipt for the approved action
    receipt = create_receipt(
        tool=target_tool,
        args=target_args,
        decision="ALLOW",
        policy_version="1.0.0",
        secret=GATEWAY_HMAC_SECRET,
    )

    # Log to audit log
    append_audit_entry(
        agent_id=approval["agent_id"],
        role=approval["role"],
        tool=target_tool,
        args=target_args,
        action_hash=target_hash,
        verdict="ALLOW",
        reason=f"Approved by supervisor ({req.approver}) after escalation: {approval['reason']}",
    )

    return {
        "status": "approved",
        "approval_id": approval_id,
        "action_hash": target_hash,
        "receipt": receipt,
        "tool": target_tool,
        "args": target_args,
    }


@app.post("/gateway/approvals/{approval_id}/reject")
def reject_action(approval_id: str, req: RejectRequest):
    now = time.time()
    approval = PENDING_APPROVALS.get(approval_id)

    if not approval:
        raise HTTPException(status_code=404, detail=f"Approval '{approval_id}' not found")

    if approval["used"] or approval["status"] != "PENDING":
        raise HTTPException(
            status_code=400,
            detail=f"Approval '{approval_id}' cannot be rejected (status: {approval['status']})",
        )

    approval["status"] = "REJECTED"
    approval["used"] = True
    approval["rejected_by"] = req.approver
    approval["rejected_at"] = now
    approval["rejection_reason"] = req.reason

    append_audit_entry(
        agent_id=approval["agent_id"],
        role=approval["role"],
        tool=approval["tool"],
        args=approval["args"],
        action_hash=approval["action_hash"],
        verdict="BLOCK",
        reason=f"Rejected by supervisor ({req.approver}): {req.reason}",
    )

    return {"status": "rejected", "approval_id": approval_id}


@app.get("/gateway/audit")
def list_audit_entries(limit: int = 50):
    conn = get_audit_connection()
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='audit_log'")
    if not cur.fetchone():
        conn.close()
        return {"entries": []}

    cur.execute("SELECT * FROM audit_log ORDER BY seq DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"entries": rows}


@app.get("/gateway/verify-audit")
def verify_audit_endpoint():
    is_valid, msg, head_hash, count = verify_audit_chain()
    return {
        "verified": is_valid,
        "message": msg,
        "head_hash": head_hash,
        "entry_count": count,
    }


@app.post("/gateway/reset")
def reset_gateway_state():
    from gateway.pipeline import BREAKER_STATE
    BREAKER_STATE.reset()
    clear_pending_approvals()
    return {"status": "ok", "message": "Gateway circuit breaker and approvals reset"}


@app.get("/title_card.html")
@app.get("/cards")
@app.get("/docs/title_card.html")
def serve_title_cards():
    card_path = BASE_DIR / "docs" / "title_card.html"
    if card_path.exists():
        return FileResponse(str(card_path))
    fallback = BASE_DIR / "dashboard" / "title_card.html"
    if fallback.exists():
        return FileResponse(str(fallback))
    raise HTTPException(status_code=404, detail="Title cards not found")


# Mount dashboard static files at root
DASHBOARD_DIR = BASE_DIR / "dashboard"
if DASHBOARD_DIR.exists():
    app.mount("/", StaticFiles(directory=str(DASHBOARD_DIR), html=True), name="dashboard")


# Helper for testing
def clear_pending_approvals():
    PENDING_APPROVALS.clear()
