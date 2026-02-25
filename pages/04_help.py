"""
Pagina 04 — Ajuda: Documentacao completa do usuario.

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
# 1. Introducao
# =====================================================================

st.header("1. Introducao")

st.markdown(
    "O **GDQ Rule Proposer** e uma ferramenta que analisa o historico de dados "
    "de uma tabela e propoe regras de qualidade para o "
    "**AWS Glue Data Quality (GDQ)**."
)

st.markdown(
    "A ferramenta consulta dados agregados via **Amazon Athena** (ou via DuckDB "
    "em modo local), calcula estatisticas sobre o comportamento historico das "
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


# =====================================================================
# 2. Fluxo de Trabalho
# =====================================================================

st.header("2. Fluxo de Trabalho")

st.markdown(
    "O processo segue 4 etapas sequenciais. "
    "Cada etapa corresponde a uma pagina no menu lateral."
)

st.subheader("Etapa 1 — Home")
st.markdown(
    "A pagina inicial mostra o **status da conexao** (modo local ou Athena real), "
    "as **tabelas disponiveis** no backend ativo e um preview das colunas. "
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
    "- Visualizar o grafico interativo com as bandas de aceitacao\n"
    "- Ver as metricas do backtest (cobertura, falsos positivos, estabilidade)\n"
    "- Ler a explicacao em linguagem natural de cada regra\n"
    "- Adicionar regras aprovadas ao carrinho"
)
st.markdown(
    "A pagina tem 4 abas: **Numericas** (Mean, StdDev, Completeness por coluna), "
    "**Categoricas** (AllowedValues, DistinctValuesCount, Frequencia por coluna), "
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


# =====================================================================
# 3. Conceitos
# =====================================================================

st.header("3. Conceitos Principais")

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
        "Funciona como rede de seguranca quando a banda sigma e muito estreita.\n\n"
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
        "- **Falsos positivos:** periodos normais que seriam reprovados. "
        "Ideal: 0 ou proximo de 0\n"
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
    st.markdown("**Regras de coluna numerica:**")
    st.markdown(
        "- **Mean (media):** verifica se a media da coluna esta dentro da banda "
        "esperada. Detecta mudancas no nivel dos dados (ex: valores sistematicamente "
        "maiores ou menores que o normal).\n"
        "- **StdDev (desvio padrao):** verifica se o desvio padrao da coluna "
        "esta dentro do esperado. Detecta mudancas na dispersao (ex: dados "
        "ficaram muito mais volateis ou muito mais homogeneos).\n"
        "- **Completeness (completude):** verifica se a porcentagem de valores "
        "nao-nulos esta acima de um limite. Util para colunas que devem "
        "estar sempre preenchidas."
    )
    st.markdown("**Regras de coluna categorica:**")
    st.markdown(
        "- **AllowedValues (valores permitidos):** verifica se todos os valores "
        "da coluna pertencem a uma lista fixa. Qualquer valor fora da lista "
        "reprova a regra. Util para colunas com dominio estavel (ex: UF, status).\n"
        "- **DistinctValuesCount (distintos):** verifica se o numero de valores "
        "distintos esta correto (exato ou dentro de um range). Detecta se valores "
        "sumiram ou apareceram.\n"
        "- **Frequencia de categoria (CustomSql):** verifica se a proporcao de "
        "cada valor esta dentro de uma faixa esperada. Detecta mudancas na "
        "distribuicao dos dados (ex: um valor que era 30% passou a ser 10%).\n"
        "- **IsPrimaryKey (chave primaria):** verifica se uma combinacao de "
        "colunas nao tem duplicatas. Util para validar integridade referencial."
    )
    st.markdown("**Regras de tabela:**")
    st.markdown(
        "- **RowCount (volume):** verifica se a quantidade de linhas por periodo "
        "esta dentro do esperado. Detecta cargas com volume anomalo "
        "(muito acima ou muito abaixo do normal)."
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

with st.expander("Regras estaticas vs. dinamicas"):
    st.markdown(
        "As regras da ferramenta se dividem em dois tipos:\n\n"
        "**Regras dinamicas** (numericas e volume):\n"
        "- Mean, StdDev, RowCount\n"
        "- Usam funcoes `avg(last(N))` e `std(last(N))` na sintaxe GDQ\n"
        "- O GDQ **recalcula automaticamente** os limites a cada execucao\n"
        "- Nao precisam de manutencao manual\n\n"
        "**Regras estaticas** (categoricas):\n"
        "- AllowedValues, DistinctValuesCount, CategoryFrequency, IsPrimaryKey\n"
        "- Os valores/limites sao **fixos** na sintaxe GDQ\n"
        "- Calculados pela ferramenta com base no historico, mas uma vez "
        "exportados, nao mudam sozinhos\n"
        "- Podem precisar de atualizacao se o dominio mudar\n\n"
        "**Dica:** para categoricas, revise as regras periodicamente ou use "
        "a ferramenta novamente quando houver mudancas no dominio."
    )


# =====================================================================
# 4. Setup da Tabela
# =====================================================================

st.header("4. Setup da Tabela (Detalhado)")

with st.expander("Selecao da tabela"):
    st.markdown(
        "No passo 1, informe o **schema** (banco de dados do Glue Catalog) "
        "e o **nome da tabela**. Exemplos:\n"
        "- Schema: `gdq_test_db`, `datalake_raw`, `datalake_trusted`\n"
        "- Tabela: `tb_operacoes_credito`, `tb_clientes_pf`\n\n"
        "Em modo local (mock/DuckDB), o schema e fixo (`mock_db`) e as tabelas "
        "disponiveis sao as que tem dados sinteticos na pasta `mock_data/`.\n\n"
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
        "A expressao e gerada automaticamente para o backend ativo "
        "(Athena ou DuckDB) e sera adaptada ao trocar de ambiente."
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


# =====================================================================
# 5. Calibracao de Regras
# =====================================================================

st.header("5. Calibracao de Regras (Explore)")

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


# =====================================================================
# 6. Review e Exportacao
# =====================================================================

st.header("6. Review e Exportacao")

with st.expander("Gerenciando o carrinho"):
    st.markdown(
        "O carrinho acumula todas as regras que voce adicionou nas abas "
        "Numericas e Tabela. Para cada regra, voce pode:\n\n"
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


# =====================================================================
# 7. Perguntas Frequentes
# =====================================================================

st.header("7. Perguntas Frequentes")

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
        "Falsos positivos sao periodos normais que a regra reprovaria "
        "indevidamente. No backtest, a ferramenta identifica periodos que "
        "estao fora das bandas mas nao sao outliers reais.\n\n"
        "**Ideal:** 0 falsos positivos. Se houver 1-2, avalie se a regra "
        "ainda e util. Se houver muitos, a regra e muito rigorosa "
        "e vai gerar alertas desnecessarios em producao."
    )

with st.expander("Drift detectado — devo ignorar a regra?"):
    st.markdown(
        "Nao necessariamente. Drift significa que os dados tem uma tendencia "
        "(ex: volume crescendo). A regra ainda pode ser util se:\n\n"
        "- Voce reduzir N para acompanhar a tendencia (ex: N=10 em vez de N=30)\n"
        "- A tendencia for esperada e voce aumentar a margem para acomodar\n\n"
        "Se o drift e inesperado, investigue a causa antes de criar regras."
    )

with st.expander("Posso usar a ferramenta sem Athena (modo local)?"):
    st.markdown(
        "Sim. O modo local usa **DuckDB** como backend e carrega dados "
        "sinteticos da pasta `mock_data/`. E util para:\n\n"
        "- Aprender a usar a ferramenta sem precisar de acesso AWS\n"
        "- Testar configuracoes antes de rodar contra dados reais\n"
        "- Desenvolvimento e debug\n\n"
        "As regras geradas em modo local sao sintaticamente validas, "
        "mas os limites (thresholds) refletem os dados sinteticos, "
        "nao os dados de producao."
    )

with st.expander("Como trocar entre modo local e Athena real?"):
    st.markdown(
        "Use o seletor **Ambiente** na barra lateral (sidebar):\n\n"
        "- **Local (Mock/DuckDB):** usa dados sinteticos locais\n"
        "- **Dev (Athena real):** conecta ao Athena com o perfil AWS configurado\n"
        "- **Prod (Athena + IAM):** conecta ao Athena com IAM role\n\n"
        "Ao trocar de ambiente, a sessao e reiniciada. Voce precisara "
        "refazer o Setup."
    )

with st.expander("Minha coluna de data e do tipo string. O que fazer?"):
    st.markdown(
        "No passo 2 do Setup, ao selecionar uma coluna de tipo string "
        "como eixo temporal, a ferramenta exibe automaticamente um seletor "
        "de formato. Escolha o formato que corresponde aos valores da coluna "
        "(ex: `yyyy-MM-dd` para `2024-01-15`).\n\n"
        "Se nenhum formato padrao servir, selecione \"Customizado\" e "
        "digite a expressao SQL manualmente. Exemplos:\n\n"
        "- `DATE_PARSE(\"dt_ref\", '%Y%m%d')` (para Athena)\n"
        "- `STRPTIME(\"dt_ref\", '%Y%m%d')::DATE` (para DuckDB)\n\n"
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

with st.expander("O que acontece se eu mudar os parametros depois de adicionar ao carrinho?"):
    st.markdown(
        "As regras no carrinho nao sao afetadas por mudancas nos sliders. "
        "Cada regra e \"fotografada\" no momento em que voce clica "
        "\"Adicionar ao carrinho\" com os parametros vigentes naquele momento.\n\n"
        "Se quiser uma versao com parametros diferentes, remova a regra "
        "antiga do carrinho (no Review), ajuste os sliders e adicione novamente."
    )


# =====================================================================
# 8. Glossario
# =====================================================================

st.header("8. Glossario")

st.caption(
    "Referencia rapida de todos os termos usados na ferramenta."
)

glossary = [
    ("Athena", "Servico da AWS para consultar dados no data lake via SQL. A ferramenta usa Athena para analisar historico de tabelas."),
    ("Backtest", "Simulacao da regra no historico passado para medir cobertura, falsos positivos e estabilidade."),
    ("Banda margem", "Faixa de aceitacao calculada como porcentagem fixa da media (ex: media +/- 10%). Parte do dual guard."),
    ("Banda sigma", "Faixa de aceitacao calculada como media +/- K desvios padrao. Parte do dual guard."),
    ("Buffer", "Valor minimo (ex: 0.01) adicionado aos limites das bandas para evitar falsos positivos por arredondamento."),
    ("Carrinho", "Lista de regras selecionadas para exportacao. Funciona como um carrinho de compras."),
    ("Cobertura", "Porcentagem de periodos historicos que passariam na regra. Quanto maior, melhor."),
    ("Completeness", "Regra que verifica se uma coluna tem uma porcentagem minima de valores preenchidos (nao-nulos)."),
    ("Confianca", "Avaliacao geral da qualidade da regra: HIGH (recomendada), MEDIUM (revisar), LOW (nao recomendada)."),
    ("Drift", "Tendencia de crescimento ou queda nos dados ao longo do tempo. Pode tornar as bandas desalinhadas."),
    ("Dual guard", "Mecanismo que combina banda sigma OR banda margem. A regra passa se o valor estiver dentro de qualquer uma das duas."),
    ("DuckDB", "Banco de dados local usado em modo mock para simular o Athena durante desenvolvimento."),
    ("Estabilidade", "Metrica de 0 a 1 que indica quao pouco a banda muda ao variar parametros. 1.0 = muito estavel."),
    ("Falso positivo", "Periodo normal que seria reprovado indevidamente pela regra. Ideal: 0."),
    ("GDQ", "AWS Glue Data Quality. Servico da AWS para definir e executar regras de qualidade de dados."),
    ("Granularidade", "Frequencia dos periodos de analise: diario (1 periodo por dia), mensal (1 periodo por mes)."),
    ("K (sigma)", "Multiplicador do desvio padrao para a banda sigma. K=2 cobre ~95% dos dados normais. K=3 cobre ~99.7%."),
    ("Lookback", "Quantidade de periodos recentes considerados na analise (ex: ultimos 30 dias)."),
    ("Mean", "Regra GDQ que verifica se a media de uma coluna esta dentro da banda esperada."),
    ("Margem %", "Porcentagem fixa usada para calcular a banda margem do dual guard (ex: 10%)."),
    ("N (periodos)", "Tamanho da janela movel de historico usada para calcular media e desvio padrao."),
    ("Outlier", "Valor atipico que se destaca significativamente do padrao normal dos dados."),
    ("Particao", "Organizacao fisica dos dados em pastas por periodo (ex: dt_ref=2024-01-15/). Otimiza custo e performance."),
    ("Preset", "Configuracao salva em arquivo JSON que pode ser reutilizada em futuras analises."),
    ("Profiling", "Processo de classificacao automatica das colunas (numerico, categorico, data, etc.)."),
    ("RowCount", "Regra GDQ que verifica se a quantidade de linhas por periodo esta dentro do esperado."),
    ("Schema", "Nome do banco de dados no Glue Catalog (ex: gdq_test_db, datalake_raw)."),
    ("StdDev", "Regra GDQ que verifica se o desvio padrao de uma coluna esta dentro do esperado."),
    ("Tipo semantico", "Classificacao inferida pelo profiling: numerico, categorico (low/mid/high), data, identificador."),
]

for term, definition in glossary:
    st.markdown(f"- **{term}:** {definition}")


# =====================================================================
# Footer
# =====================================================================

st.divider()

st.caption(
    "GDQ Rule Proposer — Documentacao gerada automaticamente. "
    "Para duvidas adicionais, consulte a equipe de engenharia de dados."
)
