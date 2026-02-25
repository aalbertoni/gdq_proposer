# ADR-002: RowCount Strategy como Python Protocol

- **Status:** Aceito
- **Data:** 2026-02-10
- **Decisores:** Equipe GDQ Rule Proposer

---

## Contexto

O GDQ Rule Proposer precisa gerar regras de RowCount (volume de linhas
por periodo) para detectar cargas anomalas. A abordagem default usa
banda estatistica (sigma + margem), mas equipes enterprise podem ter
necessidades diferentes:

- **Sazonalidade:** Tabelas de vendas com volume maior em fins de semana
  ou meses especificos (ex: dezembro)
- **Calendario de negocios:** Dias uteis vs feriados, fechamentos
  mensais com volume diferente
- **Regras de negocio customizadas:** Volume minimo fixo, ou proporcional
  a outra metrica
- **Modelos avancados:** Previsao com ARIMA, Prophet ou outros modelos
  de series temporais

A logica de RowCount precisa ser extensivel sem modificar o core.

---

## Decisao

Usar um `@runtime_checkable Protocol` do Python como contrato para
estrategias de RowCount. A implementacao default
`GenericBandRowCountStrategy` reutiliza o pipeline existente do core.

### Protocol

```python
@runtime_checkable
class RowCountStrategy(Protocol):
    def propose(
        self,
        row_counts: list[float],
        dates: list[str],
        table: str,
        baseline: BaselineStrategy,
    ) -> RuleProposal | None:
        ...

    def recalculate(
        self,
        proposal: RuleProposal,
        new_baseline: BaselineStrategy,
    ) -> RuleProposal:
        ...
```

### Uso no ProposalService

```python
def propose_table_rules(
    self,
    row_count_history: pd.DataFrame,
    table: str,
    baseline: BaselineStrategy,
    strategy=None,  # aceita qualquer RowCountStrategy
) -> list[RuleProposal]:
    if strategy is None:
        from strategies.row_count_strategy import GenericBandRowCountStrategy
        strategy = GenericBandRowCountStrategy()
    ...
```

### Implementacao default

`GenericBandRowCountStrategy` reutiliza:
- `statistical_engine.compute_dynamic_band()` para banda sigma
- `statistical_engine.compute_margin_band()` para banda margem
- `backtest.backtest_band()` para simulacao historica
- `rule_scoring.score_proposal()` para avaliacao composta
- `GDQRuleGenerator.generate()` para sintaxe GDQ

---

## Alternativas Consideradas

### 1. ABC (Abstract Base Class)

- **Pros:** Forca implementacao de metodos, erro claro se algo faltar
- **Contras:** Requer heranca, o que acopla plugins ao nosso codigo base.
  Incompativel com classes de terceiros que nao herdam do ABC.

### 2. Interface via duck typing puro (sem Protocol)

- **Pros:** Nenhum acoplamento, qualquer objeto funciona
- **Contras:** Sem verificacao de tipo, erros so aparecem em runtime.
  IDEs nao conseguem oferecer autocomplete ou deteccao de erros.

### 3. Strategy via configuracao (dict/YAML)

- **Pros:** Extensivel sem codigo Python
- **Contras:** Limita a logica a parametros pre-definidos. Nao permite
  logica customizada complexa (ex: consultar calendario de feriados).

### 4. Classe base concreta com hooks (template method)

- **Pros:** Reutiliza pipeline padrao, so sobrescreve partes
- **Contras:** Heranca profunda dificulta composicao. Se o pipeline
  default mudar, plugins podem quebrar.

---

## Consequencias

### Positivas

- **Extensibilidade real:** Equipes enterprise podem implementar estrategias
  arbitrariamente complexas sem tocar no core
- **Compatibilidade estrutural:** `@runtime_checkable` permite verificar
  em runtime se um objeto implementa o Protocol, sem exigir heranca
- **Sem acoplamento:** Plugins nao precisam importar nossa classe base.
  Qualquer objeto com os metodos `propose()` e `recalculate()` funciona
- **Testavel:** Facil de criar mocks para testes
- **Default robusto:** A `GenericBandRowCountStrategy` cobre 90% dos
  casos sem necessidade de customizacao

### Negativas

- **Indire cao adicional:** O parametro `strategy` no `propose_table_rules()`
  adiciona um nivel de indirecao. Para usuarios que so usam o default,
  isso e overhead desnecessario. Mitigado pelo default `None` com lazy
  import.
- **Lazy import:** O import da `GenericBandRowCountStrategy` dentro do
  metodo (ao inves de no topo do arquivo) e necessario para evitar
  dependencias circulares, mas e menos obvio.
- **Tipagem parcial:** O parametro `strategy` nao tem type hint explicito
  para evitar import circular. IDEs nao conseguem inferir o tipo.

---

## Notas de Implementacao

- Arquivo: `strategies/row_count_strategy.py`
- O Protocol define 2 metodos: `propose()` e `recalculate()`
- `GenericBandRowCountStrategy` inicializa seu proprio `GDQRuleGenerator`
- O lazy import em `ProposalService.propose_table_rules()` evita
  circular dependency entre `proposal_service` -> `row_count_strategy` -> core
- Para usar uma estrategia customizada:

```python
class MySeasonalStrategy:
    def propose(self, row_counts, dates, table, baseline):
        # logica sazonal customizada
        ...
    def recalculate(self, proposal, new_baseline):
        ...

# Na UI ou no script:
proposals = proposal_service.propose_table_rules(
    row_count_history=df,
    table="minha_tabela",
    baseline=baseline,
    strategy=MySeasonalStrategy(),
)
```
