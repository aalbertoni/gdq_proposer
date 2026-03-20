"""
Pagina 05 — Ajuda: Documentacao completa do usuario.

Guia de uso da ferramenta GDQ Rule Proposer com explicacoes
de conceitos, fluxo de trabalho e perguntas frequentes.
"""

import streamlit as st


st.set_page_config(
    page_title="Ajuda - GDQ Rule Proposer",
    page_icon=":question:",
)

st.title("Ajuda")
st.caption(
    "Documentacao completa do GDQ Rule Proposer. "
    "Use as secoes abaixo para entender como a ferramenta funciona "
    "e como tirar o melhor proveito das regras propostas."
)


# =====================================================================
# Section rendering functions
# =====================================================================


def _render_intro():
    """Sections 1 (Introducao) + 2 (Fluxo de Trabalho)."""

    # -----------------------------------------------------------------
    # Introducao
    # -----------------------------------------------------------------

    st.subheader("Introducao")

    st.markdown(
        "O **GDQ Rule Proposer** e uma ferramenta que analisa o historico de dados "
        "de uma tabela e propoe regras de qualidade para o "
        "**AWS Glue Data Quality (GDQ)**."
    )

    st.markdown(
        "A ferramenta consulta dados agregados via **Amazon Athena**, "
        "calcula estatisticas sobre o comportamento historico das "
        "colunas e da tabela, e gera regras prontas para copiar e colar no GDQ."
    )

    st.info(
        "Voce **nao** precisa conhecer a sintaxe GDQ para usar esta ferramenta. "
        "Todas as regras sao explicadas em linguagem natural e podem ser exportadas "
        "como arquivo de texto."
    )

    with st.expander("Para quem e esta ferramenta?"):
        st.markdown(
            "- **Analistas de dados** que querem monitorar a qualidade de tabelas "
            "no data lake\n"
            "- **Engenheiros de dados** que precisam configurar regras GDQ de forma "
            "rapida e baseada em evidencia\n"
            "- **Equipes de governanca** que querem padronizar a criacao de regras "
            "de qualidade com base no historico real dos dados\n\n"
            "A ferramenta e util especialmente quando voce tem tabelas com muitas "
            "colunas e precisa definir limites (thresholds) que facam sentido "
            "para os dados reais, em vez de chutar valores arbitrarios."
        )

    # -----------------------------------------------------------------
    # Fluxo de Trabalho
    # -----------------------------------------------------------------

    st.subheader("Fluxo de Trabalho")

    st.markdown(
        "O processo segue 4 etapas sequenciais. "
        "Cada etapa corresponde a uma pagina no menu lateral."
    )

    st.subheader("Etapa 1 — Home")
    st.markdown(
        "A pagina inicial mostra o **status da conexao** com o Athena, "
        "as **tabelas disponiveis** e um preview das colunas. "
        "Use essa pagina para verificar que o ambiente esta funcionando antes "
        "de comecar."
    )

    st.subheader("Etapa 2 — Setup")
    st.markdown(
        "Configuracao da tabela alvo. O wizard guia voce por 7 passos:"
    )
    st.markdown(
        "- **Passo 1 — Tabela:** selecione o schema e a tabela, depois clique em "
        "\"Validar Tabela\" para confirmar que ela existe\n"
        "- **Passo 2 — Eixo temporal:** escolha a coluna de data que define os "
        "periodos de analise (ex: `dt_ref`, `data_carga`). Se a coluna for do tipo "
        "string, a ferramenta oferece um seletor de formato para gerar a expressao "
        "SQL correta automaticamente. Configure tambem a granularidade (diario/mensal) "
        "e o lookback (quantos periodos recentes analisar)\n"
        "- **Passo 3 — Filtro base:** opcionalmente, defina um filtro WHERE que sera "
        "aplicado em todas as queries (ex: `IND_ATIVO = 1`)\n"
        "- **Passo 4 — Validar configuracao:** a ferramenta consulta o range temporal "
        "e confirma quantos periodos estao disponiveis\n"
        "- **Passo 5 — Profiling:** classificacao automatica de cada coluna "
        "(numerica, categorica, data, etc.)\n"
        "- **Passo 6 — Selecao de colunas:** revise a classificacao e selecione quais "
        "colunas devem receber regras. Voce pode alterar o tipo semantico manualmente\n"
        "- **Passo 7 — Ativar:** salve a configuracao na sessao e (opcionalmente) "
        "como preset reutilizavel"
    )

    st.subheader("Etapa 3 — Explore (Calibracao)")
    st.markdown(
        "Para cada coluna numerica e para a tabela inteira, a ferramenta propoe "
        "regras com parametros ajustaveis. Voce pode:"
    )
    st.markdown(
        "- Ajustar os 4 parametros (N, K, Margem, Buffer) usando sliders\n"
        "- Usar o botao **Sugerir melhor combinacao** para auto-tuning\n"
        "- Visualizar o grafico interativo com as bandas de aceitacao\n"
        "- Ver as metricas do backtest (cobertura, falsos positivos, estabilidade)\n"
        "- Ler a explicacao em linguagem natural de cada regra\n"
        "- Adicionar regras aprovadas ao carrinho"
    )
    st.markdown(
        "A pagina tem 4 abas: **Numericas** (Mean, StdDev, Completeness por coluna), "
        "**Categoricas** (AllowedValues, DistinctValuesCount, Frequencia em 3 modos por coluna), "
        "**Tabela** (RowCount) e **Resumo** (regras no carrinho)."
    )

    st.subheader("Etapa 4 — Review & Export")
    st.markdown(
        "Revise todas as regras no carrinho. Para cada regra voce pode:"
    )
    st.markdown(
        "- Habilitar ou desabilitar individualmente (sem remover do carrinho)\n"
        "- Ver a sintaxe GDQ final e a explicacao detalhada\n"
        "- Remover regras que nao fizerem mais sentido\n"
        "- Baixar um arquivo `.txt` com todas as regras habilitadas\n"
        "- Copiar a sintaxe diretamente do bloco de codigo exibido na tela"
    )


