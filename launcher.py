"""
Ponto unico de entrada para o GDQ Rule Proposer.

Gerencia automaticamente:
1. Criacao/ativacao do ambiente virtual (.venv)
2. Instalacao de dependencias
3. Verificacao de ambiente (preflight checks)
4. Inicializacao do app Streamlit

Uso:
    python launcher.py                 # padrao
    python launcher.py --port 8502     # porta customizada
    python launcher.py --skip-checks   # pular verificacao
    python launcher.py --check-only    # so verificar, nao subir o app
"""

import argparse
import os
import platform
import subprocess
import sys
import webbrowser
from pathlib import Path
from threading import Timer

# Diretorio do projeto (onde este script esta)
PROJECT_DIR = Path(__file__).resolve().parent
VENV_DIR = PROJECT_DIR / ".venv"
REQUIREMENTS = PROJECT_DIR / "requirements.txt"


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def _print_header(text: str) -> None:
    print(f"\n  >> {text}")


def _print_ok(text: str) -> None:
    print(f"     [OK] {text}")


def _print_warn(text: str) -> None:
    print(f"     [!!] {text}")


def _print_error(text: str) -> None:
    print(f"     [ERRO] {text}")


def _get_venv_python() -> Path:
    """Retorna o caminho do Python dentro do .venv."""
    if sys.platform == "win32":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def _get_venv_pip() -> Path:
    """Retorna o caminho do pip dentro do .venv."""
    if sys.platform == "win32":
        return VENV_DIR / "Scripts" / "pip.exe"
    return VENV_DIR / "bin" / "pip"


def _is_running_in_venv() -> bool:
    """Verifica se estamos rodando dentro do .venv do projeto."""
    venv = os.environ.get("VIRTUAL_ENV", "")
    return venv and Path(venv).resolve() == VENV_DIR.resolve()


# ---------------------------------------------------------------------------
# Etapas do launcher
# ---------------------------------------------------------------------------

def _load_env_file() -> dict[str, str]:
    """Carrega variaveis do .env e retorna dict. Aplica no os.environ."""
    env_file = PROJECT_DIR / ".env"
    loaded = {}
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                key, value = key.strip(), value.strip()
                loaded[key] = value
                os.environ.setdefault(key, value)

    # Garantir AWS_PROFILE
    aws_profile = loaded.get("GDQ_AWS_PROFILE") or os.environ.get("GDQ_AWS_PROFILE", "")
    if aws_profile:
        os.environ.setdefault("AWS_PROFILE", aws_profile)

    return loaded


def ensure_venv() -> bool:
    """Cria o ambiente virtual se nao existir. Retorna True se OK."""
    venv_python = _get_venv_python()

    if venv_python.exists():
        _print_ok(f"Ambiente virtual encontrado em .venv/")
        return True

    _print_header("Criando ambiente virtual (.venv)...")
    print("     Isso e necessario apenas na primeira vez.\n")

    try:
        subprocess.run(
            [sys.executable, "-m", "venv", str(VENV_DIR)],
            check=True,
            cwd=str(PROJECT_DIR),
        )
        _print_ok("Ambiente virtual criado com sucesso.")
        return True
    except subprocess.CalledProcessError as e:
        _print_error(f"Falha ao criar ambiente virtual: {e}")
        print("     Tente manualmente: python -m venv .venv")
        return False


