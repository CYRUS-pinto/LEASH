"""Tests for Acceptance Criterion 4:
Killing the gateway or corrupting the policy file never results in an executed protected action.
Fail-closed property verification.
"""

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from gateway.pipeline import evaluate_action
from gateway.server import app as gateway_app
from leash.config import POLICY_FILE_PATH
from leash.db import init_db
from tools_server.server import app as tools_app


@pytest.fixture(autouse=True)
def setup_db():
    init_db(seed=True)


def test_corrupted_policy_file_fails_closed(tmp_path):
    client = TestClient(gateway_app)
    backup_content = POLICY_FILE_PATH.read_text(encoding="utf-8")

    try:
        # Corrupt the policy file with invalid syntax
        POLICY_FILE_PATH.write_text("{ corrupted invalid json syntax ...", encoding="utf-8")

        res = client.post(
            "/gateway/propose",
            json={
                "agent_id": "agent_01",
                "role": "support_agent",
                "tool": "issue_refund",
                "args": {"order_id": "ord_101", "amount": 10.0, "recipient_email": "billing@acme.com"},
            },
        )
        assert res.status_code == 200
        data = res.json()
        # MUST BE BLOCK, NEVER ALLOW
        assert data["verdict"] == "BLOCK"
        assert "Fail closed" in data["reason"]
        assert "receipt" not in data or data["receipt"] is None

        # Verify tool server rejects because no receipt was minted
        tools_client = TestClient(tools_app)
        tool_res = tools_client.post(
            "/tools/execute",
            json={
                "tool": "issue_refund",
                "args": {"order_id": "ord_101", "amount": 10.0, "recipient_email": "billing@acme.com"},
                "receipt": None,
            },
        )
        assert tool_res.status_code == 401
        assert "Direct tool execution rejected" in tool_res.json()["detail"]

    finally:
        # Restore policy file
        POLICY_FILE_PATH.write_text(backup_content, encoding="utf-8")


def test_missing_policy_file_fails_closed():
    client = TestClient(gateway_app)
    backup_content = POLICY_FILE_PATH.read_text(encoding="utf-8")

    try:
        # Temporarily remove policy file
        POLICY_FILE_PATH.unlink()

        res = client.post(
            "/gateway/propose",
            json={
                "agent_id": "agent_01",
                "role": "support_agent",
                "tool": "issue_refund",
                "args": {"order_id": "ord_101", "amount": 10.0, "recipient_email": "billing@acme.com"},
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["verdict"] == "BLOCK"
        assert "Fail closed" in data["reason"]
        assert "receipt" not in data or data["receipt"] is None

    finally:
        POLICY_FILE_PATH.write_text(backup_content, encoding="utf-8")


def test_corrupted_policy_schema_fails_closed():
    backup_content = POLICY_FILE_PATH.read_text(encoding="utf-8")

    try:
        # Valid JSON but missing required 'roles' key
        POLICY_FILE_PATH.write_text(json.dumps({"invalid_key": 123}), encoding="utf-8")

        result = evaluate_action(
            agent_id="agent_01",
            role="support_agent",
            tool="issue_refund",
            args={"order_id": "ord_101", "amount": 10.0, "recipient_email": "billing@acme.com"},
        )
        assert result.verdict == "BLOCK"
        assert "Fail closed" in result.reason
        assert result.receipt is None

    finally:
        POLICY_FILE_PATH.write_text(backup_content, encoding="utf-8")