def _render_conceitos():
    """Section 3 (Conceitos Principais)."""

    st.subheader("Conceitos Principais")

    st.markdown(
        "Estes sao os conceitos centrais da ferramenta. "
        "Para uma referencia rapida de todos os termos, veja o **Glossario** no final da pagina."
    )

    with st.expander("Dual Guard (banda dupla)"):
        st.markdown(
            "O **dual guard** e o mecanismo central de validacao. Cada regra dinamica "
            "combina **duas bandas** com logica OR:\n\n"
            "- **Banda sigma:** media historica +/- K desvios padrao. "
            "Captura a variabilidade natural dos dados. Se os dados sao estaveis, "
            "a banda e estreita; se sao volateis, a banda e larga.\n"
            "- **Banda margem:** media historica +/- X%. "
            "Funciona como rede de seguranca quando a banda sigma e muito estreita "
            "(ex: dados quase constantes onde o desvio padrao e proximo de zero).\n\n"
            "A regra **passa** se o valor atual estiver dentro de **qualquer uma** "
            "das duas bandas. Isso reduz falsos positivos sem perder sensibilidade."
        )
        st.markdown(
            "**Exemplo pratico:** uma coluna com media 100 e desvio padrao 2, "
            "usando K=2 e margem 10%:\n"
            "- Banda sigma: 96 a 104\n"
            "- Banda margem: 90 a 110\n"
            "- Se o valor for 108, a banda sigma reprovaria, mas a margem aceita "
            "-- a regra passa."
        )

    with st.expander("Parametros de calibracao (N, K, Margem%, Buffer)"):
        st.markdown(
            "Cada regra dinamica tem 4 parametros ajustaveis:\n\n"
            "- **N (periodos):** tamanho da janela movel de historico. "
            "Exemplo: N=20 significa que a regra considera os ultimos 20 periodos "
            "para calcular media e desvio padrao. Valores maiores suavizam variacao "
            "mas podem incluir dados desatualizados. Valores menores reagem mais rapido "
            "a mudancas recentes.\n\n"
            "- **K (sigma):** multiplicador do desvio padrao para a banda sigma. "
            "K=2 significa que a banda vai de (media - 2 desvios) ate (media + 2 desvios), "
            "o que cobre aproximadamente 95% dos dados normais. "
            "K=3 cobre ~99.7%. Valor menor = regra mais rigorosa.\n\n"
            "- **Margem % (margin):** largura da banda alternativa, em porcentagem da media. "
            "Margem=10% significa que a banda vai de (media * 0.9) ate (media * 1.1). "
            "Funciona como rede de seguranca quando a banda sigma e muito estreita. "
            "Pode ser desativada via checkbox se voce preferir usar apenas a banda sigma.\n\n"
            "- **Buffer:** valor minimo adicionado aos limites para proteger contra "
            "falsos positivos por arredondamento. Tipicamente 0.01. "
            "Em regras de RowCount, o buffer e 0 (desabilitado)."
        )

    with st.expander("Backtest"):
        st.markdown(
            "O **backtest** simula a regra no historico passado para medir "
            "como ela teria se comportado. Ele responde a pergunta: "
            "\"Se esta regra estivesse ativa nos ultimos N periodos, quantas vezes "
            "ela teria disparado alarme?\"\n\n"
            "O backtest usa uma **janela rolante**: para cada periodo, ele calcula "
            "a banda usando os N periodos **anteriores** e verifica se o valor "
            "daquele periodo esta dentro. Isso simula o comportamento real da regra "
            "em producao.\n\n"
            "**Metricas do backtest:**\n"
            "- **Cobertura:** porcentagem de periodos que passariam na regra. "
            "Ideal: acima de 90%\n"
            "- **Falsos positivos (~N):** estimativa de periodos normais que "
            "seriam reprovados indevidamente. Usa heuristica de 4 sigma global "
            "para distinguir valores normais de outliers reais. "
            "Ideal: 0 ou proximo de 0. Veja mais em \"O que significam os "
            "falsos positivos?\"\n"
            "- **Estabilidade:** quao pouco a banda muda ao variar os parametros. "
            "1.0 = muito estavel. Abaixo de 0.5 pode indicar instabilidade\n"
            "- **Outliers:** periodos com valores atipicos detectados no historico"
        )

    with st.expander("Confianca (HIGH / MEDIUM / LOW)"):
        st.markdown(
            "A **confianca** e uma avaliacao geral da qualidade da regra proposta, "
            "baseada nas metricas do backtest:\n\n"
            "- **HIGH (verde):** regra recomendada para producao. "
            "Boa cobertura, poucos falsos positivos, banda estavel. "
            "Pode ser exportada com seguranca.\n\n"
            "- **MEDIUM (laranja):** regra que precisa de revisao. "
            "Pode ter cobertura moderada ou instabilidade. "
            "Considere ajustar os parametros (aumentar N, ajustar K ou margem) "
            "antes de exportar.\n\n"
            "- **LOW (vermelho):** regra nao recomendada. "
            "Alta taxa de falsos positivos ou banda muito instavel. "
            "Pode indicar que os dados nao se prestam a esse tipo de regra "
            "ou que ha drift no historico."
        )

    with st.expander("Drift (tendencia)"):
        st.markdown(
            "**Drift** e uma tendencia de crescimento ou queda nos dados ao longo "
            "do tempo. Quando a ferramenta detecta drift, significa que o valor "
            "esta mudando sistematicamente (nao aleatoriamente).\n\n"
            "Isso e relevante porque as bandas sao calculadas sobre o historico. "
            "Se ha uma tendencia, a banda pode ficar desalinhada com os valores "
            "mais recentes.\n\n"
            "**O que fazer:**\n"
            "- Reduza o N (janela) para usar dados mais recentes e acompanhar "
            "a tendencia\n"
            "- Aumente a margem para acomodar a variacao\n"
            "- Investigue se o drift e esperado (ex: crescimento natural) ou "
            "indica um problema nos dados"
        )

    with st.expander("Tipos de regra"):
        st.markdown("**Regras de coluna numerica (dinamicas):**")
        st.markdown(
            "- **Mean (media):** verifica se a media da coluna esta dentro da banda "
            "esperada. Detecta mudancas no nivel dos dados (ex: valores sistematicamente "
            "maiores ou menores que o normal). Usa dual guard com `avg(last(N))` e `std(last(N))`.\n"
            "- **StdDev (desvio padrao):** verifica se o desvio padrao da coluna "
            "esta dentro do esperado. Detecta mudancas na dispersao (ex: dados "
            "ficaram muito mais volateis ou muito mais homogeneos). Mesmo padrao dual guard.\n"
            "- **Percentil (analise):** analisa a distribuicao via percentis P5 e P95 "
            "para identificar caudas extremas. Usado como insumo de analise para "
            "calibrar outras regras."
        )
        st.markdown("**Regras de coluna categorica:**")
        st.markdown(
            "- **AllowedValues (valores permitidos):** verifica se todos os valores "
            "da coluna pertencem a uma lista fixa. Qualquer valor fora da lista "
            "reprova a regra. Util para colunas com dominio estavel (ex: UF, status). "
            "Regra estatica.\n"
            "- **DistinctValuesCount (distintos):** verifica se o numero de valores "
            "distintos esta correto (exato ou dentro de um range). Detecta se valores "
            "sumiram ou apareceram. Regra estatica.\n"
            "- **Frequencia estatica (CustomSql):** verifica se a proporcao de "
            "cada valor esta dentro de uma faixa fixa (between X and Y). "
            "Calculada com base no historico, mas nao se auto-ajusta.\n"
            "- **Frequencia dinamica (CustomSql):** como a estatica, mas usa "
            "`avg(last(N))` e `std(last(N))` para auto-ajustar os limites "
            "a cada execucao. Ideal para distribuicoes que mudam gradualmente.\n"
            "- **Frequencia hibrida (CustomSql):** combina modo dinamico com "
            "floor/ceiling absolutos. O dual guard se auto-ajusta, mas o resultado "
            "e validado AND com limites fixos de negocio."
        )
        st.markdown("**Regras de tabela e chave:**")
        st.markdown(
            "- **RowCount (volume):** verifica se a quantidade de linhas por periodo "
            "esta dentro do esperado. Detecta cargas com volume anomalo "
            "(muito acima ou muito abaixo do normal). Dinamica com dual guard.\n"
            "- **IsPrimaryKey (chave primaria):** verifica se uma combinacao de "
            "colunas nao tem duplicatas. Util para validar integridade referencial. "
            "Regra estatica.\n"
            "- **Unicidade (CustomSql):** verifica que o COUNT(DISTINCT) de uma "
            "coluna e 100% dos registros. Util para colunas que devem ser unicas "
            "individualmente."
        )
        st.markdown("**Regra geral:**")
        st.markdown(
            "- **Completeness (completude):** verifica se a porcentagem de valores "
            "nao-nulos esta acima de um limite. Aplica-se a qualquer tipo de coluna. "
            "Util para colunas que devem estar sempre preenchidas. Regra estatica."
        )

    with st.expander("Classificacao de colunas (profiling)"):
        st.markdown(
            "O profiling analisa cada coluna e classifica em um tipo semantico:\n\n"
            "- **Numerico:** colunas int, double, float, ou strings com mais de "
            "95% dos valores castaveis para numero. Geram regras Mean e StdDev.\n"
            "- **Categorico (low):** ate ~50 valores distintos. Dominio fixo "
            "(ex: UF, tipo de operacao, status).\n"
            "- **Categorico (mid):** entre ~50 e ~500 valores distintos.\n"
            "- **Categorico (high):** mais de ~500 valores distintos. "
            "Tipicamente identificadores ou texto livre.\n"
            "- **Data/hora:** colunas de tipo date ou timestamp. "
            "Normalmente usadas como eixo temporal.\n"
            "- **Identificador:** colunas de alta cardinalidade reconhecidas "
            "como chaves.\n\n"
            "Voce pode alterar a classificacao manualmente no passo 6 do Setup "
            "se a inferencia automatica nao estiver correta."
        )

    with st.expander("Cardinalidade de colunas categoricas"):
        st.markdown(
            "A **cardinalidade** indica quantos valores distintos uma coluna categorica "
            "possui. A ferramenta classifica automaticamente em tres niveis:\n\n"
            "- **Baixa (low):** ate ~50 valores distintos. Dominio fixo e pequeno. "
            "Exemplos: UF, status, tipo de operacao. "
            "Gera regras de: valores permitidos, contagem de distintos (exata), "
            "frequencia por categoria, completude.\n"
            "- **Media (mid):** entre ~50 e ~500 valores distintos. "
            "Exemplos: cidade, codigo de produto. "
            "Gera regras de: contagem de distintos (range), frequencia top-K, completude.\n"
            "- **Alta (high):** mais de ~500 valores distintos. "
            "Exemplos: CPF, ID de transacao. "
            "Gera apenas: completude. Regras de dominio nao sao recomendadas."
        )

    with st.expander("Regras estaticas vs. dinamicas vs. hibridas"):
        st.markdown(
            "As regras da ferramenta se dividem em tres modos:\n\n"
            "**Regras dinamicas** (numericas, volume e categoricas):\n"
            "- Mean, StdDev, RowCount e Frequencia Dinamica\n"
            "- Usam funcoes `avg(last(N))` e `std(last(N))` na sintaxe GDQ\n"
            "- O GDQ **recalcula automaticamente** os limites a cada execucao\n"
            "- Nao precisam de manutencao manual\n\n"
            "**Regras estaticas** (categoricas):\n"
            "- AllowedValues, DistinctValuesCount, Frequencia Estatica, IsPrimaryKey\n"
            "- Os valores/limites sao **fixos** na sintaxe GDQ\n"
            "- Calculados pela ferramenta com base no historico, mas uma vez "
            "exportados, nao mudam sozinhos\n"
            "- Podem precisar de atualizacao se o dominio mudar\n\n"
            "**Regras hibridas** (categoricas):\n"
            "- Frequencia Hibrida (dinamica + floor/ceiling absolutos)\n"
            "- Combinam auto-ajuste dinamico com limites absolutos de negocio\n"
            "- O dual guard (sigma OR margem) se auto-ajusta, mas o resultado "
            "e validado AND com floor/ceiling fixos\n"
            "- Ideal quando a distribuicao muda naturalmente mas ha limites "
            "que nunca devem ser ultrapassados\n\n"
            "**Dica:** para categoricas com dominio estavel, use estatico. "
            "Para categoricas com variacao natural, use dinamico. "
            "Para categoricas criticas com limites de negocio, use hibrido."
        )


