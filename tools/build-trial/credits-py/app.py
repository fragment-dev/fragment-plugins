"""A small text-generation API. Every call is free today."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json

USERS = {"u1": {"email": "ana@example.com"}, "u2": {"email": "bo@example.com"}}


def generate(user_id: str, prompt: str) -> str:
    return f"echo: {prompt}"


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        out = generate(body["user_id"], body["prompt"])
        self.send_response(200); self.end_headers(); self.wfile.write(json.dumps({"text": out}).encode())


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", 8000), Handler).serve_forever()
