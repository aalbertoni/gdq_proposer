# GDQ Rule Proposer — Evolução: CustomSql Dinâmico + Integração de IA

> **Status:** Proposta de evolução pós-MVP
> **Última atualização:** 2026-02-24

---

## Parte 1: CustomSql com Bandas Dinâmicas

### 1.1 Descoberta

As funções `avg(last(N))` e `std(last(N))` podem ser utilizadas no `between` de regras
`CustomSql`, não apenas em `Mean`, `StandardDeviation` e `RowCount`.

Isso significa que **regras categóricas de frequência podem ser dinâmicas** —
se auto-ajustam a cada execução sem precisar recalibrar manualmente.

### 1.2 Sintaxe: CustomSql Dinâmico (Dual Guard)

#### Frequência de categoria — versão dinâmica

```
(
  (CustomSql "select cast(sum(case when {COL} = '{VALUE}' then 1 else 0 end) as double) * 100.0 / count(*) from primary" between (avg(last({N})) - ({K} * std(last({N}))) - {BUFFER}) and (avg(last({N})) + ({K} * std(last({N}))) + {BUFFER}))
  OR
  (CustomSql "select cast(sum(case when {COL} = '{VALUE}' then 1 else 0 end) as double) * 100.0 / count(*) from primary" between (avg(last({N})) * {1-MARGIN} - {BUFFER}) and (avg(last({N})) * {1+MARGIN} + {BUFFER}))
)
```

#### Parâmetros

| Parâmetro | Default | Descrição |
|-----------|---------|-----------|
| N | 30 | Lookback de processamentos |
| K | 2 | Multiplicador sigma |
| BUFFER | 0.01 | Margem absoluta (importante para categorias raras ~0%) |
| MARGIN | 0.10 | Margem percentual |

#### Comparação: estático vs dinâmico vs híbrido

| Aspecto | Estático | Dinâmico | Híbrido |
|---------|---------|----------|---------|
| Limites | Fixos (85.61 a 97.66) | Recalculados a cada execução | Dinâmico com floor/ceiling |
| Manutenção | Precisa recalibrar | Auto-ajusta | Auto-ajusta com proteção |
| Risco | FP após drift natural | Acompanha drift ruim | Protege contra drift excessivo |
| Complexidade | Simples | Dual guard padrão | Dual guard + AND absolutos |
| Melhor uso | Regra de negócio fixa | Distribuição natural variável | Variação permitida com limites |

#### Quando usar cada um

- **Estático:** Quando a distribuição é uma regra de negócio fixa
  (ex: "categoria X sempre deve estar entre 85% e 98%")
- **Dinâmico:** Quando a distribuição varia naturalmente com o tempo
  (ex: mix de produtos muda sazonalmente)
- **Híbrido:** Quando há variação natural, mas com limites absolutos de negócio
  (ex: "categoria rara varia, mas nunca pode passar de 5%" ou
   "categoria mandatória varia, mas nunca pode cair abaixo de 1%")

#### Sintaxe híbrida (dinâmico com floor/ceiling)

```
(
  (
    -- Parte dinâmica (dual guard)
    (CustomSql "select ..." between (avg(last({N})) - ({K} * std(last({N}))) - {BUFFER})
                                and (avg(last({N})) + ({K} * std(last({N}))) + {BUFFER}))
    OR
    (CustomSql "select ..." between (avg(last({N})) * {1-MARGIN} - {BUFFER})
                                and (avg(last({N})) * {1+MARGIN} + {BUFFER}))
  )
  AND
  -- Limites absolutos (floor/ceiling)
  (CustomSql "select ..." between {FLOOR} and {CEILING})
)
```

Isso garante que a banda dinâmica nunca ultrapasse os limites de negócio.

### 1.3 Outras regras que ganham versão dinâmica

#### DistinctValuesCount dinâmico

```
(
  (DistinctValuesCount {COL} >= (avg(last({N})) - ({K} * std(last({N})))))
  AND
  (DistinctValuesCount {COL} <= (avg(last({N})) + ({K} * std(last({N})))))
)
```

Útil para colunas onde o número de categorias muda gradualmente.

#### Completeness dinâmico (se aplicável)

