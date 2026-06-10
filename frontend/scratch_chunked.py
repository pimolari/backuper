import requests
import json

# Send a chunked multipart request to the backend
url = "http://127.0.0.1:8000/api/upload" # or whatever the backend URL is

def generate_chunked():
    yield b"--boundary123\r\n"
    yield b"Content-Disposition: form-data; name=\"file\"; filename=\"test.txt\"\r\n"
    yield b"Content-Type: text/plain\r\n\r\n"
    yield b"a" * 1000000
    yield b"\r\n--boundary123--\r\n"

headers = {
    "Content-Type": "multipart/form-data; boundary=boundary123"
}

try:
    response = requests.post(url, data=generate_chunked(), headers=headers)
    print(response.status_code, response.text)
except Exception as e:
    print("Error:", e)