def _render_guia_passo_a_passo():
    """Sections 4 (Setup) + 5 (Calibracao) + 6 (Review)."""

    # -----------------------------------------------------------------
    # Setup da Tabela
    # -----------------------------------------------------------------

    st.subheader("Setup da Tabela (Detalhado)")

    with st.expander("Selecao da tabela"):
        st.markdown(
            "No passo 1, informe o **schema** (banco de dados do Glue Catalog) "
            "e o **nome da tabela**. Exemplos:\n"
            "- Schema: `gdq_test_db`, `datalake_raw`, `datalake_trusted`\n"
            "- Tabela: `tb_operacoes_credito`, `tb_clientes_pf`\n\n"
            "Clique em **Validar Tabela** para confirmar que a tabela existe "
            "e carregar a lista de colunas."
        )

    with st.expander("Deteccao de particao"):
        st.markdown(
            "A ferramenta detecta automaticamente as **colunas de particao** "
            "da tabela a partir do catalogo Glue. Se uma particao for encontrada, "
            "voce vera o nome da coluna e podera escolher o metodo de particao:\n\n"
            "- **Incremental:** cada particao contem dados novos daquele periodo. "
            "Exemplo: `dt_ref=2024-01-15` contem apenas as operacoes do dia 15. "
            "E o tipo mais comum.\n"
            "- **Full Snapshot:** cada particao contem a foto completa dos dados "
            "naquele momento. Exemplo: `dt_carga=2024-01-15` contem todos os "
            "clientes ativos ate o dia 15.\n\n"
            "Se a tabela nao tem particao, ela sera tratada como **nao-particionada** "
            "e o eixo temporal sera determinado por uma coluna interna de data."
        )

    with st.expander("Formato de data para colunas string"):
        st.markdown(
            "Quando a coluna de data e do tipo **string** (e nao date/timestamp), "
            "a ferramenta precisa de uma expressao SQL para converter o texto "
            "em data. O seletor de formato oferece opcoes comuns:\n\n"
            "- `yyyy-MM-dd` (ex: 2024-01-15) -- usa `CAST(coluna AS DATE)`\n"
            "- `yyyyMMdd` (ex: 20240115) -- usa `DATE_PARSE` no Athena\n"
            "- `yyyyMM` (ex: 202401) -- para colunas mensais\n"
            "- `dd/MM/yyyy` (ex: 15/01/2024) -- formato brasileiro\n"
            "- `yyyy-MM-dd HH:mm:ss` -- para strings com hora\n"
            "- **Customizado** -- permite digitar uma expressao SQL manualmente\n\n"
            "A expressao SQL e gerada automaticamente para o Athena."
        )

    with st.expander("Lookback e granularidade"):
        st.markdown(
            "O **lookback** define quantos periodos recentes serao considerados "
            "na analise. Exemplos:\n"
            "- Lookback 30, diario = ultimos 30 dias\n"
            "- Lookback 12, mensal = ultimos 12 meses\n\n"
            "**Recomendacoes:**\n"
            "- 20 a 60 periodos costuma funcionar bem para a maioria das tabelas\n"
            "- Mais periodos = amostra maior e mais estavel, porem pode incluir "
            "dados desatualizados\n"
            "- Menos periodos = mais sensivel a mudancas recentes, porem amostra "
            "menor\n"
            "- Se a tabela tem sazonalidade semanal, use pelo menos 14 periodos "
            "(2 semanas) para capturar o padrao\n"
            "- Se a tabela tem sazonalidade mensal, considere 60+ periodos "
            "ou granularidade mensal"
        )

    with st.expander("Filtro base"):
        st.markdown(
            "O filtro base e uma clausula WHERE aplicada em **todas** as queries "
            "de analise. Uso tipico:\n\n"
            "- Excluir registros de teste: `IND_TESTE = 0`\n"
            "- Filtrar segmento: `COD_SEGMENTO = 'VAREJO'`\n"
            "- Combinar filtros: `IND_ATIVO = 1 AND COD_TIPO != 'DUMMY'`\n\n"
            "**Atencao:**\n"
            "- Nao inclua a palavra `WHERE` (ela e adicionada automaticamente)\n"
            "- Use aspas simples para valores de texto: `COD_UF = 'SP'`\n"
            "- O filtro e opcional. Se nao informar, todas as linhas serao "
            "consideradas"
        )

    with st.expander("Presets"):
        st.markdown(
            "Um **preset** e uma configuracao salva em arquivo `.json` na pasta "
            "`presets/`. Ele armazena todas as escolhas do Setup (tabela, eixo temporal, "
            "lookback, filtro, colunas selecionadas).\n\n"
            "**Para salvar:** no passo 7 do Setup, marque \"Salvar como preset\" "
            "e escolha um nome.\n\n"
            "**Para carregar:** no inicio da pagina Setup, selecione o preset "
            "no dropdown e clique \"Carregar Preset\".\n\n"
            "Presets sao uteis quando voce analisa as mesmas tabelas periodicamente "
            "e quer manter a configuracao consistente."
        )

    # -----------------------------------------------------------------
    # Calibracao de Regras
    # -----------------------------------------------------------------

    st.subheader("Calibracao de Regras (Explore)")

    with st.expander("Como funciona a calibracao"):
        st.markdown(
            "Para cada regra, a ferramenta:\n\n"
            "1. Consulta o historico agregado da coluna ou tabela\n"
            "2. Calcula as bandas (sigma e margem) com base nos parametros atuais\n"
            "3. Executa o backtest para medir cobertura e falsos positivos\n"
            "4. Gera a sintaxe GDQ correspondente\n"
            "5. Exibe tudo em um grafico interativo\n\n"
            "Ao mover os sliders, os resultados sao recalculados. O objetivo "
            "e encontrar parametros que deem **cobertura alta** (acima de 90%) "
            "com **poucos falsos positivos** (idealmente 0)."
        )

    with st.expander("Aba Numericas — Mean e StdDev"):
        st.markdown(
            "Selecione uma coluna numerica no dropdown. Para cada coluna, "
            "a ferramenta exibe dois blocos:\n\n"
            "**Mean (media):**\n"
            "- Grafico: linha azul = media historica por periodo. "
            "Banda azul clara = banda sigma (K desvios padrao). "
            "Banda verde clara = banda margem (X%). "
            "Linha tracejada cinza = media movel.\n"
            "- Sliders: N, K, Margem%, Buffer\n"
            "- Metricas: cobertura, falsos positivos, estabilidade, confianca\n"
            "- Botao: adicionar ao carrinho\n\n"
            "**StdDev (desvio padrao):**\n"
            "- Mesmo formato do Mean, mas analisa a dispersao (volatilidade) "
            "da coluna em vez do nivel medio\n\n"
            "**Completeness:**\n"
            "- Disponivel como expander abaixo do StdDev\n"
            "- Verifica se a coluna tem uma porcentagem minima de valores "
            "preenchidos (nao nulos)\n"
            "- Nao tem sliders -- o limite e calculado automaticamente\n\n"
            "**Dica:** comece com os parametros padrao (N=20, K=2.0, Margem=10%, "
            "Buffer=0.01) e ajuste se a cobertura for muito baixa ou se "
            "houver drift."
        )

    with st.expander("Aba Categoricas — Modo Dinamico e Hibrido"):
        st.markdown(
            "Alem do modo estatico (limites fixos), a aba Categoricas oferece "
            "dois modos adicionais para regras de frequencia:\n\n"
            "**Dinamico:**\n"
            "- Usa `avg(last(N))` e `std(last(N))` na regra CustomSql\n"
            "- O GDQ recalcula os limites a cada execucao, assim como faz com Mean e StdDev\n"
            "- Aplica dual guard: passa se a frequencia estiver na banda sigma **OU** na margem\n"
            "- Ideal para categorias cuja proporcao varia naturalmente ao longo do tempo\n\n"
            "**Hibrido:**\n"
            "- Igual ao dinamico, mas com floor e ceiling absolutos\n"
            "- O dual guard se auto-ajusta, mas o resultado final e AND com floor/ceiling\n"
            "- Exemplo: frequencia de UF='SP' pode variar entre avg +/- sigma, "
            "mas NUNCA pode ficar abaixo de 20% ou acima de 80%\n"
            "- Configure os valores de floor e ceiling nos campos numericos "
            "que aparecem ao selecionar o modo hibrido\n\n"
            "**Como escolher:**\n"
            "- Dominio fixo e estavel (ex: status com 3 valores) → estatico\n"
            "- Distribuicao que muda gradualmente (ex: UF por regiao) → dinamico\n"
            "- Limites criticos de negocio (ex: tipo de produto nunca < 5%) → hibrido"
        )

    with st.expander("Sugestao automatica de parametros (auto-tuning)"):
        st.markdown(
            "O botao **\"Sugerir melhor combinacao\"** testa diversas combinacoes "
            "de N, sigma e margem para encontrar a que melhor equilibra cobertura "
            "e falsos positivos.\n\n"
            "**Como funciona:**\n"
            "- Testa combinacoes de N (10, 15, 20, 30, 45), sigma (1.5, 2.0, 2.5, 3.0) "
            "e margem (5%, 10%, 15%, 20%), com e sem margem ativada\n"
            "- Para cada combinacao, executa backtest completo no historico\n"
            "- Calcula score composto: maximiza cobertura, penaliza falsos positivos, "
            "bonifica estabilidade\n"
            "- Retorna a melhor combinacao com recomendacao de confianca\n\n"
            "**Resultado:**\n"
            "- **HIGH (verde):** combinacao recomendada — cobertura >= 90%, 0 FPs\n"
            "- **MEDIUM (laranja):** aceitavel — cobertura >= 70%, revisar parametros\n"
            "- **LOW (vermelho):** nao recomendado — cobertura abaixo de 70% ou "
            "muitos falsos positivos. Considere nao usar essa regra\n\n"
            "**Dica:** use o auto-tuning como ponto de partida e ajuste "
            "manualmente com os sliders se necessario."
        )

    with st.expander("Aba Tabela — RowCount"):
        st.markdown(
            "A regra **RowCount** verifica o volume de linhas por periodo. "
            "Funciona como as regras de Mean, mas em vez de analisar "
            "uma coluna especifica, analisa a contagem total de linhas.\n\n"
            "**Quando usar:**\n"
            "- Para detectar cargas vazias (0 linhas)\n"
            "- Para detectar cargas com volume muito acima do normal (possivel "
            "duplicacao)\n"
            "- Para detectar cargas com volume muito abaixo do normal (possivel "
            "falha parcial)\n\n"
            "**Diferenca em relacao ao Mean/StdDev:**\n"
            "- Nao tem buffer (Buffer=0)\n"
            "- O formato da banda margem e diferente internamente, mas o "
            "efeito pratico e o mesmo\n"
            "- E uma regra de **tabela**, nao de coluna"
        )

    with st.expander("Aba Resumo"):
        st.markdown(
            "A aba Resumo mostra todas as regras que ja foram adicionadas "
            "ao carrinho, com:\n"
            "- Nome da regra e coluna alvo\n"
            "- Nivel de confianca (HIGH/MEDIUM/LOW)\n"
            "- Cobertura do backtest\n"
            "- Explicacao em linguagem natural\n\n"
            "Use essa aba para ter uma visao geral antes de ir para o Review."
        )

    with st.expander("Como interpretar o grafico"):
        st.markdown(
            "O grafico Plotly mostra o historico da metrica com as bandas de "
            "aceitacao sobrepostas:\n\n"
            "- **Linha azul com marcadores:** valor historico real da metrica "
            "em cada periodo\n"
            "- **Faixa azul clara:** banda sigma (media +/- K desvios). "
            "Quanto mais estreita, mais estaveis sao os dados\n"
            "- **Faixa verde clara:** banda margem (media +/- X%). "
            "Largura fixa proporcional a media\n"
            "- **Linha tracejada cinza:** media movel dos ultimos N periodos\n\n"
            "**Pontos fora das DUAS bandas** sao periodos que a regra reprovaria. "
            "Se um ponto esta fora da banda sigma mas dentro da margem (ou vice-versa), "
            "a regra ainda passa gracias ao dual guard.\n\n"
            "Voce pode interagir com o grafico: zoom, pan, hover para ver "
            "valores exatos, e clicar na legenda para mostrar/esconder bandas."
        )

    # -----------------------------------------------------------------
    # Review e Exportacao
    # -----------------------------------------------------------------

    st.subheader("Review e Exportacao")

    with st.expander("Gerenciando o carrinho"):
        st.markdown(
            "O carrinho acumula todas as regras que voce adicionou nas abas "
            "Numericas, Categoricas e Tabela. Para cada regra, voce pode:\n\n"
            "- **Habilitar/desabilitar** usando o checkbox a esquerda. "
            "Regras desabilitadas nao sao incluidas na exportacao, "
            "mas permanecem no carrinho para referencia\n"
            "- **Remover** usando o botao \"X\" a direita. Remove permanentemente "
            "do carrinho\n"
            "- **Ver sintaxe e detalhes** no expander de cada regra\n"
            "- **Remover todas desabilitadas** com o botao dedicado\n"
            "- **Voltar ao Explore** para adicionar mais regras"
        )

    with st.expander("O que e a sintaxe GDQ?"):
        st.markdown(
            "A **sintaxe GDQ** e o formato de texto que o AWS Glue Data Quality "
            "usa para definir regras. Exemplo:\n"
        )
        st.code(
            '(((Mean VLR_SALDO >= (avg(last(20)) - (2 * std(last(20))) - 0.01)) '
            'AND (Mean VLR_SALDO <= (avg(last(20)) + (2 * std(last(20))) + 0.01))) '
            'OR ((Mean VLR_SALDO >= (avg(last(20)) * 0.9) - 0.01) '
            'AND (Mean VLR_SALDO <= (avg(last(20)) * 1.1) + 0.01)))',
            language=None,
        )
        st.markdown(
            "Voce **nao precisa entender** essa sintaxe para usar a ferramenta. "
            "Ela e gerada automaticamente com base nos parametros que voce ajustou "
            "nos sliders. A explicacao em linguagem natural sempre acompanha cada regra.\n\n"
            "Quando for cadastrar no GDQ, basta copiar ou baixar o bloco de texto "
            "e colar no campo de regras."
        )

    with st.expander("Como exportar"):
        st.markdown(
            "Na secao **Sintaxe Final**, a pagina mostra um bloco com todas as "
            "regras habilitadas em formato GDQ. Voce tem duas opcoes:\n\n"
            "- **Baixar .txt:** clique no botao para salvar um arquivo de texto "
            "com todas as regras, uma por linha\n"
            "- **Copiar:** use o icone de copia no canto superior direito "
            "do bloco de codigo para copiar para a area de transferencia\n\n"
            "O expander \"O que essas regras fazem?\" lista todas as regras "
            "habilitadas com explicacao em linguagem natural, util para "
            "documentar as regras escolhidas."
        )


