# Referência de Sintaxe GDQ — Regras de Qualidade AWS Glue Data Quality

> **Fonte:** Exemplos reais de produção (captura de 24/02/2026)
> **Importante:** Observar rigorosamente maiúsculas/minúsculas, presença/ausência de aspas, e parênteses.

---

## Convenções Gerais

| Aspecto | Regra |
|---------|-------|
| Nomes de coluna | **SEM aspas**, uppercase: `VLR_SALD_AVNC_OPCR` |
| Nomes de regra | **CamelCase**: `Mean`, `StandardDeviation`, `RowCount`, `CustomSql` |
| Funções dinâmicas | `avg(last(N))`, `std(last(N))` — sempre em **lowercase** |
| Valores string em CustomSql | Com aspas simples: `'1'`, `'2'` |
| Valores em ColumnValues | Numéricos sem aspas: `in [2, 1, 3]`; strings com aspas duplas: `in ["SP", "RJ"]`; `NULL` nunca tem aspas |
| Buffer numérico | `0.01` adicionado/subtraído para evitar falso positivo em zero |
| Operadores | `>=`, `<=`, `=`, `in`, `between ... and` |

---

## 1. Mean (Colunas Numéricas) — Padrão "Dual Guard"

### Conceito

A regra Mean usa um padrão **OR** com duas proteções complementares:
- **Guarda A:** Banda baseada em desvio padrão (avg ± K×std)
- **Guarda B:** Banda baseada em margem percentual (avg × margin)

Se qualquer uma das duas bandas for atendida, a regra passa. Isso protege contra:
- Séries estáveis com pouca variação (a margem % evita banda muito apertada)
- Séries voláteis (o desvio padrão acompanha a volatilidade)

### Sintaxe Completa

```
(((Mean {COL} >= (avg(last({N})) - ({K} * std(last({N}))) - {BUFFER})) AND (Mean {COL} <= (avg(last({N})) + ({K} * std(last({N}))) + {BUFFER}))) OR ((Mean {COL} >= (avg(last({N})) * {1-MARGIN}) - {BUFFER}) AND (Mean {COL} <= (avg(last({N})) * {1+MARGIN}) + {BUFFER})))
```

### Parâmetros

| Parâmetro | Valor padrão | Descrição |
|-----------|-------------|-----------|
| `{COL}` | — | Nome da coluna (sem aspas, uppercase) |
| `{N}` | 30 | Número de processamentos no lookback |
| `{K}` | 2 | Multiplicador de desvio padrão (inteiro neste contexto) |
| `{BUFFER}` | 0.01 | Margem absoluta para evitar falso positivo |
| `{MARGIN}` | 0.10 | Margem percentual (0.10 = 10%) |
| `{1-MARGIN}` | 0.9 | Fator inferior da margem |
| `{1+MARGIN}` | 1.1 | Fator superior da margem |

### Exemplo Real

```
(((Mean VLR_SALD_AVNC_OPCR >= (avg(last(30)) - (2 * std(last(30))) - 0.01)) AND (Mean VLR_SALD_AVNC_OPCR <= (avg(last(30)) + (2 * std(last(30))) + 0.01))) OR ((Mean VLR_SALD_AVNC_OPCR >= (avg(last(30)) * 0.9) - 0.01) AND (Mean VLR_SALD_AVNC_OPCR <= (avg(last(30)) * 1.1) + 0.01)))
```

### Decomposição Visual

```
(
  (
    -- GUARDA A: banda σ
    (Mean VLR_SALD_AVNC_OPCR >= (avg(last(30)) - (2 * std(last(30))) - 0.01))
    AND
    (Mean VLR_SALD_AVNC_OPCR <= (avg(last(30)) + (2 * std(last(30))) + 0.01))
  )
  OR
  (
    -- GUARDA B: margem percentual
    (Mean VLR_SALD_AVNC_OPCR >= (avg(last(30)) * 0.9) - 0.01)
    AND
    (Mean VLR_SALD_AVNC_OPCR <= (avg(last(30)) * 1.1) + 0.01)
  )
)
```

---

## 2. StandardDeviation (Colunas Numéricas) — Mesmo Padrão "Dual Guard"

### Sintaxe Completa

