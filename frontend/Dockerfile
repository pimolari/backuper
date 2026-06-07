FROM python:3.11-slim

WORKDIR /app

# Copy dependency definition
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copy frontend source code
COPY . .

# Expose port (Cloud Run sets PORT env variable, defaulting to 8080)
EXPOSE 8080

# Run gunicorn with settings that allow large file uploads:
#   --timeout 1800  = 30 min per request (large file transfers)
#   --workers 2     = handle concurrent requests while one is uploading
#   --threads 4     = gthread concurrency within each worker
#   --limit-request-line 0  = no limit on request header line length
CMD ["sh", "-c", "gunicorn", "--bind", "0.0.0.0:$PORT", "--timeout", "240", "--workers", "2", "--threads", "4", "--limit-request-line", "0", "app:app"]
