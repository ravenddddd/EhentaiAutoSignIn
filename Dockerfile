FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    EHENTAI_DATA_DIR=/data

WORKDIR /app

# tzdata is required for TZ to affect the scheduler inside the container.
RUN apt-get update \
    && apt-get install --no-install-recommends -y tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md main.py ./
COPY ehentai/ ./ehentai/
RUN pip install --no-cache-dir . \
    && mkdir /data \
    && chown 1000:1000 /data

USER 1000:1000

VOLUME ["/data"]
EXPOSE 18391

ENTRYPOINT ["python", "/app/main.py"]