```
(((StandardDeviation {COL} >= (avg(last({N})) - ({K} * std(last({N}))) - {BUFFER})) AND (StandardDeviation {COL} <= (avg(last({N})) + ({K} * std(last({N}))) + {BUFFER}))) OR ((StandardDeviation {COL} >= (avg(last({N})) * {1-MARGIN}) - {BUFFER}) AND (StandardDeviation {COL} <= (avg(last({N})) * {1+MARGIN}) + {BUFFER})))
```

### Exemplo Real

```
(((StandardDeviation VLR_PARC_OPCR >= (avg(last(30)) - (2 * std(last(30))) - 0.01)) AND (StandardDeviation VLR_PARC_OPCR <= (avg(last(30)) + (2 * std(last(30))) + 0.01))) OR ((StandardDeviation VLR_PARC_OPCR >= (avg(last(30)) * 0.9) - 0.01) AND (StandardDeviation VLR_PARC_OPCR <= (avg(last(30)) * 1.1) + 0.01)))
```

### Nota Semântica

As funções `avg(last(N))` e `std(last(N))` dentro da regra StandardDeviation referem-se à **média e desvio padrão históricos do desvio padrão calculado em cada processamento**, não da coluna diretamente. Ou seja, o GDQ:
1. Calcula o desvio padrão da coluna no processamento atual
2. Compara com avg/std dos desvios padrão dos últimos N processamentos

---

## 3. RowCount (Regra de Tabela) — Padrão "Dual Guard" (sem buffer)

### Sintaxe Completa

```
(((RowCount >= (avg(last({N})) * 1.0 - ({K} * std(last({N}))))) AND (RowCount <= (avg(last({N})) * 1.0 + ({K} * std(last({N})))))) OR ((RowCount >= (avg(last({N})) - (avg(last({N})) * {MARGIN}))) AND (RowCount <= (avg(last({N})) + (avg(last({N})) * {MARGIN}))))
```

### Parâmetros

| Parâmetro | Valor padrão | Nota |
|-----------|-------------|------|
| `{N}` | 30 | Lookback |
| `{K}` | 2.0 | Sigma (**usa `2.0` float**, não `2` int) |
| `{MARGIN}` | 0.1 | 10% |

### Exemplo Real

```
(((RowCount >= (avg(last(30)) * 1.0 - (2.0 * std(last(30)))))) AND (RowCount <= (avg(last(30)) * 1.0 + (2.0 * std(last(30)))))) OR ((RowCount >= (avg(last(30)) - (avg(last(30)) * 0.1)))) AND (RowCount <= (avg(last(30)) + (avg(last(30)) * 0.1))))
```

### Diferenças em relação ao Mean/StdDev

| Aspecto | Mean/StdDev | RowCount |
|---------|-------------|----------|
| Buffer 0.01 | Sim | **Não** |
| `* 1.0` no avg | Não | **Sim** (`avg(last(30)) * 1.0`) |
| K como float | `2` (int) | `2.0` (float) |
| Formato da margem | `avg * 0.9` / `avg * 1.1` | `avg - (avg * 0.1)` / `avg + (avg * 0.1)` |

---

## 4. CustomSql (Frequência de Categoria)

### Uso

Verificar que a **proporção de uma categoria específica** em uma coluna está dentro de uma faixa esperada. Uma regra CustomSql é gerada **para cada valor** da coluna categórica.

### Sintaxe

```
CustomSql "select cast(sum(case when {COL} = '{VALUE}' then 1 else 0 end) as double) * 100.0 / count(*) from primary" between {LOWER} and {UPPER}
```

### Parâmetros

| Parâmetro | Descrição |
|-----------|-----------|
| `{COL}` | Nome da coluna (sem aspas, uppercase) — dentro do SQL |
| `{VALUE}` | Valor da categoria (com aspas simples dentro do SQL) |
| `{LOWER}` | Percentual mínimo esperado (pode ser negativo como buffer) |
| `{UPPER}` | Percentual máximo esperado |
| `"from primary"` | Referência à tabela sendo avaliada (sempre `primary`) |

### Exemplos Reais