```
Completeness {COL} >= (avg(last({N})) - ({K} * std(last({N}))) - 0.01)
```

Para colunas onde a completude varia naturalmente (ex: campos opcionais que
dependem de tipo de produto).

### 1.4 Impacto na Ferramenta

A ferramenta precisa oferecer ao usuário **a escolha** entre estático e dinâmico:

```
┌─────────────────────────────────────────────────────┐
│  Regra de frequência: COD_SITU_OPCR = '1'           │
│                                                      │
│  Modo: [● Dinâmico (auto-ajuste)] [○ Estático]     │
│                                                      │
│  Se dinâmico:                                        │
│    N períodos: [====●====] 30                       │
│    Sigma (σ):  [● 2  ○ 3  ○ Custom]                │
│    Margem %:   [====●====] 10%                      │
│                                                      │
│  Se estático:                                        │
│    Mín %: [85.61]  Máx %: [97.66]                  │
│                                                      │
│  Gráfico: [série histórica + banda proposta]         │
│                                                      │
│  ⬇ Preview da sintaxe                               │
│  ┌──────────────────────────────────────────┐       │
│  │ (CustomSql "select cast(sum(case when    │       │
│  │ COD_SITU_OPCR = '1' then 1 else 0 end)  │       │
│  │ ..." between avg(last(30)) - (2 * std(   │       │
│  │ last(30))) - 0.01 and avg(last(30)) +    │       │
│  │ (2 * std(last(30))) + 0.01)              │       │
│  └──────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────┘
```

### 1.5 Atualização do GDQRuleGenerator

```python
def category_frequency_dynamic(
    self,
    col: str,
    value: str,
    n_periods: int = 30,
    n_sigma: int = 2,
    margin_pct: float = 0.10,
    buffer: float = 0.01,
) -> str:
    """CustomSql dinâmico com dual guard para frequência de categoria."""
    sql = (
        f"select cast(sum(case when {col} = '{value}' "
        f"then 1 else 0 end) as double) * 100.0 / count(*) from primary"
    )
    n = n_periods
    k = n_sigma
    lo_margin = round(1 - margin_pct, 2)
    hi_margin = round(1 + margin_pct, 2)
    return (
        f'((CustomSql "{sql}" between '
        f"(avg(last({n})) - ({k} * std(last({n}))) - {buffer}) "
        f"and (avg(last({n})) + ({k} * std(last({n}))) + {buffer})) "
        f'OR (CustomSql "{sql}" between '
        f"(avg(last({n})) * {lo_margin} - {buffer}) "
        f"and (avg(last({n})) * {hi_margin} + {buffer})))"
    )


def category_frequency_static(
    self,
    col: str,
    value: str,
    min_pct: float,
    max_pct: float,
) -> str:
    """CustomSql estático para frequência de categoria."""
    sql = (
        f"select cast(sum(case when {col} = '{value}' "
        f"then 1 else 0 end) as double) * 100.0 / count(*) from primary"
    )
    return f'CustomSql "{sql}" between {min_pct} and {max_pct}'


def category_frequency_hybrid(
    self,
    col: str,
    value: str,
    n_periods: int = 30,
    n_sigma: int = 2,
    margin_pct: float = 0.10,
    buffer: float = 0.01,
    floor_pct: float = 0.0,
    ceiling_pct: float = 100.0,
) -> str:
    """CustomSql híbrido: dinâmico com floor/ceiling absolutos.

    A banda dinâmica se auto-ajusta, mas nunca ultrapassa os limites
    de negócio definidos por floor/ceiling.

    Uso: "categoria rara varia naturalmente, mas nunca pode passar de 5%"
    """
    sql = (
        f"select cast(sum(case when {col} = '{value}' "
        f"then 1 else 0 end) as double) * 100.0 / count(*) from primary"
    )
    n = n_periods
    k = n_sigma
    lo_margin = round(1 - margin_pct, 2)
    hi_margin = round(1 + margin_pct, 2)
    return (
        f'(((CustomSql "{sql}" between '
        f"(avg(last({n})) - ({k} * std(last({n}))) - {buffer}) "
        f"and (avg(last({n})) + ({k} * std(last({n}))) + {buffer})) "
        f'OR (CustomSql "{sql}" between '
        f"(avg(last({n})) * {lo_margin} - {buffer}) "
        f"and (avg(last({n})) * {hi_margin} + {buffer}))) "
        f'AND (CustomSql "{sql}" between {floor_pct} and {ceiling_pct}))'
    )
```

