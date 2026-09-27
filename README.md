# dialproof

**Proof of what your LLM endpoint actually dials.**

`dialproof` is an air-gap conformance harness for OpenAI-compatible LLM endpoints. Point it at any endpoint and it measures four capability axes the vendors document but nobody verifies — while recording every socket the run attempted, and flagging any that fell outside an explicit allowlist.

The constraint is simple: **every number is reader-reproducible**. No credentials needed, no infrastructure required beyond the endpoint itself.

> **Status: v0.1.** This README describes what the shipped CLI does today, and marks
> everything that is *planned* as planned. Where a feature is named but not built, it says so
> in the same sentence. If you find a claim here that the code does not back, that is a bug —
> please open an issue.

## What v0.1 does today

- **Four capability axes** the vendors document but measurements are rare: native tool calls vs silent JSON-mode fallback, JSON-schema adherence, streaming delta shape, token-count accuracy.
- **L1 egress recording, always on**: a CPython audit hook on `socket.connect` and `socket.getaddrinfo`. No root, no Docker, works everywhere.
- **A monitor that self-tests inside every run**: `dialproof` deliberately dials a disallowed host before each run and asserts the monitor recorded the denial. If it did not, the run is stamped `selftest: FAIL` and `dialproof verify` refuses the report.
- **JSON is the source of truth**, Markdown is rendered from it. `verify` re-reads a stored report and checks its integrity without re-running anything.
- **One target**: a self-hosted OpenAI-compatible endpoint (vLLM, llama-server, Ollama) over raw `httpx`.

## What is planned and not yet built

These are on the roadmap. None of them exist in v0.1, and the CLI will not pretend otherwise.

- **L2 sealed mode (`--sealed`)** — running the probe inside a container with no default route and a logging DNS sinkhole, so evidence is produced *outside* the audited process. Not implemented; there is no `--sealed` flag.
- **Blocking, as opposed to recording.** The L1 audit hook **records** every attempt and labels it `allow`/`deny`. It does **not** intercept or prevent the connection. A run that attempted a denied connection exits non-zero *afterwards*, with the full ledger in the report. If you need the connection actually prevented, you need L2 or a network policy outside the process.
- **LiteLLM-as-transport (`--transport litellm`)** — probing the library's own import-time egress rather than a raw HTTP client. Not implemented. `--transport` currently accepts only `raw-httpx`, and deliberately **rejects** `litellm`, so that no report can carry a transport label for something that never ran.
- **Recomputing axis verdicts from stored artifacts.** `verify` today re-reads the stored report and checks its integrity (selftest status, presence of required fields). It does not yet re-derive the axis verdicts from raw per-call artifacts, because v0.1 does not store the raw per-call artifacts. `artifacts_sha256` is written as an empty string for the same reason.
- **The other four axes**: embeddings, logprobs, seed determinism, context-length honesty.

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
    --out runs/2026-09-27-vllm-qwen3/
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
    [--transport raw-httpx]
```

- **`--endpoint`**: Base URL of the OpenAI-compatible endpoint (e.g., `http://localhost:8000/v1`).
- **`--model`**: Model name to test.
- **`--allow`**: Allowed hosts (multiple allowed). Format: `host:port` or just `host`. The endpoint's own host is added automatically.
- **`--out`**: Directory where reports will be saved.
- **`--transport`**: `raw-httpx` only in v0.1. See "planned" above.

Exit code: 0 if no attempt fell outside the allowlist, 1 if one did. The connection is **recorded, not blocked** — the non-zero exit and the ledger are the evidence, after the fact.

### `dialproof verify` — check a stored report without re-running

```bash
dialproof verify runs/2026-09-27-vllm-qwen3/report.json
```

Re-reads the report, prints its identity, transport, selftest status and egress verdict, and **exits non-zero if the monitor selftest did not pass** — so a report from an unverified monitor cannot silently be quoted. No model calls, no network. It does not yet recompute the axis verdicts; see "planned" above.

### `dialproof render` — quotable Markdown from a report

```bash
dialproof render runs/2026-09-27-vllm-qwen3/report.json --format md
```

Renders the JSON report to Markdown suitable for posts or documentation.

### `dialproof selftest` — prove the monitor works

```bash
dialproof selftest
```