```
CustomSql "select cast(sum(case when COD_SITU_OPCR = '1' then 1 else 0 end) as double) * 100.0 / count(*) from primary" between 85.61 and 97.66
CustomSql "select cast(sum(case when COD_SITU_OPCR = '2' then 1 else 0 end) as double) * 100.0 / count(*) from primary" between 2.31 and 14.35
CustomSql "select cast(sum(case when COD_SITU_OPCR = '3' then 1 else 0 end) as double) * 100.0 / count(*) from primary" between -0.01 and 5.04
```

### Notas Importantes

- O SQL inteiro fica entre **aspas duplas**
- Valores de string dentro do SQL usam **aspas simples**: `= '1'`
- O resultado é em **percentual (0-100)**, não proporção (0-1)
- `LOWER` pode ser negativo (ex: `-0.01`) como buffer para categorias muito raras
- `from primary` é a referência fixa à tabela sendo avaliada
- O `cast(... as double)` é obrigatório para evitar divisão inteira
- Valores de LOWER/UPPER são **estáticos** (calculados pela ferramenta), não dinâmicos

---

## 4b. CustomSql (Frequencia Dinamica)

### Conceito

Versao dinamica da regra de frequencia categorica. Em vez de limites fixos, usa
`avg(last(N))` e `std(last(N))` para calcular a faixa aceita com base no historico.
Segue o padrao dual guard (sigma OR margem).

### Sintaxe

```
(((CustomSql "select cast(sum(case when {COL} = '{VALUE}' then 1 else 0 end) as double) * 100.0 / count(*) from primary" >= (avg(last({N})) - ({K} * std(last({N}))) - {BUFFER})) AND (CustomSql "select cast(sum(case when {COL} = '{VALUE}' then 1 else 0 end) as double) * 100.0 / count(*) from primary" <= (avg(last({N})) + ({K} * std(last({N}))) + {BUFFER}))) OR ((CustomSql "select cast(sum(case when {COL} = '{VALUE}' then 1 else 0 end) as double) * 100.0 / count(*) from primary" >= (avg(last({N})) * {1-MARGIN}) - {BUFFER}) AND (CustomSql "select cast(sum(case when {COL} = '{VALUE}' then 1 else 0 end) as double) * 100.0 / count(*) from primary" <= (avg(last({N})) * {1+MARGIN}) + {BUFFER})))
```

### Parametros

Mesmos do Mean/StdDev dual guard (N, K, BUFFER, MARGIN).

### Quando usar

- Distribuicao categorica com drift lento (ex: migracao de sistema)
- Valores cuja proporcao evolui naturalmente ao longo do tempo
- Quando limites fixos geram falsos positivos frequentes

---

## 4c. CustomSql (Frequencia Hibrida)

### Conceito

Combina a adaptabilidade do modo dinamico com limites absolutos (floor/ceiling).
A regra passa se: (dentro da banda dinamica) **AND** (entre floor e ceiling).

### Sintaxe

```
((DUAL_GUARD_EXPRESSION) AND (CustomSql "..." between {FLOOR} and {CEILING}))
```

Onde `DUAL_GUARD_EXPRESSION` e a mesma expressao da secao 4b (sigma OR margem).

### Parametros adicionais

- `{FLOOR}`: Limite inferior absoluto (percentual 0-100). Ex: `5.0`
- `{CEILING}`: Limite superior absoluto (percentual 0-100). Ex: `50.0`

### Quando usar

- Ha limites de negocio que nunca devem ser violados
  (ex: "categoria X nunca deve passar de 50%")
- Quer adaptabilidade do dinamico mas com guardrails fixos
- Drift e aceitavel dentro de limites conhecidos

### Referencia

Veja ADR-004 para detalhes da decisao de design do modo hibrido.

---

## 5. ColumnValues (Valores Permitidos)

### Sintaxe

```
ColumnValues {COL} in [{VALUE1}, {VALUE2}, {VALUE3}]
```

### Exemplos Reais

```
ColumnValues COD_SITU_OPCR in [2, 1, 3]
ColumnValues UF_EMPR in ["SP", "RJ", "MG"]
ColumnValues STATUS in ["ATIVO", NULL, "INATIVO"]
```

### Notas

- Valores numéricos: **sem aspas** — `in [2, 1, 3]`
- Valores string: **com aspas duplas** — `in ["SP", "RJ", "MG"]`
- `NULL` **nunca** tem aspas — `in ["ATIVO", NULL]`
- Sem aspas no nome da coluna (sempre UPPERCASE)
- Ordem dos valores não importa semanticamente

