"""Hash-chained Audit Log for LEASH."""

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from leash.config import AUDIT_DB_PATH

GENESIS_HASH = "GENESIS_0000000000000000000000000000000000000000000000000000000000000000"


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def get_audit_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    path = db_path or AUDIT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def init_audit_db(db_path: Optional[Path] = None) -> None:
    conn = get_audit_connection(db_path)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS audit_log (
        seq INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        agent_id TEXT NOT NULL,
        role TEXT NOT NULL,
        tool TEXT NOT NULL,
        args_json TEXT NOT NULL,
        action_hash TEXT NOT NULL,
        verdict TEXT NOT NULL,
        reason TEXT NOT NULL,
        prev_hash TEXT NOT NULL,
        entry_hash TEXT NOT NULL
    )
    """)
    conn.commit()
    conn.close()


def append_audit_entry(
    agent_id: str,
    role: str,
    tool: str,
    args: Dict[str, Any],
    action_hash: str,
    verdict: str,
    reason: str,
    db_path: Optional[Path] = None,
    timestamp: Optional[str] = None,
) -> Dict[str, Any]:
    """Appends an entry to the hash-chained audit log and returns the recorded row."""
    init_audit_db(db_path)
    conn = get_audit_connection(db_path)
    cur = conn.cursor()

    cur.execute("SELECT seq, entry_hash FROM audit_log ORDER BY seq DESC LIMIT 1")
    last_row = cur.fetchone()

    if last_row is None:
        next_seq = 1
        prev_hash = GENESIS_HASH
    else:
        next_seq = last_row["seq"] + 1
        prev_hash = last_row["entry_hash"]

    entry_timestamp = timestamp or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    args_json_str = canonical_json(args)

    data_to_hash = {
        "action_hash": action_hash,
        "agent_id": agent_id,
        "args_json": args_json_str,
        "reason": reason,
        "role": role,
        "seq": next_seq,
        "timestamp": entry_timestamp,
        "tool": tool,
        "verdict": verdict,
    }

    payload_canonical = canonical_json(data_to_hash)
    entry_hash = hashlib.sha256(f"{prev_hash}{payload_canonical}".encode("utf-8")).hexdigest()

    cur.execute(
        """
        INSERT INTO audit_log
        (seq, timestamp, agent_id, role, tool, args_json, action_hash, verdict, reason, prev_hash, entry_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            next_seq,
            entry_timestamp,
            agent_id,
            role,
            tool,
            args_json_str,
            action_hash,
            verdict,
            reason,
            prev_hash,
            entry_hash,
        ),
    )
    conn.commit()
    conn.close()

    return {
        "seq": next_seq,
        "timestamp": entry_timestamp,
        "agent_id": agent_id,
        "role": role,
        "tool": tool,
        "args": args,
        "action_hash": action_hash,
        "verdict": verdict,
        "reason": reason,
        "prev_hash": prev_hash,
        "entry_hash": entry_hash,
    }


def verify_audit_chain(db_path: Optional[Path] = None) -> Tuple[bool, str, Optional[str], int]:
    """
    Verifies integrity of the hash chain from genesis to head.
    Returns: (is_valid, message, head_hash, count)
    """
    path = db_path or AUDIT_DB_PATH
    if not path.exists():
        return True, "Audit log is empty (database does not exist yet)", None, 0

    conn = get_audit_connection(path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='audit_log'")
    if not cur.fetchone():
        conn.close()
        return True, "Audit table does not exist yet", None, 0

    cur.execute("SELECT * FROM audit_log ORDER BY seq ASC")
    rows = cur.fetchall()
    conn.close()

    if not rows:
        return True, "Audit log is empty", None, 0

    expected_prev_hash = GENESIS_HASH
    for i, row in enumerate(rows, start=1):
        if row["seq"] != i:
            return False, f"Sequence gap or out of order at index {i}, found seq={row['seq']}", None, len(rows)

        if row["prev_hash"] != expected_prev_hash:
            return (
                False,
                f"Broken hash chain at seq={row['seq']}: prev_hash {row['prev_hash']} != expected {expected_prev_hash}",
                None,
                len(rows),
            )

        data_to_hash = {
            "action_hash": row["action_hash"],
            "agent_id": row["agent_id"],
            "args_json": row["args_json"],
            "reason": row["reason"],
            "role": row["role"],
            "seq": row["seq"],
            "timestamp": row["timestamp"],
            "tool": row["tool"],
            "verdict": row["verdict"],
        }
        computed_hash = hashlib.sha256(
            f"{expected_prev_hash}{canonical_json(data_to_hash)}".encode("utf-8")
        ).hexdigest()

        if computed_hash != row["entry_hash"]:
            return (
                False,
                f"Tampered entry detected at seq={row['seq']}: stored {row['entry_hash']} != computed {computed_hash}",
                None,
                len(rows),
            )

        expected_prev_hash = row["entry_hash"]

    return True, f"Audit chain verified successfully ({len(rows)} entries)", expected_prev_hash, len(rows)
