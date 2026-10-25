# CAROT LEASH — Studio Production & Multimodal Critique Summary
**Project**: CAROT LEASH (Problem Statement PS 2.1: AI Agent Safety and Control)  
**Team**: CAROT (Thejas Jagadeesh, Cyrus Pinto, Chrisel Lobo, Waqqas Hejazi)  
**Institution**: St Aloysius Deemed To Be University  
**Event**: Sahyadri DevHost 2026 / SOSC Synergia 26  
**Repository**: [https://github.com/CYRUS-pinto/LEASH](https://github.com/CYRUS-pinto/LEASH)  
**Live Interactive Terminal**: [https://leash-git-main-cyrus-projects-526b6596.vercel.app/](https://leash-git-main-cyrus-projects-526b6596.vercel.app/)  
**Live Cinema Studio**: [https://leash-git-main-cyrus-projects-526b6596.vercel.app/film](https://leash-git-main-cyrus-projects-526b6596.vercel.app/film)

---

## 1. Executive Summary & Core Thesis
Enterprise agentic AI is expanding exponentially—from less than 1% in 2024 to an estimated 33% by 2028 (Gartner). However, autonomy without enforcement creates an unbounded blast radius: in India, corporate data breaches average ₹25.5 crore (IBM 2026), while 63% of enterprises lack AI access controls. A single indirect prompt injection (OWASP LLM #1) in an incoming customer support ticket can turn an autonomous agent into an internal adversary.

**Foundational Governance Formula**:
$$\text{Autonomy} \times \text{Access} - \text{Enforcement} = \text{Unaudited Blast Radius}$$

> **"Logs are a rear-view mirror. LEASH is the brake."**

CAROT LEASH is a deterministic action-control gateway built on Python 3.13 and FastAPI that intercepts tool proposals in real-time, executing system-of-record invariant checks before any live API call moves money, modifies records, or exfiltrates data.

---

## 2. Technical Architecture & Defense-in-Depth

### The 8-Stage Ordered Decision Pipeline
Every proposed action (`POST /v1/propose`) passes through 8 strict policy stages:
- **[Stage 0] Quarantine Check**: Verifies agent trip state. Quarantined agents are blocked immediately with zero evaluation overhead.
- **[Stage 1] Role Scope**: Enforces default-deny role ACLs (e.g. `support_agent` vs `finance_admin`).
- **[Stage 2] Task Scope**: Restricts operations strictly to active workflow boundaries.
- **[Stage 3] System of Record (SoR) Invariant Check**: Queries live database ground truth (e.g. `refund.to == order.payer AND amount <= order.balance`).
- **[Stage 4] Provenance (Taint) Tracking**: Flags untrusted user input channels and external email bodies.
- **[Stage 5] Context-Aware DLP**: Scans arguments for sensitive tokens (credit cards, SSNs, secret keys).
- **[Stage 6] Caps & Human Quorum**: Enforces financial limits ($300 ceiling) and routes high-risk operations to 1-click human escalation.
- **[Stage 7] Cryptographic HMAC Receipt Minting**: Issues single-use signed tokens (`X-LEASH-Receipt`) required by downstream tool servers.

### Downstream Tool-Server Contract Guarantees
1. Direct tool invocation without valid receipt $\rightarrow$ `403 Forbidden` (`test_direct_call_without_receipt_rejected`).
2. Replayed receipt $\rightarrow$ `409 Conflict: Single-use nonce already consumed` (`test_replayed_receipt_rejected`).
3. Argument tampering $\rightarrow$ `401 Unauthorized: HMAC signature mismatch` (`test_modified_args_with_receipt_rejected`).
4. Stale receipt ($TTL > 30\text{s}$) $\rightarrow$ `410 Gone: Receipt expired` (`test_expired_receipt_rejected`).

### Cryptographic Audit Integrity
All decisions are appended to an immutable SHA-256 DAG ledger:
$$\text{Chain Hash}_N = \text{SHA-256}(\text{Chain Hash}_{N-1} \parallel \text{Payload}_N)$$
Any manual database alteration or hash tampering invalidates the chain check (`test_verify_audit_fails_after_one_row_edit` and `test_verify_audit_fails_on_prev_hash_tampering`).

---

## 3. Empirical Benchmark (LaunderBench-mini)
Evaluated across **48 synthetic attack traces** and **42 benign enterprise traces**:

| Defense Mechanism | Exploit Success Rate | Bypass Percentage | Benign False Blocks | P50 Latency |
|---|---|---|---|---|
| **Direct Tool Access** (No Gateway) | 48 / 48 | 100.0% | 0 / 42 | < 1 ms |
| **Regex / Deny-List Filters** | 33 / 48 | 68.8% | 0 / 42 | 1.8 ms |
| **Taint Tracking Alone** | 25 / 48 | 52.1% (100% of Hindi/Kannada translations) | 0 / 42 | 3.4 ms |
| **CAROT LEASH** (SoR Invariants) | **0 / 48** | **0.0% (100% BLOCKED)** | **0 / 42** (5 escalated to human) | **7.9 ms** |

---

## 4. Multimodal Visual Critique Loop Progression

### Iteration 1 vs. Iteration 2 Score Comparison
| Scene / Act | Timecode | Iteration 1 Score | Iteration 2 Score | Core Fixes Implemented |
|---|---|---|---|---|
| **Scene 1 (Hook)** | 00:00–00:03.5 | 88.0 / 100 | **96.0 / 100** | Card width expanded to 1420px; red perimeter aura and glowing highlight added. |
| **Scene 2 (Blast Radius)** | 00:03.5–00:11.5 | 92.0 / 100 | **97.0 / 100** | Numerals increased to 64px bold; 3D card drop-shadows on Anthropic parchment. |
| **Scene 3 (Thesis)** | 00:11.5–00:19.5 | 90.0 / 100 | **96.0 / 100** | Formula scaled to 42px; "LEASH is the brake" elevated to 78px with dual-layer neon glow. |
| **Scene 4 (8 Stages)** | 00:19.5–00:32.5 | 89.0 / 100 | **95.0 / 100** | Stage 3 (SoR Cyan), Stage 6 (Caps Amber), Stage 7 (HMAC Emerald) illuminated. |
| **Scene 5 (Demo)** | 00:32.5–00:55.0 | 91.0 / 100 | **96.0 / 100** | Golden Section split (61.8% / 38.2%); spring overshoot BLOCK badge pop; 1-click human review. |
| **Scene 6 (Climax)** | 00:55.0–01:16.0 | 93.0 / 100 | **98.0 / 100** | Bar heights doubled to 38px with gradient caps; 0/48 zero-bypass shield badge. |
| **Scene 7 (CTA)** | 01:16.0–01:29.0 | 92.0 / 100 | **96.0 / 100** | Dual CTA pills (GitHub + Vercel Terminal) with complete team and event credentials. |

**Mean Release Quality**: **96.3 / 100** (Launch Film) & **96.9 / 100** (Technical Walkthrough) — Target $\ge 95/100$ exceeded.

---

## 5. Master Video Deliverables

1. **CAROT LEASH Product Launch Film (89s)**:
   - File: `./dist/CAROT_LEASH_Launch_89s.mp4`
   - Resolution: **4K UHD (3840x2160)**
   - Framerate: **60.0 fps**
   - Video Codec: H.264 / AVC (High Profile, CRF 18, YUV420p)
   - Audio Codec: AAC (320 kbps, 96 kHz)
   - Narration: en-US-AndrewNeural locked to millisecond Fibonacci scene intervals
   - Music & Foley: Procedural acoustic piano + 55Hz sub-bass drone with -10dB sidechain speech ducking and mechanical latch drop at 18.0s and 37.0s.

2. **CAROT LEASH Extended Technical Walkthrough (210s)**:
   - File: `./dist/CAROT_LEASH_Walkthrough_210s.mp4`
   - Resolution: **4K UHD (3840x2160)**
   - Framerate: **60.0 fps**
   - Video Codec: H.264 / AVC (High Profile, CRF 18, YUV420p)
   - Audio Codec: AAC (320 kbps, 96 kHz)
   - Content: Complete 8-Act deep dive covering governance gap, rear-view mirror thesis, 8-stage pipeline, multilingual prompt evasion reproduction, SHA-256 DAG tamper-evidence, fail-closed YAML hot-reloading, 23 passing pytest security tests, and LaunderBench-mini metrics.

---
*Priced like software. Saves like insurance. Put autonomous AI agents on a LEASH.*
