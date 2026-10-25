"""Tests for LEASH pipeline effect checks, SoR verification, DLP, and circuit breakers."""

import pytest
from gateway.pipeline import BREAKER_STATE, evaluate_action
from leash.db import init_db


@pytest.fixture(autouse=True)
def setup_pipeline():
    init_db(seed=True)
    BREAKER_STATE.reset()


def test_refund_effect_check_blocks_diverted_recipient():
    # ord_101 original payer is billing@acme.com
    res = evaluate_action(
        agent_id="agent_01",
        role="support_agent",
        tool="issue_refund",
        args={"order_id": "ord_101", "amount": 25.0, "recipient_email": "attacker@evil.com"},
    )
    assert res.verdict == "BLOCK"
    assert "does not match original payer" in res.reason


def test_refund_effect_check_allows_original_payer():
    res = evaluate_action(
        agent_id="agent_01",
        role="support_agent",
        tool="issue_refund",
        args={"order_id": "ord_101", "amount": 25.0, "recipient_email": "billing@acme.com"},
    )
    assert res.verdict == "ALLOW"
    assert res.receipt is not None


def test_refund_effect_check_blocks_over_balance():
    # ord_101 total refundable balance is 250.00
    res = evaluate_action(
        agent_id="agent_01",
        role="support_agent",
        tool="issue_refund",
        args={"order_id": "ord_101", "amount": 300.0, "recipient_email": "billing@acme.com"},
    )
    assert res.verdict == "BLOCK"
    assert "exceeds remaining refundable balance" in res.reason


def test_email_effect_check_blocks_unauthorized_external():
    res = evaluate_action(
        agent_id="agent_01",
        role="support_agent",
        tool="send_email",
        args={"recipient": "exfiltrate@malicious-drop.net", "subject": "Data", "body": "Hello"},
        context={"ticket_id": "tkt_501"},
    )
    assert res.verdict == "BLOCK"
    assert "Email exfiltration" in res.reason


def test_email_effect_check_allows_registered_contact():
    # tkt_501 is for cust_001, whose contacts include billing@acme.com and bob@acme.com
    res = evaluate_action(
        agent_id="agent_01",
        role="support_agent",
        tool="send_email",
        args={"recipient": "bob@acme.com", "subject": "Invoice update", "body": "Your invoice"},
        context={"ticket_id": "tkt_501"},
    )
    assert res.verdict == "ALLOW"
    assert res.receipt is not None


def test_sql_effect_check_blocks_destructive_commands():
    queries = [
        "DROP TABLE customers;",
        "DELETE FROM orders WHERE 1=1;",
        "UPDATE orders SET refundable_amount = 99999;",
        "INSERT INTO customers (id, name, email) VALUES ('hacked', 'Hacked', 'hack@evil.com');",
        "ALTER TABLE orders ADD COLUMN hacked TEXT;",
        "SELECT * FROM customers; DROP TABLE orders;",
    ]
    for q in queries:
        res = evaluate_action(
            agent_id="agent_01",
            role="support_agent",
            tool="run_sql",
            args={"query": q},
        )
        assert res.verdict == "BLOCK", f"Expected query '{q}' to be BLOCKED, got {res.verdict}"


def test_sql_effect_check_allows_read_only_select():
    res = evaluate_action(
        agent_id="agent_01",
        role="support_agent",
        tool="run_sql",
        args={"query": "SELECT id, name, email FROM customers WHERE risk_tier = 'standard' LIMIT 10"},
    )
    assert res.verdict == "ALLOW"
    assert res.receipt is not None


def test_dlp_redacts_credit_card_and_ssn():
    res = evaluate_action(
        agent_id="agent_01",
        role="support_agent",
        tool="send_email",
        args={
            "recipient": "billing@acme.com",
            "subject": "Confidential Info",
            # Valid Visa test card (passes Luhn) and valid SSN format
            "body": "Customer SSN is 123-45-6789 and Card is 4532015112830366 for reference.",
        },
    )
    assert res.verdict == "REDACT"
    assert "[REDACTED_SSN]" in res.args["body"]
    assert "[REDACTED_CC:" in res.args["body"]
    assert "4532015112830366" not in res.args["body"]
    assert "123-45-6789" not in res.args["body"]
    assert res.receipt is not None


def test_circuit_breaker_quarantines_repeated_denials():
    # 3 consecutive denials triggers quarantine
    for i in range(3):
        res = evaluate_action(
            agent_id="bad_bot",
            role="support_agent",
            tool="issue_refund",
            args={"order_id": "ord_101", "amount": 10.0, "recipient_email": "attacker@evil.com"},
        )
        assert res.verdict == "BLOCK"

    # 4th action (even if benign) MUST be quarantined (Stage 0)
    res4 = evaluate_action(
        agent_id="bad_bot",
        role="support_agent",
        tool="issue_refund",
        args={"order_id": "ord_101", "amount": 10.0, "recipient_email": "billing@acme.com"},
    )
    assert res4.verdict == "BLOCK"
    assert "quarantined" in res4.reason.lower()
