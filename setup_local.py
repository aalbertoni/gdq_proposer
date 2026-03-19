"""
Wizard guiado para configurar o arquivo .env do GDQ Rule Proposer.

Faz perguntas simples e gera o .env preenchido.
Sem dependencias externas.

Uso:
    python setup_local.py
"""

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

    # --- Athena ---
    print("  --- Configuracao do Athena ---")
    print()

    region = _ask("Regiao AWS", default="us-east-1")
    workgroup = _ask("Workgroup do Athena", default="primary")
    s3_output = _ask(
        "Bucket S3 para resultados (ex: s3://meu-bucket/athena-results/)",
        required=True,
    )

    # Garantir que s3_output termina com /
    if s3_output and not s3_output.endswith("/"):
        s3_output += "/"

    # --- Thundera (opcional) ---
    print()
    print("  --- Thundera / Glue DQ (opcional) ---")
    print("  Preencha se sua equipe usa o pipeline Thundera.")
    print("  Deixe em branco para pular.\n")

    racf = _ask("Seu RACF")
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

# Workgroup do Athena (geralmente "primary").
GDQ_ATHENA_WORKGROUP={workgroup}

# Bucket S3 onde o Athena salva resultados das queries.
# Formato: s3://nome-do-bucket/pasta/
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
    print("  Proximo passo: execute o app com:")
    print("    python launcher.py")
    print()


if __name__ == "__main__":
    main()
