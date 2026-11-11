#!/bin/bash
set -e

echo "=== Starting GRMV xLUCH store container ==="

PORT="${PORT:-7860}"

if [ -n "$SPACE_HOST" ]; then
    if [ -z "$APP_BASE_URL" ]; then
        export APP_BASE_URL="https://$SPACE_HOST"
    fi
    if [ -z "$API_BASE_URL" ]; then
        export API_BASE_URL="https://$SPACE_HOST"
    fi
fi

export PORT
export GRMV_SERVE_FRONTEND="1"
export DATABASE_URL="${DATABASE_URL:-sqlite+aiosqlite:////app/data/combined-live.sqlite3}"
export UPLOAD_DIR="${UPLOAD_DIR:-/app/data/uploads}"
export DEV_AUTH_ENABLED="false"

echo "Public URL: ${APP_BASE_URL:-not set yet}"
echo "Listening port: $PORT"

mkdir -p "$UPLOAD_DIR/products" "$UPLOAD_DIR/receipts"

# Function to gracefully stop all processes on exit
cleanup() {
    echo "Shutting down services..."
    if [ -n "$BOT_PID" ]; then
        kill -TERM "$BOT_PID" 2>/dev/null || true
    fi
    if [ -n "$API_PID" ]; then
        kill -TERM "$API_PID" 2>/dev/null || true
    fi
    wait
    exit 0
}

trap cleanup SIGTERM SIGINT

# Start API server in background
echo "Starting FastAPI server..."
python -m uvicorn apps.api.main:app --host 0.0.0.0 --port "$PORT" &
API_PID=$!

# Wait for API to respond
echo "Waiting for API to initialize..."
for i in $(seq 1 30); do
    if curl -s "http://127.0.0.1:$PORT/api/v1/health" | grep -q '"status":"ok"'; then
        echo "FastAPI is healthy and serving requests!"
        break
    fi
    sleep 1
done

# Start Telegram Bot if BOT_TOKEN is present
if [ -n "$BOT_TOKEN" ]; then
    echo "Starting Telegram Bot..."
    python -m apps.bot.main &
    BOT_PID=$!
else
    echo "WARNING: BOT_TOKEN is not configured! Telegram bot will not start."
fi

# Wait for child processes
if [ -n "$BOT_PID" ]; then
    wait -n "$API_PID" "$BOT_PID"
else
    wait "$API_PID"
fi
