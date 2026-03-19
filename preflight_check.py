"""
Validacao de ambiente para o GDQ Rule Proposer.

Executa checagens de pre-voo e retorna resultados estruturados.
Sem dependencias externas — usa apenas stdlib.

Uso standalone:
    python preflight_check.py

Uso programatico:
    from preflight_check import run_all_checks
    results = run_all_checks()
"""

import os
import socket
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class CheckStatus(str, Enum):
    OK = "OK"
    WARN = "WARN"
    ERROR = "ERROR"


@dataclass
class CheckResult:
    """Resultado de uma checagem individual."""
    name: str
    status: CheckStatus
    message: str
    fix_hint: str = ""


# ---------------------------------------------------------------------------
# Checagens individuais
# ---------------------------------------------------------------------------

def check_python_version(min_major: int = 3, min_minor: int = 10) -> CheckResult:
    """Verifica se a versao do Python e compativel."""
    v = sys.version_info
    current = f"{v.major}.{v.minor}.{v.micro}"

    if v.major < min_major or (v.major == min_major and v.minor < min_minor):
        return CheckResult(
            name="Python",
            status=CheckStatus.ERROR,
            message=f"Python {current} encontrado, mas o minimo e {min_major}.{min_minor}.",
            fix_hint=(
                f"Instale Python {min_major}.{min_minor}+ em https://www.python.org/downloads/\n"
                "  No Windows, marque a opcao 'Add Python to PATH' durante a instalacao."
            ),
        )

    return CheckResult(
        name="Python",
        status=CheckStatus.OK,
        message=f"Python {current}",
    )


def check_venv_active() -> CheckResult:
    """Verifica se um ambiente virtual esta ativo."""
    venv = os.environ.get("VIRTUAL_ENV", "")

    if venv:
        return CheckResult(
            name="Ambiente virtual",
            status=CheckStatus.OK,
            message=f"venv ativo: {Path(venv).name}",
        )

    # Verifica se .venv existe mas nao esta ativo
    venv_dir = Path(".venv")
    if venv_dir.is_dir():
        if sys.platform == "win32":
            activate = ".venv\\Scripts\\activate"
        else:
            activate = "source .venv/bin/activate"
        return CheckResult(
            name="Ambiente virtual",
            status=CheckStatus.WARN,
            message="Pasta .venv existe mas nao esta ativada.",
            fix_hint=(
                f"Ative o ambiente virtual:\n"
                f"  {activate}\n"
                "  Ou use o launcher.py que ativa automaticamente."
            ),
        )

    return CheckResult(
        name="Ambiente virtual",
        status=CheckStatus.WARN,
        message="Nenhum ambiente virtual detectado.",
        fix_hint=(
            "Crie um ambiente virtual:\n"
            "  python -m venv .venv\n"
            "  Ou use o launcher.py que cria automaticamente."
        ),
    )


def check_dependencies() -> CheckResult:
    """Verifica se as dependencias principais estao instaladas."""
    missing = []

    packages = {
        "streamlit": "streamlit",
        "plotly": "plotly",
        "pandas": "pandas",
        "numpy": "numpy",
        "pyathena": "pyathena",
        "boto3": "boto3",
        "jinja2": "jinja2",
    }

    for import_name, pip_name in packages.items():
        try:
            __import__(import_name)
        except ImportError:
            missing.append(pip_name)

    if missing:
        return CheckResult(
            name="Dependencias",
            status=CheckStatus.ERROR,
            message=f"Pacotes faltando: {', '.join(missing)}",
            fix_hint=(
                "Instale as dependencias:\n"
                "  pip install -r requirements.txt\n"
                "  Ou use o launcher.py que instala automaticamente."
            ),
        )

    return CheckResult(
        name="Dependencias",
        status=CheckStatus.OK,
        message="Todas as dependencias instaladas.",
    )