---

## Parte 2: Integração de IA

### 2.1 Onde IA agrega valor real (e onde não agrega)

#### ✅ Alto valor

| Ponto de integração | O que a IA faz | Quando acionar |
|---------------------|----------------|----------------|
| **Análise de anomalias** | Dado um período que falhou na regra, explicar por que (contexto, correlações) | Pós-falha no backtest |
| **Sugestão inteligente de parâmetros** | Dado o perfil da coluna + histórico, sugerir N, K, margem ideal | Setup da regra |
| **Classificação semântica** | Dado nome + amostra, inferir se é monetário, percentual, indicador, etc. | Profiling |
| **Resumo executivo** | Gerar relatório legível das regras propostas, tradeoffs, riscos | Export |
| **Natural language → regra** | "quero monitorar se o saldo médio caiu mais que 2 desvios" → sintaxe | UI avançada |

#### ⚠️ Valor marginal (não priorizar)

| Ponto | Por que não priorizar |
|-------|----------------------|
| Gerar a regra automaticamente | O dual guard já é um template; IA não melhora a sintaxe |
| Calcular estatísticas | Athena faz melhor e mais barato |
| Detectar outliers | Regras estatísticas simples (σ, IQR) são mais auditáveis |

### 2.2 Arquitetura de Integração

```
┌─────────────────────────────────────────────────────────┐
│  Streamlit UI                                            │
│  └─ AI Insights Panel (expandível, não bloqueia fluxo)  │
├─────────────────────────────────────────────────────────┤
│  AI Service Layer (core/ai_service.py)                   │
│  ├─ Provider abstraction (protocol)                      │
│  ├─ Prompt templates (prompts/)                          │
│  ├─ Response parser                                      │
│  └─ Cache (evitar chamadas duplicadas)                   │
├─────────────────────────────────────────────────────────┤
│  Provider Adapters (infra/ai_providers/)                  │
│  ├─ StackSpotAdapter                                     │
│  ├─ BedrockAdapter (Claude via Bedrock)                  │
│  ├─ AnthropicAdapter (API direta, se disponível)         │
│  └─ MockAdapter (desenvolvimento/testes)                 │
└─────────────────────────────────────────────────────────┘
```

#### Princípio: IA é aditiva, nunca bloqueante

- A ferramenta funciona 100% sem IA
- IA aparece como "insights opcionais" que enriquecem a decisão
- Se a API falhar/demorar, o fluxo continua normalmente
- Cada chamada tem timeout curto (10-15s) e fallback gracioso

### 2.3 Provider Protocol (abstração de provedor)

```python
# core/ai_service.py
from typing import Protocol


class AIProvider(Protocol):
    """Protocolo para qualquer provedor de IA."""

    async def complete(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 1000,
        temperature: float = 0.3,
    ) -> str:
        """Envia prompt e retorna resposta textual."""
        ...


class AIService:
    """Orquestra chamadas de IA com cache e fallback."""

    def __init__(self, provider: AIProvider, cache_ttl: int = 3600):
        self.provider = provider
        self._cache: dict[str, str] = {}

    async def get_insight(
        self, insight_type: str, context: dict
    ) -> dict:
        """Gera insight baseado no tipo e contexto.

        Args:
            insight_type: "anomaly_analysis", "parameter_suggestion",
                         "semantic_classification", "executive_summary",
                         "natural_language_rule"
            context: dados relevantes (perfil, histórico agregado, etc.)

        Returns:
            {"insight": str, "confidence": float, "suggestions": list}
        """
        ...
```

### 2.4 Provider Adapters

