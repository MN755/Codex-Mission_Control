from __future__ import annotations

import contextlib
import json
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, unquote_plus, urlparse


PROMETHEUS_QUERIES = {
    "avg(DCGM_FI_DEV_GPU_UTIL)": 78.0,
    "sum(DCGM_FI_DEV_FB_USED)": 512.0,
    "sum(DCGM_FI_DEV_FB_FREE)": 1536.0,
    "count(DCGM_FI_DEV_GPU_UTIL)": 1.0,
    'sum(kube_pod_status_phase{phase="Pending"})': 0.0,
    'sum(kube_pod_status_phase{phase="Running"})': 2.0,
}


@dataclass
class MockNvidiaStackConfig:
    dynamo_models: list[str] = field(default_factory=lambda: ["Qwen/Qwen3-0.6B"])
    nim_models: list[str] = field(default_factory=lambda: ["meta/llama-3.1-8b-instruct"])
    aiq_agent_types: list[str] = field(default_factory=lambda: ["deep_researcher"])
    aiq_data_sources: list[str] = field(default_factory=lambda: ["pubmed", "arxiv"])
    aiq_report: str = "Use a bounded CUDA validation loop with benchmark and profile evidence."
    aiq_cited_urls: list[str] = field(default_factory=lambda: ["https://developer.nvidia.com/blog"])
    prometheus_values: dict[str, float] = field(default_factory=lambda: dict(PROMETHEUS_QUERIES))
    auth_token: str | None = None


