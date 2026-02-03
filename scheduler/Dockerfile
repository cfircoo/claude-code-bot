FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/

WORKDIR /app

COPY scheduler/run.py .

RUN uv pip install --system httpx pyyaml

CMD ["python", "run.py"]
