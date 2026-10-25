"""Tests for Acceptance Criterion 2:
Direct tool-server call without receipt → rejected.
Replayed receipt → rejected.
Modified args → rejected.
Expired → rejected.
"""

import time
import pytest
from fastapi.testclient import TestClient

from leash.config import GATEWAY_HMAC_SECRET
from leash.db import init_db
from leash.receipt import compute_action_hash, create_receipt
from tools_server.server import app as tools_app, clear_seen_nonces


@pytest.fixture(autouse=True)
def setup_db_and_nonces():
    init_db(seed=True)
    clear_seen_nonces()


def test_direct_call_without_receipt_rejected():
    client = TestClient(tools_app)

    # Direct call to /tools/issue_refund without receipt
    res = client.post(
        "/tools/issue_refund",
        json={"order_id": "ord_101", "amount": 10.0, "recipient_email": "billing@acme.com"},
    )
    assert res.status_code == 401
    assert "Direct tool execution rejected" in res.json()["detail"]

    # Direct call to /tools/execute without receipt
    res2 = client.post(
        "/tools/execute",
        json={
            "tool": "issue_refund",
            "args": {"order_id": "ord_101", "amount": 10.0, "recipient_email": "billing@acme.com"},
        },
    )
    assert res2.status_code == 401
    assert "Direct tool execution rejected" in res2.json()["detail"]


def test_replayed_receipt_rejected():
    client = TestClient(tools_app)
    args = {"order_id": "ord_101", "amount": 5.0, "recipient_email": "billing@acme.com"}
    receipt = create_receipt("issue_refund", args)

    # First execution succeeds
    res1 = client.post("/tools/execute", json={"tool": "issue_refund", "args": args, "receipt": receipt})
    assert res1.status_code == 200
    assert res1.json()["status"] == "success"

    # Second execution with identical receipt MUST be rejected (replay attack)
    res2 = client.post("/tools/execute", json={"tool": "issue_refund", "args": args, "receipt": receipt})
    assert res2.status_code == 400
    assert "replay detected" in res2.json()["detail"].lower()


def test_modified_args_with_receipt_rejected():
    client = TestClient(tools_app)
    original_args = {"order_id": "ord_101", "amount": 5.0, "recipient_email": "billing@acme.com"}
    receipt = create_receipt("issue_refund", original_args)

    # Attacker tampers with amount or recipient
    tampered_args = {"order_id": "ord_101", "amount": 250.0, "recipient_email": "attacker@evil.com"}
    res = client.post("/tools/execute", json={"tool": "issue_refund", "args": tampered_args, "receipt": receipt})
    assert res.status_code == 400
    assert "do not match receipt" in res.json()["detail"].lower()


def test_expired_receipt_rejected():
    client = TestClient(tools_app)
    args = {"order_id": "ord_101", "amount": 5.0, "recipient_email": "billing@acme.com"}
    # Create receipt with negative expiry (-10 seconds)
    receipt = create_receipt("issue_refund", args, expiry_seconds=-10)

    res = client.post("/tools/execute", json={"tool": "issue_refund", "args": args, "receipt": receipt})
    assert res.status_code == 400
    assert "expired" in res.json()["detail"].lower()


def test_forged_signature_receipt_rejected():
    client = TestClient(tools_app)
    args = {"order_id": "ord_101", "amount": 5.0, "recipient_email": "billing@acme.com"}
    # Receipt signed with wrong attacker key
    receipt = create_receipt("issue_refund", args, secret="attacker-fake-secret-key-12345")

    res = client.post("/tools/execute", json={"tool": "issue_refund", "args": args, "receipt": receipt})
    assert res.status_code == 403
    assert "signature" in res.json()["detail"].lower()