def ensure_dependencies(force_update: bool = False) -> bool:
    """Instala dependencias se necessario. Retorna True se OK.

    Args:
        force_update: Se True, reinstala mesmo se ja instaladas (--update).
    """
    venv_python = _get_venv_python()
    venv_pip = _get_venv_pip()

    if not venv_python.exists():
        _print_error("Ambiente virtual nao encontrado.")
        return False

    if not force_update:
        # Verificar se streamlit esta instalado (proxy para deps completas)
        result = subprocess.run(
            [str(venv_python), "-c", "import streamlit"],
            capture_output=True,
        )

        if result.returncode == 0:
            _print_ok("Dependencias ja instaladas.")
            return True

    action = "Atualizando" if force_update else "Instalando"
    _print_header(f"{action} dependencias...")
    if not force_update:
        print("     Isso pode levar alguns minutos na primeira vez.\n")

    try:
        cmd = [str(venv_pip), "install", "-r", str(REQUIREMENTS)]
        if force_update:
            cmd.insert(2, "--upgrade")
        subprocess.run(cmd, check=True, cwd=str(PROJECT_DIR))
        _print_ok(f"Dependencias {'atualizadas' if force_update else 'instaladas'} com sucesso.")
        return True
    except subprocess.CalledProcessError as e:
        _print_error(f"Falha ao instalar dependencias: {e}")
        print("     Tente manualmente:")
        print(f"     {venv_pip} install -r requirements.txt")
        return False


def ensure_dotenv() -> bool:
    """Verifica se .env existe. Oferece wizard se nao existir."""
    env_file = PROJECT_DIR / ".env"
    env_example = PROJECT_DIR / ".env.example"
    setup_script = PROJECT_DIR / "setup_local.py"

    if env_file.exists():
        _print_ok("Arquivo .env encontrado.")
        return True

    _print_warn("Arquivo .env nao encontrado.")
    print()
    print("     O arquivo .env contem configuracoes obrigatorias como")
    print("     o profile AWS e o bucket S3 para o Athena.")
    print()

    if setup_script.exists():
        print("     Opcoes:")
        print("     1. Executar o wizard guiado (recomendado)")
        print("     2. Copiar .env.example e editar manualmente")
        print("     3. Cancelar")
        print()
        choice = input("     Escolha (1/2/3): ").strip()

        if choice == "1":
            venv_python = _get_venv_python()
            python = str(venv_python) if venv_python.exists() else sys.executable
            subprocess.run([python, str(setup_script)], cwd=str(PROJECT_DIR))
            return env_file.exists()
        elif choice == "2":
            if env_example.exists():
                import shutil
                shutil.copy2(str(env_example), str(env_file))
                print(f"\n     Arquivo .env criado a partir de .env.example.")
                print(f"     Edite o arquivo .env e preencha os valores.")
                print(f"     Depois, execute novamente: python launcher.py\n")
            else:
                print("     .env.example nao encontrado.")
            return False
        else:
            return False
    elif env_example.exists():
        print("     Copie .env.example para .env e preencha os valores:")
        if sys.platform == "win32":
            print("     copy .env.example .env")
        else:
            print("     cp .env.example .env")
        return False
    else:
        print("     Crie o arquivo .env com as variaveis de configuracao.")
        print("     Consulte: docs/INSTALL_TROUBLESHOOTING.md")
        return False


def run_preflight(port: int = 8501) -> str:
    """Executa checagens de ambiente.

    Returns:
        "ok" — nenhum erro
        "blocking" — erros bloqueantes (SSL, credenciais, S3, .env, deps)
        "warn" — apenas erros nao-bloqueantes ou warnings
    """
    venv_python = _get_venv_python()

    # Rodar preflight no contexto do venv para checar deps corretamente
    # Exit codes: 0 = ok, 1 = non-blocking errors only, 2 = blocking errors
    result = subprocess.run(
        [str(venv_python), "-c", (
            "import sys; sys.path.insert(0, '.'); "
            "from preflight_check import run_all_checks, get_blocking_errors, get_non_blocking_errors, print_results; "
            f"r = run_all_checks(port={port}); print_results(r); "
            "blocking = get_blocking_errors(r); "
            "non_blocking = get_non_blocking_errors(r); "
            "sys.exit(2 if blocking else (1 if non_blocking else 0))"
        )],
        cwd=str(PROJECT_DIR),
    )

    if result.returncode == 2:
        return "blocking"
    elif result.returncode == 1:
        return "warn"
    return "ok"