def _render_sintaxe_gdq():
    """Section 7 (Referencia Rapida — Sintaxe GDQ)."""

    st.subheader("Referencia Rapida — Sintaxe GDQ")

    st.markdown(
        "Esta secao lista a sintaxe exata de cada tipo de regra gerada pela ferramenta. "
        "Use como referencia ao revisar ou debugar regras exportadas."
    )

    st.caption(
        "Convencoes: nomes de coluna SEM aspas e em UPPERCASE. "
        "Nomes de regra em CamelCase. Funcoes dinamicas em lowercase."
    )

    with st.expander("Mean (coluna numerica — dual guard dinamico)"):
        st.markdown(
            "Verifica se a **media** da coluna esta dentro da banda esperada. "
            "Usa dual guard: banda sigma OR banda margem, com buffer 0.01."
        )
        st.code(
            "(((Mean VLR_SALDO >= (avg(last(30)) - (2 * std(last(30))) - 0.01)) "
            "AND (Mean VLR_SALDO <= (avg(last(30)) + (2 * std(last(30))) + 0.01))) "
            "OR ((Mean VLR_SALDO >= (avg(last(30)) * 0.9) - 0.01) "
            "AND (Mean VLR_SALDO <= (avg(last(30)) * 1.1) + 0.01)))",
            language=None,
        )
        st.caption(
            "Parametros: N=30 (lookback), K=2 (sigma), Margem=10%, Buffer=0.01"
        )

    with st.expander("StandardDeviation (coluna numerica — dual guard dinamico)"):
        st.markdown(
            "Verifica se o **desvio padrao** da coluna esta dentro do esperado. "
            "Mesmo padrao do Mean, troca apenas o nome da regra."
        )
        st.code(
            "(((StandardDeviation VLR_PARC >= (avg(last(30)) - (2 * std(last(30))) - 0.01)) "
            "AND (StandardDeviation VLR_PARC <= (avg(last(30)) + (2 * std(last(30))) + 0.01))) "
            "OR ((StandardDeviation VLR_PARC >= (avg(last(30)) * 0.9) - 0.01) "
            "AND (StandardDeviation VLR_PARC <= (avg(last(30)) * 1.1) + 0.01)))",
            language=None,
        )
        st.caption(
            "As funcoes avg/std dentro de StandardDeviation referem-se a media "
            "e desvio padrao historicos do proprio desvio padrao (nao da coluna)."
        )

    with st.expander("RowCount (tabela — dual guard dinamico, sem buffer)"):
        st.markdown(
            "Verifica se a **quantidade de linhas** esta dentro do esperado. "
            "Sem buffer, K como float (2.0), formato de margem diferente."
        )
        st.code(
            "(((RowCount >= (avg(last(30)) * 1.0 - (2.0 * std(last(30))))) "
            "AND (RowCount <= (avg(last(30)) * 1.0 + (2.0 * std(last(30)))))) "
            "OR ((RowCount >= (avg(last(30)) - (avg(last(30)) * 0.1))) "
            "AND (RowCount <= (avg(last(30)) + (avg(last(30)) * 0.1)))))",
            language=None,
        )
        col_rc1, col_rc2, col_rc3 = st.columns(3)
        with col_rc1:
            st.caption("K usa float: `2.0`")
        with col_rc2:
            st.caption("Sem buffer (0)")
        with col_rc3:
            st.caption("Margem: `avg - (avg * 0.1)`")

    with st.expander("Completeness (qualquer coluna — estatico)"):
        st.markdown(
            "Verifica a porcentagem de valores **nao-nulos**. "
            "Usa `>=`, nunca `between`. Threshold em decimal (1.00 = 100%)."
        )
        st.code(
            "Completeness VLR_SALDO >= 1.00",
            language=None,
        )

    with st.expander("ColumnValues (categorica — estatico)"):
        st.markdown(
            "Verifica se todos os valores pertencem a uma **lista fixa**. "
            "Valores numericos sem aspas; valores string com aspas simples; "
            "NULL nunca tem aspas. Ordem nao importa."
        )
        st.code(
            "ColumnValues COD_SITU_OPCR in [2, 1, 3]\n"
            "ColumnValues UF_EMPR in ['SP', 'RJ', 'MG']\n"
            "ColumnValues STATUS in ['ATIVO', NULL, 'INATIVO']",
            language=None,
        )

    with st.expander("DistinctValuesCount (categorica — estatico)"):
        st.markdown(
            "Verifica o **numero de valores distintos**. "
            "Pode ser exato (`= N`) ou range (`between X and Y`)."
        )
        st.code(
            "DistinctValuesCount COD_SITU_OPCR = 3",
            language=None,
        )
        st.code(
            "DistinctValuesCount COD_CIDADE between 180 and 220",
            language=None,
        )

    with st.expander("CustomSql — Frequencia estatica (categorica)"):
        st.markdown(
            "Verifica se a **proporcao** de um valor esta entre limites fixos. "
            "Resultado em percentual 0-100. Uma regra por valor monitorado."
        )
        st.code(
            'CustomSql "select cast(sum(case when COD_SITU_OPCR = \'1\' then 1 '
            'else 0 end) as double) * 100.0 / count(*) from primary" '
            'between 85.61 and 97.66',
            language=None,
        )
        st.caption(
            "SQL entre aspas duplas. Nome da coluna em UPPERCASE sem aspas. "
            "Valores string com aspas simples. "
            "`from primary` referencia a tabela sendo avaliada."
        )

    with st.expander("CustomSql — Frequencia dinamica (categorica)"):
        st.markdown(
            "Versao dinamica da frequencia. Usa `avg(last(N))` e `std(last(N))` "
            "com dual guard (sigma OR margem), igual ao Mean."
        )
        st.code(
            '(((CustomSql "select cast(sum(case when COD_SITU = \'1\' then 1 '
            'else 0 end) as double) * 100.0 / count(*) from primary" '
            '>= (avg(last(30)) - (2 * std(last(30))) - 0.01)) '
            'AND (CustomSql "..." <= (avg(last(30)) + (2 * std(last(30))) + 0.01))) '
            'OR ((CustomSql "..." >= (avg(last(30)) * 0.9) - 0.01) '
            'AND (CustomSql "..." <= (avg(last(30)) * 1.1) + 0.01)))',
            language=None,
        )
        st.caption(
            "Exemplo simplificado — na sintaxe real, o SQL completo e repetido "
            "em cada comparacao (>=, <=)."
        )

    with st.expander("CustomSql — Frequencia hibrida (categorica)"):
        st.markdown(
            "Igual a dinamica, mas com floor e ceiling absolutos. "
            "Dual guard AND entre floor e ceiling."
        )
        st.code(
            '((DUAL_GUARD_EXPRESSION) AND (CustomSql "select ... from primary" '
            'between 5.0 and 50.0))',
            language=None,
        )
        st.caption(
            "DUAL_GUARD_EXPRESSION e a mesma expressao da frequencia dinamica. "
            "Floor=5.0% e ceiling=50.0% sao limites absolutos de negocio."
        )

    with st.expander("IsPrimaryKey (chave primaria — estatico)"):
        st.markdown(
            "Valida **unicidade** de uma combinacao de colunas. "
            "Colunas separadas por espaco (nao virgula). Sem aspas."
        )
        st.code(
            "IsPrimaryKey NUM_CTRT COD_PRODUTO DT_REF",
            language=None,
        )


