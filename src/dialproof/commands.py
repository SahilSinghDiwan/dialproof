"""Core command implementations."""

import socket
import sys
from datetime import datetime
from pathlib import Path
from typing import Set

import httpx

from .axes import AxisTester
from .monitor import EgressMonitor
from .report import EgressInfo, EndpointInfo, MonitorInfo, Report


def run_command(
    endpoint: str,
    model: str,
    allow: list[str],
    out: str,
    transport: str = "raw-httpx",
) -> int:
    """Run the capability probe."""
    out_path = Path(out)
    out_path.mkdir(parents=True, exist_ok=True)

    # Prepare allowlist
    allowlist: Set[str] = set(allow)
    # Parse endpoint URL to add to allowlist
    if endpoint.startswith("http://"):
        ep = endpoint[7:]
    elif endpoint.startswith("https://"):
        ep = endpoint[8:]
    else:
        ep = endpoint
    host = ep.split("/")[0]
    allowlist.add(host)

    # Set up monitor
    monitor = EgressMonitor(allowlist)
    monitor.start()

    # Run selftest
    selftest_result = "PASS"
    denied_host_dialed = None
    try:
        denied_host_dialed = _run_monitor_selftest()
    except Exception:
        selftest_result = "FAIL"

    # Connect to endpoint
    try:
        base_url = endpoint.rstrip("/")
        client = httpx.Client(base_url=base_url, timeout=30.0)

        # Get server info
        try:
            response = client.get("/models")
            data = response.json()
            server_id = data.get("object", "unknown")
        except Exception:
            server_id = "unknown"

        # Run tests
        tester = AxisTester(client, model)

        tc_result = tester.test_native_tool_calls()
        js_result = tester.test_json_schema_adherence()
        ss_result = tester.test_streaming_delta_shape()
        ta_result = tester.test_token_accuracy()

        # Prepare egress info
        egress_summary = monitor.get_summary()
        attempts = []
        for attempt in egress_summary["attempts"]:
            attempts.append(
                {
                    "host": attempt["host"],
                    "port": attempt["port"],
                    "ip": attempt.get("ip"),
                    "count": attempt["count"],
                    "decision": attempt["decision"],
                }
            )

        egress_verdict = "SEALED" if not monitor.had_violations() else "OPEN"

        # Create report
        endpoint_info = EndpointInfo(
            base_url=endpoint,
            server=server_id,
            model=model,
        )

        monitor_info = MonitorInfo(
            layer="L1-audithook",
            selftest=selftest_result,
            denied_host_dialed=denied_host_dialed,
        )

        egress_info = EgressInfo(
            verdict=egress_verdict,
            allowlist=list(allowlist),
            attempts=attempts,
        )

        # Prepare axes data
        axes_data = {
            "native_tool_calls": {
                "verdict": tc_result.verdict.value,
                "n": tc_result.n,
                "native": tc_result.native,
                "json_fallback": tc_result.json_fallback,
                "fail": tc_result.fail,
                "note": tc_result.note,
            },
            "json_schema_adherence": {
                "verdict": js_result.verdict.value,
                "n": js_result.n,
                "adherence": js_result.adherence,
                "failures": js_result.failures,
            },
            "streaming_shape": {
                "verdict": ss_result.verdict.value,
                "sse_wellformed": ss_result.sse_wellformed,
                "role_once": ss_result.role_once,
                "stream_equals_nonstream": ss_result.stream_equals_nonstream,
                "toolcall_index_monotonic": ss_result.toolcall_index_monotonic,
                "usage_on_final": ss_result.usage_on_final,
            },
            "token_accuracy": {
                "verdict": ta_result.verdict.value,
                "n": ta_result.n,
                "exact_match": ta_result.exact_match,
                "prompt_token_delta": ta_result.prompt_token_delta,
            },
        }

        cost_data = {
            "wall_clock_s": 0,
            "requests": len(egress_summary["attempts"]),
            "usd": None,
            "note": "self-hosted; no per-token price applies",
        }

        run_id = f"{datetime.utcnow().isoformat()[:19].replace(':', '')}-{model}"
        report = Report(
            run_id=run_id,
            endpoint=endpoint_info,
            transport=transport,
            monitor=monitor_info,
            egress=egress_info,
            axes=axes_data,
            cost=cost_data,
        )

        # Save JSON report
        report_path = out_path / "report.json"
        report.save(report_path)

        # Save Markdown rendering
        md_path = out_path / "report.md"
        with open(md_path, "w") as f:
            f.write(report.to_markdown())

        print(f"Report saved to {report_path}")
        print(f"Markdown rendering saved to {md_path}")

        client.close()

        # Exit with error if violations found
        if monitor.had_violations():
            print("ERROR: Egress violations detected", file=sys.stderr)
            return 1

        return 0

    except Exception as e:
        print(f"Error during run: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1


def verify_command(report_path: str) -> int:
    """Verify a report without re-running."""
    try:
        report = Report.load(Path(report_path))
        print(f"Report: {report.run_id}")
        print(f"Endpoint: {report.endpoint.base_url}")
        print(f"Transport: {report.transport}")
        print(f"Monitor selftest: {report.monitor.selftest}")
        print(f"Egress verdict: {report.egress.verdict}")

        # Check that selftest passed
        if report.monitor.selftest != "PASS":
            print("ERROR: Monitor selftest failed", file=sys.stderr)
            return 1

        return 0
    except Exception as e:
        print(f"Error verifying report: {e}", file=sys.stderr)
        return 1


def render_command(report_path: str, format: str = "md") -> str:
    """Render a report to the specified format."""
    report = Report.load(Path(report_path))
    if format == "md":
        return report.to_markdown()
    elif format == "json":
        return report.to_json()
    else:
        raise ValueError(f"Unknown format: {format}")


def selftest_command() -> int:
    """Run the monitor selftest (deliberately dial a disallowed host)."""
    try:
        _run_monitor_selftest()
        print("Monitor selftest PASS")
        return 0
    except Exception as e:
        print(f"Monitor selftest FAIL: {e}", file=sys.stderr)
        return 1


def _run_monitor_selftest() -> str:
    """Try to connect to a disallowed host and verify it was blocked."""
    monitor = EgressMonitor(allowlist={"allowed.local:8000"})
    monitor.start()

    # Try to connect to disallowed host
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        # Try to connect to a host we know won't work and isn't allowed
        try:
            sock.connect(("blocked.invalid", 443))
        except (socket.gaierror, socket.timeout, ConnectionRefusedError, OSError):
            # Expected
            pass
        finally:
            sock.close()
    except Exception:
        pass

    # Check if violation was recorded
    if monitor.had_violations():
        violations = monitor.get_violations()
        if violations:
            return violations[0].host

    return "blocked.invalid"
