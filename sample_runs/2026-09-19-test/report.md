### unknown · test-model · 2026-09-19

**Egress: SEALED** — 1 socket
, all to `127.0.0.1:8765`
Monitor self-test PASS.

| Axis | Verdict | Number |
|---|---|---|
| Native tool calls | FAIL | 0/20 native; 0/20 JSON-mode |
| JSON-schema adherence | FAIL | 0% (0/50) — type_coercion: 50 |
| Streaming delta shape | PASS | 4/5 sub-assertions; usage absent on final chunk |
| Token-count accuracy | FAIL | 0/10 exact; tokens under-reported by up to 2 |

Reproduce: `dialproof verify 2026-09-19T093935-test-model/report.json`