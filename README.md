# ETL — Políticas de Equidade em Saúde (Recife)

## Contexto do desafio

A Secretaria de Atenção Básica do Recife enfrenta dificuldade para transformar os dados do **PEC/e-SUS APS** (sistema de prontuário da Atenção Primária à Saúde) em indicadores estratégicos para três políticas municipais de equidade:

- Saúde Integral da População LGBTQIAPN+
- Atenção Integral à Saúde da Pessoa com Deficiência
- Saúde Integral da População Negra

Os dados existem no PEC/e-SUS, mas estão dispersos em diferentes campos e exigem hoje um processo manual de extração e análise. O objetivo deste projeto é construir um pipeline automatizado que extraia, integre e disponibilize esses dados em painéis, indicadores e, futuramente, modelos de aprendizado de máquina.

**Situação atual**: o acesso ao PEC/e-SUS ainda não foi liberado pela Secretaria. Enquanto isso, construímos a camada de dados públicos que serve de contexto territorial e populacional, e que será cruzada com o PEC assim que ele estiver disponível.

## Arquitetura

```
APIs públicas → arquivos JSON locais (bronze) → MongoDB Atlas (bronze)
                                                        │
                                    transformação e limpeza (silver)
                                                        │
                                              Neon / PostgreSQL (silver)
                                                        │
                                    ┌───────────────────┴───────────────────┐
                                    │                                       │
                          Metabase (dashboards)              Agente de perguntas em linguagem
                                                              natural (Ollama, local, sem API paga)
```

- **Extração (`src/extract/`)**: um script por fonte de dado, que consulta a API pública e salva o resultado bruto em `data/bronze/<fonte>/`, sem nenhuma transformação.
- **Carga bronze (`src/load_bronze/`)**: lê os arquivos salvos e insere cada um em uma coleção própria no MongoDB Atlas, adicionando metadados de rastreabilidade (`_meta`: arquivo de origem e data/hora da carga).
- **Transformação silver (`src/transform/`)**: lê as coleções do MongoDB, limpa e organiza os dados em tabelas relacionais, e carrega no Neon/PostgreSQL.
- **Agente (`src/agent/`)**: responde perguntas em português sobre os dados do Neon, usando um LLM local (Ollama) para gerar SQL e formular a resposta — sem depender de nenhuma API paga.

## Fontes de dados utilizadas

Nenhuma das fontes abaixo é o PEC/e-SUS. São todas fontes **públicas**, usadas para construir a dimensão de território, unidade de saúde e o "baseline" populacional — o contexto contra o qual os dados do PEC serão comparados no futuro.

### 1. CNES — Cadastro Nacional de Estabelecimentos de Saúde
**Plataforma**: `cnes.datasus.gov.br` (Ministério da Saúde / DATASUS)
**Ano de referência**: dado corrente (consulta em tempo real ao cadastro nacional)

| Dataset | Volume | Conteúdo |
|---|---|---|
| Estabelecimentos de saúde do Recife | 4.670 unidades (521 atendem SUS) | Nome, código CNES, endereço, se atende SUS |
| Equipes de Saúde da Família | 827 equipes | Tipo de equipe, unidade vinculada, marcadores de população (quilombola, indígena, ribeirinha, assentada) |

**Papel no projeto**: dimensão "Unidade de Saúde" e "Equipe" — usa o mesmo código CNES/INE que o PEC utiliza, permitindo o cruzamento direto quando os dados do PEC chegarem.

### 2. IBGE — Censo Demográfico (via API SIDRA)
**Plataforma**: `apisidra.ibge.gov.br`
**Ano de referência**: **2022** (Censo Demográfico, edição mais recente)

| Dataset | Tabela SIDRA | Conteúdo |
|---|---|---|
| População do Recife por raça/cor | 9605 | Total: 1.488.920 — Branca: 578.413, Preta: 182.546, Parda: 722.555, Amarela: 2.703, Indígena: 2.656 |
| População do Recife com deficiência, por tipo | 10127 | Total com deficiência: 122.531 — detalhado por dificuldade visual, auditiva, motora, manual e mental/cognitiva |

**Papel no projeto**: baseline populacional. Serve para comparar "quantas pessoas negras/com deficiência esperaríamos encontrar no Recife segundo o Censo" com o que estiver de fato cadastrado no PEC — uma forma de identificar sub-registro ou barreiras de acesso.

**Limitação conhecida**: o Censo, nessas tabelas, só está disponível a nível de **município inteiro** — não desce a bairro. O detalhamento territorial fino só será possível quando cruzado com o endereço de cada pessoa no PEC.

### 3. Dados Recife (Portal de Dados Abertos da Prefeitura)
**Plataforma**: `dados.recife.pe.gov.br` (mantido pela EMPREL, dado de responsabilidade da Secretaria de Saúde)
**Ano de referência**: última atualização registrada em março/2026

| Dataset | Volume | Conteúdo |
|---|---|---|
| Distritos Sanitários do Recife (geometria) | 8 distritos | Polígonos geográficos de cada Distrito Sanitário |
| Distritos Sanitários — descrição dos bairros | 94 bairros | Mapeamento de cada bairro do Recife ao seu Distrito Sanitário (ex.: Boa Vista → Distrito I) |

**Papel no projeto**: esta é a peça-chave para a análise territorial. É o único dado que permite traduzir "bairro do endereço do cidadão" em "Distrito Sanitário" — atende diretamente à exigência do desafio de analisar a população por Distrito Sanitário.

## O que este pipeline NÃO resolve (ainda)

