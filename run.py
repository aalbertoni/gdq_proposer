#!/usr/bin/env python3
"""
Launcher profissional para o GDQ Rule Proposer.

Uso:
    python run.py                    # default: local com Athena real
    python run.py --env dev          # dev com Athena real (AWS_PROFILE do .env.dev)
    python run.py --env prod         # prod com IAM role
    python run.py --mock             # DuckDB mock (testes offline)
    python run.py --env dev --port 8502

Cada ambiente carrega seu .env.{env} automaticamente.
O AWS_PROFILE e configurado antes do Streamlit subir.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path


def load_env_file(env_name: str) -> dict[str, str]:
    """Carrega variaveis de um .env.{name} file."""
    env_file = Path(f".env.{env_name}")
    env_vars = {}
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                env_vars[key.strip()] = value.strip()
    return env_vars


def main():
    parser = argparse.ArgumentParser(
        description="GDQ Rule Proposer — Launcher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ambientes:
  local   Athena real via AWS CLI profile (default)
  dev     Athena real via AWS CLI profile (configs de dev)
  prod    Athena real via IAM role

Flags:
  --mock  Usa DuckDB local em vez de Athena (testes offline)
        """,
    )
    parser.add_argument(
        "--env", "-e",
        choices=["local", "dev", "prod"],
        default="local",
        help="Ambiente de execucao (default: local)",
    )
    parser.add_argument(
        "--mock", "-m",
        action="store_true",
        help="Usar DuckDB mock em vez de Athena real (testes offline)",
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

    # Carregar variaveis do .env.{env}
    env_vars = load_env_file(args.env)

    # Montar environment
    env = os.environ.copy()
    env["GDQ_ENV"] = args.env

    # Aplicar vars do .env file (sem sobrescrever vars ja setadas)
    for key, value in env_vars.items():
        if key not in env:
            env[key] = value

    # Modo Athena: real por default, mock apenas com --mock
    if args.mock:
        env["GDQ_ATHENA_MODE"] = "mock"
    else:
        env.setdefault("GDQ_ATHENA_MODE", "real")

    # Garantir AWS_PROFILE se definido no .env
    aws_profile = env_vars.get("GDQ_AWS_PROFILE", "")
    if aws_profile and "AWS_PROFILE" not in env:
        env["AWS_PROFILE"] = aws_profile

    if args.debug:
        env["GDQ_LOG_LEVEL"] = "DEBUG"

    # Verificar SSO login (apenas em modo real com profile)
    if not args.mock and profile and profile != "(IAM role)":
        try:
            result = subprocess.run(
                ["aws", "sts", "get-caller-identity", "--profile", profile],
                capture_output=True, timeout=10,
            )
            if result.returncode != 0:
                print(f"\n  [!] SSO nao esta ativo para o profile '{profile}'.")
                print(f"  Execute: aws sso login --profile {profile}\n")
                answer = input("  Deseja executar o login agora? (s/N): ").strip().lower()
                if answer in ("s", "sim", "y", "yes"):
                    subprocess.run(["aws", "sso", "login", "--profile", profile])
                    # Re-check
                    recheck = subprocess.run(
                        ["aws", "sts", "get-caller-identity", "--profile", profile],
                        capture_output=True, timeout=10,
                    )
                    if recheck.returncode != 0:
                        print("\n  [!] Login falhou. Iniciando em modo mock.\n")
                        env["GDQ_ATHENA_MODE"] = "mock"
                        args.mock = True
                else:
                    print("\n  [!] Continuando sem SSO. A conexao pode falhar.\n")
        except FileNotFoundError:
            print("\n  [!] AWS CLI nao encontrado. Verifique a instalacao.\n")
        except subprocess.TimeoutExpired:
            print("\n  [!] Timeout ao verificar credenciais AWS.\n")

    # Banner
    mode = "DuckDB Mock" if args.mock else "Athena Real"
    profile = env.get("AWS_PROFILE", env.get("GDQ_AWS_PROFILE", "(IAM role)"))
    print(f"\n{'='*50}")
    print(f"  GDQ Rule Proposer")
    print(f"  Ambiente: {args.env}")
    print(f"  Modo:     {mode}")
    print(f"  Profile:  {profile}")
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
