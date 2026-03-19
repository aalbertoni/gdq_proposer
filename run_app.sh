#!/usr/bin/env bash
# GDQ Rule Proposer — Inicializacao rapida (Linux/macOS)
#
# Uso:
#   ./run_app.sh
#   ./run_app.sh --port 8502

set -e

echo ""
echo "  GDQ Rule Proposer"
echo "  =================="
echo ""

# Verificar Python
if ! command -v python3 &> /dev/null; then
    echo "  [ERRO] Python3 nao encontrado."
    echo ""
    echo "  Instale Python 3.10 ou superior:"
    echo "    Ubuntu/Debian: sudo apt install python3 python3-venv"
    echo "    macOS:         brew install python3"
    echo ""
    exit 1
fi

# Mudar para o diretorio do script
cd "$(dirname "$0")"

# Executar o launcher
python3 launcher.py "$@"
