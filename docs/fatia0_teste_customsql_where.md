# Fatia 0 — Teste de Viabilidade: CustomSql com WHERE + Filtro por Mês

> **Objetivo:** Validar se o engine GDQ do Thundera suporta CustomSql com cláusula WHERE
> filtrando por período (mês de referência), usando funções de data e `avg(last(N))`.
>
> **Como testar:** Baixar o payload JSON na página Teste, editar as regras manualmente
> conforme descrito abaixo, e executar via AWS CLI ou re-upload.

---

## Contexto da Tabela

| Campo | Valor | Observação |
|-------|-------|------------|
| **Partição** | `ANO_MES_DIA` | Zerada e sobrescrita a cada atualização (FULL_SNAPSHOT) |
| **Coluna numérica** | `VLR_CNTR_LIQO_OPCR` | Decimal — variável alvo para regras de Mean/StdDev |
| **Coluna de data** | `ANO_MES_RFRC_CRED` | Formato `YYYYMM` (string, ex: `"202603"`) — mês de referência |
| **Granularidade** | Mensal | Cada valor de `ANO_MES_RFRC_CRED` = 1 mês de negócio |

**Desafio principal:** `ANO_MES_RFRC_CRED` é string no formato `YYYYMM`, não é `DATE`.
O filtro WHERE precisa comparar string com string, usando `date_format` para gerar
o YYYYMM do mês corrente dinamicamente.

---

## Regras de Teste

### Regra 1 — Controle (built-in, sem WHERE)

**Objetivo:** Confirmar que o setup básico funciona. Se esta falhar, o problema é de configuração.

```
Mean VLR_CNTR_LIQO_OPCR >= 0
```

**Resultado esperado:** Passed (assumindo que a média é positiva).

---

### Regra 2 — CustomSql com WHERE + mês corrente (date_format)

**Objetivo:** Validar que `from primary WHERE ...` funciona e que conseguimos
gerar o YYYYMM do mês corrente dinamicamente.

O engine GDQ roda sobre Spark, então `date_format(current_date(), 'yyyyMM')` deve
retornar `"202603"` (março 2026).

```
CustomSql "select avg(cast(VLR_CNTR_LIQO_OPCR as double)) from primary where ANO_MES_RFRC_CRED = date_format(current_date(), 'yyyyMM')" >= 0
```

**Resultado esperado:**
- **Passed** → WHERE + date_format funciona. Viabilidade confirmada.
- **Failed com valor numérico** → WHERE funcionou mas não há dados para o mês corrente. Testar Regra 2b.
- **Failed com erro de sintaxe** → `date_format` ou `current_date()` não funciona. Testar alternativas.

#### Regra 2b — Alternativa com mês fixo (se 2 falhar por falta de dados)

Substituir `202603` pelo mês mais recente com dados na tabela.

```
CustomSql "select avg(cast(VLR_CNTR_LIQO_OPCR as double)) from primary where ANO_MES_RFRC_CRED = '202603'" >= 0
```

#### Regra 2c — Alternativa: concat + year + month

Se `date_format` não funcionar, testar composição manual:

```
CustomSql "select avg(cast(VLR_CNTR_LIQO_OPCR as double)) from primary where ANO_MES_RFRC_CRED = concat(cast(year(current_date()) as string), lpad(cast(month(current_date()) as string), 2, '0'))" >= 0
```

#### Regra 2d — Alternativa: substring de current_date cast

```
CustomSql "select avg(cast(VLR_CNTR_LIQO_OPCR as double)) from primary where ANO_MES_RFRC_CRED = replace(substr(cast(current_date() as string), 1, 7), '-', '')" >= 0
```

> **Nota sobre as alternativas:** Testar em ordem (2 → 2b → 2c → 2d).
> Se a Regra 2b (mês fixo) passar, sabemos que WHERE funciona e o problema é só
> na geração dinâmica do YYYYMM. Se 2b também falhar, o problema é no WHERE em si.

---

### Regra 3 — CustomSql com WHERE + between dinâmico (avg/std)

**Objetivo:** Validar que `avg(last(N))` e `std(last(N))` funcionam no `between`
quando o `select` tem WHERE. Esta é a **sintaxe final** que o proposer geraria.

```
CustomSql "select avg(cast(VLR_CNTR_LIQO_OPCR as double)) from primary where ANO_MES_RFRC_CRED = date_format(current_date(), 'yyyyMM')" between (avg(last(30)) - (3 * std(last(30))) - 0.01) and (avg(last(30)) + (3 * std(last(30))) + 0.01)
```

