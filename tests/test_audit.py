"""Tests for Acceptance Criterion 5:
`verify-audit` passes on a clean log and fails after a one-row edit.
"""

import sqlite3
import subprocess
import sys
from pathlib import Path
import pytest

from leash.audit import append_audit_entry, verify_audit_chain
from leash_cli import anchor_audit, verify_audit


def test_verify_audit_passes_on_clean_log(tmp_path):
    test_db = tmp_path / "test_audit.db"

    # Append 5 legitimate entries
    for i in range(1, 6):
        append_audit_entry(
            agent_id=f"agent_{i:02d}",
            role="support_agent",
            tool="issue_refund",
            args={"order_id": f"ord_{100+i}", "amount": float(i * 10), "recipient_email": "billing@acme.com"},
            action_hash=f"hash_{i:04d}",
            verdict="ALLOW",
            reason=f"Legitimate action {i} verified",
            db_path=test_db,
        )

    # 1. API verification passes
    is_valid, msg, head_hash, count = verify_audit_chain(test_db)
    assert is_valid is True
    assert count == 5
    assert head_hash is not None

    # 2. Standalone CLI verification passes with exit code 0
    code = verify_audit(test_db)
    assert code == 0


def test_verify_audit_fails_after_one_row_edit(tmp_path):
    test_db = tmp_path / "test_tampered_audit.db"

    # Append 5 entries
    for i in range(1, 6):
        append_audit_entry(
            agent_id=f"agent_{i:02d}",
            role="support_agent",
            tool="issue_refund",
            args={"order_id": f"ord_{100+i}", "amount": float(i * 10), "recipient_email": "billing@acme.com"},
            action_hash=f"hash_{i:04d}",
            verdict="ALLOW",
            reason=f"Legitimate action {i}",
            db_path=test_db,
        )

    # Verify clean log passes first
    assert verify_audit(test_db) == 0

    # Tamper with row seq=3 directly in SQLite (simulate attacker editing DB)
    conn = sqlite3.connect(str(test_db))
    cur = conn.cursor()
    cur.execute(
        "UPDATE audit_log SET reason = 'Tampered reason that was never signed' WHERE seq = 3"
    )
    conn.commit()
    conn.close()

    # CLI verification MUST FAIL
    code_tampered = verify_audit(test_db)
    assert code_tampered == 1

    # Python API verification MUST FAIL
    is_valid, msg, _, _ = verify_audit_chain(test_db)
    assert is_valid is False
    assert "Tampered entry detected at seq=3" in msg


def test_verify_audit_fails_on_prev_hash_tampering(tmp_path):
    test_db = tmp_path / "test_prev_tampered.db"

    for i in range(1, 4):
        append_audit_entry(
            agent_id=f"agent_{i}",
            role="support_agent",
            tool="run_sql",
            args={"query": "SELECT 1"},
            action_hash=f"h_{i}",
            verdict="ALLOW",
            reason="ok",
            db_path=test_db,
        )

    conn = sqlite3.connect(str(test_db))
    cur = conn.cursor()
    cur.execute("UPDATE audit_log SET prev_hash = 'tampered_previous_hash' WHERE seq = 2")
    conn.commit()
    conn.close()

    code = verify_audit(test_db)
    assert code == 1


def test_leash_anchor_command(tmp_path):
    test_db = tmp_path / "test_anchor_audit.db"
    test_anchor_file = tmp_path / "anchors.txt"

    append_audit_entry(
        agent_id="agent_01",
        role="support_agent",
        tool="run_sql",
        args={"query": "SELECT 1"},
        action_hash="hash_abc",
        verdict="ALLOW",
        reason="ok",
        db_path=test_db,
    )

    code = anchor_audit(test_db, test_anchor_file)
    assert code == 0
    assert test_anchor_file.exists()
    content = test_anchor_file.read_text(encoding="utf-8")
    assert "head_hash=" in content
    assert "seq=1" in content
