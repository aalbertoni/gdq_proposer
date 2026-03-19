"""
Wizard guiado para configurar o arquivo .env do GDQ Rule Proposer.

Faz perguntas simples e gera o .env preenchido.
Sem dependencias externas.

Uso:
    python setup_local.py
"""

import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
ENV_FILE = PROJECT_DIR / ".env"


def _ask(prompt: str, default: str = "", required: bool = False) -> str:
    """Pergunta interativa com default."""
    suffix = f" [{default}]" if default else ""
    required_tag = " (obrigatorio)" if required and not default else ""

    while True:
        answer = input(f"  {prompt}{required_tag}{suffix}: ").strip()
        value = answer or default

        if required and not value:
            print("    Este campo e obrigatorio. Tente novamente.\n")
            continue
        return value


def _detect_profiles() -> list[str]:
    """Lista profiles AWS disponiveis."""
    try:
        result = subprocess.run(
            ["aws", "configure", "list-profiles"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return [p.strip() for p in result.stdout.strip().splitlines() if p.strip()]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return []


def _detect_account_id(profile: str) -> str:
    """Tenta detectar o numero da conta AWS via STS."""
    try:
        result = subprocess.run(
            ["aws", "sts", "get-caller-identity", "--profile", profile],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return data.get("Account", "")
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        pass
    return ""


def main():
    print()
    print("  =============================================")
    print("  GDQ Rule Proposer — Configuracao guiada")
    print("  =============================================")
    print()

    if ENV_FILE.exists():
        print(f"  Arquivo .env ja existe em: {ENV_FILE}")
        answer = input("  Deseja sobrescrever? (s/N): ").strip().lower()
        if answer not in ("s", "sim", "y", "yes"):
            print("  Configuracao mantida.\n")
            return
        print()

    print("  Este wizard vai criar o arquivo .env com as configuracoes")
    print("  necessarias para o app se conectar ao AWS Athena.")
    print()
    print("  Se nao souber algum valor, pergunte ao seu time de dados.")
    print()

    # --- AWS Profile ---
    print("  --- AWS Profile ---")
    print()

    profiles = _detect_profiles()
    if profiles:
        print("  Profiles AWS encontrados no seu computador:")
        for i, p in enumerate(profiles[:15], 1):
            print(f"    {i}. {p}")
        print()
        choice = input("  Digite o numero do profile ou o nome: ").strip()

        if choice.isdigit() and 1 <= int(choice) <= len(profiles):
            aws_profile = profiles[int(choice) - 1]
        else:
            aws_profile = choice
    else:
        print("  Nenhum profile AWS detectado.")
        print("  Voce precisa de um profile configurado no AWS CLI.")
        print("  Se nao tiver, peca ao seu time de dados ou consulte:")
        print("  docs/INSTALL_TROUBLESHOOTING.md\n")
        aws_profile = _ask("Nome do profile AWS", required=True)

    print(f"  Profile selecionado: {aws_profile}\n")

    # --- RACF ---
    print("  --- Identificacao ---")
    print()
    racf = _ask("Seu RACF (ex: a12345)", required=True)
    print()

    # --- Detectar conta AWS ---
    print("  Detectando numero da conta AWS...")
    account_id = _detect_account_id(aws_profile)

    if account_id:
        print(f"  Conta detectada: {account_id}\n")
    else:
        print("  Nao foi possivel detectar automaticamente.")
        print("  (Pode ser necessario fazer login: aws sso login --profile " + aws_profile + ")\n")
        account_id = _ask("Numero da conta AWS (12 digitos)", required=True)

    # --- Athena ---
    print("  --- Configuracao do Athena ---")
    print()

    region = _ask("Regiao AWS", default="sa-east-1")
    workgroup = _ask("Workgroup do Athena", default="analytics-workgroup-v3")

    # Montar S3 output automaticamente
    s3_default = f"s3://itau-self-wkp-{region}-{account_id}/{racf}/query_results/"
    print()
    print(f"  O bucket S3 de resultados do Athena sera:")
    print(f"    {s3_default}")
    print()
    use_default = input("  Usar este caminho? (S/n): ").strip().lower()

    if use_default in ("n", "nao", "no"):
        s3_output = _ask(
            "Bucket S3 para resultados",
            required=True,
        )
    else:
        s3_output = s3_default

    # Garantir que s3_output termina com /
    if s3_output and not s3_output.endswith("/"):
        s3_output += "/"

    # --- Thundera (opcional) ---
    print()
    print("  --- Thundera / Glue DQ (opcional) ---")
    print("  Preencha se sua equipe usa o pipeline Thundera.")
    print("  Deixe em branco para pular.\n")

    squad = _ask("Nome da squad")
    comunidade = _ask("Nome da comunidade")

    # --- Gerar .env ---
    content = f"""# GDQ Rule Proposer — Configuracao
# Gerado automaticamente por setup_local.py
# Edite os valores conforme necessario.

# === AWS Profile (obrigatorio) ===
# Nome do profile configurado no AWS CLI.
# Para listar: aws configure list-profiles
GDQ_AWS_PROFILE={aws_profile}

# === Athena (obrigatorio) ===
# Regiao onde o Athena esta configurado.
GDQ_ATHENA_REGION={region}

# Workgroup do Athena.
GDQ_ATHENA_WORKGROUP={workgroup}

# Bucket S3 onde o Athena salva resultados das queries.
# Formato: s3://itau-self-wkp-{{regiao}}-{{conta}}/{{racf}}/query_results/
GDQ_ATHENA_S3_OUTPUT={s3_output}

# === Thundera / Glue DQ Test (opcional) ===
# Preencha se sua equipe usa o pipeline Thundera para testes de qualidade.
GDQ_GLUE_JOB_NAME=glueplataformathundera
GDQ_GLUE_REGION=
GDQ_RACF={racf}
GDQ_SQUAD={squad}
GDQ_COMUNIDADE={comunidade}
"""

    ENV_FILE.write_text(content.strip() + "\n")

    print()
    print("  =============================================")
    print(f"  Arquivo .env criado com sucesso!")
    print(f"  Local: {ENV_FILE}")
    print("  =============================================")
    print()
    print("  Configuracao salva:")
    print(f"    Profile:   {aws_profile}")
    print(f"    Regiao:    {region}")
    print(f"    Workgroup: {workgroup}")
    print(f"    S3 Output: {s3_output}")
    print(f"    RACF:      {racf}")
    print()
    print("  Proximo passo: execute o app com:")
    print("    python launcher.py")
    print()


if __name__ == "__main__":
    main()