class _JsonHandler(BaseHTTPRequestHandler):
    server: "_JsonServer"

    def _send_json(self, payload: Any, *, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8", errors="ignore")
        try:
            payload = json.loads(raw or "{}")
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _authorized(self) -> bool:
        required = self.server.auth_token
        if not required:
            return True
        return self.headers.get("Authorization") == f"Bearer {required}"

    def do_GET(self) -> None:  # noqa: N802
        self.server.handle_request(self, "GET")

    def do_POST(self) -> None:  # noqa: N802
        self.server.handle_request(self, "POST")

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return


class _JsonServer(ThreadingHTTPServer):
    def __init__(self, handler, *, auth_token: str | None = None):
        super().__init__(("127.0.0.1", 0), handler)
        self.auth_token = auth_token

    @property
    def base_url(self) -> str:
        host, port = self.server_address
        return f"http://{host}:{port}"

    def start(self) -> threading.Thread:
        thread = threading.Thread(target=self.serve_forever, daemon=True)
        thread.start()
        return thread


class _DynamoServer(_JsonServer):
    def __init__(self, config: MockNvidiaStackConfig):
        super().__init__(_JsonHandler, auth_token=config.auth_token)
        self.models = list(config.dynamo_models)

    def handle_request(self, handler: _JsonHandler, method: str) -> None:
        if not handler._authorized():
            handler._send_json({"error": "unauthorized"}, status=401)
            return
        if method == "GET" and handler.path == "/v1/models":
            handler._send_json({"data": [{"id": model} for model in self.models]})
            return
        handler._send_json({"error": "not found"}, status=404)


class _NimServer(_JsonServer):
    def __init__(self, config: MockNvidiaStackConfig):
        super().__init__(_JsonHandler, auth_token=config.auth_token)
        self.models = list(config.nim_models)

    def handle_request(self, handler: _JsonHandler, method: str) -> None:
        if not handler._authorized():
            handler._send_json({"error": "unauthorized"}, status=401)
            return
        if method == "GET" and handler.path == "/v1/models":
            handler._send_json({"data": [{"id": model} for model in self.models]})
            return
        handler._send_json({"error": "not found"}, status=404)


class _AiqServer(_JsonServer):
    def __init__(self, config: MockNvidiaStackConfig):
        super().__init__(_JsonHandler, auth_token=config.auth_token)
        self.agent_types = list(config.aiq_agent_types)
        self.data_sources = list(config.aiq_data_sources)
        self.report = config.aiq_report
        self.cited_urls = list(config.aiq_cited_urls)
        self.jobs: dict[str, dict[str, Any]] = {}
        self._counter = 0

    def _job_state(self, job_id: str) -> dict[str, Any]:
        state = self.jobs.setdefault(
            job_id,
            {
                "poll_count": 0,
                "report": self.report,
                "sources": {
                    "found": len(self.cited_urls),
                    "cited": len(self.cited_urls),
                    "cited_urls": list(self.cited_urls),
                    "found_urls": list(self.cited_urls),
                },
                "tools": [{"name": "retriever", "status": "ok", "workflow": "deep_research"}],
            },
        )
        return state

    def handle_request(self, handler: _JsonHandler, method: str) -> None:
        if not handler._authorized():
            handler._send_json({"error": "unauthorized"}, status=401)
            return
        path = handler.path.split("?", 1)[0]
        if method == "GET" and path == "/health":
            handler._send_json({"status": "ok", "dask_available": True})
            return
        if method == "GET" and path == "/v1/jobs/async/agents":
            handler._send_json({"agents": [{"agent_type": name} for name in self.agent_types]})
            return
        if method == "GET" and path == "/v1/data_sources":
            handler._send_json([{"id": name} for name in self.data_sources])
            return
        if method == "POST" and path == "/v1/jobs/async/submit":
            self._counter += 1
            job_id = f"job-{self._counter}"
            payload = handler._read_json_body()
            state = self._job_state(job_id)
            state["input"] = payload.get("input")
            handler._send_json({"job_id": job_id, "status": "SUBMITTED"})
            return
        if method == "GET" and path.startswith("/v1/jobs/async/job/"):
            parts = [part for part in path.split("/") if part]
            if len(parts) >= 5:
                job_id = parts[4]
                state = self._job_state(job_id)
                if len(parts) == 5:
                    state["poll_count"] += 1
                    status = "RUNNING" if state["poll_count"] == 1 else "SUCCESS"
                    handler._send_json({"job_id": job_id, "status": status})
                    return
                if len(parts) == 6 and parts[5] == "report":
                    handler._send_json({"report": state["report"]})
                    return
                if len(parts) == 6 and parts[5] == "state":
                    handler._send_json({"artifacts": {"sources": state["sources"], "tools": state["tools"]}})
                    return
        handler._send_json({"error": "not found"}, status=404)


class _PrometheusServer(_JsonServer):
    def __init__(self, config: MockNvidiaStackConfig):
        super().__init__(_JsonHandler)
        self.values = dict(config.prometheus_values)

    def handle_request(self, handler: _JsonHandler, method: str) -> None:
        parsed = urlparse(handler.path)
        if method == "GET" and parsed.path == "/api/v1/query":
            query = unquote_plus(parse_qs(parsed.query).get("query", [""])[0])
            value = self.values.get(query)
            payload = {
                "status": "success",
                "data": {
                    "resultType": "vector",
                    "result": [] if value is None else [{"value": [0, str(value)]}],
                },
            }
            handler._send_json(payload)
            return
        handler._send_json({"error": "not found"}, status=404)


@dataclass
class MockNvidiaStack:
    dynamo: _DynamoServer
    nim: _NimServer
    aiq: _AiqServer
    prometheus: _PrometheusServer
    threads: list[threading.Thread]

    @property
    def dynamo_url(self) -> str:
        return self.dynamo.base_url

    @property
    def aiq_url(self) -> str:
        return self.aiq.base_url

    @property
    def nim_url(self) -> str:
        return self.nim.base_url

    @property
    def prometheus_url(self) -> str:
        return self.prometheus.base_url

    def close(self) -> None:
        for server in (self.dynamo, self.nim, self.aiq, self.prometheus):
            with contextlib.suppress(Exception):
                server.shutdown()
            with contextlib.suppress(Exception):
                server.server_close()
        for thread in self.threads:
            thread.join(timeout=2.0)


def start_mock_nvidia_stack(config: MockNvidiaStackConfig | None = None) -> MockNvidiaStack:
    resolved = config or MockNvidiaStackConfig()
    dynamo = _DynamoServer(resolved)
    nim = _NimServer(resolved)
    aiq = _AiqServer(resolved)
    prometheus = _PrometheusServer(resolved)
    threads = [dynamo.start(), nim.start(), aiq.start(), prometheus.start()]
    return MockNvidiaStack(dynamo=dynamo, nim=nim, aiq=aiq, prometheus=prometheus, threads=threads)
