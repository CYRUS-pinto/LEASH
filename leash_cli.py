#!/usr/bin/env python3
"""
LEASH Standalone CLI.
Independent tool with NO gateway or framework dependencies.
Provides:
  - verify-audit: Recomputes and verifies the hash chain of audit_log.db
  - anchor: Writes the current head hash to anchors.txt with timestamp
"""

import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path

GENESIS_HASH = "GENESIS_0000000000000000000000000000000000000000000000000000000000000000"


def canonical_json(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def get_default_paths():
    base_dir = Path(__file__).resolve().parent
    audit_db = base_dir / "data" / "audit_log.db"
    anchors_file = base_dir / "anchors.txt"
    return audit_db, anchors_file


def verify_audit(db_path=None):
    if db_path is None:
        db_path, _ = get_default_paths()
    else:
        db_path = Path(db_path)

    if not db_path.exists():
        print(f"[OK] Audit database '{db_path}' does not exist yet (clean state).")
        return 0

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='audit_log'")
    if not cur.fetchone():
        print("[OK] Audit table not initialized yet (clean state).")
        conn.close()
        return 0

    cur.execute("SELECT * FROM audit_log ORDER BY seq ASC")
    rows = cur.fetchall()
    conn.close()

    if not rows:
        print("[OK] Audit log is empty (0 entries).")
        return 0

    expected_prev = GENESIS_HASH
    for i, row in enumerate(rows, start=1):
        if row["seq"] != i:
            print(f"[FAIL] Sequence discontinuity at row index {i}: expected seq={i}, got seq={row['seq']}")
            return 1

        if row["prev_hash"] != expected_prev:
            print(f"[FAIL] Hash chain broken at seq={row['seq']}:")
            print(f"       Expected prev_hash: {expected_prev}")
            print(f"       Found prev_hash:    {row['prev_hash']}")
            return 1

        entry_data = {
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
            f"{expected_prev}{canonical_json(entry_data)}".encode("utf-8")
        ).hexdigest()

        if computed_hash != row["entry_hash"]:
            print(f"[FAIL] Entry content tampered at seq={row['seq']}!")
            print(f"       Stored entry_hash:   {row['entry_hash']}")
            print(f"       Recomputed hash:     {computed_hash}")
            return 1

        expected_prev = row["entry_hash"]

    print(f"[SUCCESS] Audit chain verified successfully! Total verified entries: {len(rows)}")
    print(f"          Head hash: {expected_prev}")
    return 0


def anchor_audit(db_path=None, anchor_path=None):
    default_db, default_anchor = get_default_paths()
    db_path = Path(db_path) if db_path else default_db
    anchor_path = Path(anchor_path) if anchor_path else default_anchor

    if not db_path.exists():
        print(f"[WARN] Database '{db_path}' does not exist. Nothing to anchor.")
        return 1

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT seq, entry_hash, timestamp FROM audit_log ORDER BY seq DESC LIMIT 1")
    row = cur.fetchone()
    conn.close()

    if not row:
        print("[WARN] Audit log is empty. Nothing to anchor.")
        return 1

    seq = row["seq"]
    head_hash = row["entry_hash"]
    ts = row["timestamp"]

    line = f"{ts} | seq={seq} | head_hash={head_hash}\n"
    with open(anchor_path, "a", encoding="utf-8") as f:
        f.write(line)

    print(f"[ANCHOR RECORDED] Anchored head at seq={seq} to {anchor_path.name}:")
    print(f"                  {head_hash}")
    return 0


def main():
    if len(sys.argv) < 2:
        print("Usage: python leash_cli.py [verify-audit | anchor] [db_path] [anchor_path]")
        sys.exit(1)

    cmd = sys.argv[1].lower().replace("_", "-")
    db_path = sys.argv[2] if len(sys.argv) > 2 else None

    if cmd == "verify-audit":
        sys.exit(verify_audit(db_path))
    elif cmd == "anchor":
        anchor_path = sys.argv[3] if len(sys.argv) > 3 else None
        sys.exit(anchor_audit(db_path, anchor_path))
    else:
        print(f"Unknown command: {cmd}")
        print("Available commands: verify-audit, anchor")
        sys.exit(1)


if __name__ == "__main__":
    main()
