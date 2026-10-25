"""Configuration settings for LEASH."""

import os
import secrets
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
if os.getenv("VERCEL"):
    DATA_DIR = Path("/tmp/leash_data")
else:
    DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

GATEWAY_HOST = os.getenv("GATEWAY_HOST", "127.0.0.1")
GATEWAY_PORT = int(os.getenv("GATEWAY_PORT", "8000"))
TOOLS_HOST = os.getenv("TOOLS_HOST", "127.0.0.1")
TOOLS_PORT = int(os.getenv("TOOLS_PORT", "8001"))


def _get_or_create_hmac_secret() -> str:
    env_secret = os.getenv("GATEWAY_HMAC_SECRET")
    if env_secret and env_secret.strip():
        return env_secret.strip()
    secret_file = DATA_DIR / ".hmac_secret"
    if secret_file.exists():
        val = secret_file.read_text(encoding="utf-8").strip()
        if val:
            return val
    generated = secrets.token_hex(32)
    secret_file.write_text(generated, encoding="utf-8")
    return generated


GATEWAY_HMAC_SECRET = _get_or_create_hmac_secret()

BUSINESS_DB_PATH = Path(os.getenv("BUSINESS_DB_PATH", str(DATA_DIR / "business_systems.db")))
AUDIT_DB_PATH = Path(os.getenv("AUDIT_DB_PATH", str(DATA_DIR / "audit_log.db")))
ANCHORS_FILE_PATH = BASE_DIR / "anchors.txt"
POLICY_FILE_PATH = BASE_DIR / "gateway" / "policy.json"
