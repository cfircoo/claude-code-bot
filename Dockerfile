FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-editable

COPY src/ src/
COPY config.example.yaml /app/config.yaml
COPY .claude/ /app/.claude/


VOLUME ["/app/data"]

EXPOSE 8000

# Set headless environment to reduce SDK noise
ENV TERM=dumb
ENV CI=true

CMD ["uv", "run", "python", "-m", "claude_code_bot"]
