### unknown · test-model · 2026-09-19

**Egress: SEALED** — 1 socket
, all to `127.0.0.1:60913`
Monitor self-test PASS.

| Axis | Verdict | Number |
|---|---|---|
| Native tool calls | FAIL | 0/20 native; 0/20 JSON-mode |
| JSON-schema adherence | FAIL | 0% (0/50) |
| Streaming delta shape | FAIL | 3/5 sub-assertions; usage absent on final chunk |
| Token-count accuracy | FAIL | 0/10 exact |

Reproduce: `dialproof verify 2026-09-19T093903-test-model/report.json`