```python
# infra/ai_providers/bedrock_adapter.py
import boto3
import json


class BedrockAdapter:
    """Adapter para Claude via AWS Bedrock."""

    def __init__(
        self,
        model_id: str = "anthropic.claude-3-5-sonnet-20241022-v2:0",
        region: str = "us-east-1",
    ):
        self.client = boto3.client("bedrock-runtime", region_name=region)
        self.model_id = model_id

    async def complete(
        self, prompt: str, system: str = "", max_tokens: int = 1000,
        temperature: float = 0.3,
    ) -> str:
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
        })
        response = self.client.invoke_model(
            modelId=self.model_id,
            body=body,
        )
        result = json.loads(response["body"].read())
        return result["content"][0]["text"]


# infra/ai_providers/stackspot_adapter.py
import httpx


class StackSpotAdapter:
    """Adapter para API StackSpot AI."""

    def __init__(self, api_url: str, api_key: str):
        self.api_url = api_url
        self.api_key = api_key

    async def complete(
        self, prompt: str, system: str = "", max_tokens: int = 1000,
        temperature: float = 0.3,
    ) -> str:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{self.api_url}/v1/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "prompt": f"{system}\n\n{prompt}" if system else prompt,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
            )
            response.raise_for_status()
            return response.json()["content"]


# infra/ai_providers/mock_adapter.py

class MockAdapter:
    """Adapter para desenvolvimento e testes — sem chamada externa."""

    async def complete(
        self, prompt: str, system: str = "", max_tokens: int = 1000,
        temperature: float = 0.3,
    ) -> str:
        return "[Mock AI] Insight simulado para desenvolvimento."
```

### 2.5 Prompt Templates (os 5 pontos de IA)

```python
# prompts/templates.py

ANOMALY_ANALYSIS = """
Você é um analista de qualidade de dados. Analise por que o processamento
de {date} falhou na regra proposta para a coluna {column} da tabela {table}.

Contexto:
- Tipo da coluna: {semantic_type}
- Métrica monitorada: {metric} (ex: média, frequência)
- Valor do período: {current_value}
- Banda esperada: {lower} a {upper}
- Histórico recente (últimos {n} períodos): {history_summary}

Responda em português, de forma concisa (máx 3 parágrafos):
1. Diagnóstico provável (o que pode ter causado o desvio)
2. É um problema real ou variação aceitável?
3. Sugestão de ação (ajustar regra, investigar dados, ou manter)
"""

PARAMETER_SUGGESTION = """
Você é um especialista em regras de qualidade de dados.
Dado o perfil abaixo, sugira os melhores parâmetros para a regra.

Coluna: {column}
Tipo: {semantic_type}
Estatísticas do histórico ({n_periods} períodos):
- Média das médias: {mean_of_means}
- Desvio padrão das médias: {std_of_means}
- Coeficiente de variação: {cv}
- Tendência (drift): {drift_info}
- Outliers detectados: {outlier_count}
- Sazonalidade aparente: {seasonality}

Responda em JSON:
{{
  "n_periods": <int>,
  "n_sigma": <int>,
  "margin_pct": <float>,
  "rationale": "<explicação curta>",
  "warnings": ["<warning1>", ...]
}}
"""

SEMANTIC_CLASSIFICATION = """
Classifique semanticamente esta coluna de banco de dados:

Nome: {column_name}
Tipo Athena: {athena_type}
Valores distintos: {distinct_count}
Amostra de valores: {sample_values}
Percentual nulo: {null_pct}%
Tabela: {table_name}

Classifique em uma das categorias:
- monetary: valores monetários (saldo, valor, preço)
- percentage: percentuais (taxa, proporção)
- indicator: flag binário (0/1, sim/não, ativo/inativo)
- counter: contagem inteira (quantidade, parcelas)
- identifier: chave ou código
- date_component: ano, mês, anomes
- categorical_domain: categoria de domínio fixo (status, tipo)
- categorical_variable: categoria que varia (cidade, produto)
- free_text: texto livre
- unknown: não classificável

Responda em JSON:
{{
  "semantic_type": "<tipo>",
  "confidence": <0-1>,
  "suggested_rules": ["<rule_type1>", ...],
  "rationale": "<explicação curta>"
}}
"""

EXECUTIVE_SUMMARY = """
Gere um resumo executivo das regras de qualidade propostas para
a tabela {schema}.{table}.

Regras propostas:
{rules_summary}

Estatísticas de backtest:
{backtest_summary}

Gere em português:
1. Resumo geral (2-3 frases)
2. Regras de maior risco (baixa confiança ou alto falso positivo)
3. Recomendações para o time
"""

NATURAL_LANGUAGE_TO_RULE = """
Você é um gerador de regras AWS Glue Data Quality.
O usuário descreve em linguagem natural o que quer monitorar.
Gere a sintaxe GDQ exata.

Referência de sintaxe disponível:
- Mean com dual guard (banda σ OR margem %)
- StandardDeviation com dual guard
- RowCount com dual guard
- CustomSql para frequência de categoria
- ColumnValues para domínio
- DistinctValuesCount
- Completeness
- IsPrimaryKey

Colunas disponíveis na tabela: {columns}

Pedido do usuário: {user_request}

Responda em JSON:
{{
  "rules": ["<sintaxe_gdq_1>", ...],
  "explanation": "<explicação curta>"
}}
"""
```

