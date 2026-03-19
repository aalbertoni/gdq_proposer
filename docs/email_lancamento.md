# E-mail de Lancamento — GDQ Rule Proposer

**Assunto:** Novo: GDQ Rule Proposer — Proposta automatica de regras de qualidade de dados

---

Ola pessoal,

Estamos lancando o **GDQ Rule Proposer**, uma ferramenta que analisa o historico de dados das nossas tabelas e propoe regras de qualidade prontas para o AWS Glue Data Quality (GDQ).

O objetivo e simples: **reduzir o tempo e o risco de criar regras GDQ manualmente**, substituindo achismo por evidencia estatistica.

---

## O que a ferramenta faz

O GDQ Rule Proposer se conecta ao Athena, consulta o historico de cada coluna, calcula estatisticas e propoe regras calibradas com backtest — tudo via interface visual.

**Voce nao precisa conhecer a sintaxe GDQ.** A ferramenta gera tudo automaticamente.

---

## Principais funcionalidades

### Classificacao automatica de colunas
A ferramenta analisa cada coluna e classifica automaticamente como numerica, categorica (baixa, media ou alta cardinalidade), data, identificador ou texto. Isso determina quais regras sao propostas.

### Regras com Dual Guard
As regras dinamicas combinam duas bandas com logica OR:
- **Banda sigma** — media ± K desvios padrao
- **Banda margem** — media ± X%

Se o valor real cair dentro de qualquer uma das bandas, a regra passa. Isso reduz drasticamente os falsos positivos.

### Calibracao interativa
Graficos em tempo real mostram a banda de confianca sobre o historico. Voce ajusta os parametros (janela, sigma, margem) e ve imediatamente o impacto na cobertura e nos falsos positivos.

O **Auto-Tune** encontra automaticamente a melhor combinacao de parametros, priorizando cobertura de pontos normais e penalizando cobertura de outliers.

### Backtest historico
Cada regra e testada no historico antes de ser sugerida. Metricas incluem:
- **Cobertura** — % de periodos que passariam na regra
- **Falsos positivos** — quantos periodos normais seriam reprovados
- **Estabilidade** — consistencia da regra ao longo do tempo
- **Confianca** — HIGH, MEDIUM ou LOW

### Diagnosticos estatisticos
Painel de apoio na calibracao com:
- **Deteccao de mudanca de regime** — identifica quando a serie mudou de patamar
- **Sazonalidade semanal** — detecta padroes dia-da-semana
- **Analise de outliers** — IQR e MAD para identificar pontos extremos
- **Cobertura ponderada** — peso maior para dados recentes

### Regime estatistico
Cada serie e classificada automaticamente (estavel, volatil, com tendencia, sazonal, mudanca de regime, etc.). O regime orienta a calibracao e aparece como badge colorido na tela.

### Validacao de sintaxe
Antes de exportar, a ferramenta verifica:
- Sintaxe GDQ correta (parenteses, casing, aspas)
- Consistencia entre regras (conflitos, parametros divergentes)

### Relatorio analitico
Exporta um relatorio markdown com evidencia, racional e recomendacoes para cada regra. Ideal para documentacao e aprovacao tecnica.

### Teste via Thundera
Integracao com o pipeline Thundera para testar as regras em um Glue job antes de implantar em producao.

---

## Tipos de regras suportadas

| Tipo | O que monitora | Exemplo |
|------|---------------|---------|
| **Mean** | Media da coluna | Media de VLR_SALDO entre limites dinamicos |
| **StandardDeviation** | Volatilidade | Desvio padrao dentro de faixa esperada |
| **RowCount** | Volume de linhas | Tabela com 5000 +/- 500 linhas por dia |
| **Completeness** | Nulos | Coluna 100% preenchida |
| **AllowedValues** | Dominio fixo | Apenas valores [1, 2, 3] permitidos |
| **DistinctValuesCount** | Cardinalidade | Entre 5 e 10 valores distintos |
| **CategoryFrequency** | Distribuicao | Valor "A" entre 40% e 60% do total |
| **IsPrimaryKey** | Unicidade | Combinacao de colunas e unica |
| **Percentile** | Distribuicao numerica | P5 e P95 dentro de faixas esperadas |

---

## Fluxo de uso

A ferramenta guia voce em 5 etapas:

**1. Setup** — Informe a tabela, o eixo temporal e selecione as colunas para analise.

**2. Explore** — Calibre as regras com graficos interativos. Use o Auto-Tune para encontrar os melhores parametros automaticamente. Adicione as regras aprovadas ao carrinho.

**3. Review** — Revise as regras do carrinho, veja a sintaxe GDQ gerada, valide a consistencia e exporte como arquivo .txt ou relatorio analitico.

**4. Teste** — Teste as regras exportadas via Glue job Thundera antes de implantar em producao.

**5. Ajuda** — Documentacao completa com explicacao de cada conceito, tipo de regra e parametro.

---

## Como comecar

### Pre-requisitos
- Python 3.10+ instalado
- AWS CLI instalado com profile SSO configurado

### Passo a passo

```
1. Clone o repositorio:
   git clone https://github.com/aalbertoni/gdq_proposer.git
   cd gdq_proposer

2. Execute o app:
   python launcher.py
```

Na primeira execucao, o launcher:
- Cria o ambiente virtual automaticamente
- Instala as dependencias
- Pede para configurar o .env (wizard guiado com deteccao automatica de conta AWS)
- Verifica o ambiente
- Abre o app no navegador

**Atalho Windows:** de duplo-clique em `run_app.bat`.

### Configuracao

O wizard (`python setup_local.py`) pede apenas:
1. Qual profile AWS usar
2. Seu RACF
3. Confirmar regiao e workgroup (ja vem preenchido)
4. Confirmar o bucket S3 (montado automaticamente)

Defaults ja configurados:
- Regiao: `sa-east-1`
- Workgroup: `analytics-workgroup-v3`
- Bucket: `s3://itau-self-wkp-sa-east-1-{conta}/{racf}/query_results/`

---

## Se algo der errado

- O app tem uma pagina de **Diagnostico** (menu lateral) que verifica Python, dependencias, .env, AWS CLI, credenciais e conexao Athena
- Se as credenciais SSO expirarem, o dashboard mostra um botao **"Fazer login AWS (SSO)"** que reconecta sem sair do app
- No terminal, rode `python preflight_check.py` para um diagnostico completo
- Guia detalhado de troubleshooting: `docs/INSTALL_TROUBLESHOOTING.md`

---

## Links uteis

- Repositorio: https://github.com/aalbertoni/gdq_proposer
- Troubleshooting: `docs/INSTALL_TROUBLESHOOTING.md`
- Spec tecnica: `docs/technical_spec_v1.md`
- Referencia de sintaxe GDQ: `docs/gdq_syntax_reference.md`

---

Qualquer duvida, e so chamar.

Abracos
