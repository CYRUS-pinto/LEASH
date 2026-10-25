# LEASH — Threat Model & Security Boundaries

## 1. System Assumptions

1. **Untrusted Autonomous Agent**: The AI agent (whether running local weights or calling remote cloud APIs) is considered untrusted. It can be manipulated via direct or indirect prompt injection embedded in incoming customer messages, ticket bodies, emails, or third-party web content.
2. **Attacker Capabilities**: Attackers can supply arbitrary natural language text, translate malicious instructions into non-English languages (Hindi, Kannada), split attack tokens across multiple fields, and attempt to manipulate tool invocation arguments.
3. **Protected Infrastructure**: The database server, tool execution server, and LEASH gateway operate in a trusted execution domain. The gateway shares a symmetric HMAC key with the tool server.

---

## 2. In-Scope Threats

| Threat Actor | Threat Vector | LEASH Mitigation Mechanism | Verified Test |
| :--- | :--- | :--- | :--- |
| **External Attacker** | Indirect prompt injection embedded in support tickets instructing the agent to divert refunds to an external wallet. | **Stage 3 SoR Effect Check**: Validates proposed recipient against the immutable `original_payer_email` in SQLite. | `test_refund_effect_check_blocks_diverted_recipient` |
| **External Attacker** | SQL injection commands (`DROP TABLE`, `DELETE FROM`) laundered through support notes. | **Stage 3 AST Analysis**: Parses SQL with `sqlparse`; strictly prohibits DDL and DML mutation statements. | `test_sql_effect_check_blocks_destructive_commands` |
| **Compromised Agent** | Bypassing LEASH gateway to invoke the protected tool server directly on port 8001. | **Cryptographic Receipts**: Protected tool server unconditionally rejects calls lacking an unexpired HMAC-SHA256 receipt. | `test_direct_call_without_receipt_rejected` |
| **Compromised Agent** | Replaying an intercepted or previously used gateway receipt. | **Single-Use Nonces**: Tool server maintains an atomic in-memory set of consumed nonces. | `test_replayed_receipt_rejected` |
| **Compromised Agent** | Tampering with tool arguments after receiving a valid receipt (e.g. changing refund amount from $25 to $500). | **Action Hash Verification**: Tool server recomputes `SHA256(tool || args)` and rejects if it mismatches the receipt. | `test_modified_args_with_receipt_rejected` |
| **Compromised Agent** | Re-using an expired receipt (>60 seconds old). | **Timestamp Expiration**: Tool server verifies current timestamp against `expires_at`. | `test_expired_receipt_rejected` |
| **Compromised Agent** | Using an approved human authorization for Action A to execute malicious Action B. | **Action-Bound Approvals**: Approvals are cryptographically tied to the action hash; parameter mismatch triggers `403 Forbidden`. | `test_approval_for_action_a_cannot_execute_action_b` |
| **Malicious Insider** | Silently altering historical decision rows in the database. | **Hash-Chained Audit DAG**: Parent-child SHA-256 chain breaks if any field or previous hash is tampered with. | `test_verify_audit_fails_after_one_row_edit` |

---

## 3. Out-of-Scope Risks & Residual Limitations

1. **Pre-Invasion LLM Logic**: LEASH does not attempt to fix LLM attention heads or prevent the model from becoming confused. It intercepts the resulting tool call before execution occurs.
2. **Log Truncation**: A local SQLite hash chain detects modifications to existing entries, but cannot prevent an attacker with full root access from deleting the database file. LEASH provides `leash_cli.py anchor` to publish head hashes to external storage.
3. **Complex Cross-Entity Semantics**: If a business rule cannot be expressed as a database invariant or schema constraint, human escalation (`ESCALATE`) is required.
