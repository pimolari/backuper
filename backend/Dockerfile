FROM python:3.11-slim

WORKDIR /app

# Copy dependency definition
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code into backend directory to match structure
COPY . /app/backend

# Set pythonpath so that it can resolve "backend.*" imports
ENV PYTHONPATH=/app

# Expose port (Cloud Run sets PORT env variable, defaulting to 8080)
EXPOSE 8080

# Run uvicorn with settings that allow large file uploads:
#   --timeout-keep-alive 300    = keep connections alive during slow uploads
#   --limit-max-header-size 0   = no limit on header size (large multipart boundaries)
#CMD ["python", "-m", "uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "$PORT", "--timeout-keep-alive", "1300"]
#CMD ["sh", "-c", "python -m uvicorn backend.app:app --host 0.0.0.0 --port $PORT --timeout-keep-alive 240"]
#CMD ["sh", "-c", "gunicorn", "--bind", "0.0.0.0:$PORT", "--timeout", "240", "--workers", "2", "--threads", "4", "--limit-request-line", "0", "app:app"]
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8080", "--timeout-keep-alive", "240"]