---

## 6. DistinctValuesCount (Contagem de Valores Distintos)

### Sintaxe (exata)

```
DistinctValuesCount {COL} = {COUNT}
```

### Sintaxe (range)

```
DistinctValuesCount {COL} between {MIN} and {MAX}
```

### Exemplo Real

```
DistinctValuesCount COD_SITU_OPCR = 3
```

---

## 7. Completeness (Completude)

### Sintaxe

```
Completeness {COL} >= {THRESHOLD}
```

### Exemplos Reais

```
Completeness COD_SITU_OPCR >= 1.00
Completeness VLR_CNTR_OPCR >= 1.00
Completeness VLR_PARC_OPCR >= 1.00
Completeness VLR_SALD_VNCD_OPCR >= 1.00
Completeness VLR_SALD_AVNC_OPCR >= 1.00
Completeness VLR_SALD_ABRT_OPCR >= 1.00
Completeness VLR_SALD_DEVE_CTBL >= 1.00
```

### Notas

- Usa `>=`, **não** `between`
- Threshold em decimal (1.00 = 100%, 0.95 = 95%)
- Para colunas que permitem nulos legítimos, ajustar threshold

---

## 8. IsPrimaryKey (Chave Primária)

### Sintaxe

```
IsPrimaryKey {COL1} {COL2} {COL3}
```

### Exemplo Real

```
IsPrimaryKey PK_RIZINPDOC_XX NUM_CTRT_OPCR PK_TPP_XX
```

### Notas

- Múltiplas colunas separadas por **espaço** (não vírgula)
- Sem aspas nos nomes
- Valida unicidade da combinação de colunas

---

## 9. Resumo: Todas as Regras

### Regras Dinâmicas (recalculadas pelo motor GDQ a cada execução)

| Regra | Aplica-se a | Padrão | Funções |
|-------|------------|--------|---------|
| Mean | Coluna numérica | Dual guard (σ OR margem%) | `avg(last(N))`, `std(last(N))` |
| StandardDeviation | Coluna numérica | Dual guard (σ OR margem%) | `avg(last(N))`, `std(last(N))` |
| RowCount | Tabela | Dual guard (σ OR margem%) | `avg(last(N))`, `std(last(N))` |

### Regras Estáticas (valores fixos calculados pela ferramenta)

| Regra | Aplica-se a | Operador |
|-------|------------|----------|
| CustomSql (frequência %) | Coluna categórica | `between X and Y` |
| ColumnValues | Coluna categórica | `in [...]` |
| DistinctValuesCount | Coluna categórica | `= N` ou `between X and Y` |
| Completeness | Qualquer coluna | `>= T` |
| IsPrimaryKey | Colunas (chave) | lista de colunas |

### Implicação para a Ferramenta

- **Regras dinâmicas:** A ferramenta gera a sintaxe parametrizada com `avg(last(N))` / `std(last(N))`. O backtest visual serve para o usuário **validar os parâmetros** (N, K, margem), mas a sintaxe final contém as funções dinâmicas.

- **Regras estáticas:** A ferramenta **calcula os valores** com base no histórico e o usuário ajusta os limites na UI antes de exportar. A sintaxe final contém valores fixos.

---

## 10. Parâmetros Configuráveis pelo Usuário na UI

| Parâmetro | Regras que usam | Control UI | Default |
|-----------|----------------|-----------|---------|
| N (lookback) | Mean, StdDev, RowCount | Slider (5–90) | 30 |
| K (sigma) | Mean, StdDev, RowCount | Select (2 / 3 / Custom) | 2 |
| Margem % | Mean, StdDev, RowCount | Slider (5%–30%) | 10% |
| Buffer | Mean, StdDev | Input (0 / 0.01 / 0.001) | 0.01 |
| Threshold completude | Completeness | Slider (0.90–1.00) | 1.00 |
| Categorias monitoradas | CustomSql freq | Multi-select | Top-K auto |
| Faixa % por categoria | CustomSql freq | Range slider por valor | Calculado |
| Valores permitidos | ColumnValues | Multi-select | Distintos do histórico |
| Colunas de chave | IsPrimaryKey | Multi-select | — |