Dials a disallowed host and asserts the monitor recorded a denial for it. It exits non-zero if no denial was observed — it cannot report PASS on a monitor that saw nothing. Every `run` performs this same check, on its own separate monitor, *before* the run's monitor is installed, so the selftest's own dial never contaminates the run's ledger.

## The four axes

| Axis | What it measures | Pass criterion |
|------|---|---|
| **Native tool calls** | Does the endpoint support function calling natively, or fall back to silent JSON mode? | `message.tool_calls` present + valid JSON arguments + `finish_reason == "tool_calls"` on ≥80% of calls. |
| **JSON-schema adherence** | Can the endpoint produce strict `response_format` JSON that validates against a schema? | Parses *and* validates on ≥80% of calls (n=50, temp=0). Classifies failures (enum drift, missing required, type coercion, extra keys). |
| **Streaming delta shape** | Are stream chunks well-formed SSE, with role appearing once, deltas that reassemble to the non-streamed completion, and usage on the final chunk when requested? | 5 sub-assertions (SSE wellformed, role once, delta byte-equality, monotonic tool-call index, usage on final). |
| **Token-count accuracy** | Does the endpoint's reported prompt token count match what a local tokenizer measures? | Exact match on all 10 fixed prompts. Reports signed delta distribution if not. |

## Sample output

**This sample is a run against the bundled mock endpoint** (`tests/test_endpoint.py`, a local
process on `127.0.0.1:8765`), not against a production model server. It exists to show the
report's shape and to let you reproduce the harness end to end offline with
`./run_sample.sh`, which writes to the gitignored `runs/`.
Its axis verdicts describe the mock, and say nothing about any real endpoint.

The artifacts are committed verbatim at
[`sample_runs/2026-09-27-mock-endpoint/`](sample_runs/2026-09-27-mock-endpoint/).

**JSON report** (excerpted; the committed file is the full one):

```json
{
  "dialproof_version": "0.1.0",
  "run_id": "2026-09-27T163631-test-model",
  "endpoint": {
    "base_url": "http://127.0.0.1:8765/v1",
    "server": "unknown",
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
    "attempts": [{"host": "127.0.0.1", "port": 8765, "ip": null, "count": 164, "decision": "allow"}]
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

**Rendered to Markdown** (verbatim from the committed `report.md`):

```markdown
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
```

Reading the two together: the run made **164 connection attempts, every one of them to the
single allowlisted destination** `127.0.0.1:8765` — so the verdict is `SEALED`. `count: 164`
in the JSON and "164 connection attempts to 1 destination" in the Markdown are the same
number; the Markdown never counts ledger *entries* and calls them sockets.

Against the mock: streaming is well-formed, native tool calls fail (the mock does not return
`message.tool_calls`), schema adherence fails on type coercion, and prompt token counts are
under-reported by up to 2.

## Egress monitoring — what L1 can and cannot see

**L1 (always on):** a CPython audit hook on `socket.connect` and `socket.getaddrinfo`. For every attempt it records host, port, a per-destination attempt count, the `allow`/`deny` decision against `--allow`, and the stack frame that caused it.

Stated limits, because a measurement that hides its blind spot is worse than no measurement:

- **It records; it does not block.** The hook never raises. The connection proceeds; the run exits non-zero afterwards and the report carries the full ledger.
- **Subprocesses escape it.** An audit hook is per-process.
- **C-level code that bypasses Python's `socket` module escapes it.** Anything that opens a file descriptor without going through `socket.connect`/`socket.getaddrinfo` is invisible.
- **A bare `socket.connect(("name", port))` to a name that does not resolve is invisible**, because CPython resolves it in C and emits no audit event when resolution fails. Real HTTP clients call `socket.getaddrinfo` first, which is audited. The bundled selftest exercises that path deliberately, for exactly this reason.

Closing the first and last of those is what L2 is for, and L2 is not built yet.

## Not a gateway, router, or proxy

`dialproof` never sits in a production request path. It is run out-of-band and leaves a file behind. It does not wrap providers, does not normalize responses, and adds no runtime dependency to anything it measures.

## Development

```bash
# Install in editable mode with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Reproduce the committed sample run offline (writes to runs/, which is gitignored)
./run_sample.sh

# Format and lint
black src tests
ruff check --fix src tests

# Type check
mypy src
```

## License

MIT
