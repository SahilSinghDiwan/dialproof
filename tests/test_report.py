"""Tests for report generation."""

import json
from pathlib import Path
import tempfile
import pytest
from dialproof.report import Report, EndpointInfo, MonitorInfo, EgressInfo


def test_report_to_dict():
    """Test report serialization to dict."""
    endpoint = EndpointInfo(
        base_url="http://localhost:8000/v1",
        server="vllm/0.11.2",
        model="qwen3-32b",
    )
    monitor = MonitorInfo(layer="L1-audithook", selftest="PASS")
    egress = EgressInfo(
        verdict="SEALED",
        allowlist=["localhost:8000"],
        attempts=[
            {"host": "localhost", "port": 8000, "ip": None, "count": 10, "decision": "allow"}
        ],
    )
    axes = {
        "native_tool_calls": {"verdict": "PASS", "n": 20, "native": 20, "json_fallback": 0, "fail": 0},
    }
    cost = {"wall_clock_s": 10, "requests": 20, "usd": None}

    report = Report(
        run_id="test-run-001",
        endpoint=endpoint,
        transport="raw-httpx",
        monitor=monitor,
        egress=egress,
        axes=axes,
        cost=cost,
    )

    data = report.to_dict()
    assert data["run_id"] == "test-run-001"
    assert data["endpoint"]["model"] == "qwen3-32b"
    assert data["monitor"]["selftest"] == "PASS"
    assert data["egress"]["verdict"] == "SEALED"


def test_report_json_round_trip():
    """Test JSON serialization and deserialization."""
    endpoint = EndpointInfo(
        base_url="http://localhost:8000/v1",
        server="vllm/0.11.2",
        model="qwen3-32b",
    )
    monitor = MonitorInfo(layer="L1-audithook", selftest="PASS")
    egress = EgressInfo(
        verdict="SEALED",
        allowlist=["localhost:8000"],
        attempts=[],
    )
    axes = {}
    cost = {"wall_clock_s": 0, "requests": 0, "usd": None}

    report = Report(
        run_id="test-run-001",
        endpoint=endpoint,
        transport="raw-httpx",
        monitor=monitor,
        egress=egress,
        axes=axes,
        cost=cost,
    )

    # Serialize to JSON and back
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "report.json"
        report.save(path)

        loaded = Report.load(path)
        assert loaded.run_id == "test-run-001"
        assert loaded.endpoint.model == "qwen3-32b"
        assert loaded.egress.verdict == "SEALED"


def test_report_markdown_render():
    """Test Markdown rendering."""
    endpoint = EndpointInfo(
        base_url="http://localhost:8000/v1",
        server="vllm/0.11.2",
        model="qwen3-32b",
    )
    monitor = MonitorInfo(layer="L1-audithook", selftest="PASS")
    egress = EgressInfo(
        verdict="SEALED",
        allowlist=["localhost:8000"],
        attempts=[{"host": "localhost", "port": 8000, "ip": None, "count": 10, "decision": "allow"}],
    )
    axes = {
        "native_tool_calls": {"verdict": "PASS", "n": 20, "native": 20, "json_fallback": 0, "fail": 0},
        "json_schema_adherence": {"verdict": "PASS", "n": 50, "adherence": 0.95, "failures": {}},
    }
    cost = {"wall_clock_s": 10, "requests": 20, "usd": None}

    report = Report(
        run_id="test-run-001",
        endpoint=endpoint,
        transport="raw-httpx",
        monitor=monitor,
        egress=egress,
        axes=axes,
        cost=cost,
    )

    md = report.to_markdown()
    assert "vllm/0.11.2" in md
    assert "qwen3-32b" in md
    assert "SEALED" in md
    assert "PASS" in md
    assert "| Axis |" in md
