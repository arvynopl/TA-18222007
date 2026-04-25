#!/usr/bin/env bash
set -euo pipefail

echo "=== CDT Bias Detection System — Setup ==="
echo ""

echo "Checking Python version..."
python3 --version
python3 - <<'PYCHECK'
import sys
required = (3, 10)
if sys.version_info < required:
    sys.stderr.write(
        f"ERROR: Python {required[0]}.{required[1]}+ diperlukan, tetapi {sys.version.split()[0]} terdeteksi.\n"
        "       Codebase CDT menggunakan sintaks PEP 604 ('X | None') saat runtime.\n"
        "       Pasang Python yang lebih baru (mis. via pyenv) lalu jalankan ulang setup.sh.\n"
    )
    sys.exit(1)
PYCHECK

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
