#!/bin/bash

set -e

echo "Activating virtual environment..."
source .venv/bin/activate

# Load environment variables from .env file
if [ -f .env ]; then
    echo "Loading environment variables from .env..."
    source .env
fi

export FLASK_APP=main.py
export PORT=5000

echo "Starting Flask development server..."
flask run --host 0.0.0.0 --port $PORT
