# Fatia 0 — Teste de Viabilidade: CustomSql com WHERE + current_date

> **Objetivo:** Validar se o engine GDQ do Thundera suporta CustomSql com cláusula WHERE
> filtrando por data, usando `current_date` e funções dinâmicas `avg(last(N))`.
>
> **Pré-requisito:** Tabela FULL_SNAPSHOT com partição ≠ coluna de data de negócio.
> Exemplo: partição `dt_carga`, coluna de análise `DT_ABERTURA`, coluna numérica `VLR_SALDO`.
>
> **Como testar:** Baixar o payload JSON na página Teste, editar as regras manualmente
> conforme descrito abaixo, e executar via AWS CLI ou re-upload.

---

## Regras de Teste

Substituir os nomes de coluna (`VLR_SALDO`, `DT_ABERTURA`) pelos da sua tabela real.

### Regra 1 — Controle (built-in, sem WHERE)

**Objetivo:** Confirmar que o setup básico funciona. Se esta falhar, o problema é de configuração.

```
Mean VLR_SALDO >= 0
```

**Resultado esperado:** Passed (assumindo que a média é positiva).

---

### Regra 2 — CustomSql com WHERE + current_date (estático)

**Objetivo:** Validar que `current_date` é resolvido corretamente dentro do CustomSql
e que `from primary WHERE ...` funciona.

```
CustomSql "select avg(cast(VLR_SALDO as double)) from primary where DT_ABERTURA = current_date" >= 0
```

**Resultado esperado:**
- **Passed** → `current_date` funciona, WHERE aceito. Viabilidade confirmada.
- **Failed com valor numérico** → WHERE funcionou mas não há dados para a data de hoje. Trocar por `>=` com data fixa (ver Regra 2b).
- **Failed com erro de sintaxe** → `current_date` não é suportado no engine. Testar alternativas (Regras 2c/2d).

#### Regra 2b — Alternativa com data fixa (se 2 falhar por falta de dados)

Substituir `2026-03-26` pela data de uma partição recente com dados.

```
CustomSql "select avg(cast(VLR_SALDO as double)) from primary where DT_ABERTURA = date '2026-03-26'" >= 0
```

#### Regra 2c — Alternativa com CURRENT_DATE maiúsculo

```
CustomSql "select avg(cast(VLR_SALDO as double)) from primary where DT_ABERTURA = CURRENT_DATE" >= 0
```

#### Regra 2d — Alternativa Spark: current_date()

```
CustomSql "select avg(cast(VLR_SALDO as double)) from primary where DT_ABERTURA = current_date()" >= 0
```

---

### Regra 3 — CustomSql com WHERE + between dinâmico

**Objetivo:** Validar que `avg(last(N))` e `std(last(N))` funcionam no `between`
quando o `select` tem WHERE. Esta é a sintaxe final que o proposer geraria.

```
CustomSql "select avg(cast(VLR_SALDO as double)) from primary where DT_ABERTURA = current_date" between (avg(last(30)) - (3 * std(last(30))) - 0.01) and (avg(last(30)) + (3 * std(last(30))) + 0.01)
```

**Resultado esperado:**
- **Failed na primeira execução** → Normal (sem histórico para `last(30)`)
- **Passed na segunda execução** → Viabilidade total confirmada
- **Erro de sintaxe** → `between` com `avg(last())` incompatível com CustomSql + WHERE

> **Nota:** Esta regra precisa de pelo menos 2 execuções para validar.
> Na primeira, o GDQ não tem histórico e `avg(last(30))` não pode ser calculado.

---

### Regra 4 — CustomSql com date_add (filtro relativo)

**Objetivo:** Validar que funções de data (Athena/Spark) funcionam dentro do CustomSql.

```
CustomSql "select cast(count(*) as double) from primary where DT_ABERTURA >= date_add('day', -7, current_date)" >= 0
```

