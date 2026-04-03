#!/usr/bin/env bash
set -euo pipefail

echo "=== CDT Bias Detection System — Setup ==="
echo ""

echo "Checking Python version..."
python3 --version

echo ""
echo "Installing dependencies..."
pip install -r requirements.txt

echo ""
echo "Initializing database and seeding market data..."
python3 -c "from database.seed import run_seed; run_seed()"

echo ""
echo "============================================"
echo "Setup complete!"
echo ""
echo "Run the application with:"
echo "  streamlit run app.py"
echo ""
echo "Run tests with:"
echo "  pytest tests/ -v"
echo "============================================"