def _render_faq_glossario():
    """Sections 8 (FAQ) + 9 (Glossario)."""

    # -----------------------------------------------------------------
    # Perguntas Frequentes
    # -----------------------------------------------------------------

    st.subheader("Perguntas Frequentes")

    with st.expander("Como escolher N (lookback)?"):
        st.markdown(
            "O N define quantos periodos recentes sao usados para calcular media e "
            "desvio padrao. A escolha depende do comportamento dos dados:\n\n"
            "- **N=20 a 30 (padrao):** bom ponto de partida para a maioria das tabelas. "
            "Equilibra estabilidade e sensibilidade.\n"
            "- **N=10 a 15:** use quando os dados tem drift (tendencia) ou mudaram "
            "de patamar recentemente. Janela curta acompanha mudancas mais rapido.\n"
            "- **N=45 a 60:** use quando os dados tem sazonalidade semanal "
            "(inclui varias semanas completas) ou mensal.\n"
            "- **N=60+:** use apenas para dados muito estaveis ou quando quer "
            "suavizar variacao sazonal forte.\n\n"
            "**Regra pratica:** se o backtest mostra boa cobertura (>90%), o N esta adequado. "
            "Se a cobertura e baixa e ha drift, reduza o N. Se a banda oscila muito, "
            "aumente o N."
        )

    with st.expander("Qual sigma (K) usar?"):
        st.markdown(
            "O sigma (K) controla a largura da banda de desvio padrao:\n\n"
            "- **K=1.5 (rigoroso):** banda apertada, mais sensivel a desvios. "
            "Use para colunas criticas onde qualquer variacao acima do normal "
            "deve ser investigada. Risco: mais falsos positivos.\n"
            "- **K=2.0 (padrao):** cobre ~95% dos dados normais. "
            "Bom equilibrio entre sensibilidade e tolerancia. "
            "Recomendado para a maioria dos casos.\n"
            "- **K=2.5:** intermediario. Use quando K=2.0 gera 1-2 FPs "
            "e voce quer reduzir sem perder muita sensibilidade.\n"
            "- **K=3.0 (tolerante):** cobre ~99.7% dos dados normais. "
            "Use para colunas com variacao natural alta ou quando falsos positivos "
            "sao mais custosos que deixar passar anomalias.\n\n"
            "**Dica:** o auto-tuning testa K=1.5, 2.0, 2.5 e 3.0 automaticamente "
            "e recomenda o melhor valor."
        )

    with st.expander("Cobertura vs. Falsos Positivos — como equilibrar?"):
        st.markdown(
            "**Cobertura** e **falsos positivos** sao metricas complementares:\n\n"
            "- **Cobertura:** porcentagem de periodos historicos que passariam na regra. "
            "Mede quao **tolerante** a regra e. Ideal: >= 90%.\n"
            "- **Falsos positivos (~N):** estimativa de periodos **normais** que seriam "
            "reprovados. Mede quao **precisa** a regra e. Ideal: 0.\n\n"
            "O equilibrio depende do contexto:\n\n"
            "| Cenario | Prioridade | Acao |\n"
            "|---------|------------|------|\n"
            "| Coluna critica (financeiro) | Sensibilidade | Aceitar cobertura ~85%, K=1.5 |\n"
            "| Coluna de monitoramento geral | Equilibrio | Cobertura >= 90%, K=2.0 |\n"
            "| Coluna com variacao natural alta | Tolerancia | Cobertura >= 95%, K=3.0 |\n\n"
            "**Situacoes problematicas:**\n"
            "- Cobertura alta (95%) mas 3+ FPs: a banda pode estar desalinhada "
            "por drift. Reduza N.\n"
            "- Cobertura baixa (70%) e 0 FPs: os dados podem ter mudado de patamar. "
            "Reduza N ou investigue o historico.\n"
            "- Cobertura baixa e muitos FPs: a regra nao e adequada para essa coluna."
        )

    with st.expander("A cobertura esta abaixo de 90%. O que fazer?"):
        st.markdown(
            "Cobertura baixa significa que a regra reprovaria muitos periodos "
            "historicos. Tente:\n\n"
            "- **Aumentar K (sigma):** de 2.0 para 2.5 ou 3.0. Isso alarga "
            "a banda sigma\n"
            "- **Aumentar a margem %:** de 10% para 15% ou 20%. Isso alarga "
            "a banda margem\n"
            "- **Reduzir N:** usar dados mais recentes pode dar uma banda "
            "mais alinhada ao comportamento atual\n"
            "- **Verificar se ha drift:** se o aviso de tendencia apareceu, "
            "reduzir N pode ajudar\n\n"
            "Se nenhum ajuste funcionar, os dados podem ser naturalmente muito "
            "volateis para essa regra. Considere usar uma regra mais simples "
            "(ex: Completeness) ou investigar se ha problemas no historico."
        )

    with st.expander("O que significam os falsos positivos?"):
        st.markdown(
            "O numero de falsos positivos mostrado no backtest e uma **estimativa** "
            "(por isso aparece com `~` na frente). O criterio usado e:\n\n"
            "> Um periodo e contado como falso positivo quando **viola a regra** "
            "mas esta **dentro de 4 desvios padrao** da media global do historico.\n\n"
            "A logica: se o valor esta a menos de 4 sigma da media global, "
            "provavelmente e um valor normal que a regra esta reprovando "
            "indevidamente (regra muito rigorosa). Se esta alem de 4 sigma, "
            "provavelmente e um outlier genuino.\n\n"
            "**Limitacoes:**\n"
            "- E uma heuristica, nao uma classificacao definitiva\n"
            "- Usa a media e desvio padrao **globais** (todo o historico), "
            "que podem ser influenciados por outliers\n"
            "- Nao considera sazonalidade ou tendencia\n\n"
            "**Como interpretar:**\n"
            "- **0 FPs:** a regra parece calibrada corretamente\n"
            "- **1-2 FPs:** aceitavel na maioria dos casos\n"
            "- **3+ FPs:** a regra pode estar rigorosa demais — "
            "aumente K (sigma) ou a margem %\n"
            "- Muitos FPs com cobertura alta: a banda pode estar desalinhada "
            "por causa de drift"
        )

    with st.expander("Drift detectado — devo ignorar a regra?"):
        st.markdown(
            "Nao necessariamente. Drift significa que os dados tem uma tendencia "
            "(ex: volume crescendo). A regra ainda pode ser util se:\n\n"
            "- Voce reduzir N para acompanhar a tendencia (ex: N=10 em vez de N=30)\n"
            "- A tendencia for esperada e voce aumentar a margem para acomodar\n\n"
            "Se o drift e inesperado, investigue a causa antes de criar regras."
        )

    with st.expander("Minha coluna de data e do tipo string. O que fazer?"):
        st.markdown(
            "No passo 2 do Setup, ao selecionar uma coluna de tipo string "
            "como eixo temporal, a ferramenta exibe automaticamente um seletor "
            "de formato. Escolha o formato que corresponde aos valores da coluna "
            "(ex: `yyyy-MM-dd` para `2024-01-15`).\n\n"
            "Se nenhum formato padrao servir, selecione \"Customizado\" e "
            "digite a expressao SQL manualmente. Exemplo:\n\n"
            "- `DATE_PARSE(\"dt_ref\", '%Y%m%d')`\n\n"
            "A expressao sera usada em todas as queries para converter "
            "a coluna string em data."
        )

    with st.expander("Posso alterar a classificacao de uma coluna?"):
        st.markdown(
            "Sim. No passo 6 do Setup (Selecao de Colunas), cada coluna tem "
            "um dropdown com o tipo semantico. Voce pode alterar de \"Numerico\" "
            "para \"Categorico\" ou vice-versa.\n\n"
            "Isso e util quando a inferencia automatica erra. Exemplos comuns:\n"
            "- Coluna de codigo (ex: `COD_AGENCIA`) classificada como numerica "
            "porque contem apenas digitos -- altere para categorico\n"
            "- Coluna de valor (ex: `VLR_IMPOSTO`) classificada como string "
            "porque o tipo Athena e varchar -- altere para numerico"
        )

    with st.expander("Quantas regras devo criar por tabela?"):
        st.markdown(
            "Nao ha limite tecnico, mas como referencia:\n\n"
            "- **Minimo recomendado:** 1 regra de RowCount + 1 regra de Mean "
            "ou Completeness para as colunas mais criticas\n"
            "- **Tipico:** RowCount + Mean + StdDev para 3-5 colunas numericas "
            "mais importantes, totalizando 7-11 regras\n"
            "- **Completo:** RowCount + Mean + StdDev + Completeness para todas "
            "as colunas numericas\n\n"
            "Regras demais podem gerar muitos alertas e dificultar a triagem. "
            "Comece com poucas regras de alta confianca e adicione mais "
            "conforme necessario."
        )

    with st.expander("A sessao expirou e perdi minhas regras. Como evitar?"):
        st.markdown(
            "O Streamlit armazena dados na memoria da sessao do navegador. "
            "Se a pagina for recarregada ou ficar inativa por muito tempo, "
            "a sessao pode ser perdida.\n\n"
            "**Para evitar:**\n"
            "- Use presets no Setup para salvar a configuracao em disco\n"
            "- Exporte as regras (baixe o .txt) assim que estiverem prontas\n"
            "- Nao feche a aba do navegador durante a calibracao"
        )

    with st.expander("Quando usar modo estatico, dinamico ou hibrido para categoricas?"):
        st.markdown(
            "A escolha depende do comportamento da coluna:\n\n"
            "- **Estatico:** a distribuicao e estavel e previsivel. Exemplos: "
            "colunas de status com 3 valores fixos, UF com proporcoes constantes. "
            "Vantagem: simples e interpretavel.\n\n"
            "- **Dinamico:** a distribuicao muda gradualmente ao longo do tempo. "
            "Exemplo: proporcao de clientes por canal que varia com sazonalidade. "
            "Vantagem: acompanha drift natural sem precisar recalibrar.\n\n"
            "- **Hibrido:** ha limites de negocio que nunca devem ser ultrapassados, "
            "mas a distribuicao varia dentro desses limites. "
            "Exemplo: a frequencia de um tipo de operacao pode variar, mas nunca "
            "deve cair abaixo de 5% (floor) ou subir acima de 50% (ceiling). "
            "Vantagem: auto-ajuste com protecao contra desvios excessivos.\n\n"
            "**Na duvida:** comece com estatico. Se a cobertura for baixa ou houver "
            "drift, tente dinamico. Se precisar de limites absolutos, use hibrido."
        )

    with st.expander("O auto-tuning sugeriu LOW. Devo ignorar essa regra?"):
        st.markdown(
            "Quando o auto-tuning retorna **LOW**, significa que nenhuma combinacao "
            "de parametros conseguiu atingir 70% de cobertura. Isso pode significar:\n\n"
            "- Os dados sao **muito volateis** para essa metrica — a variacao natural "
            "e maior que qualquer banda razoavel\n"
            "- Ha **drift significativo** no historico — os dados mudaram de patamar\n"
            "- Ha **poucos pontos** no historico para uma avaliacao confiavel\n\n"
            "**Opcoes:**\n"
            "- **Nao usar essa regra:** regras com baixa cobertura geram muitos "
            "alertas falsos e perdem credibilidade\n"
            "- **Usar uma regra mais simples:** ex: Completeness em vez de Mean\n"
            "- **Investigar os dados:** o problema pode estar no historico, nao na regra\n"
            "- **Aumentar o lookback:** mais dados podem estabilizar a banda"
        )

    with st.expander("O que acontece se eu mudar os parametros depois de adicionar ao carrinho?"):
        st.markdown(
            "As regras no carrinho nao sao afetadas por mudancas nos sliders. "
            "Cada regra e \"fotografada\" no momento em que voce clica "
            "\"Adicionar ao carrinho\" com os parametros vigentes naquele momento.\n\n"
            "Se quiser uma versao com parametros diferentes, remova a regra "
            "antiga do carrinho (no Review), ajuste os sliders e adicione novamente."
        )

    # -----------------------------------------------------------------
    # Glossario
    # -----------------------------------------------------------------

    st.subheader("Glossario")

    st.caption(
        "Referencia rapida de todos os termos usados na ferramenta."
    )

    glossary = [
        ("AllowedValues", "Regra GDQ estatica que verifica se todos os valores de uma coluna pertencem a uma lista fixa. Sintaxe: ColumnValues COL in [...]. Valores numericos sem aspas, strings com aspas simples, NULL sem aspas."),
        ("Athena", "Servico da AWS para consultar dados no data lake via SQL. A ferramenta usa Athena para analisar historico de tabelas."),
        ("Auto-tuning", "Busca automatica da melhor combinacao de N/sigma/margem via grid search. Testa multiplas combinacoes e retorna a que maximiza cobertura com menos falsos positivos."),
        ("Backtest", "Simulacao da regra no historico passado para medir cobertura, falsos positivos e estabilidade. Usa janela rolante para simular o comportamento real da regra em producao."),
        ("Banda margem", "Faixa de aceitacao calculada como porcentagem fixa da media (ex: media +/- 10%). Parte do dual guard."),
        ("Banda sigma", "Faixa de aceitacao calculada como media +/- K desvios padrao. Parte do dual guard."),
        ("Buffer", "Valor minimo (ex: 0.01) adicionado aos limites das bandas para evitar falsos positivos por arredondamento. RowCount nao usa buffer."),
        ("Cardinalidade", "Numero de valores distintos em uma coluna categorica. Baixa (<50), media (50-500), alta (>500). Determina quais regras sao geradas."),
        ("Carrinho", "Lista de regras selecionadas para exportacao. Funciona como um carrinho de compras. Persiste na sessao do Streamlit."),
        ("Ceiling", "Limite superior absoluto (%) usado no modo hibrido. A frequencia nunca pode ultrapassar este valor, independente do dual guard."),
        ("Cobertura", "Porcentagem de periodos historicos que passariam na regra. Quanto maior, melhor. Ideal: >= 90%."),
        ("Completeness", "Regra que verifica se uma coluna tem uma porcentagem minima de valores preenchidos (nao-nulos). Usa >=, nao between."),
        ("Confianca", "Avaliacao geral da qualidade da regra: HIGH (recomendada), MEDIUM (revisar), LOW (nao recomendada). Baseada em cobertura, FPs e estabilidade."),
        ("CustomSql", "Tipo de regra GDQ que permite executar SQL customizado. Usado para frequencia categorica (estatica, dinamica ou hibrida). Usa `from primary` para referenciar a tabela."),
        ("DistinctValuesCount", "Regra GDQ que verifica o numero de valores distintos de uma coluna. Pode ser exata (= N) ou range (between X and Y)."),
        ("Drift", "Tendencia de crescimento ou queda nos dados ao longo do tempo. Pode tornar as bandas desalinhadas. Solucao: reduzir N ou aumentar margem."),
        ("Dual guard", "Mecanismo que combina banda sigma OR banda margem. A regra passa se o valor estiver dentro de qualquer uma das duas bandas."),
        ("Estabilidade", "Metrica de 0 a 1 que indica quao pouco a banda muda ao variar parametros. 1.0 = muito estavel. Abaixo de 0.5 pode indicar instabilidade."),
        ("Falso positivo", "Estimativa (~) de periodos normais que seriam reprovados pela regra. Criterio: viola a regra mas esta dentro de 4 sigma da media global. Ideal: 0."),
        ("Floor", "Limite inferior absoluto (%) usado no modo hibrido. A frequencia nunca pode ficar abaixo deste valor, independente do dual guard."),
        ("Frequencia dinamica", "Regra CustomSql de frequencia que usa avg(last(N)) e std(last(N)) para auto-ajustar os limites a cada execucao do GDQ."),
        ("Frequencia estatica", "Regra CustomSql de frequencia com limites fixos (between X and Y). Calculada pela ferramenta com base no historico, mas nao se auto-ajusta."),
        ("Frequencia hibrida", "Regra dinamica com floor/ceiling absolutos. Combina auto-ajuste com limites de negocio fixos. Logica: dual guard AND between floor and ceiling."),
        ("GDQ", "AWS Glue Data Quality. Servico da AWS para definir e executar regras de qualidade de dados em pipelines Glue."),
        ("Granularidade", "Frequencia dos periodos de analise: diario (1 periodo por dia), mensal (1 periodo por mes)."),
        ("IsPrimaryKey", "Regra GDQ que valida unicidade de uma combinacao de colunas. Colunas separadas por espaco, sem aspas."),
        ("K (sigma)", "Multiplicador do desvio padrao para a banda sigma. K=1.5 (rigoroso), K=2 (~95%), K=3 (~99.7%)."),
        ("Lookback", "Quantidade de periodos recentes considerados na analise (ex: ultimos 30 dias). Controla o tamanho da janela de historico usada nas queries."),
        ("Mean", "Regra GDQ dinamica que verifica se a media de uma coluna esta dentro da banda esperada. Usa dual guard com avg(last(N)) e std(last(N))."),
        ("Margem %", "Porcentagem fixa usada para calcular a banda margem do dual guard (ex: 10%). Funciona como rede de seguranca quando a banda sigma e muito estreita."),
        ("N (periodos)", "Tamanho da janela movel de historico usada para calcular media e desvio padrao. Valores tipicos: 10 a 60."),
        ("Outlier", "Valor atipico que se destaca significativamente do padrao normal dos dados. Detectado pelo backtest usando heuristica de 4 sigma global."),
        ("Particao", "Organizacao fisica dos dados em pastas por periodo (ex: dt_ref=2024-01-15/). Otimiza custo e performance no Athena."),
        ("Percentil", "Ponto de corte que divide a distribuicao em partes. P5 e P95 delimitam os extremos. Usado como analise complementar para calibracao."),
        ("Preset", "Configuracao salva em arquivo JSON que pode ser reutilizada em futuras analises. Inclui tabela, eixo temporal, lookback, filtro e colunas."),
        ("Profiling", "Processo de classificacao automatica das colunas (numerico, categorico, data, etc.) com base no tipo Athena e heuristicas estatisticas."),
        ("RowCount", "Regra GDQ dinamica que verifica se a quantidade de linhas por periodo esta dentro do esperado. Sem buffer, K como float."),
        ("Schema", "Nome do banco de dados no Glue Catalog (ex: gdq_test_db, datalake_raw)."),
        ("Score", "Avaliacao composta da regra que combina cobertura (35%), estabilidade (25%), interpretabilidade (20%) e custo (20%). Determina a confianca."),
        ("StdDev", "Regra GDQ dinamica que verifica se o desvio padrao de uma coluna esta dentro do esperado. Detecta mudancas na dispersao dos dados."),
        ("Tipo semantico", "Classificacao inferida pelo profiling: NUMERIC, CAT_LOW, CAT_MID, CAT_HIGH, DATETIME, IDENTIFIER. Determina quais regras sao propostas."),
    ]

    for term, definition in glossary:
        st.markdown(f"- **{term}:** {definition}")


# =====================================================================
# Tab layout
# =====================================================================

tab_intro, tab_conceitos, tab_guia, tab_sintaxe, tab_faq = st.tabs(
    ["Introducao", "Conceitos", "Guia Passo a Passo", "Sintaxe GDQ", "FAQ e Glossario"]
)

with tab_intro:
    _render_intro()

with tab_conceitos:
    _render_conceitos()

with tab_guia:
    _render_guia_passo_a_passo()

with tab_sintaxe:
    _render_sintaxe_gdq()

with tab_faq:
    _render_faq_glossario()


# =====================================================================
# Footer
# =====================================================================

st.divider()

st.caption(
    "GDQ Rule Proposer — Documentacao gerada automaticamente. "
    "Para duvidas adicionais, consulte a equipe de engenharia de dados."
)
