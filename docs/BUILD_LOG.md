# LEASH — Build Log

## WHAT TO REPORT BACK WHEN DONE

### 1. Exact `results.json` Summary Table

#### Overall Defence Comparison (n=48 attacks, n=42 benign)
| Defence | Attack Success Rate | Attacks Succeeded / Total | False Block Rate (Benign) | Escalation Rate |
| :--- | :---: | :---: | :---: | :---: |
| **`none`** (Direct) | **100.0%** | 48/48 | 0.0% (0/42) | 0.0% (0/42) |
| **`regex`** (Deny-list) | **68.8%** | 33/48 | 2.4% (1/42) | 0.0% (0/42) |
| **`taint`** (Substring match) | **52.1%** | 25/48 | 0.0% (0/42) | 0.0% (0/42) |
| **`leash`** (SoR Effect Checks) | **0.0%** | 0/48 | 0.0% (0/42) | 11.9% (5/42) |

#### Attack Success Rate by Laundering Variant
| Laundering Variant | `none` (No Gateway) | `regex` (Deny-list) | `taint` (Substring) | `leash` (SoR Checks) |
| :--- | :---: | :---: | :---: | :---: |
| **verbatim** | 100.0% | 33.3% | 8.3% | **0.0%** |
| **paraphrased** | 100.0% | 83.3% | 100.0% | **0.0%** |
| **translated** (Hindi & Kannada) | 100.0% | 83.3% | 100.0% | **0.0%** |
| **split_field** | 100.0% | 75.0% | 0.0% | **0.0%** |

### 2. Decision Latency & Hardware
- **Decision Latency (LEASH Gateway only, excluding agent generation)**:
  - **p50**: `7.853 ms`
  - **p95**: `10.200 ms`
  - **Min / Max**: `5.435 ms` / `13.550 ms`
  - **Sample Count**: 90 requests
- **Hardware Platform**: Windows 11 (AMD64 Family 25 Model 80 Stepping 0, AuthenticAMD) | Python 3.13.15

### 3. Acceptance Criteria Status
- **Failed Criteria**: **None (0 failed)**. All 8 Acceptance Criteria PASSED.
  - Details:
    1. AC1 (make demo starts gateway + tool server + dashboard): PASS
    2. AC2 (bypass resistance on direct call, replay, modified args, expired): PASS (0.0% bypass success)
    3. AC3 (approval for refund A cannot execute refund B): PASS
    4. AC4 (fail closed on gateway kill or policy corruption): PASS
    5. AC5 (verify-audit clean pass and single-row tampering detection): PASS
    6. AC6 (make eval regenerates results.json deterministically): PASS
    7. AC7 (README contains no numbers not in results.json): PASS
    8. AC8 (KNOWN_LIMITATIONS.md documents synthetic traces, small counts, regex/PII gaps, truncation, SQLite): PASS

### 4. Case Counts & Frozen Commit Hash
- **Attack Cases**: 48 cases (12 base scenarios × 4 laundering variants: verbatim, paraphrased, translated [Hindi & Kannada], split-field)
- **Benign Cases**: 42 cases (including 7 false-positive bait cases and 5 large-refund escalations)
- **Frozen Cases Git Commit**: `970a194feef781bc42f7497f519bd6c225b2a2e6`

### 5. Repository URL and Demo Command
- **Repository URL**: `https://github.com/CYRUS-pinto/LEASH.git`
- **Command to Launch Demo**:
  ```bash
  python run_demo.py
  # or
  make demo
  ```
  Opens Dashboard & Gateway on `http://127.0.0.1:8000/` and Protected Tool Server on `http://127.0.0.1:8001/`.

---

## ACCEPTANCE CRITERIA STATUS
- [x] **AC1**: `make demo` starts gateway + tool server + dashboard; one command, no manual DB setup.
- [x] **AC2**: Direct tool-server call without receipt → rejected. Replayed receipt → rejected. Modified args → rejected. Expired → rejected.
- [x] **AC3**: Approval for refund A cannot execute refund B.
- [x] **AC4**: Killing the gateway or corrupting the policy file never results in an executed protected action.
- [x] **AC5**: `verify-audit` passes on a clean log and fails after a one-row edit.
- [x] **AC6**: `make eval` regenerates `results.json` from scratch deterministically (seed fixed).
- [x] **AC7**: README contains no number that is not in `results.json`.
- [x] **AC8**: `KNOWN_LIMITATIONS.md` lists at least: synthetic traces, small case counts, regex/PII gaps, hash-chain truncation, single-node SQLite.

---

## PHASE EXECUTION LOG

