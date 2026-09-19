# dialproof

**Proof of what your LLM endpoint actually dials.**

`dialproof` is an air-gap conformance harness for OpenAI-compatible LLM endpoints. Point it at any endpoint and it measures four capability axes the vendors document but nobody verifies — while proving the run opened no sockets outside an explicit allowlist.

The constraint is simple: **every number is reader-reproducible**. No credentials needed, no infrastructure required beyond the endpoint itself.

## v0.1 scope

- **Four capability axes** the vendors document but measurements are rare: native tool calls vs silent JSON-mode fallback, JSON-schema adherence, streaming delta shape, token-count accuracy.
- **Two egress monitoring layers**: L1 (always on) is a CPython audit hook — no root, no Docker, works everywhere. L2 (opt-in `--sealed`) runs in a container with no default route, producting irrefutable evidence.
- **Self-testing monitor**: `monitor_selftest` deliberately dials a disallowed host inside every run. A monitor you've never seen fail is not evidence.
- **JSON source of truth**, Markdown rendering for quotability, `verify` recomputes all verdicts from stored artifacts with no re-running.
- **Two targets**: a self-hosted OpenAI-compatible endpoint (vLLM, llama-server, Ollama), and LiteLLM-as-transport (measuring the library's import-time calls to raw.githubusercontent.com and its cost-map fetch).

Deferred and declared in the README: embeddings, logprobs, seed determinism, context-length honesty (the other four of the eight-axis roadmap).

## Install

```bash
pip install dialproof
```

## One runnable command

```bash
dialproof run \
    --endpoint http://vllm.internal:8000/v1 \
    --model qwen3-32b \
    --allow vllm.internal:8000 \
    --out runs/2026-09-19-vllm-qwen3/
```

The output directory contains `report.json` (the source of truth) and `report.md` (the quotable half).

## Commands

### `dialproof run` — measure an endpoint

```bash
dialproof run \
    --endpoint <base_url> \
    --model <model_name> \
    --allow <host1:port1> \
    --allow <host2:port2> \
    --out <output_dir> \
    [--transport raw-httpx|litellm]
```

- **`--endpoint`**: Base URL of the OpenAI-compatible endpoint (e.g., `http://localhost:8000/v1`).
- **`--model`**: Model name to test.
- **`--allow`**: Allowed hosts (multiple allowed). Format: `host:port` or just `host`.
- **`--out`**: Directory where reports will be saved.
- **`--transport`**: Which layer to use (`raw-httpx` for direct calls, `litellm` to probe the library itself).

Exit code: 0 on success (no egress violations), 1 if violations detected.

### `dialproof verify` — recompute verdicts without re-running

```bash
dialproof verify runs/2026-09-19-vllm-qwen3/report.json
```

Recomputes every axis verdict from stored artifacts with no model calls and no network. Useful for auditing or CI gates.

### `dialproof render` — quotable Markdown from a report

```bash
dialproof render runs/2026-09-19-vllm-qwen3/report.json --format md
```

Renders the JSON report to Markdown suitable for posts or documentation.

### `dialproof selftest` — prove the monitor works

```bash
dialproof selftest
```

Deliberately tries to dial a disallowed host and asserts it was caught. Every `run` includes this selftest; if it fails, the report is stamped `unverified` and `verify` refuses it.

## The four axes

| Axis | What it measures | Pass criterion |
|------|---|---|
| **Native tool calls** | Does the endpoint support function calling natively, or fall back to silent JSON mode? | `message.tool_calls` present + valid JSON arguments + `finish_reason == "tool_calls"` on ≥80% of calls. |
| **JSON-schema adherence** | Can the endpoint produce strict `response_format` JSON that validates against a schema? | Parses *and* validates on ≥80% of calls (n=50, temp=0). Classifies failures (enum drift, missing required, type coercion, extra keys). |
| **Streaming delta shape** | Are stream chunks well-formed SSE, with role appearing once, deltas that reassemble to the non-streamed completion, and usage on the final chunk when requested? | 5 sub-assertions (SSE wellformed, role once, delta byte-equality, monotonic tool-call index, usage on final). |
| **Token-count accuracy** | Does the endpoint's reported prompt token count match what a local tokenizer measures? | Exact match on all 10 fixed prompts. Reports signed delta distribution if not. |

Deferred to increment 2: embeddings, logprobs, seed determinism, context-length honesty.

## Sample output

**JSON report:**

```json
{
  "dialproof_version": "0.1.0",
  "run_id": "2026-09-19T093935-test-model",
  "endpoint": {
    "base_url": "http://127.0.0.1:8765/v1",
    "server": "test-endpoint",
    "model": "test-model"
  },
  "transport": "raw-httpx",
  "monitor": {
    "layer": "L1-audithook",
    "selftest": "PASS",
    "denied_host_dialed": "blocked.invalid"
  },
  "egress": {
    "verdict": "SEALED",
    "allowlist": ["127.0.0.1:8765"],
    "attempts": [{"host": "127.0.0.1", "port": 8765, "count": 164, "decision": "allow"}]
  },
  "axes": {
    "native_tool_calls": {"verdict": "FAIL", "n": 20, "native": 0, "json_fallback": 0, "fail": 20},
    "json_schema_adherence": {"verdict": "FAIL", "n": 50, "adherence": 0.0, "failures": {"type_coercion": 50}},
    "streaming_shape": {"verdict": "PASS", "sse_wellformed": true, "role_once": true, "stream_equals_nonstream": true, "usage_on_final": false},
    "token_accuracy": {"verdict": "FAIL", "n": 10, "exact_match": 0, "prompt_token_delta": {"min": -5, "median": -4, "max": -2}}
  },
  "cost": {"wall_clock_s": 0, "requests": 164, "usd": null, "note": "self-hosted; no per-token price applies"},
  "verdict": {"conformance": "1/4 axes pass", "egress": "SEALED"}
}
```

**Rendered to Markdown:**

```markdown
### test-endpoint · test-model · 2026-09-19

**Egress: SEALED** — 164 sockets, all to `127.0.0.1:8765`
Monitor self-test PASS.

| Axis | Verdict | Number |
|---|---|---|
| Native tool calls | FAIL | 0/20 native; 0/20 JSON-mode |
| JSON-schema adherence | FAIL | 0% (0/50) — type_coercion: 50 |
| Streaming delta shape | PASS | 4/5 sub-assertions; usage absent on final chunk |
| Token-count accuracy | FAIL | 0/10 exact; tokens under-reported by up to 5 |

Reproduce: `dialproof verify 2026-09-19T093935-test-model/report.json`
```

This sample run measured a test endpoint and found that streaming works correctly, but native tool calls fail (the endpoint doesn't return `message.tool_calls`), schema adherence fails due to type coercion, and token counts are under-reported.

## Egress monitoring — layered

**L1 (always on):** CPython audit hook on `socket.connect` and `socket.getaddrinfo`. Records host, port, resolved IP, and stack frame for every attempt; blocks anything off `--allow`. No root, no Docker, works everywhere. Weakness (stated in the report): subprocesses and C-level libraries escape it.

**L2 (opt-in `--sealed`):** Run inside a container with no default route and a logging DNS sinkhole. Nothing evades it; evidence is produced outside the audited process. This is the mode the launch post uses.

A violation produces **both**: the run exits non-zero *and* the report carries the full ledger with stack frames. A blocked call is the evidence, not an error to suppress.

## Not a gateway, router, or proxy

`dialproof` never sits in a production request path. It is run out-of-band and leaves a file behind. It does not wrap providers, does not normalize responses, and adds no runtime dependency to anything it measures.

## Development

```bash
# Install in editable mode with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Format and lint
black src tests
ruff check --fix src tests

# Type check
mypy src
```

## License

MIT
