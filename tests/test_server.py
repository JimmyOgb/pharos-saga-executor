"""
Unit tests for SagaServerHandler and web visualizer API.
"""

import io
import json
from unittest.mock import MagicMock
from scripts.saga_server import SagaServerHandler


class MockServerHandler(SagaServerHandler):
    """Subclass of SagaServerHandler to test HTTP request handling without opening real sockets."""

    def __init__(self, method: str, path: str, body: bytes = b""):
        self.rfile = io.BytesIO(body)
        self.wfile = io.BytesIO()
        self.command = method
        self.path = path
        self.headers = {"Content-Length": str(len(body))}
        self.requestline = f"{method} {path} HTTP/1.1"
        self.request_version = "HTTP/1.1"
        self._headers_buffer = []

    def send_response(self, code, message=None):
        self.response_code = code

    def send_header(self, keyword, value):
        self._headers_buffer.append((keyword, value))

    def end_headers(self):
        pass


def test_server_get_index():
    handler = MockServerHandler("GET", "/")
    handler.do_GET()
    assert handler.response_code == 200
    body = handler.wfile.getvalue().decode("utf-8")
    assert "Pharos Saga Executor" in body
    assert "Atlantic Testnet" in body


def test_server_get_api_status():
    handler = MockServerHandler("GET", "/api/status")
    handler.do_GET()
    assert handler.response_code == 200
    data = json.loads(handler.wfile.getvalue().decode("utf-8"))
    assert data["chain_id"] == 688689
    assert data["status"] == "ONLINE"
    assert data["simulation_sandbox"] is True


def test_server_post_api_run_happy_path():
    payload = json.dumps({"force_fail_step": None}).encode("utf-8")
    handler = MockServerHandler("POST", "/api/run", body=payload)
    handler.do_POST()
    assert handler.response_code == 200
    log = json.loads(handler.wfile.getvalue().decode("utf-8"))
    assert log["status"] == "COMPLETED"
    assert log["steps_succeeded"] == 3


def test_server_post_api_run_forced_failure():
    payload = json.dumps({"force_fail_step": 3}).encode("utf-8")
    handler = MockServerHandler("POST", "/api/run", body=payload)
    handler.do_POST()
    assert handler.response_code == 200
    log = json.loads(handler.wfile.getvalue().decode("utf-8"))
    assert log["status"] == "ROLLED_BACK"
    assert log["steps_compensated"] == 2


def test_server_get_tokens():
    handler = MockServerHandler("GET", "/api/tokens")
    handler.do_GET()
    assert handler.response_code == 200
    data = json.loads(handler.wfile.getvalue().decode("utf-8"))
    assert "tokens" in data
    assert "USDC" in data["tokens"]
    assert "WPHRS" in data["tokens"]
    assert data["tokens"]["USDC"]["decimals"] == 6



def test_server_get_sagas():
    handler = MockServerHandler("GET", "/api/sagas")
    handler.do_GET()
    assert handler.response_code == 200
    data = json.loads(handler.wfile.getvalue().decode("utf-8"))
    assert "saga_id" in data
    assert len(data["steps"]) == 3


def test_server_post_api_reset():
    handler = MockServerHandler("POST", "/api/reset")
    handler.do_POST()
    assert handler.response_code == 200
    data = json.loads(handler.wfile.getvalue().decode("utf-8"))
    assert data["status"] == "INITIALIZED"
    assert data["total_steps"] == 3
    assert data["steps_succeeded"] == 0
    assert len(data["steps"]) == 3
    assert data["steps"][0]["status"] == "PENDING"


def test_server_post_api_run_manual_recovery():
    payload = json.dumps({"force_fail_step": 3, "fail_compensation": True}).encode("utf-8")
    handler = MockServerHandler("POST", "/api/run", body=payload)
    handler.do_POST()
    assert handler.response_code == 200
    log = json.loads(handler.wfile.getvalue().decode("utf-8"))
    assert log["status"] == "MANUAL_RECOVERY_REQUIRED"


def test_server_post_api_run_invalid_step_validation():
    payload = json.dumps({"force_fail_step": 99}).encode("utf-8")
    handler = MockServerHandler("POST", "/api/run", body=payload)
    handler.do_POST()
    assert handler.response_code == 400
    data = json.loads(handler.wfile.getvalue().decode("utf-8"))
    assert "error" in data


def test_server_post_api_run_invalid_retries_validation():
    payload = json.dumps({"transient_retries": 100}).encode("utf-8")
    handler = MockServerHandler("POST", "/api/run", body=payload)
    handler.do_POST()
    assert handler.response_code == 400
    data = json.loads(handler.wfile.getvalue().decode("utf-8"))
    assert "error" in data


def test_server_post_api_run_invalid_json():
    handler = MockServerHandler("POST", "/api/run", body=b"invalid-json-body")
    handler.do_POST()
    assert handler.response_code == 400
    data = json.loads(handler.wfile.getvalue().decode("utf-8"))
    assert "error" in data

