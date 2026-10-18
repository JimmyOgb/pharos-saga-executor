#!/usr/bin/env python3
"""
Lightweight Zero-Dependency HTTP Server & API for Pharos Saga Executor Web Visualizer.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from saga.client import PharosClient
from saga.coordinator import SagaCoordinator
from saga.models import RetryConfig
from saga.steps import ApproveStep, DepositStep, SwapStep

WEB_DIR = REPO_ROOT / "web"


class SagaServerHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler providing REST endpoints and static file serving."""

    def _set_headers(self, content_type: str = "application/json", status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_OPTIONS(self) -> None:
        self._set_headers(status=HTTPStatus.NO_CONTENT)

    def do_GET(self) -> None:
        parsed_url = urlparse(self.path)
        path = parsed_url.path

        if path in ("/", "/index.html"):
            index_file = WEB_DIR / "index.html"
            if index_file.exists():
                self._set_headers("text/html; charset=utf-8")
                with open(index_file, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_error(404, "Web dashboard file not found")
            return

        if path == "/api/status":
            client = PharosClient()
            try:
                data = {
                    "network": "Pharos Atlantic Testnet",
                    "chain_id": 688689,
                    "rpc_url": client.rpc_url,
                    "mcp_url": client.mcp_url,
                    "status": "ONLINE",
                    "simulation_sandbox": True,
                }
                self._set_headers("application/json")
                self.wfile.write(json.dumps(data).encode("utf-8"))
            except Exception as e:
                self._set_headers("application/json", status=500)
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            return

        # Serve static assets from web/
        safe_path = (WEB_DIR / path.lstrip("/")).resolve()
        if safe_path.is_file() and str(safe_path).startswith(str(WEB_DIR)):
            mime_type, _ = mimetypes.guess_type(str(safe_path))
            self._set_headers(mime_type or "application/octet-stream")
            with open(safe_path, "rb") as f:
                self.wfile.write(f.read())
            return

        self.send_error(404, "Endpoint not found")

    def do_POST(self) -> None:
        parsed_url = urlparse(self.path)
        if parsed_url.path == "/api/run":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                payload = {}

            force_fail_step = payload.get("force_fail_step")
            fail_compensation = bool(payload.get("fail_compensation", False))
            transient_retries = int(payload.get("transient_retries", 0))
            saga_id = payload.get("saga_id", "web_interactive_run")

            steps = [
                ApproveStep(
                    force_fail=(force_fail_step == 1),
                    force_fail_compensation=fail_compensation,
                    transient_fail_count=transient_retries if force_fail_step != 1 else 0,
                ),
                SwapStep(
                    force_fail=(force_fail_step == 2),
                    force_fail_compensation=fail_compensation,
                    transient_fail_count=transient_retries if force_fail_step != 2 else 0,
                ),
                DepositStep(
                    force_fail=(force_fail_step == 3),
                    force_fail_compensation=fail_compensation,
                    transient_fail_count=transient_retries if force_fail_step != 3 else 0,
                ),
            ]

            retry_config = RetryConfig(
                max_retries=3,
                base_delay_seconds=0.1,
                backoff_factor=1.5,
                max_delay_seconds=1.0,
                jitter=False,
            )

            coordinator = SagaCoordinator(
                saga_id=saga_id,
                title="Pharos Web Dashboard Execution",
                steps=steps,
                retry_config=retry_config,
            )

            log = coordinator.execute()

            self._set_headers("application/json")
            self.wfile.write(log.to_json().encode("utf-8"))
            return

        self.send_error(404, "Endpoint not found")

    def log_message(self, format: str, *args) -> None:
        """Suppress default HTTP request clutter during normal runs."""
        pass


def run_server(port: int = 8080, host: str = "127.0.0.1") -> None:
    server_address = (host, port)
    httpd = HTTPServer(server_address, SagaServerHandler)
    print(f"[PHAROS SAGA SERVER] Serving DAG Visualizer at http://{host}:{port}/")
    print(f"[PHAROS SAGA SERVER] Press Ctrl+C to terminate.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[PHAROS SAGA SERVER] Shutting down.")
        httpd.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Pharos Saga Executor Visualizer Server")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on (default: 8080)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host interface (default: 127.0.0.1)")
    args = parser.parse_args()
    run_server(port=args.port, host=args.host)


if __name__ == "__main__":
    main()
