"""Mock OpenAI-compatible endpoint for testing."""

import json
import socket
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread


class MockEndpointHandler(BaseHTTPRequestHandler):
    """Mock OpenAI-compatible endpoint."""

    def do_POST(self):
        """Handle POST requests."""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        request_data = json.loads(body) if body else {}

        if self.path == "/v1/chat/completions":
            self._handle_chat_completions(request_data)
        elif self.path == "/models":
            self._handle_models()
        else:
            self.send_error(404)

    def do_GET(self):
        """Handle GET requests."""
        if self.path == "/models":
            self._handle_models()
        else:
            self.send_error(404)

    def _handle_chat_completions(self, request_data):
        """Handle /chat/completions endpoint."""
        model = request_data.get("model", "test-model")
        stream = request_data.get("stream", False)
        tools = request_data.get("tools", [])
        response_format = request_data.get("response_format")

        if stream:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()

            # Send streamed response
            chunks = [
                {"choices": [{"delta": {"role": "assistant", "content": ""}}]},
                {"choices": [{"delta": {"content": "Hello"}}]},
                {"choices": [{"delta": {"content": " from"}}]},
                {"choices": [{"delta": {"content": " test"}}]},
                {"choices": [{"delta": {"content": " endpoint"}}]},
                {
                    "choices": [{"delta": {"content": ""}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                },
            ]

            for chunk in chunks:
                self.wfile.write(b"data: " + json.dumps(chunk).encode() + b"\n\n")
                time.sleep(0.01)

            self.wfile.write(b"data: [DONE]\n\n")
        else:
            # Handle tool calls
            if tools:
                response = {
                    "id": "chatcmpl-test",
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": model,
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "tool_calls": [
                                    {
                                        "id": "call_123",
                                        "type": "function",
                                        "function": {
                                            "name": "test_tool",
                                            "arguments": '{"name": "test", "value": 42}',
                                        },
                                    }
                                ],
                            },
                            "finish_reason": "tool_calls",
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                }
            # Handle JSON schema response format
            elif response_format:
                response = {
                    "id": "chatcmpl-test",
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": model,
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": '{"status": "active", "count": 42}',
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                }
            else:
                response = {
                    "id": "chatcmpl-test",
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": model,
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": "Hello from test endpoint"},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                }

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())

    def _handle_models(self):
        """Handle /models endpoint."""
        response = {
            "object": "list",
            "data": [{"id": "test-model", "object": "model", "created": int(time.time())}],
        }

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(response).encode())

    def log_message(self, format, *args):
        """Suppress logging."""
        pass


def find_free_port():
    """Find a free port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


def run_mock_endpoint(port=8765):
    """Run mock endpoint in a background thread."""
    server = HTTPServer(("127.0.0.1", port), MockEndpointHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.1)  # Give server time to start
    return server


if __name__ == "__main__":
    port = find_free_port()
    print(f"Starting mock endpoint on http://127.0.0.1:{port}")
    server = run_mock_endpoint(port)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.shutdown()