**Resultado esperado:**
- **Failed na primeira execução** → Normal (sem histórico para `last(30)`).
- **Passed ou Failed com valor numérico na segunda execução** → Viabilidade total confirmada.
- **Erro de sintaxe** → `between` com `avg(last())` incompatível com CustomSql + WHERE.

> **Importante:** Esta regra precisa de pelo menos **2 execuções** para validar.
> Na primeira, o GDQ não tem histórico e `avg(last(30))` não pode ser calculado.

#### Regra 3b — Alternativa com between fixo (se 3 der erro de sintaxe)

Isolar se o problema é o between dinâmico ou o WHERE:

```
CustomSql "select avg(cast(VLR_CNTR_LIQO_OPCR as double)) from primary where ANO_MES_RFRC_CRED = date_format(current_date(), 'yyyyMM')" between 0 and 999999999
```

Se 3b passar e 3 falhar, o problema é a combinação WHERE + avg(last(N)).

---

### Regra 4 — Filtro de mês anterior (aritmética de datas)

**Objetivo:** Validar que conseguimos fazer aritmética de meses dentro do CustomSql.
Útil para lookback de N meses (ex: últimos 6 meses de referência).

```
CustomSql "select cast(count(*) as double) from primary where ANO_MES_RFRC_CRED >= date_format(add_months(current_date(), -6), 'yyyyMM')" >= 0
```

**Resultado esperado:**
- **Passed** → `add_months` + `date_format` funciona. Podemos gerar filtros de janela.
- **Erro de sintaxe** → Testar alternativa:

#### Regra 4b — Alternativa: cast aritmético sobre inteiro

```
CustomSql "select cast(count(*) as double) from primary where cast(ANO_MES_RFRC_CRED as int) >= cast(date_format(add_months(current_date(), -6), 'yyyyMM') as int)" >= 0
```

#### Regra 4c — Alternativa com mês fixo (fallback)

Substituir `202509` por um mês 6 meses atrás com dados reais:

```
CustomSql "select cast(count(*) as double) from primary where ANO_MES_RFRC_CRED >= '202509'" >= 0
```

---

### Regra 5 — RowCount filtrado com between dinâmico

**Objetivo:** Validar que `count(*)` filtrado com between dinâmico funciona
(substituto de RowCount para dados de um mês específico).

```
CustomSql "select cast(count(*) as double) from primary where ANO_MES_RFRC_CRED = date_format(current_date(), 'yyyyMM')" between (avg(last(30)) - (2.0 * std(last(30)))) and (avg(last(30)) + (2.0 * std(last(30))))
```

> Mesma nota: precisa 2+ execuções por causa do `last(30)`.

---

### Regra 6 — StdDev filtrado

**Objetivo:** Validar que `stddev` com WHERE funciona como substituto de StandardDeviation.

```
CustomSql "select stddev(cast(VLR_CNTR_LIQO_OPCR as double)) from primary where ANO_MES_RFRC_CRED = date_format(current_date(), 'yyyyMM')" between (avg(last(30)) - (3 * std(last(30))) - 0.01) and (avg(last(30)) + (3 * std(last(30))) + 0.01)
```

---

### Regra 7 — Completeness filtrada

**Objetivo:** Validar que ratio `count(col)/count(*)` com WHERE funciona.

```
CustomSql "select cast(count(VLR_CNTR_LIQO_OPCR) as double) / nullif(count(*), 0) from primary where ANO_MES_RFRC_CRED = date_format(current_date(), 'yyyyMM')" >= 0.95
```

---

## Formato no Payload JSON

Cada regra vai dentro de `VARIAVEIS.GDQ` como um objeto `RegraGDQ`.
As aspas duplas internas devem ser escapadas como `\"`:

