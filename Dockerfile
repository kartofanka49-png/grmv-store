FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 user

ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONPATH=/app

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=1000:1000 apps /app/apps
COPY --chown=1000:1000 data /app/data
COPY --chown=1000:1000 start.sh /app/start.sh

RUN chmod +x /app/start.sh && \
    chmod -R 777 /app/data

USER 1000

EXPOSE 7860

CMD ["/app/start.sh"]
