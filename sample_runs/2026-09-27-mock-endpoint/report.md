### unknown · test-model · 2026-09-27

**Egress: SEALED** — 164 connection attempts to 1 destination: `127.0.0.1:8765`
Monitor self-test PASS.

| Axis | Verdict | Number |
|---|---|---|
| Native tool calls | FAIL | 0/20 native; 0/20 JSON-mode |
| JSON-schema adherence | FAIL | 0% (0/50) — type_coercion: 50 |
| Streaming delta shape | PASS | 4/5 sub-assertions; usage absent on final chunk |
| Token-count accuracy | FAIL | 0/10 exact; tokens under-reported by up to 2 |

Reproduce: `dialproof verify 2026-09-27T163631-test-model/report.json`