**Resultado esperado:**
- **Passed** → Funções de data Athena funcionam no engine GDQ.
- **Erro de sintaxe** → O engine GDQ usa dialeto diferente. Testar alternativa Spark:

#### Regra 4b — Alternativa Spark

```
CustomSql "select cast(count(*) as double) from primary where DT_ABERTURA >= date_sub(current_date(), 7)" >= 0
```

---

### Regra 5 — CustomSql com count filtrado (RowCount equivalente)

**Objetivo:** Validar que `count(*)` com WHERE funciona como substituto de RowCount.

```
CustomSql "select cast(count(*) as double) from primary where DT_ABERTURA = current_date" between (avg(last(30)) - (2.0 * std(last(30)))) and (avg(last(30)) + (2.0 * std(last(30))))
```

---

### Regra 6 — CustomSql com stddev filtrado (StdDev equivalente)

**Objetivo:** Validar que `stddev` com WHERE funciona como substituto de StandardDeviation.

```
CustomSql "select stddev(cast(VLR_SALDO as double)) from primary where DT_ABERTURA = current_date" between (avg(last(30)) - (3 * std(last(30))) - 0.01) and (avg(last(30)) + (3 * std(last(30))) + 0.01)
```

---

### Regra 7 — CustomSql com completeness filtrada

**Objetivo:** Validar que ratio `count(col)/count(*)` com WHERE funciona.

```
CustomSql "select cast(count(VLR_SALDO) as double) / nullif(count(*), 0) from primary where DT_ABERTURA = current_date" >= 0.95
```

---

## Formato no Payload JSON

Cada regra vai dentro de `VARIAVEIS.GDQ` como um objeto `RegraGDQ`:

```json
{
  "VARIAVEIS": {
    "GDQ": [
      {"RegraGDQ": "Mean VLR_SALDO >= 0"},
      {"RegraGDQ": "CustomSql \"select avg(cast(VLR_SALDO as double)) from primary where DT_ABERTURA = current_date\" >= 0"},
      {"RegraGDQ": "CustomSql \"select avg(cast(VLR_SALDO as double)) from primary where DT_ABERTURA = current_date\" between (avg(last(30)) - (3 * std(last(30))) - 0.01) and (avg(last(30)) + (3 * std(last(30))) + 0.01)"}
    ]
  }
}
```

> **Atenção ao escaping:** As aspas duplas dentro do valor de `RegraGDQ` devem ser
> escapadas como `\"` no JSON. O `json.dumps` do Python faz isso automaticamente,
> mas ao editar manualmente, garantir que o JSON é válido.

---

## Matriz de Decisão

| Regra 1 | Regra 2 | Regra 3 | Regra 4 | Decisão |
|---------|---------|---------|---------|---------|
| Pass | Pass | Pass* | Pass | **Viável** — implementar Fatias 1-5 |
| Pass | Pass | Pass* | Fail | Viável com restrição — sem funções de data relativa |
| Pass | Pass | Fail | — | **Parcial** — CustomSql + WHERE funciona, mas between dinâmico não. Regras seriam estáticas. |
| Pass | Fail | — | — | **Inviável via current_date** — testar 2b/2c/2d para alternativas |
| Pass (2b) | — | — | — | **Viável com data fixa** — precisaria parametrizar data no payload |
| Fail | — | — | — | **Problema de setup** — revisar configuração |

*Regra 3 precisa de 2+ execuções para validar. Na primeira execução, "Failed" por falta de histórico é esperado.

---

## Coleta de Evidência

Após cada execução, copiar:
1. **Status** de cada regra (Passed/Failed)
2. **EvaluatedRule** (se disponível — mostra os limites compilados)
3. **EvaluatedMetrics** (valor numérico calculado)
4. **FailureReason** (se Failed — distingue erro de sintaxe de valor fora da banda)

Gravar em `reviews/latest/fatia0-thundera-results.md` para referência.
