"""HMAC-SHA256 Receipt Generation and Verification for LEASH."""

import hashlib
import hmac
import json
import time
import uuid
from typing import Any, Dict, Optional, Set, Tuple
from leash.config import GATEWAY_HMAC_SECRET


def canonical_json(obj: Any) -> str:
    """Produces deterministic, canonical JSON representation with sorted keys and no extra whitespace."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_action_hash(tool: str, args: Dict[str, Any]) -> str:
    """Computes SHA-256 of canonical JSON of tool + args."""
    canonical = canonical_json({"args": args, "tool": tool})
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def create_receipt(
    tool: str,
    args: Dict[str, Any],
    decision: str = "ALLOW",
    policy_version: str = "1.0.0",
    expiry_seconds: int = 60,
    secret: str = GATEWAY_HMAC_SECRET,
    nonce: Optional[str] = None,
) -> Dict[str, Any]:
    """Mints a single-use signed HMAC receipt bound to action_hash."""
    action_hash = compute_action_hash(tool, args)
    receipt_nonce = nonce or uuid.uuid4().hex
    expiry = int(time.time()) + expiry_seconds

    payload = {
        "action_hash": action_hash,
        "decision": decision,
        "expiry": expiry,
        "nonce": receipt_nonce,
        "policy_version": policy_version,
    }

    message = canonical_json(payload)
    sig = hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()

    receipt = dict(payload)
    receipt["signature"] = sig
    return receipt


def verify_receipt(
    receipt: Dict[str, Any],
    tool: str,
    args: Dict[str, Any],
    seen_nonces: Optional[Set[str]] = None,
    secret: str = GATEWAY_HMAC_SECRET,
    current_time: Optional[float] = None,
) -> Tuple[bool, str]:
    """Verifies a receipt: signature, expiry, replay (nonce), and action_hash matching."""
    if not isinstance(receipt, dict):
        return False, "Receipt must be an object"

    required_keys = {"action_hash", "decision", "policy_version", "expiry", "nonce", "signature"}
    if not required_keys.issubset(receipt.keys()):
        return False, f"Missing required receipt fields: {required_keys - set(receipt.keys())}"

    sig = receipt["signature"]
    payload = {
        "action_hash": receipt["action_hash"],
        "decision": receipt["decision"],
        "expiry": receipt["expiry"],
        "nonce": receipt["nonce"],
        "policy_version": receipt["policy_version"],
    }
    expected_msg = canonical_json(payload)
    expected_sig = hmac.new(secret.encode("utf-8"), expected_msg.encode("utf-8"), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(sig, expected_sig):
        return False, "Invalid receipt signature"

    now = time.time() if current_time is None else current_time
    if now > receipt["expiry"]:
        return False, f"Receipt expired (expiry: {receipt['expiry']}, now: {int(now)})"

    if seen_nonces is not None:
        if receipt["nonce"] in seen_nonces:
            return False, f"Receipt already used (replay detected for nonce: {receipt['nonce']})"

    expected_action_hash = compute_action_hash(tool, args)
    if not hmac.compare_digest(receipt["action_hash"], expected_action_hash):
        return False, "Action arguments do not match receipt action_hash"

    if receipt["decision"] != "ALLOW":
        return False, f"Receipt decision is {receipt['decision']}, must be ALLOW"

    return True, "Valid receipt"