```json
{
  "VARIAVEIS": {
    "GDQ": [
      {
        "RegraGDQ": "Mean VLR_CNTR_LIQO_OPCR >= 0"
      },
      {
        "RegraGDQ": "CustomSql \"select avg(cast(VLR_CNTR_LIQO_OPCR as double)) from primary where ANO_MES_RFRC_CRED = date_format(current_date(), 'yyyyMM')\" >= 0"
      },
      {
        "RegraGDQ": "CustomSql \"select avg(cast(VLR_CNTR_LIQO_OPCR as double)) from primary where ANO_MES_RFRC_CRED = date_format(current_date(), 'yyyyMM')\" between (avg(last(30)) - (3 * std(last(30))) - 0.01) and (avg(last(30)) + (3 * std(last(30))) + 0.01)"
      },
      {
        "RegraGDQ": "CustomSql \"select cast(count(*) as double) from primary where ANO_MES_RFRC_CRED >= date_format(add_months(current_date(), -6), 'yyyyMM')\" >= 0"
      },
      {
        "RegraGDQ": "CustomSql \"select cast(count(*) as double) from primary where ANO_MES_RFRC_CRED = date_format(current_date(), 'yyyyMM')\" between (avg(last(30)) - (2.0 * std(last(30)))) and (avg(last(30)) + (2.0 * std(last(30))))"
      },
      {
        "RegraGDQ": "CustomSql \"select stddev(cast(VLR_CNTR_LIQO_OPCR as double)) from primary where ANO_MES_RFRC_CRED = date_format(current_date(), 'yyyyMM')\" between (avg(last(30)) - (3 * std(last(30))) - 0.01) and (avg(last(30)) + (3 * std(last(30))) + 0.01)"
      },
      {
        "RegraGDQ": "CustomSql \"select cast(count(VLR_CNTR_LIQO_OPCR) as double) / nullif(count(*), 0) from primary where ANO_MES_RFRC_CRED = date_format(current_date(), 'yyyyMM')\" >= 0.95"
      }
    ]
  }
}
```

> **Dica:** Validar o JSON em jsonlint.com ou similar antes de submeter.
> Um `\"` faltando quebra o payload inteiro.

---

## Ordem de Execução Recomendada

**Rodada 1 — Validação básica (regras 1, 2, 2b, 4c, 7):**

Começa pelas regras mais simples para isolar problemas rapidamente.

| Ordem | Regra | O que valida |
|-------|-------|-------------|
| 1 | Regra 1 | Setup OK, tabela acessível |
| 2 | Regra 2b (mês fixo `'202603'`) | WHERE funciona com string literal |
| 3 | Regra 2 (date_format dinâmico) | date_format + current_date() funciona |
| 4 | Regra 4c (mês fixo janela) | WHERE com `>=` funciona |
| 5 | Regra 7 (completeness) | Expressão aritmética no SELECT + WHERE |

**Rodada 2 — Validação dinâmica (regras 3b, 3, 4, 5, 6):**

Só faz sentido se a Rodada 1 passar.

| Ordem | Regra | O que valida |
|-------|-------|-------------|
| 6 | Regra 3b (between fixo + WHERE) | between estático + WHERE combinados |
| 7 | Regra 4 (add_months dinâmico) | Aritmética de meses |
| 8 | Regra 3 (between dinâmico) | avg(last(N)) + WHERE — **precisa 2 execuções** |
| 9 | Regra 5 (RowCount dinâmico) | count(*) + between dinâmico + WHERE |
| 10 | Regra 6 (StdDev dinâmico) | stddev + between dinâmico + WHERE |

---

## Matriz de Decisão

| Regra 1 | Regra 2b | Regra 2 | Regra 3 | Regra 4 | Decisão |
|---------|----------|---------|---------|---------|---------|
| Pass | Pass | Pass | Pass* | Pass | **Viável** — implementar Fatias 1-5 com date_format dinâmico |
| Pass | Pass | Pass | Pass* | Fail | Viável — sem aritmética de meses (add_months), usar string literal |
| Pass | Pass | Pass | Fail | — | **Parcial** — WHERE + date_format funciona, mas between dinâmico não. Regras estáticas only. |
| Pass | Pass | Fail | — | — | **Viável com mês fixo** — WHERE funciona, mas date_format não. Precisaria parametrizar mês no payload. |
| Pass | Pass (2c/2d) | — | — | — | Viável com sintaxe alternativa para YYYYMM |
| Pass | Fail | — | — | — | **Inviável** — WHERE não funciona no CustomSql do GDQ |
| Fail | — | — | — | — | **Problema de setup** — revisar configuração da tabela |

*Regra 3 precisa de 2+ execuções para validar. "Failed" na primeira execução é esperado.

---

## Coleta de Evidência

Após cada execução, anotar para cada regra:

| Campo | Onde encontrar | Exemplo |
|-------|---------------|---------|
| **Status** | Outcome | Passed / Failed |
| **Valor calculado** | EvaluatedMetrics | `{"Dataset.*.CustomSQL": 1523.45}` |
| **Regra compilada** | EvaluatedRule | Mostra limites expandidos de avg/std |
| **Motivo da falha** | FailureReason | Distingue erro de sintaxe vs valor fora da banda |

**Erro de sintaxe** no FailureReason geralmente contém: `AnalysisException`, `ParseException`,
`cannot resolve`, `Column not found`, ou `Syntax error`.

**Valor fora da banda** no FailureReason contém: `Value`, `expected`, `threshold`, `between`.

Gravar resultados em `reviews/latest/fatia0-thundera-results.md` para referência.
