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

    # Forward headers (skip hop-by-hop and content-type for multipart)
    headers = {}
    for key, value in request.headers.items():
        if key.lower() not in ['host', 'content-length', 'content-type', 'transfer-encoding']:
            headers[key] = value

    # Include content-type if not multipart (requests library handles multipart boundary)
    if request.content_type and "multipart/form-data" not in request.content_type:
        headers["Content-Type"] = request.content_type

    # Forward query params
    params = request.args

    try:
        if request.files:
            # -----------------------------------------------------------
            # Stream file uploads through the proxy without buffering the
            # entire file in memory.  We use requests-toolbelt's
            # MultipartEncoder which reads the file in 8 KB chunks.
            # -----------------------------------------------------------
            fields = {}

            # Carry form fields alongside files
            for field_name, field_value in request.form.items():
                fields[field_name] = field_value

            # Wrap each uploaded file's stream (SpooledTemporaryFile) —
            # the stream is already disk-backed for large files thanks to
            # Werkzeug, so we just pass it through without .read().
            for name, file_storage in request.files.items():
                fields[name] = (
                    file_storage.filename,
                    file_storage.stream,
                    file_storage.content_type or "application/octet-stream",
                )

            encoder = MultipartEncoder(fields=fields)
            headers["Content-Type"] = encoder.content_type

            response = requests.request(
                method=request.method,
                url=url,
                headers=headers,
                params=params,
                data=encoder,
                timeout=UPLOAD_TIMEOUT,
                stream=True,
            )
        else:
            # Standard request (JSON, raw body, or empty)
            response = requests.request(
                method=request.method,
                url=url,
                headers=headers,
                params=params,
                data=request.get_data(),
                timeout=DEFAULT_TIMEOUT,
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

