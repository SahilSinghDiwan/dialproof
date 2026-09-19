"""Tests for egress monitoring."""

import pytest
from dialproof.monitor import EgressMonitor


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
