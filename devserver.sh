#!/bin/bash

set -e

echo "Activating virtual environment..."
source .venv/bin/activate

export FLASK_APP=main.py

echo "Starting Flask development server..."
flask run --host 0.0.0.0 --port $PORT
