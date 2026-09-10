# ETL — Políticas de Equidade em Saúde (Recife)

## Contexto do desafio

A Secretaria de Atenção Básica do Recife enfrenta dificuldade para transformar os dados do **PEC/e-SUS APS** (sistema de prontuário da Atenção Primária à Saúde) em indicadores estratégicos para três políticas municipais de equidade:

- Saúde Integral da População LGBTQIAPN+
- Atenção Integral à Saúde da Pessoa com Deficiência
- Saúde Integral da População Negra

Os dados existem no PEC/e-SUS, mas estão dispersos e exigem hoje um processo manual de extração e análise, feito por unidade de saúde — não por Equipe de Saúde da Família, que é o nível em que a gestão precisaria agir para priorizar capacitação. Raça/cor e deficiência já são campos obrigatórios no sistema, mas sem garantia de completude; orientação sexual e identidade de gênero dependem de um filtro de duas etapas ("deseja informar?" → categoria), o que resulta em um alto volume de registros "não informado" — e os dados de LGBTQIAPN+ ainda dependem de planilhas extraídas manualmente, sem relatório sistematizado no próprio PEC. Esse sub-registro é atribuído, em boa parte, aos Agentes Comunitários de Saúde (ACS), que muitas vezes não chegam a perguntar esses campos.

Resolver isso destravaria decisões concretas de gestão: descentralizar a distribuição de hormônio para pessoas trans (hoje concentrada em uma única farmácia da cidade), direcionar busca ativa de prevenção ao câncer de colo do útero e cursos de Libras por território, e identificar erros de cadastro a partir de padrões espaciais. O escopo é a Atenção Básica (ACS/UBS); o Serviço de Atenção Domiciliar (SAD) fica fora.

**Situação atual**: o acesso ao PEC/e-SUS ainda não foi liberado pela Secretaria.

## Nossa solução

Um pipeline de dados em camadas (arquitetura medalhão), desenhado para funcionar hoje com fontes públicas reais e uma camada de dados **fictícios/simulados** — com a mesma estrutura do PEC real — e para absorver o PEC de verdade, sem redesenho, no momento em que o acesso for liberado. Enquanto isso, o pipeline já entrega: uma base territorial real (unidades, equipes, distritos), mapas de calor e ranking de completude sobre dados simulados, e um agente de consulta em linguagem natural — tudo pronto para receber o dado real no lugar do fictício.

## Arquitetura

```
                              APIs públicas (CNES, IBGE, Dados Recife)
                                              │
                                arquivos JSON locais (bronze)
                                              │
                    ┌─────────────────────────┴─────────────────────────┐
                    │                                                   │
        MongoDB Atlas (bronze) ◄────────── gerador de dados fictícios (src/mock/)
                    │                       estrutura real do PEC, dados simulados
                    │
      transformação e limpeza (silver)
                    │
          Neon / PostgreSQL (silver)
                    │
      ┌─────────────┴─────────────┐
      │                           │
Dashboard (Streamlit + Plotly)   Agente de perguntas em linguagem
                                  natural (Ollama, local, sem API paga)
```

- **Extração (`src/extract/`)**: um script por fonte pública, que consulta a API e salva o resultado bruto em `data/bronze/<fonte>/`, sem transformação.
- **Simulação (`src/mock/`)**: gera dados **fictícios** com a estrutura real do PEC (raça/cor, deficiência, orientação sexual e identidade de gênero com o filtro de duas etapas, exclusão de crianças de 0 a 10 anos), ancorados nas equipes/unidades/distritos reais do CNES. Não é extração — não existe fonte real por trás.
- **Carga bronze (`src/load_bronze/`)**: lê os arquivos (reais e fictícios) e insere cada um em uma coleção no MongoDB Atlas, com metadados de rastreabilidade (`_meta`) — coleções fictícias recebem também um aviso explícito (`_meta.aviso`).
- **Transformação silver (`src/transform/`)**: lê as coleções do MongoDB, limpa e organiza os dados em tabelas relacionais no Neon/PostgreSQL. Separado em dois scripts: um para os dados reais, outro para os fictícios.
- **Agente (`src/agent/`)**: responde perguntas em português sobre os dados do Neon, usando um LLM local (Ollama) para gerar SQL — sem depender de nenhuma API paga.

