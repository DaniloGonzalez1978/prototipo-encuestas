#!/bin/sh

# Setup virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
  echo "Creating virtual environment in ./.venv..."
  python -m venv .venv
  echo "Virtual environment created."
fi

# Activate virtual environment
source .venv/bin/activate

# Force reinstall dependencies, ignoring any cache
echo "Force reinstalling dependencies from requirements.txt..."
pip install --no-cache-dir --force-reinstall -r requirements.txt

# Find the tessdata directory
TESSDATA_PATH=$(find /nix/store -maxdepth 1 -name "*tessdata-best*" -type d | head -n 1)

if [ -n "$TESSDATA_PATH" ]; then
  export TESSDATA_PREFIX="$TESSDATA_PATH/share/tessdata"
  echo "Found tessdata at: $TESSDATA_PREFIX"
else
  echo "Warning: tessdata_best package not found. Tesseract might fail."
fi

# Run the Flask application
echo "Starting Flask server..."
python -u -m flask --app main run --debug -p ${PORT:-5000}
