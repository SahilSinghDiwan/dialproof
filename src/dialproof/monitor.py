"""Egress monitoring via CPython audit hook (L1)."""

import socket
import sys
import traceback
from dataclasses import dataclass
from threading import Lock
from typing import List, Optional, Set


@dataclass
class EgressAttempt:
    """Record of a socket connection attempt."""

    host: str
    port: int
    ip: Optional[str]
    decision: str  # "allow" or "deny"
    stack: List[str]
    count: int = 1


class EgressMonitor:
    """Monitors all outbound network connections via audit hook."""

    def __init__(self, allowlist: Set[str]):
        """
        Initialize the egress monitor.

        Args:
            allowlist: Set of allowed "host:port" strings
        """
        self.allowlist = allowlist
        self.attempts: dict[str, EgressAttempt] = {}
        self.denied: List[EgressAttempt] = []
        self._lock = Lock()
        self._violations_found = False
        self._hook_installed = False

    def start(self):
        """Start monitoring egress."""
        if not self._hook_installed:
            sys.addaudithook(self._audit_hook)
            self._hook_installed = True

    def stop(self):
        """Stop monitoring (note: audit hooks cannot be removed, but we track state)."""
        pass

    def _audit_hook(self, event: str, args):
        """Audit hook callback for socket operations."""
        if event == "socket.connect":
            self._handle_connect(args)
        elif event == "socket.getaddrinfo":
            self._handle_getaddrinfo(args)

    def _handle_connect(self, args):
        """Handle socket.connect audit event."""
        try:
            sock = args[0]
            if not isinstance(sock, socket.socket):
                return

            address = args[1]
            if not isinstance(address, (tuple, str)):
                return

            if isinstance(address, tuple):
                host, port = address[0], address[1]
            else:
                host, port = address, 0

            self._record_attempt(host, port)
        except Exception:
            pass

    def _handle_getaddrinfo(self, args):
        """Handle socket.getaddrinfo audit event."""
        try:
            host = args[0]
            port = args[1] if len(args) > 1 else 0
            self._record_attempt(host, port)
        except Exception:
            pass

    def _record_attempt(self, host: str, port: int):
        """Record a connection attempt and check allowlist."""
        with self._lock:
            key = f"{host}:{port}" if port else host

            # Check allowlist
            allowed = key in self.allowlist or host in self.allowlist

            # Record or update
            if key in self.attempts:
                self.attempts[key].count += 1
            else:
                stack = traceback.format_stack()[:-1]
                decision = "allow" if allowed else "deny"
                self.attempts[key] = EgressAttempt(
                    host=host,
                    port=port,
                    ip=None,
                    decision=decision,
                    stack=stack,
                )

            # Track violations
            if not allowed:
                self._violations_found = True
                self.denied.append(self.attempts[key])

    def get_violations(self) -> List[EgressAttempt]:
        """Get all denied connection attempts."""
        with self._lock:
            return list(self.denied)

    def had_violations(self) -> bool:
        """Check if any denied attempts were made."""
        return self._violations_found

    def clear(self):
        """Clear recorded attempts."""
        with self._lock:
            self.attempts.clear()
            self.denied.clear()
            self._violations_found = False

    def get_summary(self) -> dict:
        """Get a summary of all attempts."""
        with self._lock:
            result = []
            for attempt in self.attempts.values():
                result.append(
                    {
                        "host": attempt.host,
                        "port": attempt.port,
                        "ip": attempt.ip,
                        "count": attempt.count,
                        "decision": attempt.decision,
                    }
                )
            return {"attempts": result, "denied_count": len(self.denied)}