## Fontes de dados reais utilizadas

Nenhuma das fontes abaixo é o PEC/e-SUS. São fontes **públicas**, usadas para construir a dimensão de território, unidade de saúde e o "baseline" populacional.

### 1. CNES — Cadastro Nacional de Estabelecimentos de Saúde
**Plataforma**: `cnes.datasus.gov.br` (Ministério da Saúde / DATASUS)

| Dataset | Volume | Conteúdo |
|---|---|---|
| Estabelecimentos de saúde do Recife | 4.670 unidades (521 atendem SUS) | Nome, código CNES, endereço, distrito sanitário |
| Equipes de Saúde da Família | 827 equipes (433 do tipo ESF) | Tipo de equipe, unidade vinculada, status de ativação |

**Papel no projeto**: dimensão "Unidade" e "Equipe" — usa o mesmo código CNES que o PEC utiliza, e é a base territorial sobre a qual a camada de simulação (e futuramente o PEC real) se apoia.

### 2. IBGE — Censo Demográfico (via API SIDRA)
**Ano de referência**: 2022

| Dataset | Conteúdo |
|---|---|
| População do Recife por raça/cor | Branca, Preta, Parda, Amarela, Indígena |
| População do Recife com deficiência, por tipo | 5 tipos de dificuldade + total oficial |

**Papel no projeto**: linha de base populacional real da cidade — referência ("esperado") para comparar com o que for observado nos atendimentos.

**Limitação conhecida**: só disponível a nível de município inteiro, não por distrito — por isso a distribuição por Distrito Sanitário (usada no mapa de gap racial) é, por ora, simulada (ver seção de dados fictícios).

### 3. Dados Recife (Portal de Dados Abertos da Prefeitura)

| Dataset | Volume | Conteúdo |
|---|---|---|
| Distritos Sanitários do Recife (geometria) | 8 distritos | Polígonos geográficos de cada Distrito Sanitário |
| Distritos Sanitários — bairros | 94 bairros | Mapeamento de bairro → Distrito Sanitário |

**Papel no projeto**: base geográfica para os mapas de calor e de gap.

## Dados fictícios/simulados (`src/mock/`)

**Importante**: os dados abaixo são 100% fictícios. Não representam pacientes, atendimentos ou população real de Recife. Foram gerados para testar o pipeline (mapas, indicadores, modelo de ML) enquanto o PEC/e-SUS real não é liberado, seguindo a estrutura real descrita pela Secretaria.

| Dataset | Volume | Conteúdo |
|---|---|---|
| Atendimentos simulados | ~54.800 registros | Um atendimento por linha, ligado a uma equipe ESF real; raça/cor, deficiência, orientação sexual e identidade de gênero seguindo a lógica real do PEC (incluindo a possibilidade de campo vazio, simulando o sub-registro) |
| População negra esperada por distrito | 8 distritos | Percentual ilustrativo, usado como referência ("esperado") no mapa de gap racial |

**Regra de negócio replicada**: atendimentos de pacientes com menos de 10 anos não têm orientação sexual/identidade de gênero preenchidos — mesma exclusão adotada pela Secretaria.

**Desigualdade simulada de propósito**: cada equipe tem uma taxa de completude diferente, para que o ranking de piores equipes (usado para priorizar capacitação) tenha algo real para ordenar, em vez de todas as equipes terem o mesmo número por acaso.

Gerado por `src/mock/gerar_mock_pec.py`, que lê as equipes ESF reais e ativas no Neon para ancorar a simulação na estrutura territorial verdadeira.

## Banco de dados (MongoDB Atlas — camada bronze)

**Banco**: `bronze_equidade_saude`

| Coleção | Documentos | Fonte |
|---|---|---|
| `cnes_estabelecimentos` | 4.670 | real |
| `cnes_estabelecimentos_detalhe` | 521 | real |
| `cnes_equipes` | 827 | real |
| `ibge_censo_raca_cor` | 7 | real |
| `ibge_censo_deficiencia_tipo` | 19 | real |
| `dados_recife_distritos_geometria` | 1 (GeoJSON) | real |
| `dados_recife_distritos_bairros` | 94 | real |
| `mock_pec_atendimentos` | ~54.800 | **fictício** |
| `mock_populacao_negra_distrito` | 8 | **fictício** |