def check_dotenv() -> CheckResult:
    """Verifica se o arquivo .env existe e tem as variaveis obrigatorias."""
    env_file = Path(".env")

    if not env_file.exists():
        return CheckResult(
            name="Arquivo .env",
            status=CheckStatus.ERROR,
            message="Arquivo .env nao encontrado.",
            fix_hint=(
                "Crie o arquivo .env a partir do exemplo:\n"
                "  Copie .env.example para .env e preencha os valores.\n"
                "  Ou execute: python setup_local.py\n"
                "  O wizard guiado cria o .env para voce."
            ),
        )

    # Ler variaveis do .env
    env_vars = {}
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, value = line.split("=", 1)
            env_vars[key.strip()] = value.strip()

    # Variaveis obrigatorias
    required = {
        "GDQ_AWS_PROFILE": "Nome do profile AWS CLI (ex: seu-profile)",
        "GDQ_ATHENA_S3_OUTPUT": "Bucket S3 para resultados do Athena (ex: s3://seu-bucket/athena-results/)",
    }

    missing = []
    for var, desc in required.items():
        val = env_vars.get(var, "") or os.environ.get(var, "")
        if not val or val.startswith("seu-"):
            missing.append(f"  {var} — {desc}")

    if missing:
        return CheckResult(
            name="Arquivo .env",
            status=CheckStatus.ERROR,
            message="Variaveis obrigatorias nao preenchidas no .env:",
            fix_hint=(
                "Edite o arquivo .env e preencha:\n"
                + "\n".join(missing)
                + "\n  Ou execute: python setup_local.py"
            ),
        )

    return CheckResult(
        name="Arquivo .env",
        status=CheckStatus.OK,
        message=f".env configurado ({len(env_vars)} variaveis).",
    )