### Phase P0 (0:00–0:15): Repo Skeleton, Database Seeding, Make Targets
- Status: COMPLETED (PASS)
- Deliverables:
  - `.gitignore`, `.env.example`
  - SQLite database seeding script (`leash/db.py`) with 20 customers, 24 orders, 30 contacts, 20 tickets
  - `Makefile` and `make.bat` providing `demo`, `eval`, `test`, `seed`, `verify-audit`, `anchor` targets
- Verification: Database initialized and seeded successfully via `.\make.bat seed` / `python -m leash.db`.

### Phase P1 (0:15–1:15): Protected Tool Server, Core Gateway Pipeline, Audit Chain
- Status: COMPLETED (PASS)
- Deliverables:
  - `tools_server/server.py`: Enforces receipt HMAC, single-use nonce replay checks, expiry (60s), protected actions for `issue_refund`, `send_email`, `run_sql`.
  - `leash/receipt.py`: Canonical JSON sorting, SHA-256 action_hash computation, HMAC-SHA256 signing.
  - `leash/audit.py`: Hash-chained audit logging (`prev_hash`, `entry_hash = SHA256(prev_hash || canonical_json(entry))`).
  - `gateway/pipeline.py`: Stages 0–3, 6, 7 deterministic pipeline with circuit breakers and fail-closed error handling.
- Verification: 22 tests passing in `tests/test_bypass.py`, `tests/test_fail_closed.py`, `tests/test_pipeline.py`.

### Phase P2 (1:15–1:45): Taint & DLP, Action-Bound Approvals, Standalone Audit Verifier & Anchor
- Status: COMPLETED (PASS)
- Deliverables:
  - Stage 4 taint analysis and Stage 5 DLP PII/secret redaction (`gateway/policy.py`).
  - Action-bound approvals (`gateway/server.py`): bound to `action_hash`, single-use, 5m expiry.
  - Standalone `leash_cli.py` (`verify-audit`, `anchor`) without gateway imports.
- Verification: `tests/test_approval.py` passed (AC3), `tests/test_audit.py` passed (AC5).

### Phase P3 (1:45–2:30): LaunderBench-mini Attack & Benign Cases, Evaluation Harness
- Status: COMPLETED (PASS)
- Deliverables:
  - Frozen cases in `eval/cases/attacks.json` (48 cases across 12 scenarios × 4 laundering variants: verbatim, paraphrased, translated [Hindi & Kannada], split-field).
  - Frozen cases in `eval/cases/benign.json` (42 cases including 7 false-positive bait cases and 5 large-refund escalation cases).
  - Frozen commit hash: `970a194feef781bc42f7497f519bd6c225b2a2e6`.
  - `eval/harness.py`: Evaluates 4 defence configurations (`none`, `regex`, `taint`, `leash`), generates `eval/results.json`, `eval/RESULTS.md`, and `eval/results_chart.png`.
- Verification: `make eval` runs cleanly and deterministically. Results:
  - `none`: 100.0% attack success (48/48)
  - `regex`: 68.8% attack success (33/48), 2.4% false block (1/42)
  - `taint`: 52.1% attack success (25/48), 0.0% false block (0/42) — misses 100% of paraphrased and translated attacks!
  - `leash`: 0.0% attack success (0/48), 0.0% false block (0/42), 11.9% escalation rate (5/42)
  - Bypass attempts: 5/5 blocked (0.0% bypass success rate).
  - Gateway decision latency: p50 = 7.85 ms, p95 = 10.20 ms.

### Phase P4 (2:30–2:50): Web Dashboard (Live Feed, Approvals, Audit Badge, Run Attack)
- Status: COMPLETED (PASS)
- Deliverables:
  - `dashboard/index.html`, `dashboard/style.css`, `dashboard/app.js`: Dark-mode single-page dashboard with glassmorphism, live decision feed, action-bound approvals, verified audit badge, and interactive attack lab.
  - `run_demo.py`: Single command that automatically seeds DB, starts protected tool server (8001), gateway & dashboard (8000), and handles clean shutdown.
- Verification: Tested with `python run_demo.py --test` and `tests/test_demo.py` (AC1).

### Phase P5: Scripted/Live Evaluation Verification
- Status: COMPLETED (PASS)
- Deliverables:
  - `eval/live_agent.py`: Demonstrates 10 injected tickets processed through LEASH. 10/10 blocked. Circuit breaker quarantine activated after 3 violations.

### Phase P6 (2:50–3:00): Documentation, Limitations, Secret Scan, Final Verification
- Status: COMPLETED (PASS)
- Deliverables:
  - `README.md` containing architecture diagram, 2-command run guide, exact results table matching `eval/results.json`, and acceptance criteria status.
  - `KNOWN_LIMITATIONS.md` listing synthetic traces, case counts, regex/PII gaps, hash-chain truncation, and single-node SQLite.
  - Secret scan across git history verified 0 secrets or API keys.
  - Final `make test` (23/23 tests pass) and `make eval` (deterministic evaluation complete).