def run_app(port: int = 8501, debug: bool = False) -> None:
    """Inicia o app Streamlit."""
    venv_python = _get_venv_python()

    # .env ja foi carregado em os.environ por _load_env_file() no main()
    env = os.environ.copy()

    aws_profile = env.get("GDQ_AWS_PROFILE", "")

    if debug:
        env["GDQ_LOG_LEVEL"] = "DEBUG"

    # Banner
    print(f"\n{'=' * 54}")
    print(f"  GDQ Rule Proposer")
    print(f"  Profile:  {aws_profile or '(default/IAM role)'}")
    print(f"  Porta:    {port}")
    print(f"  URL:      http://localhost:{port}")
    print(f"{'=' * 54}\n")

    # Abrir navegador apos 3 segundos
    def _open_browser():
        webbrowser.open(f"http://localhost:{port}")

    Timer(3.0, _open_browser).start()

    # Streamlit command
    cmd = [
        str(venv_python), "-m", "streamlit", "run", "app.py",
        "--server.port", str(port),
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
    ]

    try:
        proc = subprocess.run(cmd, env=env, cwd=str(PROJECT_DIR))
        sys.exit(proc.returncode)
    except KeyboardInterrupt:
        print("\n  App encerrado.")
        sys.exit(0)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="GDQ Rule Proposer — Launcher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemplos:\n"
            "  python launcher.py               # subir o app\n"
            "  python launcher.py --port 8502    # porta customizada\n"
            "  python launcher.py --check-only   # so verificar ambiente\n"
            "  python launcher.py --update       # atualizar dependencias\n"
        ),
    )
    parser.add_argument("--port", "-p", type=int, default=8501, help="Porta (default: 8501)")
    parser.add_argument("--debug", action="store_true", help="Log level DEBUG")
    parser.add_argument("--skip-checks", action="store_true", help="Pular verificacao de ambiente")
    parser.add_argument("--check-only", action="store_true", help="Apenas verificar, nao subir o app")
    parser.add_argument("--update", action="store_true", help="Atualizar dependencias (pip install -r requirements.txt)")

    args = parser.parse_args()

    print(f"\n  GDQ Rule Proposer — Setup automatico")
    print(f"  {'=' * 40}")

    # Etapa 1: Ambiente virtual
    _print_header("Verificando ambiente virtual...")
    if not ensure_venv():
        sys.exit(1)

    # Etapa 2: Dependencias (force reinstall se --update)
    if args.update:
        _print_header("Atualizando dependencias...")
    else:
        _print_header("Verificando dependencias...")
    if not ensure_dependencies(force_update=args.update):
        sys.exit(1)

    # Etapa 3: Arquivo .env
    _print_header("Verificando configuracao (.env)...")
    if not ensure_dotenv():
        sys.exit(1)

    # Carregar .env no ambiente (proxy, AWS profile, etc.)
    # Isso garante que o preflight e o app herdem as variaveis.
    _load_env_file()

    # Etapa 4: Preflight checks
    if not args.skip_checks:
        _print_header("Executando verificacao de ambiente...")
        preflight_result = run_preflight(port=args.port)

        if args.check_only:
            sys.exit(0 if preflight_result == "ok" else 1)

        if preflight_result == "blocking":
            print()
            _print_error(
                "Erros bloqueantes detectados (credenciais, SSL, S3 ou configuracao)."
            )
            print("     O app nao pode funcionar corretamente com esses erros.")
            print("     Corrija os problemas acima e tente novamente.")
            print("     Consulte: docs/INSTALL_TROUBLESHOOTING.md\n")
            sys.exit(1)

        elif preflight_result == "warn":
            print("  Avisos detectados, mas nenhum bloqueante.")
            print("  Deseja continuar mesmo assim? (S/n): ", end="")
            answer = input().strip().lower()
            if answer in ("n", "nao", "no"):
                print("  Abortado. Corrija os avisos e tente novamente.\n")
                sys.exit(1)
    elif args.check_only:
        print("\n  --check-only e --skip-checks nao podem ser usados juntos.\n")
        sys.exit(1)

    # Etapa 5: Subir o app
    run_app(port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
