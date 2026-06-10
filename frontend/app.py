import os
import requests
from flask import Flask, render_template, request, Response, stream_with_context


app = Flask(__name__)

# Allow uploads up to 5 GB through the Flask proxy
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024 * 1024  # 5 GB

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

# Timeouts: (connect_timeout, read_timeout) in seconds
UPLOAD_TIMEOUT = (30, 1800)   # 30 min read timeout for large uploads
DEFAULT_TIMEOUT = (10, 300)   # 5 min read timeout for regular requests


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/login")
def login():
    return render_template("login.html")


# Reverse Proxy for all API calls to FastAPI backend
@app.route("/api/<path:path>", methods=["GET", "POST", "PUT", "DELETE"])
def api_proxy(path):
    url = f"{BACKEND_URL}/api/{path}"
    print(f"[proxy] Forwarding {request.method} -> {url}")

    # Forward headers (skip hop-by-hop).
    # content-length is intentionally excluded here: the requests library
    # sets it automatically from the body object's __len__. Forwarding it
    # manually alongside a streamed body would produce a duplicate
    # Content-Length / Transfer-Encoding: chunked conflict that causes
    # HTTP 400 errors on the backend (uvicorn enforces RFC 7230).
    headers = {}
    for key, value in request.headers.items():
        if key.lower() not in ['host', 'transfer-encoding', 'content-length']:
            headers[key] = value

    # Forward query params
    params = request.args

    # Wrap the raw WSGI input stream with __len__ so the requests library
    # can report Content-Length instead of falling back to chunked encoding.
    # (The original StreamWrapper used a .len *attribute* which requests
    # ignores — it calls len() which requires __len__.)
    class SizedStream:
        """File-like wrapper that exposes __len__ for the requests library."""
        def __init__(self, stream, length: int):
            self._stream = stream
            self._length = length

        def __len__(self) -> int:
            return self._length

        def read(self, size: int = -1) -> bytes:
            return self._stream.read(size)

    try:
        content_length = request.headers.get('Content-Length')

        # -----------------------------------------------------------
        # Stream the raw request body directly to the backend without
        # triggering Werkzeug's form parser (avoids buffering large
        # files). SizedStream lets requests set Content-Length so the
        # backend receives a well-formed request.
        # -----------------------------------------------------------
        if content_length and int(content_length) > 0:
            data = SizedStream(request.stream, int(content_length))
        else:
            data = request.get_data()

        # Apply a long timeout only for upload routes; use a shorter
        # default for fast reads like browse/profile/tree.
        is_upload = request.method == "POST" and "upload" in path
        timeout = UPLOAD_TIMEOUT if is_upload else DEFAULT_TIMEOUT

        response = requests.request(
            method=request.method,
            url=url,
            headers=headers,
            params=params,
            data=data,
            timeout=timeout,
            stream=True,
        )

        # Exclude hop-by-hop headers that conflict with Flask's response
        excluded_headers = {
            'content-encoding', 'content-length',
            'transfer-encoding', 'connection',
        }
        resp_headers = {
            name: value
            for name, value in response.headers.items()
            if name.lower() not in excluded_headers
        }

        # Stream large responses (e.g. file downloads) back to the client
        # in 64 KB chunks instead of buffering the full body in memory.
        def generate():
            for chunk in response.iter_content(chunk_size=65536):
                yield chunk

        return Response(
            stream_with_context(generate()),
            status=response.status_code,
            headers=resp_headers,
        )
    except requests.exceptions.Timeout:
        print(f"[proxy] Timeout forwarding to {url}")
        return Response("Proxy timeout: the backend took too long to respond.", 504)
    except Exception as e:
        print(f"[proxy] Error forwarding to {url}: {e}")
        return Response(f"Proxy communication error: {str(e)}", 502)


if __name__ == "__main__":
    app.run(port=5000, debug=True)

