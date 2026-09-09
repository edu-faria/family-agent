FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first for layer caching
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install .

# App source
COPY src ./src
COPY config.toml ./config.toml
RUN pip install --no-deps .

# SQLite lives on a mounted volume
VOLUME ["/data"]
ENV FAMILY_AGENT_DB_PATH=/data/family.db

# Long polling — no inbound ports to expose.
CMD ["python", "-m", "family_agent"]
