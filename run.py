#!/usr/bin/env python3
"""
Launcher para o GDQ Rule Proposer.

Uso:
    python run.py                    # default: Athena real
    python run.py --port 8502        # porta customizada
    python run.py --debug            # log level DEBUG
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="GDQ Rule Proposer — Launcher",
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=8501,
        help="Porta do Streamlit (default: 8501)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Ativar modo debug (log level DEBUG)",
    )

    args = parser.parse_args()

    # Carregar .env
    env = os.environ.copy()
    env_file = Path(".env")
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                env.setdefault(key.strip(), value.strip())

    if args.debug:
        env["GDQ_LOG_LEVEL"] = "DEBUG"

    # Garantir AWS_PROFILE
    aws_profile = env.get("GDQ_AWS_PROFILE", env.get("AWS_PROFILE", ""))

    # Verificar SSO login
    if aws_profile:
        try:
            result = subprocess.run(
                ["aws", "sts", "get-caller-identity", "--profile", aws_profile],
                capture_output=True, timeout=10,
            )
            if result.returncode != 0:
                print(f"\n  [!] SSO nao esta ativo para o profile '{aws_profile}'.")
                print(f"  Execute: aws sso login --profile {aws_profile}\n")
                answer = input("  Deseja executar o login agora? (s/N): ").strip().lower()
                if answer in ("s", "sim", "y", "yes"):
                    subprocess.run(["aws", "sso", "login", "--profile", aws_profile])
        except FileNotFoundError:
            print("\n  [!] AWS CLI nao encontrado. Verifique a instalacao.\n")
        except subprocess.TimeoutExpired:
            print("\n  [!] Timeout ao verificar credenciais AWS.\n")

    # Banner
    print(f"\n{'='*50}")
    print(f"  GDQ Rule Proposer")
    print(f"  Profile:  {aws_profile or '(default/IAM role)'}")
    print(f"  Porta:    {args.port}")
    print(f"{'='*50}\n")

    # Streamlit command
    cmd = [
        sys.executable, "-m", "streamlit", "run", "app.py",
        "--server.port", str(args.port),
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
    ]

    try:
        proc = subprocess.run(cmd, env=env)
        sys.exit(proc.returncode)
    except KeyboardInterrupt:
        print("\nEncerrado.")
        sys.exit(0)


if __name__ == "__main__":
    main()
