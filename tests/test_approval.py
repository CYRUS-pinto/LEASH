"""Tests for Acceptance Criterion 3:
Approval for refund A cannot execute refund B.
"""

import pytest
from fastapi.testclient import TestClient

from gateway.server import app as gateway_app, clear_pending_approvals
from leash.db import reset_db
from leash.receipt import verify_receipt
from tools_server.server import app as tools_app, clear_seen_nonces


@pytest.fixture(autouse=True)
def setup_db_and_clean():
    reset_db()
    clear_pending_approvals()
    clear_seen_nonces()


def test_approval_for_action_a_cannot_execute_action_b():
    gw_client = TestClient(gateway_app)
    tools_client = TestClient(tools_app)

    # 1. Propose large refund A ($450.00 for ord_102) which exceeds $300 auto-approval threshold -> ESCALATE
    refund_a_args = {
        "order_id": "ord_102",
        "amount": 450.0,
        "recipient_email": "billing@acme.com",
    }
    prop_res = gw_client.post(
        "/gateway/propose",
        json={
            "agent_id": "agent_01",
            "role": "support_agent",
            "tool": "issue_refund",
            "args": refund_a_args,
        },
    )
    assert prop_res.status_code == 200
    data = prop_res.json()
    assert data["verdict"] == "ESCALATE"
    approval_id = data["approval_id"]
    assert approval_id is not None

    # 2. Malicious attempt: Try to approve refund B ($1200.00 to attacker or different order) using approval_id of A
    refund_b_args = {
        "order_id": "ord_102",
        "amount": 1200.0,
        "recipient_email": "attacker@darkweb.org",
    }
    tamper_res = gw_client.post(
        f"/gateway/approvals/{approval_id}/approve",
        json={"tool": "issue_refund", "args": refund_b_args, "approver": "supervisor_alice"},
    )
    assert tamper_res.status_code == 403
    assert "Action mismatch" in tamper_res.json()["detail"]

    # 3. Legitimate approval of refund A
    appr_res = gw_client.post(
        f"/gateway/approvals/{approval_id}/approve",
        json={"tool": "issue_refund", "args": refund_a_args, "approver": "supervisor_alice"},
    )
    assert appr_res.status_code == 200
    approval_data = appr_res.json()
    receipt_a = approval_data["receipt"]
    assert receipt_a is not None

    # 4. Try to submit receipt_a to tool server with refund B args -> Tool server rejects!
    exec_b = tools_client.post(
        "/tools/execute",
        json={"tool": "issue_refund", "args": refund_b_args, "receipt": receipt_a},
    )
    assert exec_b.status_code == 400
    assert "do not match receipt" in exec_b.json()["detail"].lower()

    # 5. Legitimate execution of refund A with receipt_a succeeds
    exec_a = tools_client.post(
        "/tools/execute",
        json={"tool": "issue_refund", "args": refund_a_args, "receipt": receipt_a},
    )
    assert exec_a.status_code == 200
    assert exec_a.json()["status"] == "success"
    assert exec_a.json()["order_id"] == "ord_102"
    assert exec_a.json()["amount"] == 450.0

    # 6. Attempting to approve or reuse the consumed approval a second time is rejected
    reuse_res = gw_client.post(
        f"/gateway/approvals/{approval_id}/approve",
        json={"tool": "issue_refund", "args": refund_a_args, "approver": "supervisor_alice"},
    )
    assert reuse_res.status_code == 400
    assert "cannot be processed" in reuse_res.json()["detail"].lower()
