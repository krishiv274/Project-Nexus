from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import hashlib


class BackendHandler(BaseHTTPRequestHandler):

    def send_json(self, data):
        body = json.dumps(data).encode("utf-8")

        etag = '"' + hashlib.sha256(body).hexdigest() + '"'

        if self.headers.get("If-None-Match") == etag:
            self.send_response(304)
            self.send_header("ETag", etag)
            self.send_header("Cache-Control", "max-age=60")
            self.end_headers()
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "max-age=60")
        self.send_header("ETag", etag)
        self.send_header("X-Backend", "B")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):

        if self.path == "/":
            self.send_json({
                "backend": "B",
                "status": "running"
            })

        elif self.path == "/api/status":
            self.send_json({
                "backend": "B",
                "status": "ok"
            })

        else:
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.send_header("X-Backend", "B")
            self.end_headers()
            self.wfile.write(
                json.dumps({
                    "error": "not found"
                }).encode("utf-8")
            )

    def log_message(self, format, *args):
        print(f"[Backend B] {self.address_string()} - {format % args}")


server = HTTPServer(("0.0.0.0", 3002), BackendHandler)

print("Backend B listening on 0.0.0.0:3002")

server.serve_forever()