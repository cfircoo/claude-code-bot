FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir .

COPY config.example.yaml /app/config.yaml

VOLUME ["/app/data"]

EXPOSE 8000

CMD ["python", "-m", "claude_code_bot"]
