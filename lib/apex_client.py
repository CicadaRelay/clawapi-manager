"""Apex Python Client — thin sync client over UDS + MessagePack.

Connects to apexd via Unix domain socket (or TCP on Windows).
All 9 RPC methods are exposed as typed Python functions.
"""

from __future__ import annotations

import os
import socket
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

import msgpack


DEFAULT_SOCKET = "/tmp/apex-daemon.sock"


class ApexError(Exception):
    """Error returned by apexd."""
    def __init__(self, code: str, message: str, retryable: bool = False):
        self.code = code
        self.retryable = retryable
        super().__init__(f"[{code}] {message}")


class ApexClient:
    """Synchronous client for apexd UDS + MessagePack API."""

    def __init__(self, socket_path: str = ""):
        self._path = socket_path or os.getenv("APEX_SOCKET", DEFAULT_SOCKET)
        self._sock: Optional[socket.socket] = None
        self._packer = msgpack.Packer(use_bin_type=True)
        self._unpacker = msgpack.Unpacker(raw=False)

    def connect(self) -> None:
        """Connect to apexd UDS."""
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.connect(self._path)

    def close(self) -> None:
        if self._sock:
            self._sock.close()
            self._sock = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *_):
        self.close()

    def _call(self, method: str, body: dict) -> dict:
        """Send RPC and return response body."""
        if not self._sock:
            self.connect()

        envelope = {
            "version": 1,
            "request_id": f"{method}-{uuid.uuid4().hex[:8]}",
            "method": method,
            "body": body,
        }
        self._sock.sendall(msgpack.packb(envelope, use_bin_type=True))

        # Read response
        while True:
            data = self._sock.recv(65536)
            if not data:
                raise ConnectionError("apexd closed connection")
            self._unpacker.feed(data)
            for resp in self._unpacker:
                if "error" in resp:
                    err = resp["error"]
                    raise ApexError(err["code"], err["message"], err.get("retryable", False))
                return resp.get("body", {})

    # --- Orchestration Plane ---

    def submit_job(
        self,
        description: str,
        priority: int = 50,
        decomposition: str = "external",
        payload: dict = None,
        initial_tasks: list[dict] = None,
    ) -> dict:
        """Submit a job. Returns {job_id, state, root_task_ids}."""
        body = {
            "description": description,
            "priority": priority,
            "decomposition": decomposition,
        }
        if payload:
            body["payload"] = payload
        if initial_tasks:
            body["initial_tasks"] = initial_tasks
        return self._call("submit_job", body)

    def upsert_tasks(self, tasks: list[dict], source_task_id: str = None) -> dict:
        """Batch create/update tasks. Returns {task_ids}."""
        body = {"tasks": tasks}
        if source_task_id:
            body["source_task_id"] = source_task_id
        return self._call("upsert_tasks", body)

    def cancel(self, scope: str, id: str, reason: str = "") -> dict:
        """Cancel a job, task, or session. Returns {accepted, affected}."""
        return self._call("cancel", {"scope": scope, "id": id, "reason": reason})

    # --- Execution Plane ---

    def register_agent(
        self,
        agent_id: str,
        roles: list[str] = None,
        model_tier: str = "medium",
        max_concurrency: int = 1,
    ) -> dict:
        """Register an agent. Returns {session_id, lease_ttl_ms, ...}."""
        return self._call("register_agent", {
            "agent_id": agent_id,
            "capabilities": {
                "roles": roles or ["code"],
                "langs": [],
                "tools": [],
                "modes": [],
            },
            "model_tier": model_tier,
            "max_concurrency": max_concurrency,
            "heartbeat_every_ms": 15000,
            "client_version": "python-0.1",
        })

    def heartbeat(self, session_id: str, status: str = "idle", active_tasks: list = None) -> dict:
        """Send heartbeat. Returns {acked_at_ms, cancel_tasks, drain, shutdown}."""
        return self._call("heartbeat", {
            "session_id": session_id,
            "status": status,
            "active_tasks": active_tasks or [],
        })

    def pull_tasks(self, session_id: str, max_tasks: int = 1, wait_ms: int = 0) -> dict:
        """Pull tasks from queue. Returns {assignments, retry_after_ms}."""
        return self._call("pull_tasks", {
            "session_id": session_id,
            "max_tasks": max_tasks,
            "wait_ms": wait_ms,
        })

    def finish_task(
        self,
        session_id: str,
        lease_id: str,
        task_id: str,
        outcome: str = "success",
        summary: str = "",
        result: dict = None,
    ) -> dict:
        """Report task completion. Returns {ack}."""
        return self._call("finish_task", {
            "session_id": session_id,
            "lease_id": lease_id,
            "task_id": task_id,
            "outcome": outcome,
            "summary": summary,
            "result": result or {},
        })

    # --- Budget Plane ---

    def request_action_budget(
        self,
        session_id: str,
        task_id: str,
        action_id: str,
        cost_units: int = 10,
        model_class: str = "smart",
        mode: str = "try",
    ) -> dict:
        """Request budget for an LLM action. Returns {status, grant}."""
        return self._call("request_action_budget", {
            "session_id": session_id,
            "task_id": task_id,
            "action_id": action_id,
            "estimate": {
                "prompt_tokens_max": 2000,
                "completion_tokens_max": 4000,
                "model_class": model_class,
                "cost_units": cost_units,
            },
            "mode": mode,
            "max_wait_ms": 0,
        })

    def finish_action(
        self,
        reservation_id: str,
        task_id: str,
        action_id: str,
        outcome: str = "committed",
        actual_cost_units: int = 0,
        model: str = "",
        latency_ms: int = 0,
    ) -> dict:
        """Report action completion. Returns {ack}."""
        body = {
            "reservation_id": reservation_id,
            "task_id": task_id,
            "action_id": action_id,
            "outcome": outcome,
        }
        if outcome == "committed" and actual_cost_units > 0:
            body["actual"] = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "cost_units": actual_cost_units,
                "model": model,
                "latency_ms": latency_ms,
            }
        return self._call("finish_action", body)
