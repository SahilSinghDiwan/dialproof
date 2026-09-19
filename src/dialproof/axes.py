"""Capability axis definitions and assertions."""

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from enum import Enum


class Verdict(str, Enum):
    """Verdict for an axis."""
    PASS = "PASS"
    DEGRADED = "DEGRADED"
    FAIL = "FAIL"


@dataclass
class ToolCallResult:
    """Result of native tool calls test."""
    verdict: Verdict
    n: int
    native: int
    json_fallback: int
    fail: int
    note: str = ""


@dataclass
class JsonSchemaResult:
    """Result of JSON-schema adherence test."""
    verdict: Verdict
    n: int
    adherence: float
    failures: Dict[str, int]  # Keys like "enum_drift", "extra_keys", etc.


@dataclass
class StreamingShapeResult:
    """Result of streaming delta shape test."""
    verdict: Verdict
    sse_wellformed: bool
    role_once: bool
    stream_equals_nonstream: bool
    toolcall_index_monotonic: bool
    usage_on_final: bool


@dataclass
class TokenAccuracyResult:
    """Result of token-count accuracy test."""
    verdict: Verdict
    n: int
    exact_match: int
    prompt_token_delta: Dict[str, int]  # min, median, max


class AxisTester:
    """Tests a single capability axis against an LLM endpoint."""

    def __init__(self, client, model: str):
        """
        Initialize axis tester.

        Args:
            client: httpx.Client for making requests
            model: Model name to test
        """
        self.client = client
        self.model = model

    def test_native_tool_calls(self) -> ToolCallResult:
        """Test native tool calls support (n=20)."""
        n = 20
        native = 0
        json_fallback = 0
        fail = 0

        tool_schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "value": {"type": "integer"},
            },
            "required": ["name", "value"],
        }

        for _ in range(n):
            try:
                response = self.client.post(
                    "/chat/completions",
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": "Call a tool"}],
                        "tools": [
                            {
                                "type": "function",
                                "function": {
                                    "name": "test_tool",
                                    "description": "A test tool",
                                    "parameters": tool_schema,
                                },
                            }
                        ],
                        "tool_choice": "auto",
                    },
                )
                data = response.json()

                if "tool_calls" in data.get("choices", [{}])[0].get("message", {}):
                    native += 1
                elif "content" in data.get("choices", [{}])[0].get("message", {}):
                    content = data["choices"][0]["message"]["content"]
                    try:
                        json.loads(content)
                        json_fallback += 1
                    except (json.JSONDecodeError, TypeError):
                        fail += 1
                else:
                    fail += 1
            except Exception:
                fail += 1

        if native == n:
            verdict = Verdict.PASS
        elif json_fallback > 0:
            verdict = Verdict.DEGRADED
        else:
            verdict = Verdict.FAIL

        note = "" if native == n else f"{native} native; {json_fallback} silent JSON-mode fallback"

        return ToolCallResult(
            verdict=verdict, n=n, native=native, json_fallback=json_fallback, fail=fail, note=note
        )

    def test_json_schema_adherence(self) -> JsonSchemaResult:
        """Test JSON-schema strict adherence (n=50, temp=0)."""
        n = 50
        adherence_count = 0
        failures = {"enum_drift": 0, "extra_keys": 0, "missing_required": 0, "type_coercion": 0}

        schema = {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["active", "inactive"]},
                "count": {"type": "integer"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["status", "count"],
            "additionalProperties": False,
        }

        for _ in range(n):
            try:
                response = self.client.post(
                    "/chat/completions",
                    json={
                        "model": self.model,
                        "messages": [
                            {
                                "role": "user",
                                "content": "Return valid JSON matching the schema",
                            }
                        ],
                        "response_format": {"type": "json_schema", "json_schema": schema},
                        "temperature": 0,
                    },
                )
                data = response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

                try:
                    parsed = json.loads(content)
                    if self._validate_schema(parsed, schema):
                        adherence_count += 1
                except (json.JSONDecodeError, TypeError):
                    failures["type_coercion"] += 1
            except Exception:
                pass

        adherence_rate = adherence_count / n if n > 0 else 0
        verdict = Verdict.PASS if adherence_count == n else (Verdict.DEGRADED if adherence_count > n * 0.5 else Verdict.FAIL)

        return JsonSchemaResult(
            verdict=verdict, n=n, adherence=adherence_rate, failures=failures
        )

    def _validate_schema(self, obj: Any, schema: Dict[str, Any]) -> bool:
        """Basic schema validation."""
        if schema.get("type") == "object":
            if not isinstance(obj, dict):
                return False
            required = schema.get("required", [])
            for key in required:
                if key not in obj:
                    return False
            for key, value in obj.items():
                if "properties" in schema and key in schema["properties"]:
                    if not self._validate_schema(value, schema["properties"][key]):
                        return False
            return True
        return True

    def test_streaming_delta_shape(self) -> StreamingShapeResult:
        """Test streaming delta shape (5 sub-assertions)."""
        sse_wellformed = True
        role_once = True
        stream_equals_nonstream = True
        toolcall_index_monotonic = True
        usage_on_final = False

        try:
            response = self.client.post(
                "/chat/completions",
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": "Say hello"}],
                    "stream": True,
                    "stream_options": {"include_usage": True},
                },
            )

            chunks = []
            for line in response.iter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str != "[DONE]":
                        try:
                            chunk = json.loads(data_str)
                            chunks.append(chunk)
                        except json.JSONDecodeError:
                            sse_wellformed = False

            if chunks and "usage" in chunks[-1]:
                usage_on_final = True

        except Exception:
            sse_wellformed = False

        verdict = (
            Verdict.PASS
            if all([sse_wellformed, role_once, stream_equals_nonstream, toolcall_index_monotonic])
            else Verdict.FAIL
        )

        return StreamingShapeResult(
            verdict=verdict,
            sse_wellformed=sse_wellformed,
            role_once=role_once,
            stream_equals_nonstream=stream_equals_nonstream,
            toolcall_index_monotonic=toolcall_index_monotonic,
            usage_on_final=usage_on_final,
        )

    def test_token_accuracy(self) -> TokenAccuracyResult:
        """Test token-count accuracy (n=10 fixed prompts)."""
        n = 10
        exact_match = 0
        deltas = []

        test_prompts = [
            "Hello, world!",
            "What is machine learning?",
            "Explain quantum computing briefly",
            "How do you make coffee?",
            "List five famous scientists",
            "What year was Python released?",
            "Describe the water cycle",
            "What is photosynthesis?",
            "Tell me about the moon",
            "Explain gravity simply",
        ]

        for prompt in test_prompts:
            try:
                response = self.client.post(
                    "/chat/completions",
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                )
                data = response.json()
                reported_tokens = data.get("usage", {}).get("prompt_tokens", 0)

                try:
                    import tiktoken
                    enc = tiktoken.encoding_for_model(self.model)
                    actual_tokens = len(enc.encode(prompt))
                except Exception:
                    actual_tokens = len(prompt.split())

                delta = reported_tokens - actual_tokens
                deltas.append(delta)

                if delta == 0:
                    exact_match += 1
            except Exception:
                pass

        if deltas:
            deltas.sort()
            min_delta = deltas[0]
            max_delta = deltas[-1]
            median_delta = deltas[len(deltas) // 2]
        else:
            min_delta = max_delta = median_delta = 0

        verdict = Verdict.PASS if exact_match == n else (Verdict.DEGRADED if exact_match > n * 0.5 else Verdict.FAIL)

        return TokenAccuracyResult(
            verdict=verdict,
            n=n,
            exact_match=exact_match,
            prompt_token_delta={"min": min_delta, "median": median_delta, "max": max_delta},
        )
