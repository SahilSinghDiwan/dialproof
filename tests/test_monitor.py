"""Tests for egress monitoring."""

import tempfile
from pathlib import Path

import pytest

from dialproof.monitor import EgressMonitor

TMP_OUT = Path(tempfile.gettempdir()) / "dialproof-selftest-out"


def test_monitor_allowlist():
    """Test that monitor respects allowlist."""
    monitor = EgressMonitor(allowlist={"allowed.local:8000"})
    monitor.start()

    # Record an allowed attempt
    monitor._record_attempt("allowed.local", 8000)
    assert not monitor.had_violations()

    # Record a denied attempt
    monitor._record_attempt("blocked.invalid", 443)
    assert monitor.had_violations()

    violations = monitor.get_violations()
    assert len(violations) == 1
    assert violations[0].host == "blocked.invalid"


def test_monitor_summary():
    """Test monitor summary output."""
    monitor = EgressMonitor(allowlist={"allowed.local:8000"})
    monitor.start()

    monitor._record_attempt("allowed.local", 8000)
    monitor._record_attempt("allowed.local", 8000)
    monitor._record_attempt("blocked.invalid", 443)

    summary = monitor.get_summary()
    assert "attempts" in summary
    assert summary["denied_count"] == 1
    assert len(summary["attempts"]) == 2


def test_monitor_clear():
    """Test clearing monitor state."""
    monitor = EgressMonitor(allowlist={"allowed.local:8000"})
    monitor.start()

    monitor._record_attempt("allowed.local", 8000)
    monitor._record_attempt("blocked.invalid", 443)

    monitor.clear()
    assert not monitor.had_violations()
    assert len(monitor.attempts) == 0


def test_selftest_observes_a_real_denial():
    """The selftest must return the host it actually saw denied."""
    from dialproof.commands import SELFTEST_HOST, _run_monitor_selftest

    assert _run_monitor_selftest() == SELFTEST_HOST


def test_selftest_raises_when_nothing_was_observed(monkeypatch):
    """A selftest that observes no denial must fail, never report PASS."""
    import dialproof.commands as commands

    monkeypatch.setattr(EgressMonitor, "had_violations", lambda self: False)

    with pytest.raises(commands.MonitorSelftestError):
        commands._run_monitor_selftest()


def test_run_records_selftest_failure(monkeypatch):
    """run_command must stamp FAIL, not PASS, when the selftest raises."""
    import dialproof.commands as commands

    def boom():
        raise commands.MonitorSelftestError("no denial observed")

    monkeypatch.setattr(commands, "_run_monitor_selftest", boom)

    captured = {}
    original = commands.Report

    class RecordingReport(original):  # type: ignore[misc,valid-type]
        def __init__(self, *args, **kwargs):
            captured["selftest"] = kwargs["monitor"].selftest
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(commands, "Report", RecordingReport)

    commands.run_command(
        endpoint="http://127.0.0.1:1/v1",
        model="test-model",
        allow=["127.0.0.1:1"],
        out=str(TMP_OUT),
    )
    assert captured.get("selftest") == "FAIL"