### 2.6 Integração na UI — Painel de Insights

```
┌─────────────────────────────────────────────────────┐
│  📊 Análise: VLR_SALD_AVNC_OPCR                    │
│                                                      │
│  [Gráfico com banda e backtest — funciona sem IA]   │
│                                                      │
│  Backtest: ✅ 96.7% cobertura                       │
│                                                      │
│  ┌─ 🤖 Insights de IA (opcional) ──────────────┐   │
│  │                                               │   │
│  │  📋 Classificação: coluna monetária (saldo)  │   │
│  │  💡 Sugestão: N=20, σ=2, margem=15%          │   │
│  │     Motivo: CV alto (0.34) + leve drift      │   │
│  │  ⚠️ Período 2026-01-15 fora da banda:       │   │
│  │     Provável causa: fechamento mensal com     │   │
│  │     volume atípico. Variação aceitável.       │   │
│  │                                               │   │
│  │  [🔄 Atualizar]  [📋 Copiar insight]        │   │
│  └───────────────────────────────────────────────┘   │
│                                                      │
│  [🛒 Adicionar ao Carrinho]                         │
└─────────────────────────────────────────────────────┘
```

### 2.7 Configuração do Provedor de IA

```python
# config.py (adição)
from dataclasses import dataclass
from enum import Enum


class AIProviderType(str, Enum):
    NONE = "none"           # IA desabilitada
    BEDROCK = "bedrock"
    STACKSPOT = "stackspot"
    ANTHROPIC = "anthropic"
    MOCK = "mock"           # para desenvolvimento


@dataclass
class AIConfig:
    provider: AIProviderType = AIProviderType.NONE
    # Bedrock
    bedrock_model_id: str = "anthropic.claude-3-5-sonnet-20241022-v2:0"
    bedrock_region: str = "us-east-1"
    # StackSpot
    stackspot_api_url: str = ""
    stackspot_api_key: str = ""
    # Anthropic direto
    anthropic_api_key: str = ""
    # Geral
    timeout_seconds: int = 15
    cache_ttl_seconds: int = 3600
    enabled_insights: list[str] = None  # None = todos habilitados
    # ["anomaly_analysis", "parameter_suggestion",
    #  "semantic_classification", "executive_summary",
    #  "natural_language_rule"]
```

### 2.8 Setup na UI de configuração

```
┌─────────────────────────────────────────────────────┐
│  ⚙️ Configurações                                   │
│                                                      │
│  ── Provedor de IA (opcional) ──                    │
│  [○ Nenhum] [● Bedrock] [○ StackSpot] [○ Mock]     │
│                                                      │
│  Modelo: [anthropic.claude-3-5-sonnet______▼]       │
│  Região: [us-east-1________________________▼]       │
│                                                      │
│  Insights habilitados:                               │
│  [☑] Classificação semântica de colunas              │
│  [☑] Sugestão de parâmetros                          │
│  [☑] Análise de anomalias                            │
│  [☑] Resumo executivo                                │
│  [☐] Natural language → regra (experimental)         │
│                                                      │
│  [🔍 Testar Conexão]  Status: ✅ Conectado          │
└─────────────────────────────────────────────────────┘
```

---

## Parte 3: Roadmap de Evolução Atualizado

### Fase 1: MVP (sem IA, sem CustomSql dinâmico)

O que já está planejado nos Sprints A-C:
- Mean dual guard (dinâmico)
- StandardDeviation dual guard (dinâmico)
- RowCount dual guard (dinâmico)
- CustomSql frequência (estático)
- ColumnValues, DistinctValuesCount, Completeness, IsPrimaryKey
- Backtest visual + scoring

