# GDQ Capability Matrix — Status de Suporte por Tipo de Regra

> **Ultima atualizacao:** 2026-03-17
> **Proposito:** Documentar o status de validacao de cada tipo de regra no runtime real do AWS Glue Data Quality.

---

## Status

| Status | Significado | Acao |
|--------|-------------|------|
| **validated** | Testado e confirmado em producao real | Pode ser usado sem ressalvas |
| **experimental** | Funciona em testes, nao confirmado em producao | Usar com cautela, validar manualmente |
| **unknown** | Sem evidencia de funcionamento | Nao usar ate validar |

---

## Regras Built-in (Sintaxe nativa GDQ)

| RuleType | Sintaxe GDQ | `avg(last(N))` | `std(last(N))` | Status |
|----------|-------------|----------------|-----------------|--------|
| Mean | `Mean COL >= ...` | **validated** | **validated** | **validated** |
| StandardDeviation | `StandardDeviation COL >= ...` | **validated** | **validated** | **validated** |
| RowCount | `RowCount >= ...` | **validated** | **validated** | **validated** |
| Completeness | `Completeness COL >= T` | N/A | N/A | **validated** |
| ColumnValues | `ColumnValues COL in [...]` | N/A | N/A | **validated** |
| DistinctValuesCount | `DistinctValuesCount COL = N` | N/A | N/A | **validated** |
| IsPrimaryKey | `IsPrimaryKey COL1 COL2` | N/A | N/A | **validated** |

---

## Regras CustomSql

### CustomSql Estatico

| RuleType | Sintaxe | `between X and Y` | Status |
|----------|---------|-------------------|--------|
| Frequencia (estatico) | `CustomSql "select ... from primary" between X and Y` | **validated** | **validated** |
| Unicidade | `CustomSql "select count(distinct ...) ..." between 100.0 and 100.0` | **validated** | **validated** |

### CustomSql Dinamico (avg/std no between)

| RuleType | Sintaxe | `avg(last(N))` no between | `std(last(N))` no between | Status |
|----------|---------|---------------------------|---------------------------|--------|
| Frequencia (dinamico) | `CustomSql "..." between (avg(last(N)) - K*std(last(N))) and (...)` | **experimental** | **experimental** | **experimental** |
| Frequencia (hibrido) | `(CustomSql dual guard) AND (CustomSql "..." between floor and ceiling)` | **experimental** | **experimental** | **experimental** |
| Percentil (dinamico) | `CustomSql "select approx_percentile..." between (avg...) and (...)` | **experimental** | **experimental** | **experimental** |

### Notas sobre CustomSql Dinamico

1. **`avg(last(N))` e `std(last(N))` sao suportados no `between` do CustomSql.**
   - Evidencia: `docs/gdq_syntax_reference.md` secao 4b/4c, baseado em exemplos observados.
   - Status: **experimental** — funciona em ambiente de teste, nao temos confirmacao definitiva
     de que o GDQ runtime processa corretamente `avg(last(N))` DENTRO do `between` de um
     `CustomSql` em todos os cenarios.

2. **Risco:** Se o GDQ runtime nao suportar `avg(last(N))` no between de CustomSql,
   as regras dinamicas de frequencia/percentil falharao silenciosamente (ou com erro).

3. **Mitigacao:** Validar via teste real com Thundera (pagina 04_test.py) antes de
   promover para producao. O app marca essas regras com badge "experimental" na UI.

---

## Operacoes Dual Guard (sigma OR margem)

| Operacao | Contexto | Status |
|----------|----------|--------|
| `(A AND B) OR (C AND D)` | Mean, StdDev, RowCount built-in | **validated** |
| `(A AND B) OR (C AND D)` | CustomSql no between | **experimental** |
| `(dual_guard) AND (absolute_check)` | Hibrido (floor/ceiling) | **experimental** |

---

## Limitacoes Conhecidas

1. **CustomSql `from primary`**: Obrigatorio — nao aceita nome de tabela explicito.
2. **CustomSql aspas**: SQL interno usa aspas simples para valores, aspas duplas para colunas.
3. **Frequencia em percentual 0-100**: Nao 0-1. O between deve usar escala 0-100.
4. **IsPrimaryKey colunas separadas por espaco**: Nao por virgula.
5. **Completeness usa `>=`**: Nao `between`.
6. **ColumnValues numeros sem aspas**: `in [2, 1, 3]`, nao `in ['2', '1', '3']`.

---

## Como Validar

1. Gere a regra com o GDQ Rule Proposer
2. Exporte a sintaxe (pagina 03_review.py)
3. Execute teste via Thundera (pagina 04_test.py)
4. Se o teste passar: regra e **validated** para seu ambiente
5. Se falhar: verifique a mensagem de erro e reporte

---

## Historico de Validacao

| Data | RuleType | Ambiente | Resultado | Observacao |
|------|----------|----------|-----------|------------|
| 2026-02-24 | Mean, StdDev, RowCount | Producao | OK | Captura original de exemplos |
| 2026-03-10 | CustomSql frequency static | Teste (Thundera) | OK | Via pagina 04_test.py |
| 2026-03-10 | Completeness, ColumnValues, DistinctValuesCount | Teste | OK | Via Thundera |
| 2026-03-10 | IsPrimaryKey | Teste | OK | Via Thundera |