def check_aws_cli() -> CheckResult:
    """Verifica se o AWS CLI esta instalado."""
    try:
        result = subprocess.run(
            ["aws", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            version = result.stdout.strip().split()[0] if result.stdout else "desconhecida"
            return CheckResult(
                name="AWS CLI",
                status=CheckStatus.OK,
                message=f"AWS CLI instalado ({version}).",
            )
    except FileNotFoundError:
        pass
    except subprocess.TimeoutExpired:
        pass

    return CheckResult(
        name="AWS CLI",
        status=CheckStatus.ERROR,
        message="AWS CLI nao encontrado.",
        fix_hint=(
            "Instale o AWS CLI:\n"
            "  Windows: https://awscli.amazonaws.com/AWSCLIV2.msi\n"
            "  Linux:   curl 'https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip' -o awscliv2.zip\n"
            "  Mac:     brew install awscli\n"
            "  Apos instalar, feche e reabra o terminal."
        ),
    )


def check_aws_profile() -> CheckResult:
    """Verifica se o AWS profile esta configurado e as credenciais sao validas."""
    # Determinar profile
    profile = os.environ.get("GDQ_AWS_PROFILE", "")
    if not profile:
        env_file = Path(".env")
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if line.startswith("GDQ_AWS_PROFILE="):
                    profile = line.split("=", 1)[1].strip()
                    break

    if not profile or profile.startswith("seu-"):
        return CheckResult(
            name="AWS Profile",
            status=CheckStatus.WARN,
            message="Nenhum AWS profile configurado.",
            fix_hint=(
                "Configure GDQ_AWS_PROFILE no arquivo .env.\n"
                "  Para listar profiles existentes: aws configure list-profiles"
            ),
        )

    # Verificar se o profile existe na config
    try:
        result = subprocess.run(
            ["aws", "configure", "list-profiles"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            profiles = result.stdout.strip().splitlines()
            if profile not in profiles:
                return CheckResult(
                    name="AWS Profile",
                    status=CheckStatus.ERROR,
                    message=f"Profile '{profile}' nao encontrado na configuracao AWS.",
                    fix_hint=(
                        f"O profile '{profile}' nao existe. Profiles disponiveis:\n"
                        + "".join(f"  - {p}\n" for p in profiles[:10])
                        + "  Para criar: aws configure --profile " + profile + "\n"
                        "  Ou para SSO: aws configure sso --profile " + profile
                    ),
                )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass  # AWS CLI not found — already caught by check_aws_cli

    # Verificar credenciais ativas
    try:
        result = subprocess.run(
            ["aws", "sts", "get-caller-identity", "--profile", profile],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            return CheckResult(
                name="AWS Profile",
                status=CheckStatus.OK,
                message=f"Profile '{profile}' — credenciais validas.",
            )
        else:
            stderr = result.stderr.strip()
            if "expired" in stderr.lower() or "sso" in stderr.lower():
                return CheckResult(
                    name="AWS Profile",
                    status=CheckStatus.ERROR,
                    message=f"Credenciais do profile '{profile}' expiradas (SSO).",
                    fix_hint=f"Faca login novamente:\n  aws sso login --profile {profile}",
                )
            return CheckResult(
                name="AWS Profile",
                status=CheckStatus.ERROR,
                message=f"Credenciais do profile '{profile}' invalidas.",
                fix_hint=(
                    f"Verifique a configuracao do profile:\n"
                    f"  aws configure list --profile {profile}\n"
                    f"  Para SSO: aws sso login --profile {profile}\n"
                    f"  Para access key: aws configure --profile {profile}"
                ),
            )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return CheckResult(
            name="AWS Profile",
            status=CheckStatus.WARN,
            message=f"Nao foi possivel verificar credenciais do profile '{profile}'.",
            fix_hint="Verifique se o AWS CLI esta instalado e tente novamente.",
        )


def check_proxy() -> CheckResult:
    """Detecta proxy corporativo que pode bloquear pip ou AWS CLI."""
    proxy_vars = ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]
    no_proxy = os.environ.get("NO_PROXY", os.environ.get("no_proxy", ""))

    active = {v: os.environ[v] for v in proxy_vars if os.environ.get(v)}

    if not active:
        return CheckResult(
            name="Proxy",
            status=CheckStatus.OK,
            message="Nenhum proxy detectado.",
        )

    proxy_list = ", ".join(f"{k}={v}" for k, v in active.items())

    # Verificar se pip consegue conectar (teste rapido)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "index", "versions", "pip"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            return CheckResult(
                name="Proxy",
                status=CheckStatus.OK,
                message=f"Proxy configurado e funcional ({proxy_list}).",
            )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Proxy detectado mas nao testado ou falhou
    return CheckResult(
        name="Proxy",
        status=CheckStatus.WARN,
        message=f"Proxy corporativo detectado: {proxy_list}",
        fix_hint=(
            "Se pip ou AWS CLI falharem por timeout ou SSL, pode ser o proxy.\n"
            "  Opcoes:\n"
            "  1. Configure o certificado do proxy:\n"
            "     pip config set global.cert /caminho/do/certificado.pem\n"
            "  2. Para pip com proxy:\n"
            "     pip install --proxy http://proxy:porta -r requirements.txt\n"
            "  3. Para AWS CLI, configure em ~/.aws/config:\n"
            "     [profile seu-profile]\n"
            "     ca_bundle = /caminho/do/certificado.pem\n"
            + (f"  NO_PROXY atual: {no_proxy}" if no_proxy else "")
        ),
    )


def check_port_available(port: int = 8501) -> CheckResult:
    """Verifica se a porta esta disponivel."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            result = s.connect_ex(("127.0.0.1", port))
            if result == 0:
                return CheckResult(
                    name="Porta",
                    status=CheckStatus.WARN,
                    message=f"Porta {port} ja esta em uso.",
                    fix_hint=(
                        f"A porta {port} esta ocupada. Opcoes:\n"
                        f"  1. Feche o outro programa usando a porta {port}\n"
                        f"  2. Use outra porta: python launcher.py --port 8502"
                    ),
                )
    except OSError:
        pass

    return CheckResult(
        name="Porta",
        status=CheckStatus.OK,
        message=f"Porta {port} disponivel.",
    )


# ---------------------------------------------------------------------------
# Orquestrador
# ---------------------------------------------------------------------------

def run_all_checks(port: int = 8501) -> list[CheckResult]:
    """Executa todas as checagens de ambiente.

    Returns:
        Lista de CheckResult ordenada por severidade.
    """
    results = [
        check_python_version(),
        check_venv_active(),
        check_dependencies(),
        check_dotenv(),
        check_aws_cli(),
        check_aws_profile(),
        check_proxy(),
        check_port_available(port),
    ]
    return results


def has_errors(results: list[CheckResult]) -> bool:
    """Retorna True se alguma checagem retornou ERROR."""
    return any(r.status == CheckStatus.ERROR for r in results)


def print_results(results: list[CheckResult]) -> None:
    """Imprime resultados formatados no terminal."""
    icons = {
        CheckStatus.OK: "  [OK]   ",
        CheckStatus.WARN: "  [!!]   ",
        CheckStatus.ERROR: "  [ERRO] ",
    }

    print("\n  === Verificacao de Ambiente ===\n")

    for r in results:
        print(f"{icons[r.status]} {r.name}: {r.message}")
        if r.fix_hint and r.status != CheckStatus.OK:
            for line in r.fix_hint.splitlines():
                print(f"           {line}")
            print()

    errors = sum(1 for r in results if r.status == CheckStatus.ERROR)
    warns = sum(1 for r in results if r.status == CheckStatus.WARN)

    print()
    if errors:
        print(f"  {errors} erro(s) encontrado(s). Corrija antes de continuar.")
        print("  Consulte: docs/INSTALL_TROUBLESHOOTING.md\n")
    elif warns:
        print(f"  {warns} aviso(s). O app pode funcionar, mas revise os avisos acima.\n")
    else:
        print("  Tudo certo! Ambiente pronto.\n")


# ---------------------------------------------------------------------------
# Execucao standalone
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    results = run_all_checks()
    print_results(results)
    sys.exit(1 if has_errors(results) else 0)