### Fase 2: CustomSql Dinâmico (pós-MVP, alta prioridade)

- [ ] Implementar `category_frequency_dynamic()` no GDQRuleGenerator
- [ ] UI: toggle estático/dinâmico por regra de frequência
- [ ] Backtest adaptado para simular comportamento dinâmico
- [ ] Testar DistinctValuesCount dinâmico
- [ ] Testar Completeness dinâmico (se aplicável)
- [ ] Documentar quais funções dinâmicas funcionam em cada contexto

**Validação necessária:**
Antes de implementar, testar manualmente no GDQ se esta sintaxe funciona:
```
CustomSql "select ... from primary" between avg(last(30)) - (2 * std(last(30))) and avg(last(30)) + (2 * std(last(30)))
```

### Fase 3: IA — Classificação + Sugestão (pós-MVP, média prioridade)

- [ ] AIProvider protocol + adapters (Bedrock, StackSpot, Mock)
- [ ] Classificação semântica (enriquece profiling do Sprint 0)
- [ ] Sugestão de parâmetros (enriquece calibração do Sprint 1-2)
- [ ] UI: painel de insights expandível (não bloqueante)
- [ ] Cache de respostas

### Fase 4: IA — Anomalias + Relatório (pós-MVP, média prioridade)

- [ ] Análise de anomalias no backtest
- [ ] Resumo executivo para export
- [ ] Relatório analítico enriquecido com insights

### Fase 5: IA — Natural Language (experimental)

- [ ] "quero monitorar se o saldo médio caiu" → sintaxe GDQ
- [ ] Validação da sintaxe gerada
- [ ] UI com input de texto livre + preview da regra

---

## Parte 4: Novas Possibilidades a Explorar

### 4.1 ColumnValues com threshold

Você mencionou que não conhecia. A sintaxe seria algo como:

```
ColumnValues COL in [1, 2, 3] with threshold >= 0.95
```

Isso significaria "95% dos valores devem estar na lista permitida",
permitindo uma margem para valores novos/raros.

**Ação:** Testar essa sintaxe no GDQ. Se funcionar, é uma alternativa
mais elegante ao CustomSql para domínio com tolerância.

### 4.2 Aggregate + Filter (se existir)

Possibilidade de regras como:
```
Mean COL where OTHER_COL = 'VALUE' between X and Y
```

Se o GDQ suportar filtros inline, abre espaço para regras segmentadas
(ex: média do saldo apenas para contratos ativos).

### 4.3 Uniqueness (verificar disponibilidade)

```
Uniqueness COL >= 0.99
```

Alternativa ao IsPrimaryKey quando permite duplicatas raras.

### 4.4 ColumnLength / ColumnPattern

```
ColumnLength COL between 8 and 11
ColumnValues COL matches "[0-9]{3}\\.[0-9]{3}\\.[0-9]{3}-[0-9]{2}"
```

Útil para validar formatos de códigos e documentos.

---

## Parte 5: Custos de IA — Estimativa Prática

### Chamadas de IA por sessão típica (1 tabela, 8 colunas)

| Insight | Chamadas | Tokens estimados | Custo Bedrock (Claude Sonnet) |
|---------|---------|-----------------|-------------------------------|
| Classificação semântica | 8 (1 por coluna) | ~500 in + 200 out cada | ~$0.02 |
| Sugestão de parâmetros | 8 | ~800 in + 300 out cada | ~$0.04 |
| Análise de anomalias | 2-5 (só outliers) | ~600 in + 400 out cada | ~$0.02 |
| Resumo executivo | 1 | ~2000 in + 500 out | ~$0.01 |
| **Total por sessão** | **~20** | | **~$0.09** |

Com cache, sessões repetidas na mesma tabela custam ~$0.00.

### Otimização de custo

- **Batch prompts:** Classificar todas as colunas em 1 chamada (não 8)
- **Cache agressivo:** Mesmo perfil → mesmo insight (TTL 1h)
- **Lazy loading:** Só chamar IA quando o usuário expandir o painel
- **Modelo certo:** Haiku para classificação, Sonnet para análise