Nenhuma fonte pública consultada tem dados sobre **orientação sexual, identidade de gênero, nome social ou raça/cor por pessoa cadastrada na APS**. Essas informações existem exclusivamente no cadastro individual do PEC/e-SUS. Ou seja, o que este pipeline entrega hoje é a **infraestrutura de apoio** (território, unidade, equipe, baseline populacional) — os indicadores centrais do desafio (quantitativo de pessoas LGBTQIAPN+, perfil de PCD e população negra cadastradas) só poderão ser calculados após a integração com o PEC.

## Banco de dados (MongoDB Atlas — camada bronze)

**Banco**: `bronze_equidade_saude`

| Coleção | Documentos |
|---|---|
| `cnes_estabelecimentos` | 4.670 |
| `cnes_equipes` | 827 |
| `ibge_censo_raca_cor` | 7 |
| `ibge_censo_deficiencia_tipo` | 19 |
| `dados_recife_distritos_geometria` | 1 (GeoJSON com os 8 distritos) |
| `dados_recife_distritos_bairros` | 94 |

## Banco de dados (Neon/PostgreSQL — camada silver)

Tabelas relacionais, já limpas e prontas para consumo (dashboards e agente):

| Tabela | Linhas | Conteúdo |
|---|---|---|
| `unidades_saude` | 521 | Unidades de saúde do Recife, com distrito sanitário, bairro, endereço e coordenadas |
| `equipes_saude` | 827 | Equipes vinculadas a cada unidade, com data de ativação/desativação |
| `censo_raca_cor` | 5 | População do Recife por raça/cor (Censo 2022) |
| `censo_deficiencia` | 6 | População do Recife por tipo de deficiência (Censo 2022) + total oficial (`e_total`) |

**Achado de qualidade de dados**: uma parte das unidades de saúde não tem `distrito_sanitario_codigo` preenchido no CNES (hospitais, laboratórios e outros estabelecimentos que não pertencem a um Distrito Sanitário). Essa lacuna foi mantida — e não "corrigida" artificialmente — porque é uma inconsistência real que a Secretaria precisa ver e resolver na fonte.

**Cuidado estatístico**: em `censo_deficiencia`, os tipos de dificuldade não são mutuamente exclusivos (uma pessoa pode ter mais de um tipo) — por isso a coluna `e_total` identifica a linha com o total oficial, que não deve ser recalculado somando as categorias.

## Agente de perguntas em linguagem natural

Permite perguntar em português sobre os dados do Neon (ex.: *"Quantas unidades de saúde tem no Distrito Sanitário I?"*) e receber uma resposta direta. Roda 100% local, sem nenhuma API paga:

1. O LLM local (`llama3.2`, via [Ollama](https://ollama.com)) traduz a pergunta em SQL.
2. O SQL é executado no Neon (só `SELECT` é permitido, por segurança).
3. O resultado é formatado em português — respostas de um único número são montadas diretamente pelo código (mais confiável); resultados com várias linhas passam pelo LLM para virar uma frase.

Arquivos: `src/agent/assistente.py` (motor) e `src/agent/app_streamlit.py` (interface web).

## Estrutura de pastas

```
Projeto - BD/
├── .env                        # credenciais (MongoDB, Neon) — não versionado
├── requirements.txt
├── data/
│   └── bronze/                 # arquivos JSON brutos, por fonte
│       ├── cnes/
│       ├── ibge/
│       └── dados_recife/
└── src/
    ├── extract/                # um script por fonte de dado
    │   ├── cnes_estabelecimentos.py
    │   ├── cnes_estabelecimentos_detalhe.py
    │   ├── cnes_equipes.py
    │   ├── ibge_censo_raca_cor.py
    │   ├── ibge_censo_deficiencia.py
    │   ├── dados_recife_distritos_geometria.py
    │   └── dados_recife_distritos_bairros.py
    ├── load_bronze/
    │   └── carregar_mongo.py   # sobe todos os arquivos bronze para o MongoDB
    ├── transform/
    │   └── mongo_para_neon.py  # limpa e carrega os dados do Mongo (bronze) no Neon (silver)
    ├── agent/
    │   ├── assistente.py       # motor do agente (SQL + resposta via Ollama)
    │   ├── app_streamlit.py    # interface web do agente
    │   └── testar_ollama.py    # script de teste da conexão com o Ollama
    └── utils/
        ├── testar_conexao_mongo.py
        └── testar_conexao_neon.py
```

## Como rodar

```bash
# 1. Extrair os dados das APIs (gera os arquivos em data/bronze/)
python src/extract/cnes_estabelecimentos.py
python src/extract/cnes_estabelecimentos_detalhe.py
python src/extract/cnes_equipes.py
python src/extract/ibge_censo_raca_cor.py
python src/extract/ibge_censo_deficiencia.py
python src/extract/dados_recife_distritos_geometria.py
python src/extract/dados_recife_distritos_bairros.py

# 2. Carregar tudo no MongoDB (bronze)
python src/load_bronze/carregar_mongo.py

# 3. Transformar e carregar no Neon (silver)
python src/transform/mongo_para_neon.py

# 4. Rodar o agente de perguntas
ollama pull llama3.2          # uma vez só, baixa o modelo local
streamlit run src/agent/app_streamlit.py
```

## Próximas etapas

1. **Dashboards (Metabase)**: painel com indicadores de contexto territorial e populacional (unidades e equipes por distrito, população por raça/cor e deficiência, e o achado de qualidade de dados).
2. **Mais validação do agente**: cobrir perguntas fora do escopo atual (ex.: dados que ainda não existem, como LGBTQIAPN+) para garantir que ele admita a limitação em vez de inventar uma resposta.
3. **Integração com o PEC/e-SUS APS**: pendente de liberação de acesso pela Secretaria — é o que vai permitir calcular os indicadores centrais do desafio (LGBTQIAPN+, PCD, população negra) cruzados por unidade de saúde.

