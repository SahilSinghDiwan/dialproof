#!/bin/bash
set -e

cd "$(dirname "$0")"

# Start mock endpoint in background
echo "Starting mock endpoint..."
python3 tests/test_endpoint.py &
ENDPOINT_PID=$!

# Give it time to start
sleep 1

# Get the port from the endpoint (it runs on port 8765 by default)
PORT=8765
ENDPOINT_URL="http://127.0.0.1:$PORT/v1"

echo "Running dialproof against $ENDPOINT_URL..."

# Run dialproof
python3 -m dialproof.cli run \
    --endpoint "$ENDPOINT_URL" \
    --model test-model \
    --allow "127.0.0.1:$PORT" \
    --out "sample_runs/2026-09-19-mock-endpoint"

# Kill the endpoint
kill $ENDPOINT_PID 2>/dev/null || true

echo "✓ Sample report generated in sample_runs/2026-09-19-mock-endpoint/"
ls -la sample_runs/2026-09-19-mock-endpoint/
