FROM python:3.12-slim

# Keep image resolution tied to the repository's uv lock rather than an
# unconstrained pip install.  The uv image is multi-architecture and is
# therefore also usable by the ARM64 release builder.
COPY --from=ghcr.io/astral-sh/uv:0.7.15 /uv /uvx /bin/

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock requirements.txt ./
RUN uv export --locked --format requirements-txt --output-file /tmp/requirements.lock \
    && tail -n +3 /tmp/requirements.lock > /tmp/requirements.generated \
    && tail -n +3 requirements.txt > /tmp/requirements.current \
    && cmp -s /tmp/requirements.generated /tmp/requirements.current \
    && pip install --no-cache-dir -r /tmp/requirements.lock \
    && rm -f /tmp/requirements.lock /tmp/requirements.generated /tmp/requirements.current

COPY . .

RUN chmod +x /app/docker-entrypoint.sh

ENTRYPOINT ["/app/docker-entrypoint.sh"]

# Default command = API server; override to "arq app.tasks.worker.WorkerSettings" for worker
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
