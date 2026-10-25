#!/usr/bin/env python3
"""
LEASH Demo Runner: Starts Gateway, Protected Tool Server, and Dashboard.
One command, zero manual database setup.
"""

import argparse
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from leash.config import BASE_DIR, GATEWAY_PORT, TOOLS_PORT
from leash.db import init_db


def wait_for_service(url: str, timeout: float = 10.0) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as res:
                if res.status == 200:
                    return True
        except Exception:
            time.sleep(0.3)
    return False


def main():
    parser = argparse.ArgumentParser(description="Run LEASH Gateway Demo")
    parser.add_argument("--test", action="store_true", help="Smoke test mode: starts servers, verifies health, exits")
    args = parser.parse_args()

    print("[1/3] Initializing and seeding System of Record SQLite database...")
    init_db(seed=True)

    python_bin = sys.executable

    print(f"[2/3] Starting Protected Tool Server on port {TOOLS_PORT}...")
    tool_proc = subprocess.Popen(
        [python_bin, "-m", "uvicorn", "tools_server.server:app", "--host", "127.0.0.1", "--port", str(TOOLS_PORT), "--log-level", "warning"],
        cwd=str(BASE_DIR),
    )

    print(f"[3/3] Starting LEASH Gateway & Dashboard on port {GATEWAY_PORT}...")
    gw_proc = subprocess.Popen(
        [python_bin, "-m", "uvicorn", "gateway.server:app", "--host", "127.0.0.1", "--port", str(GATEWAY_PORT), "--log-level", "warning"],
        cwd=str(BASE_DIR),
    )

    try:
        tool_health_url = f"http://127.0.0.1:{TOOLS_PORT}/health"
        gw_health_url = f"http://127.0.0.1:{GATEWAY_PORT}/health"
        dashboard_url = f"http://127.0.0.1:{GATEWAY_PORT}/"

        print("Waiting for services to become responsive...")
        if not wait_for_service(tool_health_url, timeout=12.0):
            print("ERROR: Tool server failed to start within timeout.")
            sys.exit(1)

        if not wait_for_service(gw_health_url, timeout=12.0):
            print("ERROR: Gateway server failed to start within timeout.")
            sys.exit(1)

        print("\n" + "=" * 64)
        print(" LEASH Action-Control Gateway is LIVE")
        print("=" * 64)
        print(f"  • Dashboard & Gateway:   {dashboard_url}")
        print(f"  • Protected Tool Server: {tool_health_url}")
        print("=" * 64)
        print("Press Ctrl+C to terminate both servers.\n")

        if args.test:
            print("[SMOKE TEST] Both services are healthy and responsive. Exiting cleanly.")
            return

        # Keep alive until Ctrl+C
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nShutting down LEASH demo servers...")
    finally:
        tool_proc.terminate()
        gw_proc.terminate()
        try:
            tool_proc.wait(timeout=3)
            gw_proc.wait(timeout=3)
        except Exception:
            tool_proc.kill()
            gw_proc.kill()
        print("Demo servers stopped.")


if __name__ == "__main__":
    main()
