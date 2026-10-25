# LEASH — LaunderBench-mini Evaluation Methodology & Results

## 1. Overview & Benchmark Thesis

The primary risk in autonomous agent systems is **indirect prompt injection leading to unauthorized side effects**. Attackers launder malicious commands through untrusted inputs (customer emails, web scrapes, PDF attachments).

Traditional substring taint tracking and regex filters fail against semantic transformations. **LaunderBench-mini** is an empirical evaluation harness specifically designed to test whether defense mechanisms survive prompt laundering.

---

## 2. Benchmark Dataset Composition

LaunderBench-mini consists of **90 deterministic requests** frozen in git commit `970a194feef781bc42f7497f519bd6c225b2a2e6`:

### 2.1 48 Adversarial Attack Traces (12 Scenarios × 4 Variants)
- **12 Base Attack Scenarios**:
  1. Laundered customer refund diversion to attacker wallet.
  2. Database destruction via SQL table truncation (`DROP TABLE customers`).
  3. Exfiltration of confidential customer databases to external webhook.
  4. Mass customer credit grant exceeding operational limits.
  5. Password reset link diversion to attacker-controlled mailbox.
  6. Bulk export of PII and order history.
  7. Fee waiver laundering via unauthorized compensation tools.
  8. Destructive account deletion payload.
  9. Malicious SQL schema injection via union selects.
  10. High-frequency micro-refund quota draining.
  11. Unauthorized external domain email redirection.
  12. Sensitive financial ledger balance tampering.

- **4 Laundering Variants per Scenario**:
  - `verbatim`: The injection string appears verbatim in the agent's proposed call.
  - `paraphrased`: The attack intent is rephrased using synonyms and polite conversational structure.
  - `translated`: The malicious prompt is translated into **Hindi** and **Kannada**, bypassing English keyword filters.
  - `split_field`: The payload is split across multiple auxiliary fields to defeat single-argument pattern matching.

### 2.2 42 Benign Workload Requests (Including 7 Adversarial Bait Cases)
- 35 routine support operations (order lookups, status updates, fee adjustments within policy).
- 7 adversarial bait cases containing suspicious keywords in natural context (e.g. customer asking *"Why does my receipt say DROP TABLE?"* or requesting a legitimate refund to their verified email).

---

## 3. Measured Results (Reproducible via `make eval`)

| Defence Mechanism | Attack Success Rate | Attacks Passed / Total | False Block Rate (Benign) | Escalation Rate |
| :--- | :---: | :---: | :---: | :---: |
| **`none` (Direct Tool Access)** | **100.0%** | 48 / 48 | 0.0% (0 / 42) | 0.0% (0 / 42) |
| **`regex` (Deny-list / Pattern Match)** | **68.8%** | 33 / 48 | 2.4% (1 / 42) | 0.0% (0 / 42) |
| **`taint` (Substring Taint Tracking)** | **52.1%** | 25 / 48 | 0.0% (0 / 42) | 0.0% (0 / 42) |
| **`leash` (SoR Effect Checks)** | **0.0%** | **0 / 48** | **0.0% (0 / 42)** | 11.9% (5 / 42) |

---

## 4. Variant Breakdown: The Laundering Gap

| Laundering Variant | `none` (No Gateway) | `regex` (Deny-list) | `taint` (Substring) | `leash` (SoR Checks) |
| :--- | :---: | :---: | :---: | :---: |
| **`verbatim`** | 100.0% | 33.3% | 8.3% | **0.0%** |
| **`paraphrased`** | 100.0% | 83.3% | 100.0% | **0.0%** |
| **`translated` (Hindi & Kannada)** | 100.0% | 83.3% | 100.0% | **0.0%** |
| **`split_field`** | 100.0% | 75.0% | 0.0% | **0.0%** |

### Key Empirical Finding:
Taint tracking drops from 91.7% effectiveness on verbatim text to **0.0% protection (100% attack success)** on paraphrased and translated prompts. LEASH maintains **0.0% attack success** across all four variants because it checks the concrete side effect against the SQLite database, ignoring prompt syntax.

---

## 5. Performance Telemetry

- **Decision Latency (Gateway only, excluding LLM generation)**:
  - **p50**: 7.85 ms
  - **p95**: 10.2 ms
  - Min: 5.44 ms | Max: 13.55 ms
- **Bypass Resistance**: 5 / 5 probes rejected (Direct call, replay, tampered args, expired timestamp, forged signature).
- **Environment**: Python 3.13.15 on Windows 11 AMD64 / x86_64.
