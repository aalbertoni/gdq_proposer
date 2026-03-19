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


def _detect_ca_bundle() -> str:
    """Detecta certificado CA corporativo.

    Prioridade:
    1. Variaveis de ambiente ja configuradas
    2. Busca em locais conhecidos no disco
    """
    # 1. Verificar env vars existentes (ordem de prioridade botocore)
    for var in ("AWS_CA_BUNDLE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "SSL_CERT_FILE"):
        val = os.environ.get(var, "")
        if val and Path(val).is_file():
            return val

    # 2. Buscar em locais conhecidos
    home = Path.home()
    candidates = []

    # ~/.aws/ — local mais comum para config AWS
    aws_dir = home / ".aws"
    if aws_dir.is_dir():
        for pattern in ("*.pem", "*.crt", "*.cer"):
            candidates.extend(aws_dir.glob(pattern))

    # Locais corporativos comuns no Windows
    if sys.platform == "win32":
        corp_dirs = [
            Path("C:/certs"),
            Path("C:/certificados"),
            home / "certs",
            home / "certificados",
            home / "Documents" / "certs",
        ]
        # AWS CLI bundled cacert
        awscli_paths = [
            Path("C:/Program Files/Amazon/AWSCLIV2/awscli/botocore/cacert.pem"),
            Path("C:/Program Files (x86)/Amazon/AWSCLIV2/awscli/botocore/cacert.pem"),
        ]
        for p in awscli_paths:
            if p.is_file():
                candidates.append(p)
        for d in corp_dirs:
            if d.is_dir():
                for pattern in ("*.pem", "*.crt", "*.cer"):
                    candidates.extend(d.glob(pattern))
    else:
        # Linux/Mac
        unix_paths = [
            Path("/etc/ssl/certs/ca-certificates.crt"),
            Path("/etc/pki/tls/certs/ca-bundle.crt"),
            Path("/etc/ssl/ca-bundle.pem"),
            home / "certs",
        ]
        for p in unix_paths:
            if p.is_file():
                candidates.append(p)
            elif p.is_dir():
                for pattern in ("*.pem", "*.crt"):
                    candidates.extend(p.glob(pattern))

    # Remover duplicatas, manter ordem
    seen = set()
    unique = []
    for c in candidates:
        resolved = str(c.resolve())
        if resolved not in seen:
            seen.add(resolved)
            unique.append(c)

    return unique


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

    # --- Proxy corporativo ---
    print()
    print("  --- Proxy Corporativo ---")
    print("  Necessario para conexoes AWS na rede Itau.")
    print("  Formato: http://RACF:SENHA@proxynew.itau:8080")
    print()
    print("  ATENCAO: se sua senha tiver caracteres especiais (@, #, !),")
    print("  use encoding URL. Ex: @ = %40, # = %23, ! = %21")
    print()

    proxy_default = f"http://{racf}:SENHA@proxynew.itau:8080"
    proxy_url = _ask("URL do proxy", default=proxy_default)

    # Se o usuario deixou SENHA no default, avisar
    if "SENHA" in proxy_url:
        print()
        print("  IMPORTANTE: substitua SENHA pela sua senha de rede no .env")
        print("  antes de executar o app.")

    no_proxy_default = (
        "127.0.0.1,10.0.0.0/8,192.168.0.0/16,"
        ".aws.clud.ihf,.cloudera.site,.localhost,.cloud.ihf,"
        "*.corp.rc.itau,*.corp.ihf,*.itau.com,*.itau.corp.ihf,localhost"
    )

    # --- Certificado CA (SSL) ---
    print()
    print("  --- Certificado CA (SSL) ---")
    print("  Necessario se a rede corporativa intercepta HTTPS (proxy SSL).")
    print("  Sem ele, voce pode receber erros SSL CERTIFICATE_VERIFY_FAILED.")
    print()

    ca_bundle_path = ""
    detected = _detect_ca_bundle()

    if isinstance(detected, str) and detected:
        # Encontrou via variavel de ambiente
        print(f"  Certificado CA detectado via variavel de ambiente:")
        print(f"    {detected}")
        print()
        use_detected = input("  Usar este certificado? (S/n): ").strip().lower()
        if use_detected not in ("n", "nao", "no"):
            ca_bundle_path = detected
        else:
            ca_bundle_path = _ask("Caminho do certificado CA (.pem ou .crt)")
    elif isinstance(detected, list) and detected:
        # Encontrou arquivos no disco
        print("  Certificados encontrados no seu computador:")
        for i, p in enumerate(detected[:10], 1):
            print(f"    {i}. {p}")
        print(f"    0. Nenhum / informar outro caminho")
        print(f"    Enter = pular")
        print()
        choice = input("  Escolha o numero do certificado: ").strip()

        if choice.isdigit() and 1 <= int(choice) <= len(detected):
            ca_bundle_path = str(detected[int(choice) - 1].resolve())
        elif choice == "0":
            ca_bundle_path = _ask("Caminho do certificado CA (.pem ou .crt)")
        else:
            ca_bundle_path = ""
    else:
        print("  Nenhum certificado CA detectado automaticamente.")
        print("  Se voce tiver erros de SSL, peca o certificado CA (.pem)")
        print("  ao time de infraestrutura e informe o caminho aqui.")
        print()
        ca_bundle_path = _ask("Caminho do certificado CA (deixe vazio para pular)")

    if ca_bundle_path:
        if Path(ca_bundle_path).is_file():
            print(f"  Certificado CA configurado: {ca_bundle_path}")
        else:
            print(f"  AVISO: arquivo '{ca_bundle_path}' nao encontrado.")
            print("  O caminho sera salvo no .env mesmo assim — corrija depois se necessario.")
    else:
        print("  Sem certificado CA configurado (pode ser adicionado depois no .env).")

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

# === Proxy corporativo ===
# Necessario para conexoes AWS na rede Itau.
# ATENCAO: substitua SENHA pela sua senha de rede.
# Se a senha tiver caracteres especiais, use URL encoding (@ = %40, # = %23, ! = %21).
HTTP_PROXY={proxy_url}
HTTPS_PROXY={proxy_url}
http_proxy={proxy_url}
https_proxy={proxy_url}
NO_PROXY={no_proxy_default}
no_proxy={no_proxy_default}

# === Certificado CA (SSL) ===
# Caminho do certificado CA corporativo (.pem ou .crt).
# Necessario se a rede intercepta HTTPS (proxy SSL/TLS inspection).
# Deixe vazio se nao aplicavel.
AWS_CA_BUNDLE={ca_bundle_path}

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
    print(f"    Proxy:     {proxy_url}")
    print(f"    CA Bundle: {ca_bundle_path or '(nao configurado)'}")
    print(f"    RACF:      {racf}")
    print()
    if "SENHA" in proxy_url:
        print("  IMPORTANTE: edite o .env e substitua SENHA pela sua senha de rede!")
        print()
    print("  Proximo passo: execute o app com:")
    print("    python launcher.py")
    print()


if __name__ == "__main__":
    main()
