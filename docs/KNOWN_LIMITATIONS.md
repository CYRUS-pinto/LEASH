# Known Limitations of LEASH Prototype

This document honestly outlines the current limitations, architectural trade-offs, and design boundaries of the LEASH prototype in accordance with the project's non-negotiable honesty rules.

---

### 1. Synthetic Traces vs. Live Model Outputs
- **Limitation**: The primary LaunderBench-mini evaluation uses 48 frozen, hand-authored attack traces and 42 benign cases representing actions an injected agent would propose.
- **Context**: While these traces realistically model verbatim injection, paraphrasing, translation (Hindi/Kannada), and field splitting, they are deterministic synthetic traces, not non-deterministic outputs from an active LLM generation loop. A separate small-scale live evaluation (n=10) is provided in `eval/live_agent.py`.
- **Roadmap**: Expanding the harness to automated red-teaming against live frontier models (e.g., Claude, GPT-4o, Gemini) in an open-ended multi-turn simulation loop.

---

### 2. Case Counts (LaunderBench-mini)
- **Limitation**: LaunderBench-mini contains 48 attack cases across 12 base scenarios and 42 benign cases.
- **Context**: While this sample size clearly measures and proves the delta between string-level taint checking (52.1% attack success) and system-of-record effect checking (0.0% attack success), production-grade certification requires thousands of edge-case scenarios covering broader business verticals.

---

### 3. Regex and PII / DLP Filter Gaps
- **Limitation**: Deny-list regexes and pattern-based DLP have known blind spots.
- **Context**: 
  - Regex keyword blocking failed against 83.3% of paraphrased and translated attacks in LaunderBench-mini, and induced false blocks on benign customer queries containing words like "delete" or "drop".
  - Outbound DLP currently targets 13–19 digit credit card numbers (with Luhn verification), standard US SSNs (`XXX-XX-XXXX`), and common API keys (`sk-...`, `ghp-...`). Non-standard national IDs, novel API key prefixes, or fragmented secrets spread across multiple network calls may bypass single-turn regex DLP.

---

### 4. Hash-Chain Truncation & External Anchoring
- **Limitation**: A local hash-chained SQLite table (`prev_hash`, `entry_hash = SHA256(prev_hash || canonical_json(entry))`) guarantees detection of any in-place row edits, sequence reordering, or inserted rows, but **cannot mathematically prevent silent tail truncation** if an attacker deletes the most recent $N$ rows and recalculates nothing.
- **Mitigation & Fix**: Truncation resistance requires anchoring the head hash externally. LEASH provides the `leash anchor` CLI command (`python leash_cli.py anchor`) which writes the timestamped head hash to `anchors.txt` (to be committed into version control or published to an immutable log).

---

### 5. Single-Node SQLite Architecture
- **Limitation**: The prototype relies on single-node SQLite databases for both the business System of Record (`business_systems.db`) and the audit log (`audit_log.db`).
- **Context**:
  - SQLite provides zero-setup, self-contained local demonstration without requiring external infrastructure.
  - However, SQLite has file-level locking constraints under high concurrent write loads and lacks built-in multi-region active replication or high-availability failover. Production deployment requires distributed databases (such as PostgreSQL with Row-Level Security) and distributed consensus ledgers.

---

### 6. Synchronous Effect Checks Latency
- **Limitation**: Each proposed tool call undergoes synchronous SQLite query checks (order lookup, contact verification, SQL AST parsing with `sqlparse`).
- **Context**: While our measured p50 decision latency is 7.85 ms and p95 is 10.20 ms on local hardware, complex multi-table joins or remote API-backed effect checks across distributed microservices will introduce network latency that must be mitigated via read replicas or caching with strict TTLs.