## Banco de dados (Neon/PostgreSQL — camada silver)

| Tabela | Linhas | Fonte | Conteúdo |
|---|---|---|---|
| `unidades_saude` | 521 | real | Unidades de saúde, distrito, bairro, endereço, coordenadas |
| `equipes_saude` | 827 | real | Equipes vinculadas a cada unidade, com status de ativação |
| `censo_raca_cor` | 5 | real | População do Recife por raça/cor (Censo 2022) |
| `censo_deficiencia` | 6 | real | População do Recife por tipo de deficiência (Censo 2022) + total oficial (`e_total`) |
| `mock_pec_atendimentos` | ~54.800 | **fictício** | Atendimentos simulados por equipe, com os campos sensíveis do PEC |
| `mock_populacao_negra_distrito` | 8 | **fictício** | Percentual esperado de população negra por distrito (referência do mapa de gap) |

As duas tabelas fictícias têm um `COMMENT ON TABLE` no próprio banco avisando que são simuladas — qualquer pessoa consultando o Neon direto vê o aviso.

**Achado de qualidade de dados (dado real)**: uma parte das unidades de saúde não tem `distrito_sanitario_codigo` preenchido no CNES (hospitais, laboratórios e outros estabelecimentos que não pertencem a um Distrito Sanitário). Essa lacuna foi mantida — não "corrigida" — porque é uma inconsistência real que a Secretaria precisa ver e resolver na fonte.

**Cuidado estatístico**: em `censo_deficiencia`, os tipos de dificuldade não são mutuamente exclusivos — por isso a coluna `e_total` identifica a linha com o total oficial, que não deve ser recalculado somando as categorias.

## Agente de perguntas em linguagem natural

Permite perguntar em português sobre os dados do Neon e receber uma resposta direta. Roda 100% local, sem API paga:

1. O LLM local (`llama3.2`, via [Ollama](https://ollama.com)) traduz a pergunta em SQL.
2. O SQL é executado no Neon (só `SELECT` é permitido, por segurança).
3. Resultado de um único número é formatado direto pelo código (mais confiável); resultados com várias linhas passam pelo LLM para virar uma frase. Se a pergunta envolver as tabelas fictícias, a resposta inclui um aviso de dado simulado.

Arquivos: `src/agent/assistente.py` (motor) e `src/agent/app_streamlit.py` (interface web).

## Dashboard (Streamlit + Plotly)

Camada de consumo/visualização — substitui o Metabase, que exigia login e não permitia depuração direta do código. Duas abas:

- **Contexto Estrutural**: 7 gráficos com dado real (CNES + Censo) — total de unidades/equipes, distribuição por distrito e tipo, população por raça/cor e deficiência, e a tabela do achado de qualidade (unidades sem Distrito Sanitário).
- **Equidade e Qualidade do Cadastro**: 10 gráficos com dado fictício (`mock_pec_atendimentos`) — KPIs de preenchimento, 3 mapas de calor com o GeoJSON real dos Distritos Sanitários (concentração LGBTQIAPN+, concentração PCD com filtro por tipo, gap racial Censo × observado), distribuição de raça/cor por distrito (detecção de inconsistência de cadastro), ranking de equipes por preenchimento, evolução no tempo, e inconsistências de orientação sexual.

Arquivo: `src/dashboard/app_dashboard.py`.

## Estrutura de pastas

```
Projeto - BD/
├── .env                            # credenciais (MongoDB, Neon) — não versionado
├── requirements.txt
├── data/
│   └── bronze/
│       ├── cnes/
│       ├── ibge/
│       ├── dados_recife/
│       └── mock_pec/               # dados fictícios gerados
└── src/
    ├── extract/                    # um script por fonte pública
    │   ├── cnes_estabelecimentos.py
    │   ├── cnes_estabelecimentos_detalhe.py
    │   ├── cnes_equipes.py
    │   ├── ibge_censo_raca_cor.py
    │   ├── ibge_censo_deficiencia.py
    │   ├── dados_recife_distritos_geometria.py
    │   └── dados_recife_distritos_bairros.py
    ├── mock/
    │   └── gerar_mock_pec.py       # gera os dados fictícios com estrutura real do PEC
    ├── load_bronze/
    │   └── carregar_mongo.py       # sobe os arquivos (reais e fictícios) para o MongoDB
    ├── transform/
    │   ├── mongo_para_neon.py      # tabelas reais: Mongo (bronze) → Neon (silver)
    │   └── mongo_para_neon_mock.py # tabelas fictícias: Mongo (bronze) → Neon (silver)
    ├── agent/
    │   ├── assistente.py           # motor do agente (SQL + resposta via Ollama)
    │   ├── app_streamlit.py        # interface web do agente
    │   └── testar_ollama.py        # script de teste da conexão com o Ollama
    ├── dashboard/
    │   └── app_dashboard.py        # dashboard de visualização (Streamlit + Plotly)
    └── utils/
        ├── testar_conexao_mongo.py
        ├── testar_conexao_neon.py
        └── gerar_kickoff_pptx.py   # gera os slides do kick-off (python-pptx)
```

## Como rodar

### Se você só vai apresentar (agente + dashboard, dado já está no Neon compartilhado)

Não precisa rodar nenhum script de extração/carga — os dados (reais e fictícios) já estão no banco Neon compartilhado pelo grupo. Só precisa:

```bash
# 1. Clonar o repositório
git clone git@github.com:fccbl/etl-equidade-saude-recife.git
cd etl-equidade-saude-recife

# 2. Criar ambiente virtual e instalar dependências
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 3. Criar o arquivo .env na raiz do projeto (peça a string pro colega que já configurou)
echo 'NEON_DATABASE_URL=postgresql://...' > .env

# 4. Instalar o Ollama (https://ollama.com) e baixar o modelo local — só na primeira vez
ollama pull llama3.2

# 5. Rodar o agente de perguntas
streamlit run src/agent/app_streamlit.py

# 6. Rodar o dashboard (em outro terminal, ou depois de encerrar o agente)
streamlit run src/dashboard/app_dashboard.py
```

⚠️ O `.env` **não vem no repositório** (fica de fora por segurança) — a `NEON_DATABASE_URL` precisa ser enviada por um canal privado (não WhatsApp de grupo, não commit no GitHub) por quem já tem acesso.

### Pipeline completo, do zero (extração + carga + geração do mock)

```bash
# 1. Extrair os dados reais das APIs públicas
python src/extract/cnes_estabelecimentos.py
python src/extract/cnes_estabelecimentos_detalhe.py
python src/extract/cnes_equipes.py
python src/extract/ibge_censo_raca_cor.py
python src/extract/ibge_censo_deficiencia.py
python src/extract/dados_recife_distritos_geometria.py
python src/extract/dados_recife_distritos_bairros.py

# 2. Carregar os dados reais no MongoDB (bronze) e transformar no Neon (silver)
python src/load_bronze/carregar_mongo.py
python src/transform/mongo_para_neon.py

# 3. Gerar os dados fictícios (precisa das equipes reais já carregadas no Neon)
python src/mock/gerar_mock_pec.py

# 4. Carregar os dados fictícios no MongoDB e transformar no Neon
python src/load_bronze/carregar_mongo.py
python src/transform/mongo_para_neon_mock.py

# 5. Rodar o agente e o dashboard
ollama pull llama3.2          # uma vez só, baixa o modelo local
streamlit run src/agent/app_streamlit.py
streamlit run src/dashboard/app_dashboard.py
```

## Próximas etapas

1. **Modelo de Machine Learning**: classificação de risco de não-preenchimento por atendimento (`risco_nao_preenchimento`), usando `mock_pec_atendimentos` como base de treino.
2. **Integração com o PEC/e-SUS APS real**: pendente de liberação de acesso pela Secretaria — nesse momento, as tabelas fictícias são substituídas pelas reais, mantendo a mesma estrutura.
