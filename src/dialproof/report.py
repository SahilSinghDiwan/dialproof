"""Report generation and rendering."""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class EndpointInfo:
    base_url: str
    server: str
    model: str


@dataclass
class MonitorInfo:
    layer: str  # "L1-audithook" or "L2-sealed"
    selftest: str  # "PASS" or "FAIL"
    denied_host_dialed: Optional[str] = None


@dataclass
class EgressInfo:
    verdict: str  # "SEALED" or "OPEN"
    allowlist: List[str]
    attempts: List[Dict[str, Any]]


class Report:
    """Represents a dialproof run report."""

    def __init__(
        self,
        run_id: str,
        endpoint: EndpointInfo,
        transport: str,
        monitor: MonitorInfo,
        egress: EgressInfo,
        axes: Dict[str, Any],
        cost: Dict[str, Any],
    ):
        self.run_id = run_id
        self.endpoint = endpoint
        self.transport = transport
        self.monitor = monitor
        self.egress = egress
        self.axes = axes
        self.cost = cost
        self.timestamp = datetime.utcnow().isoformat() + "Z"
        self.artifacts_sha256 = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert report to dictionary."""
        return {
            "dialproof_version": "0.1.0",
            "timestamp": self.timestamp,
            "run_id": self.run_id,
            "endpoint": {
                "base_url": self.endpoint.base_url,
                "server": self.endpoint.server,
                "model": self.endpoint.model,
            },
            "transport": self.transport,
            "monitor": {
                "layer": self.monitor.layer,
                "selftest": self.monitor.selftest,
                "denied_host_dialed": self.monitor.denied_host_dialed,
            },
            "egress": {
                "verdict": self.egress.verdict,
                "allowlist": self.egress.allowlist,
                "attempts": self.egress.attempts,
            },
            "axes": self.axes,
            "cost": self.cost,
            "artifacts_sha256": self.artifacts_sha256,
            "verdict": {
                "conformance": self._conformance_summary(),
                "egress": self.egress.verdict,
            },
        }

    def _conformance_summary(self) -> str:
        """Generate conformance summary."""
        verdicts = [v for v in self.axes.values() if isinstance(v, dict) and "verdict" in v]
        passed = sum(1 for v in verdicts if v["verdict"] == "PASS")
        total = len(verdicts)
        return f"{passed}/{total} axes pass"

    def to_json(self) -> str:
        """Serialize to JSON."""
        return json.dumps(self.to_dict(), indent=2)

    def to_markdown(self) -> str:
        """Render to Markdown."""
        report = self.to_dict()
        endpoint = report["endpoint"]
        monitor = report["monitor"]
        egress = report["egress"]
        axes = report["axes"]

        socket_count = len(egress['attempts'])
        plural = "s" if socket_count != 1 else ""
        socket_text = f"**Egress: {egress['verdict']}** — {socket_count} socket{plural}"

        if egress["allowlist"]:
            socket_text += f", all to `{', '.join(egress['allowlist'])}`"

        lines = [
            f"### {endpoint['server']} · {endpoint['model']} · {report['timestamp'][:10]}",
            "",
            socket_text,
            f"Monitor self-test {monitor['selftest']}.",
            "",
            "| Axis | Verdict | Number |",
            "|---|---|---|",
        ]

        # Native tool calls
        if "native_tool_calls" in axes:
            tc = axes["native_tool_calls"]
            lines.append(
                f"| Native tool calls | {tc.get('verdict', 'UNKNOWN')} | "
                f"{tc.get('native', 0)}/{tc.get('n', 0)} native; "
                f"{tc.get('json_fallback', 0)}/{tc.get('n', 0)} JSON-mode |"
            )

        # JSON-schema adherence
        if "json_schema_adherence" in axes:
            js = axes["json_schema_adherence"]
            adherence_pct = int(js.get("adherence", 0) * 100)
            failures_str = "; ".join(
                f"{k}: {v}" for k, v in js.get("failures", {}).items() if v > 0
            )
            n_val = js.get("n", 0)
            passed = int(js.get("adherence", 0) * n_val)
            failures_part = f" — {failures_str}" if failures_str else ""
            lines.append(
                f"| JSON-schema adherence | {js.get('verdict', 'UNKNOWN')} | "
                f"{adherence_pct}% ({passed}/{n_val}){failures_part} |"
            )

        # Streaming delta shape
        if "streaming_shape" in axes:
            ss = axes["streaming_shape"]
            sub_passed = sum([
                ss.get("sse_wellformed", False),
                ss.get("role_once", False),
                ss.get("stream_equals_nonstream", False),
                ss.get("toolcall_index_monotonic", False),
            ])
            usage_note = (
                "; usage absent on final chunk"
                if not ss.get("usage_on_final", False)
                else ""
            )
            lines.append(
                f"| Streaming delta shape | {ss.get('verdict', 'UNKNOWN')} | "
                f"{sub_passed}/5 sub-assertions{usage_note} |"
            )

        # Token accuracy
        if "token_accuracy" in axes:
            ta = axes["token_accuracy"]
            delta = ta.get("prompt_token_delta", {})
            max_delta = delta.get("max", 0)
            direction = "under" if max_delta < 0 else "over"
            delta_note = (
                f"; tokens {direction}-reported by up to {abs(max_delta)}"
                if max_delta != 0
                else ""
            )
            lines.append(
                f"| Token-count accuracy | {ta.get('verdict', 'UNKNOWN')} | "
                f"{ta.get('exact_match', 0)}/{ta.get('n', 0)} exact{delta_note} |"
            )

        lines.extend([
            "",
            f"Reproduce: `dialproof verify {self.run_id}/report.json`",
        ])

        return "\n".join(lines)

    def save(self, path: Path) -> None:
        """Save report to file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            f.write(self.to_json())

    @staticmethod
    def load(path: Path) -> "Report":
        """Load report from file."""
        with open(path, "r") as f:
            data = json.load(f)

        endpoint = EndpointInfo(
            base_url=data["endpoint"]["base_url"],
            server=data["endpoint"]["server"],
            model=data["endpoint"]["model"],
        )

        monitor = MonitorInfo(
            layer=data["monitor"]["layer"],
            selftest=data["monitor"]["selftest"],
            denied_host_dialed=data["monitor"].get("denied_host_dialed"),
        )

        egress = EgressInfo(
            verdict=data["egress"]["verdict"],
            allowlist=data["egress"]["allowlist"],
            attempts=data["egress"]["attempts"],
        )

        report = Report(
            run_id=data["run_id"],
            endpoint=endpoint,
            transport=data["transport"],
            monitor=monitor,
            egress=egress,
            axes=data["axes"],
            cost=data["cost"],
        )
        report.artifacts_sha256 = data.get("artifacts_sha256", "")
        return report
