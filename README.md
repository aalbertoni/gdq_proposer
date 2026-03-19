# GDQ Rule Proposer

Ferramenta visual para propor regras de qualidade de dados para o AWS Glue Data Quality (GDQ).

Conecta no AWS Athena, analisa o historico de cada coluna, propoe regras calibradas com backtest, e exporta a sintaxe GDQ pronta para uso.

## Como executar

### Pre-requisitos

- **Python 3.10+** — [Download](https://www.python.org/downloads/) (marque "Add Python to PATH")
- **AWS CLI** — [Download](https://aws.amazon.com/cli/)
- **Profile AWS** configurado com acesso ao Athena

### Passo a passo

```bash
# 1. Clone o repositorio
git clone https://github.com/aalbertoni/gdq_proposer.git
cd gdq_proposer

# 2. Execute o app (cria venv e instala tudo automaticamente)
python launcher.py
```

Na primeira execucao, o launcher:
- Cria o ambiente virtual (`.venv`)
- Instala as dependencias
- Pede para configurar o `.env` (wizard guiado)
- Verifica o ambiente
- Abre o app no navegador

**Windows — atalho:** de duplo-clique em `run_app.bat`.

### Configuracao rapida

Se preferir configurar manualmente:

```bash
# Copie o arquivo de exemplo
cp .env.example .env     # Linux/Mac
copy .env.example .env   # Windows

# Edite .env e preencha:
#   GDQ_AWS_PROFILE     → seu profile AWS
#   GDQ_ATHENA_S3_OUTPUT → bucket S3 do Athena
```

Ou use o wizard: `python setup_local.py`

### Verificar ambiente

```bash
python preflight_check.py
```

## Algo deu errado?

Consulte o guia de solucao de problemas: **[docs/INSTALL_TROUBLESHOOTING.md](docs/INSTALL_TROUBLESHOOTING.md)**

## Para desenvolvedores

```bash
# Rodar testes
pytest tests/ -v

# Rodar com porta customizada
python launcher.py --port 8502

# Rodar com debug
python launcher.py --debug
```

## Documentacao

- [Especificacao tecnica](docs/technical_spec_v1.md)
- [Referencia de sintaxe GDQ](docs/gdq_syntax_reference.md)
- [Setup de ambiente AWS de teste](docs/aws_test_setup.md)
- [Troubleshooting](docs/INSTALL_TROUBLESHOOTING.md)
