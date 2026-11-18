"""
EquiDados — Cadastro e Consultas (modelagem pessoa / atendimento)

Interface pedida pelo professor:
  1. Cadastro: nova pessoa (Ficha de Cadastro Individual do e-SUS) + atendimento
     com data e hora, ou novo atendimento para uma pessoa já cadastrada (1:N).
  2. Consultas iniciais: filtros simples sobre os atendimentos.
  3. Importar arquivo: CSV/Excel com várias fichas e atendimentos de uma vez.
  4. Consultas avançadas: tabela cruzada (linhas x colunas), lista de combinações
     e consultas prontas.
  5. Exportar dados: período (1, 2, 3, 6 meses ou personalizado), filtros e
     colunas escolhidas, em CSV ou Excel.

Usa a branch `modelagem-pessoa` do Neon (variável NEON_DATABASE_URL_MODELAGEM
no .env), para não mexer no banco principal.

Rodar com: streamlit run src/interface/app_cadastro_consultas.py
"""

import csv
import os
import re
from datetime import date, datetime, time

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()
DB_URL = os.getenv("NEON_DATABASE_URL_MODELAGEM")

st.set_page_config(page_title="EquiDados — Cadastro e Consultas", page_icon="🩺", layout="wide")

NAO_INFORMADO = "Não informado"
LIMITE_LINHAS = 500


# ---------------------------------------------------------------------------
# Banco
# ---------------------------------------------------------------------------

@st.cache_resource
def obter_engine():
    return create_engine(DB_URL, pool_pre_ping=True)


def consultar(sql, params=None):
    with obter_engine().connect() as con:
        return pd.read_sql(text(sql), con, params=params or {})


@st.cache_data(ttl=600)
def dominio(tabela, coluna_id):
    # tabela/coluna vêm só do código (nunca do usuário)
    return consultar(f"SELECT {coluna_id} AS id, descricao FROM {tabela} ORDER BY descricao")


@st.cache_data(ttl=600)
def carregar_equipes():
    return consultar("""
        SELECT e.codigo_equipe, e.nome_equipe, u.nome_fantasia AS unidade,
               coalesce(d.nome, d.codigo) AS distrito
        FROM equipes_saude e
        LEFT JOIN unidades_saude u      ON u.cnes = e.cnes_unidade
        LEFT JOIN distrito_sanitario d  ON d.codigo = u.distrito_sanitario_codigo
        WHERE EXISTS (SELECT 1 FROM microarea m WHERE m.id_equipe = e.codigo_equipe)
        ORDER BY distrito, e.nome_equipe
    """)


@st.cache_data(ttl=600)
def carregar_distritos():
    return consultar("SELECT codigo, coalesce(nome, codigo) AS nome FROM distrito_sanitario ORDER BY nome")


@st.cache_data(ttl=600)
def microareas_da_equipe(id_equipe):
    return consultar(
        "SELECT id_microarea, codigo FROM microarea WHERE id_equipe = :e ORDER BY codigo",
        {"e": id_equipe},
    )


@st.cache_data(ttl=600)
def periodo_atendimentos():
    df = consultar("SELECT min(data_hora_atendimento)::date AS ini, max(data_hora_atendimento)::date AS fim FROM atendimento")
    ini = pd.Timestamp(df.iloc[0]["ini"]).date()
    fim = pd.Timestamp(df.iloc[0]["fim"]).date()
    return ini, max(fim, date.today())  # inclui os cadastros feitos hoje


def rotulos_equipes():
    eq = carregar_equipes()
    return {
        r.codigo_equipe: f"{r.nome_equipe} — {r.unidade or 'sem unidade'} ({r.distrito or 'sem distrito'}) · INE {r.codigo_equipe}"
        for r in eq.itertuples()
    }


# ---------------------------------------------------------------------------
# Componentes
# ---------------------------------------------------------------------------

def seletor_dominio(rotulo, tabela, coluna_id, key, permitir_nulo=True):
    """Selectbox de um domínio; devolve o id escolhido ou None (= não informado)."""
    df = dominio(tabela, coluna_id)
    nomes = dict(zip(df["id"], df["descricao"]))
    opcoes = ([None] if permitir_nulo else []) + df["id"].tolist()
    return st.selectbox(
        rotulo, opcoes, key=key,
        format_func=lambda i: NAO_INFORMADO if i is None else nomes[i],
    )


def pergunta_condicional(rotulo_pergunta, rotulo_qual, tabela, coluna_id, key):
    """'Deseja informar X?' da ficha. Devolve o id escolhido ou None."""
    resposta = st.radio(rotulo_pergunta, ["Sim", "Não", NAO_INFORMADO], horizontal=True,
                        index=2, key=f"{key}_pergunta")
    if resposta == "Sim":
        return seletor_dominio(rotulo_qual, tabela, coluna_id, key=f"{key}_qual", permitir_nulo=False)
    return None


def calcular_idade(nascimento, na_data):
    return na_data.year - nascimento.year - ((na_data.month, na_data.day) < (nascimento.month, nascimento.day))


def campos_atendimento(key, data_nascimento=None):
    """Campos do atendimento. Devolve dict com os valores (ou None nos opcionais)."""
    c1, c2, c3, c4 = st.columns(4)
    data_at = c1.date_input("Data do atendimento *", value=date.today(), max_value=date.today(),
                            format="DD/MM/YYYY", key=f"{key}_data")
    hora_at = c2.time_input("Hora do atendimento *", value=time(8, 0), step=600, key=f"{key}_hora")
    with c3:
        id_tipo_at = seletor_dominio("Tipo de atendimento *", "tipo_atendimento", "id_tipo_atendimento",
                                     key=f"{key}_tipo", permitir_nulo=False)
    with c4:
        id_tipo_prof = seletor_dominio("Profissional *", "tipo_profissional", "id_tipo_profissional",
                                       key=f"{key}_prof", permitir_nulo=False)

    if data_nascimento:
        idade = calcular_idade(data_nascimento, data_at)
        st.caption(f"Idade no atendimento (calculada pela data de nascimento): **{idade} anos**")
    else:
        idade = st.number_input("Idade no atendimento (se não houver data de nascimento)",
                                min_value=0, max_value=130, value=None, step=1, key=f"{key}_idade")

    return {
        "data_hora": datetime.combine(data_at, hora_at),
        "id_tipo_atendimento": id_tipo_at,
        "id_tipo_profissional": id_tipo_prof,
        "idade": int(idade) if idade is not None else None,
    }


def inserir_atendimento(con, id_pessoa, id_equipe, at):
    return con.execute(text("""
        INSERT INTO atendimento (id_pessoa, id_equipe, id_tipo_atendimento, id_tipo_profissional,
                                 data_hora_atendimento, idade_no_atendimento)
        VALUES (:p, :e, :ta, :tp, :dh, :idade)
        RETURNING id_atendimento
    """), {
        "p": id_pessoa, "e": id_equipe, "ta": at["id_tipo_atendimento"],
        "tp": at["id_tipo_profissional"], "dh": at["data_hora"], "idade": at["idade"],
    }).scalar_one()


# ---------------------------------------------------------------------------
# Página 1 — Cadastro
# ---------------------------------------------------------------------------

def cadastro_nova_pessoa():
    st.subheader("Identificação e território")
    rotulos = rotulos_equipes()
    c1, c2 = st.columns([3, 1])
    id_equipe = c1.selectbox("Equipe que fez a coleta (INE) *", list(rotulos), key="np_equipe",
                             format_func=lambda c: rotulos[c])
    micro = microareas_da_equipe(id_equipe)
    cod_micro = dict(zip(micro["id_microarea"], micro["codigo"]))
    id_micro = c2.selectbox("Microárea *", micro["id_microarea"].tolist(), key="np_micro",
                            format_func=lambda i: cod_micro[i])

    c1, c2 = st.columns(2)
    nome_social = c1.text_input("Nome social (opcional)", key="np_nome_social").strip() or None
    data_nasc = c2.date_input("Data de nascimento", value=None, min_value=date(1900, 1, 1),
                              max_value=date.today(), format="DD/MM/YYYY", key="np_nasc")

    st.subheader("Informações sociodemográficas")
    id_raca = seletor_dominio("Raça/cor", "raca_cor", "id_raca_cor", key="np_raca")
    c1, c2 = st.columns(2)
    with c1:
        id_orient = pergunta_condicional("Deseja informar orientação sexual?", "Qual orientação sexual?",
                                         "orientacao_sexual", "id_orientacao_sexual", key="np_orient")
    with c2:
        id_ident = pergunta_condicional("Deseja informar identidade de gênero?", "Qual identidade de gênero?",
                                        "identidade_genero", "id_identidade_genero", key="np_ident")

    resp_def = st.radio("Tem alguma deficiência?", ["Sim", "Não", NAO_INFORMADO], horizontal=True,
                        index=2, key="np_def_pergunta")
    deficiencias = []
    if resp_def == "Sim":
        df_def = dominio("deficiencia", "id_deficiencia")
        nomes_def = dict(zip(df_def["id"], df_def["descricao"]))
        deficiencias = st.multiselect("Qual(is)? (pode marcar mais de uma)", df_def["id"].tolist(),
                                      format_func=lambda i: nomes_def[i], key="np_def_quais")
    tem_def = {"Sim": True, "Não": False}.get(resp_def)

    st.subheader("Atendimento")
    at = campos_atendimento("np_at", data_nasc)

    if st.button("Salvar cadastro", type="primary", key="np_salvar"):
        erros = []
        if resp_def == "Sim" and not deficiencias:
            erros.append("Marque pelo menos uma deficiência (ou responda 'Não' / 'Não informado').")
        if data_nasc and data_nasc > at["data_hora"].date():
            erros.append("A data de nascimento não pode ser depois da data do atendimento.")
        if at["data_hora"] > datetime.now():
            erros.append("O atendimento não pode estar no futuro.")
        if erros:
            for e in erros:
                st.error(e)
            return

        with obter_engine().begin() as con:  # tudo ou nada
            id_pessoa = con.execute(text("""
                INSERT INTO pessoa (id_raca_cor, id_orientacao_sexual, id_identidade_genero,
                                    id_microarea, id_equipe, data_coleta, tem_deficiencia,
                                    nome_social, data_nascimento)
                VALUES (:raca, :orient, :ident, :micro, :equipe, :coleta, :temdef, :nome, :nasc)
                RETURNING id_pessoa
            """), {
                "raca": id_raca, "orient": id_orient, "ident": id_ident, "micro": id_micro,
                "equipe": id_equipe, "coleta": at["data_hora"].date(), "temdef": tem_def,
                "nome": nome_social, "nasc": data_nasc,
            }).scalar_one()
            for id_def in deficiencias:
                con.execute(text("INSERT INTO pessoa_deficiencia (id_pessoa, id_deficiencia) VALUES (:p, :d)"),
                            {"p": id_pessoa, "d": id_def})
            id_at = inserir_atendimento(con, id_pessoa, id_equipe, at)

        st.success(f"Cadastro salvo: pessoa nº **{id_pessoa}**, atendimento nº **{id_at}**. "
                   f"Use o nº da pessoa para registrar novos atendimentos dela.")


def resumo_pessoa(id_pessoa):
    df = consultar("""
        SELECT p.id_pessoa, p.nome_social, p.data_nascimento, p.id_equipe, m.codigo AS microarea,
               coalesce(rc.descricao, :ni) AS raca_cor,
               coalesce(os.descricao, :ni) AS orientacao_sexual,
               coalesce(ig.descricao, :ni) AS identidade_genero,
               CASE WHEN p.tem_deficiencia IS NULL THEN :ni
                    WHEN NOT p.tem_deficiencia THEN 'Não'
                    ELSE 'Sim: ' || coalesce((SELECT string_agg(d.descricao, ', ' ORDER BY d.descricao)
                                              FROM pessoa_deficiencia pd
                                              JOIN deficiencia d USING (id_deficiencia)
                                              WHERE pd.id_pessoa = p.id_pessoa), '-')
               END AS deficiencia,
               (SELECT count(*) FROM atendimento a WHERE a.id_pessoa = p.id_pessoa) AS atendimentos
        FROM pessoa p
        JOIN microarea m               ON m.id_microarea = p.id_microarea
        LEFT JOIN raca_cor rc          ON rc.id_raca_cor = p.id_raca_cor
        LEFT JOIN orientacao_sexual os ON os.id_orientacao_sexual = p.id_orientacao_sexual
        LEFT JOIN identidade_genero ig ON ig.id_identidade_genero = p.id_identidade_genero
        WHERE p.id_pessoa = :id
    """, {"id": int(id_pessoa), "ni": NAO_INFORMADO})
    return None if df.empty else df.iloc[0]


def historico_atendimentos(id_pessoa):
    return consultar("""
        SELECT a.id_atendimento, a.data_hora_atendimento AS data_hora, ta.descricao AS tipo,
               tp.descricao AS profissional, e.nome_equipe AS equipe, a.idade_no_atendimento AS idade
        FROM atendimento a
        JOIN equipes_saude e            ON e.codigo_equipe = a.id_equipe
        LEFT JOIN tipo_atendimento ta   ON ta.id_tipo_atendimento = a.id_tipo_atendimento
        LEFT JOIN tipo_profissional tp  ON tp.id_tipo_profissional = a.id_tipo_profissional
        WHERE a.id_pessoa = :id
        ORDER BY a.data_hora_atendimento DESC
    """, {"id": int(id_pessoa)})


def cadastro_atendimento_existente():
    id_pessoa = st.number_input("Nº da pessoa", min_value=1, step=1, value=None, key="ex_id")
    if id_pessoa is None:
        st.info("Digite o número da pessoa (aparece ao salvar um cadastro ou nas consultas).")
        return
    pessoa = resumo_pessoa(id_pessoa)
    if pessoa is None:
        st.warning("Pessoa não encontrada.")
        return

    st.markdown(
        f"**Pessoa nº {pessoa.id_pessoa}** · {pessoa.raca_cor} · {pessoa.identidade_genero} · "
        f"{pessoa.orientacao_sexual} · Deficiência: {pessoa.deficiencia} · "
        f"Microárea {pessoa.microarea} · **{pessoa.atendimentos} atendimento(s)** até agora"
    )

    rotulos = rotulos_equipes()
    lista = list(rotulos)
    indice = lista.index(pessoa.id_equipe) if pessoa.id_equipe in rotulos else 0
    id_equipe = st.selectbox("Equipe que fez o atendimento *", lista, index=indice, key="ex_equipe",
                             format_func=lambda c: rotulos[c])
    nasc = pd.Timestamp(pessoa.data_nascimento).date() if pd.notna(pessoa.data_nascimento) else None
    at = campos_atendimento("ex_at", nasc)

    if st.button("Salvar atendimento", type="primary", key="ex_salvar"):
        if at["data_hora"] > datetime.now():
            st.error("O atendimento não pode estar no futuro.")
            return
        with obter_engine().begin() as con:
            id_at = inserir_atendimento(con, int(pessoa.id_pessoa), id_equipe, at)
        st.success(f"Atendimento nº **{id_at}** salvo para a pessoa nº **{pessoa.id_pessoa}**.")

    with st.expander("Histórico de atendimentos desta pessoa"):
        st.dataframe(historico_atendimentos(id_pessoa), hide_index=True, width="stretch")


def pagina_cadastro():
    st.header("Cadastro")
    st.caption("Baseado na Ficha de Cadastro Individual do e-SUS APS. Campos com * são obrigatórios; "
               "o que não for respondido fica como NULL no banco.")
    aba1, aba2 = st.tabs(["Nova pessoa + atendimento", "Novo atendimento (pessoa já cadastrada)"])
    with aba1:
        cadastro_nova_pessoa()
    with aba2:
        cadastro_atendimento_existente()


# ---------------------------------------------------------------------------
# Base das consultas
# ---------------------------------------------------------------------------

FROM_BASE = """
FROM atendimento a
JOIN pessoa p                    ON p.id_pessoa = a.id_pessoa
JOIN equipes_saude e             ON e.codigo_equipe = a.id_equipe
LEFT JOIN unidades_saude u       ON u.cnes = e.cnes_unidade
LEFT JOIN distrito_sanitario d   ON d.codigo = u.distrito_sanitario_codigo
JOIN microarea m                 ON m.id_microarea = p.id_microarea
LEFT JOIN raca_cor rc            ON rc.id_raca_cor = p.id_raca_cor
LEFT JOIN orientacao_sexual os   ON os.id_orientacao_sexual = p.id_orientacao_sexual
LEFT JOIN identidade_genero ig   ON ig.id_identidade_genero = p.id_identidade_genero
LEFT JOIN tipo_atendimento ta    ON ta.id_tipo_atendimento = a.id_tipo_atendimento
LEFT JOIN tipo_profissional tp   ON tp.id_tipo_profissional = a.id_tipo_profissional
"""

JOIN_DEFICIENCIA = """
LEFT JOIN pessoa_deficiencia pd  ON pd.id_pessoa = p.id_pessoa
LEFT JOIN deficiencia df         ON df.id_deficiencia = pd.id_deficiencia
"""

FAIXA_ETARIA = """CASE
    WHEN a.idade_no_atendimento IS NULL THEN 'Não informado'
    WHEN a.idade_no_atendimento < 12 THEN '0-11'
    WHEN a.idade_no_atendimento < 18 THEN '12-17'
    WHEN a.idade_no_atendimento < 30 THEN '18-29'
    WHEN a.idade_no_atendimento < 60 THEN '30-59'
    ELSE '60+' END"""

DIA_SEMANA = """(extract(isodow FROM a.data_hora_atendimento)::int || ' - ' ||
    (ARRAY['Seg','Ter','Qua','Qui','Sex','Sáb','Dom'])[extract(isodow FROM a.data_hora_atendimento)::int])"""

# Dimensões para agrupar (rótulo -> expressão SQL). Só expressões fixas do código.
DIMENSOES = {
    "Raça/cor": "coalesce(rc.descricao, 'Não informado')",
    "Orientação sexual": "coalesce(os.descricao, 'Não informado')",
    "Identidade de gênero": "coalesce(ig.descricao, 'Não informado')",
    "Deficiência": """CASE WHEN p.tem_deficiencia IS NULL THEN 'Não informado'
                         WHEN NOT p.tem_deficiencia THEN 'Nenhuma'
                         ELSE coalesce(df.descricao, 'Não especificada') END""",
    "Distrito sanitário": "coalesce(d.nome, d.codigo, 'Sem distrito')",
    "Equipe": "e.nome_equipe || ' · INE ' || e.codigo_equipe",
    "Microárea (código)": "m.codigo",
    "Tipo de profissional": "coalesce(tp.descricao, 'Não informado')",
    "Tipo de atendimento": "coalesce(ta.descricao, 'Não informado')",
    "Faixa etária": FAIXA_ETARIA,
    "Hora do dia": "lpad(extract(hour FROM a.data_hora_atendimento)::int::text, 2, '0') || 'h'",
    "Dia da semana": DIA_SEMANA,
    "Mês": "to_char(a.data_hora_atendimento, 'YYYY-MM')",
}


def filtro_lista(condicoes, params, nome, coluna, valores):
    """coluna = ANY(lista), aceitando 'Não informado' como IS NULL."""
    if not valores:
        return
    reais = [v for v in valores if v != NAO_INFORMADO]
    partes = []
    if reais:
        partes.append(f"{coluna} = ANY(:{nome})")
        params[nome] = reais
    if NAO_INFORMADO in valores:
        partes.append(f"{coluna} IS NULL")
    condicoes.append("(" + " OR ".join(partes) + ")")


def opcoes_dominio(tabela, com_nulo=True):
    nomes = dominio(tabela, f"id_{tabela}")["descricao"].tolist()
    return nomes + ([NAO_INFORMADO] if com_nulo else [])


def filtro_periodo(key):
    ini, fim = periodo_atendimentos()
    escolha = st.date_input("Período", value=(ini, fim), format="DD/MM/YYYY", key=key)
    if isinstance(escolha, (list, tuple)) and len(escolha) == 2:
        return escolha
    return ini, fim


def mostrar_sql(sql, params):
    with st.expander("Ver o SQL desta consulta"):
        st.code(sql.strip(), language="sql")
        if params:
            st.caption("Parâmetros: " + ", ".join(f"{k} = {v}" for k, v in params.items()))


# ---------------------------------------------------------------------------
# Página 2 — Consultas iniciais
# ---------------------------------------------------------------------------

def pagina_consultas_iniciais():
    st.header("Consultas iniciais")
    aba1, aba2 = st.tabs(["Atendimentos", "Buscar pessoa"])

    with aba1:
        c1, c2, c3 = st.columns(3)
        with c1:
            ini, fim = filtro_periodo("ci_periodo")
        distritos = carregar_distritos()
        nomes_distrito = dict(zip(distritos["codigo"], distritos["nome"]))
        sel_distrito = c2.multiselect("Distrito sanitário", distritos["codigo"].tolist(),
                                      format_func=lambda c: nomes_distrito[c], key="ci_distrito")
        sel_raca = c3.multiselect("Raça/cor", opcoes_dominio("raca_cor"), key="ci_raca")
        c1, c2, c3 = st.columns(3)
        sel_tipo = c1.multiselect("Tipo de atendimento", opcoes_dominio("tipo_atendimento", False), key="ci_tipo")
        sel_prof = c2.multiselect("Profissional", opcoes_dominio("tipo_profissional", False), key="ci_prof")
        rotulos = rotulos_equipes()
        sel_equipe = c3.multiselect("Equipe", list(rotulos), format_func=lambda c: rotulos[c], key="ci_equipe")

        condicoes = ["a.data_hora_atendimento >= :ini", "a.data_hora_atendimento < :fim + 1"]
        params = {"ini": ini, "fim": fim}
        filtro_lista(condicoes, params, "distritos", "d.codigo", sel_distrito)
        filtro_lista(condicoes, params, "racas", "rc.descricao", sel_raca)
        filtro_lista(condicoes, params, "tipos", "ta.descricao", sel_tipo)
        filtro_lista(condicoes, params, "profs", "tp.descricao", sel_prof)
        filtro_lista(condicoes, params, "equipes", "e.codigo_equipe", sel_equipe)
        where = "WHERE " + "\n  AND ".join(condicoes)

        totais = consultar(f"""
            SELECT count(*) AS atendimentos, count(DISTINCT a.id_pessoa) AS pessoas,
                   count(DISTINCT a.id_equipe) AS equipes
            {FROM_BASE} {where}
        """, params).iloc[0]
        m1, m2, m3 = st.columns(3)
        m1.metric("Atendimentos", f"{int(totais.atendimentos):,}".replace(",", "."))
        m2.metric("Pessoas distintas", f"{int(totais.pessoas):,}".replace(",", "."))
        m3.metric("Equipes", f"{int(totais.equipes):,}".replace(",", "."))

        sql = f"""
SELECT a.id_atendimento, a.data_hora_atendimento AS data_hora, a.id_pessoa,
       coalesce(rc.descricao, 'Não informado') AS raca_cor,
       coalesce(ig.descricao, 'Não informado') AS identidade_genero,
       coalesce(os.descricao, 'Não informado') AS orientacao_sexual,
       ta.descricao AS tipo, tp.descricao AS profissional, a.idade_no_atendimento AS idade,
       e.nome_equipe AS equipe, m.codigo AS microarea, coalesce(d.nome, d.codigo) AS distrito
{FROM_BASE}{where}
ORDER BY a.data_hora_atendimento DESC
LIMIT {LIMITE_LINHAS}"""
        st.caption(f"Mostrando os {LIMITE_LINHAS} atendimentos mais recentes do filtro.")
        st.dataframe(consultar(sql, params), hide_index=True, width="stretch")
        mostrar_sql(sql, params)

    with aba2:
        id_pessoa = st.number_input("Nº da pessoa", min_value=1, step=1, value=None, key="ci_pessoa")
        if id_pessoa is not None:
            pessoa = resumo_pessoa(id_pessoa)
            if pessoa is None:
                st.warning("Pessoa não encontrada.")
            else:
                st.dataframe(pessoa.astype(str).to_frame("valor"), width="stretch")
                st.markdown("**Atendimentos (1 pessoa → N atendimentos)**")
                st.dataframe(historico_atendimentos(id_pessoa), hide_index=True, width="stretch")


# ---------------------------------------------------------------------------
# Página 3 — Consultas avançadas
# ---------------------------------------------------------------------------

CONSULTAS_PRONTAS = {
    "Pessoas trans e negras na microárea 03, por equipe": {
        "descricao": "Exemplo do professor. Negras = pretas + pardas (padrão IBGE). "
                     "Trans = Homem transgênero, Mulher transgênero e Travesti.",
        "sql": """
SELECT e.nome_equipe AS equipe, e.codigo_equipe AS ine, m.codigo AS microarea,
       count(DISTINCT p.id_pessoa) AS pessoas
FROM pessoa p
JOIN identidade_genero ig ON ig.id_identidade_genero = p.id_identidade_genero
JOIN raca_cor rc          ON rc.id_raca_cor = p.id_raca_cor
JOIN microarea m          ON m.id_microarea = p.id_microarea
JOIN equipes_saude e      ON e.codigo_equipe = m.id_equipe
WHERE ig.descricao IN ('Homem transgênero', 'Mulher transgênero', 'Travesti')
  AND rc.descricao IN ('Preta', 'Parda')
  AND m.codigo = '03'
GROUP BY e.nome_equipe, e.codigo_equipe, m.codigo
ORDER BY pessoas DESC, equipe""",
    },
    "Atendimentos por hora do dia e profissional": {
        "descricao": "Usa a data/hora do atendimento para ver os horários de maior movimento.",
        "sql": """
SELECT lpad(extract(hour FROM a.data_hora_atendimento)::int::text, 2, '0') || 'h' AS hora,
       tp.descricao AS profissional,
       count(*) AS atendimentos
FROM atendimento a
JOIN tipo_profissional tp ON tp.id_tipo_profissional = a.id_tipo_profissional
GROUP BY 1, 2
ORDER BY 1, 2""",
    },
    "Completude do cadastro por tipo de profissional (% não informado)": {
        "descricao": "Quanto de cada campo da ficha ficou sem resposta (NULL), por quem fez a coleta.",
        "sql": """
SELECT tp.descricao AS profissional,
       count(*) AS atendimentos,
       round(100.0 * count(*) FILTER (WHERE p.id_raca_cor IS NULL) / count(*), 1)          AS pct_sem_raca_cor,
       round(100.0 * count(*) FILTER (WHERE p.id_orientacao_sexual IS NULL) / count(*), 1) AS pct_sem_orientacao,
       round(100.0 * count(*) FILTER (WHERE p.id_identidade_genero IS NULL) / count(*), 1) AS pct_sem_identidade,
       round(100.0 * count(*) FILTER (WHERE p.tem_deficiencia IS NULL) / count(*), 1)      AS pct_sem_deficiencia
FROM atendimento a
JOIN pessoa p             ON p.id_pessoa = a.id_pessoa
JOIN tipo_profissional tp ON tp.id_tipo_profissional = a.id_tipo_profissional
GROUP BY tp.descricao
ORDER BY tp.descricao""",
    },
    "Raça/cor por distrito sanitário (%)": {
        "descricao": "Distribuição de raça/cor das pessoas atendidas em cada distrito.",
        "sql": """
SELECT coalesce(d.nome, d.codigo) AS distrito,
       coalesce(rc.descricao, 'Não informado') AS raca_cor,
       count(DISTINCT p.id_pessoa) AS pessoas,
       round(100.0 * count(DISTINCT p.id_pessoa)
             / sum(count(DISTINCT p.id_pessoa)) OVER (PARTITION BY d.codigo), 1) AS pct_no_distrito
FROM atendimento a
JOIN pessoa p                  ON p.id_pessoa = a.id_pessoa
JOIN equipes_saude e           ON e.codigo_equipe = a.id_equipe
JOIN unidades_saude u          ON u.cnes = e.cnes_unidade
JOIN distrito_sanitario d      ON d.codigo = u.distrito_sanitario_codigo
LEFT JOIN raca_cor rc          ON rc.id_raca_cor = p.id_raca_cor
GROUP BY d.codigo, d.nome, rc.descricao
ORDER BY distrito, pessoas DESC""",
    },
    "Pessoas com deficiência, por tipo e identidade de gênero": {
        "descricao": "Cruza a tabela associativa pessoa_deficiencia (N:N) com identidade de gênero.",
        "sql": """
SELECT df.descricao AS deficiencia,
       coalesce(ig.descricao, 'Não informado') AS identidade_genero,
       count(DISTINCT p.id_pessoa) AS pessoas
FROM pessoa p
JOIN pessoa_deficiencia pd     ON pd.id_pessoa = p.id_pessoa
JOIN deficiencia df            ON df.id_deficiencia = pd.id_deficiencia
LEFT JOIN identidade_genero ig ON ig.id_identidade_genero = p.id_identidade_genero
GROUP BY df.descricao, ig.descricao
ORDER BY deficiencia, pessoas DESC""",
    },
    "Pessoas com mais de um atendimento (relação 1:N)": {
        "descricao": "Mostra a relação pessoa 1:N atendimento. No mock cada pessoa tem 1 atendimento; "
                     "os retornos cadastrados pela interface aparecem aqui.",
        "sql": """
SELECT p.id_pessoa, count(a.id_atendimento) AS atendimentos,
       min(a.data_hora_atendimento) AS primeiro, max(a.data_hora_atendimento) AS ultimo
FROM pessoa p
JOIN atendimento a ON a.id_pessoa = p.id_pessoa
GROUP BY p.id_pessoa
HAVING count(a.id_atendimento) > 1
ORDER BY atendimentos DESC, p.id_pessoa
LIMIT 500""",
    },
}


def filtros_avancados(k, periodo=None, aberto=False):
    """Filtros das consultas avançadas e da exportação. Devolve (condicoes, params).
    periodo=(ini, fim) usa um período já escolhido fora daqui (sem o campo de datas)."""
    with st.expander("Filtros (vazio = todos)", expanded=aberto):
        c1, c2, c3 = st.columns(3)
        if periodo is None:
            with c1:
                ini, fim = filtro_periodo(f"{k}_periodo")
        else:
            ini, fim = periodo
            rotulos = rotulos_equipes()
            sel_equipe = c1.multiselect("Equipe", list(rotulos), format_func=lambda c: rotulos[c], key=f"{k}_equipe")
        sel_raca = c2.multiselect("Raça/cor", opcoes_dominio("raca_cor"), key=f"{k}_raca")
        sel_ident = c3.multiselect("Identidade de gênero", opcoes_dominio("identidade_genero"), key=f"{k}_ident")
        c1, c2, c3 = st.columns(3)
        sel_orient = c1.multiselect("Orientação sexual", opcoes_dominio("orientacao_sexual"), key=f"{k}_orient")
        sel_def = c2.multiselect("Deficiência", opcoes_dominio("deficiencia", False) + ["Nenhuma", NAO_INFORMADO],
                                 key=f"{k}_def")
        distritos = carregar_distritos()
        nomes_distrito = dict(zip(distritos["codigo"], distritos["nome"]))
        sel_distrito = c3.multiselect("Distrito sanitário", distritos["codigo"].tolist(),
                                      format_func=lambda c: nomes_distrito[c], key=f"{k}_distrito")
        c1, c2, c3, c4 = st.columns(4)
        sel_micro = c1.multiselect("Código da microárea", ["01", "02", "03", "04", "05"], key=f"{k}_micro")
        sel_prof = c2.multiselect("Profissional", opcoes_dominio("tipo_profissional", False), key=f"{k}_prof")
        sel_tipo = c3.multiselect("Tipo de atendimento", opcoes_dominio("tipo_atendimento", False), key=f"{k}_tipo")
        sel_dia = c4.multiselect("Dia da semana", ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"], key=f"{k}_dia")
        c1, c2 = st.columns(2)
        idade_min, idade_max = c1.slider("Idade no atendimento", 0, 130, (0, 130), key=f"{k}_idade")
        hora_min, hora_max = c2.slider("Hora do atendimento", 0, 23, (0, 23), key=f"{k}_hora")

    condicoes = ["a.data_hora_atendimento >= :ini", "a.data_hora_atendimento < :fim + 1"]
    params = {"ini": ini, "fim": fim}
    filtro_lista(condicoes, params, "racas", "rc.descricao", sel_raca)
    filtro_lista(condicoes, params, "idents", "ig.descricao", sel_ident)
    filtro_lista(condicoes, params, "orients", "os.descricao", sel_orient)
    filtro_lista(condicoes, params, "distritos", "d.codigo", sel_distrito)
    filtro_lista(condicoes, params, "micros", "m.codigo", sel_micro)
    filtro_lista(condicoes, params, "profs", "tp.descricao", sel_prof)
    filtro_lista(condicoes, params, "tipos", "ta.descricao", sel_tipo)
    if periodo is not None:
        filtro_lista(condicoes, params, "equipes", "e.codigo_equipe", sel_equipe)
    if sel_dia:
        dias = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
        condicoes.append("extract(isodow FROM a.data_hora_atendimento)::int = ANY(:dias)")
        params["dias"] = [dias.index(d) + 1 for d in sel_dia]
    if (idade_min, idade_max) != (0, 130):
        condicoes.append("a.idade_no_atendimento BETWEEN :idade_min AND :idade_max")
        params.update(idade_min=idade_min, idade_max=idade_max)
    if (hora_min, hora_max) != (0, 23):
        condicoes.append("extract(hour FROM a.data_hora_atendimento) BETWEEN :hora_min AND :hora_max")
        params.update(hora_min=hora_min, hora_max=hora_max)
    if sel_def:
        partes = []
        tipos_def = [v for v in sel_def if v not in ("Nenhuma", NAO_INFORMADO)]
        if tipos_def:
            partes.append("""EXISTS (SELECT 1 FROM pessoa_deficiencia x JOIN deficiencia y USING (id_deficiencia)
                          WHERE x.id_pessoa = p.id_pessoa AND y.descricao = ANY(:defs))""")
            params["defs"] = tipos_def
        if "Nenhuma" in sel_def:
            partes.append("p.tem_deficiencia = false")
        if NAO_INFORMADO in sel_def:
            partes.append("p.tem_deficiencia IS NULL")
        condicoes.append("(" + " OR ".join(partes) + ")")
    ativos = len(condicoes) - 2
    st.caption(f"{ativos} filtro(s) ativo(s) além do período." if ativos else "Sem filtros além do período.")
    return condicoes, params


def medida_sql(contar):
    return "count(DISTINCT p.id_pessoa)" if contar == "Pessoas distintas" else "count(DISTINCT a.id_atendimento)"


def tabela_cruzada():
    st.markdown("Escolha uma característica para as **linhas** e outra para as **colunas**. "
                "Cada célula mostra quantas pessoas (ou atendimentos) têm as duas ao mesmo tempo.")
    dims = list(DIMENSOES)
    c1, c2, c3, c4 = st.columns([2, 2, 1.3, 1.5])
    linha = c1.selectbox("Linhas", dims, index=dims.index("Raça/cor"), key="tc_linha")
    opcoes_coluna = [d for d in dims if d != linha]
    padrao = "Identidade de gênero" if "Identidade de gênero" in opcoes_coluna else opcoes_coluna[0]
    coluna = c2.selectbox("Colunas", opcoes_coluna, index=opcoes_coluna.index(padrao), key="tc_coluna")
    contar = c3.radio("Contar", ["Pessoas distintas", "Atendimentos"], key="tc_contar")
    mostrar = c4.radio("Mostrar", ["Números", "% do total", "% da linha", "% da coluna"], key="tc_mostrar")

    condicoes, params = filtros_avancados("tc")
    expr_l, expr_c = DIMENSOES[linha], DIMENSOES[coluna]
    usa_def = "Deficiência" in (linha, coluna)
    where = "\n  AND ".join(condicoes)
    # GROUPING SETS calcula as células e os totais no próprio banco. Assim o total
    # conta cada pessoa uma vez só, mesmo quando ela aparece em mais de uma coluna
    # (ex.: pessoa com duas deficiências).
    sql = f"""SELECT {expr_l} AS linha,
       {expr_c} AS coluna,
       {medida_sql(contar)} AS total,
       GROUPING({expr_l}) AS g_linha,
       GROUPING({expr_c}) AS g_coluna
{FROM_BASE}{JOIN_DEFICIENCIA if usa_def else ""}WHERE {where}
GROUP BY GROUPING SETS (({expr_l}, {expr_c}), ({expr_l}), ({expr_c}), ())"""

    with st.spinner("Cruzando..."):
        df = consultar(sql, params)
    if df.empty or df["total"].sum() == 0:
        st.warning("Nenhum registro com esses filtros.")
        mostrar_sql(sql, params)
        return

    celulas = df[(df.g_linha == 0) & (df.g_coluna == 0)]
    tab = celulas.pivot(index="linha", columns="coluna", values="total").fillna(0)
    total_linha = df[(df.g_linha == 0) & (df.g_coluna == 1)].set_index("linha")["total"]
    total_coluna = df[(df.g_linha == 1) & (df.g_coluna == 0)].set_index("coluna")["total"]
    total_geral = df[(df.g_linha == 1) & (df.g_coluna == 1)]["total"].iloc[0]

    tab = tab.reindex(index=sorted(total_linha.index), columns=sorted(total_coluna.index)).fillna(0)
    if mostrar == "% do total":
        tab = tab / total_geral * 100
        tab["Total"] = total_linha / total_geral * 100
        tab.loc["Total"] = list(total_coluna.reindex(tab.columns[:-1]) / total_geral * 100) + [100.0]
    elif mostrar == "% da linha":
        tab = tab.div(total_linha, axis=0) * 100
        tab["Total"] = 100.0
        tab.loc["Total"] = list(total_coluna.reindex(tab.columns[:-1]) / total_geral * 100) + [100.0]
    elif mostrar == "% da coluna":
        tab = tab.div(total_coluna, axis=1) * 100
        tab["Total"] = total_linha / total_geral * 100
        tab.loc["Total"] = 100.0
    else:
        tab["Total"] = total_linha
        tab.loc["Total"] = list(total_coluna.reindex(tab.columns[:-1])) + [total_geral]
        tab = tab.astype(int)
    tab.index.name = f"{linha} \\ {coluna}"
    tab.columns.name = None

    formato = "%.1f%%" if mostrar != "Números" else "%d"
    st.dataframe(
        tab, width="stretch",
        column_config={c: st.column_config.NumberColumn(format=formato) for c in tab.columns},
    )
    st.caption(f"Total geral: **{int(total_geral):,}** {contar.lower()}.".replace(",", "."))
    if usa_def:
        st.caption("Na deficiência, uma pessoa pode ter mais de uma. Por isso a soma das células pode passar "
                   "do total, que conta cada pessoa uma vez só.")
    st.download_button("Baixar tabela (CSV)", tab.to_csv().encode("utf-8"),
                       "tabela_cruzada.csv", "text/csv", key="tc_baixar")
    mostrar_sql(sql, params)


def cruzamento_livre():
    st.markdown("Lista de combinações (até 3 características ao mesmo tempo), em formato de lista.")
    c1, c2 = st.columns([3, 1])
    grupos = c1.multiselect("Agrupar por", list(DIMENSOES), default=["Raça/cor"], max_selections=3, key="ca_grupos")
    contar = c2.radio("Contar", ["Pessoas distintas", "Atendimentos"], key="ca_contar")
    condicoes, params = filtros_avancados("ca")

    usa_def = "Deficiência" in grupos
    selects = [f"{DIMENSOES[g]} AS \"{g}\"" for g in grupos]
    sql = "SELECT " + ",\n       ".join(selects + [f"{medida_sql(contar)} AS total"])
    sql += "\n" + FROM_BASE + (JOIN_DEFICIENCIA if usa_def else "")
    sql += "WHERE " + "\n  AND ".join(condicoes)
    if grupos:
        n = len(grupos)
        sql += "\nGROUP BY " + ", ".join(str(i) for i in range(1, n + 1))
        sql += "\nORDER BY " + ", ".join(str(i) for i in range(1, n + 1))

    if st.button("Executar", type="primary", key="ca_executar"):
        with st.spinner("Consultando..."):
            df = consultar(sql, params)
        st.dataframe(df, hide_index=True, width="stretch")
        if len(grupos) == 1 and not df.empty:
            st.bar_chart(df.set_index(grupos[0])["total"], horizontal=True)
        if not df.empty:
            st.download_button("Baixar CSV", df.to_csv(index=False).encode("utf-8"),
                               "cruzamento.csv", "text/csv", key="ca_baixar")
    mostrar_sql(sql, params)


def consultas_prontas():
    nome = st.selectbox("Escolha uma consulta", list(CONSULTAS_PRONTAS), key="cp_nome")
    consulta = CONSULTAS_PRONTAS[nome]
    st.caption(consulta["descricao"])
    with st.spinner("Consultando..."):
        df = consultar(consulta["sql"])
    st.dataframe(df, hide_index=True, width="stretch")
    mostrar_sql(consulta["sql"], None)


def pagina_consultas_avancadas():
    st.header("Consultas avançadas")
    aba1, aba2, aba3 = st.tabs(["Tabela cruzada", "Lista de combinações", "Consultas prontas"])
    with aba1:
        tabela_cruzada()
    with aba2:
        cruzamento_livre()
    with aba3:
        consultas_prontas()


# ---------------------------------------------------------------------------
# Página 4 — Importar arquivo
# ---------------------------------------------------------------------------

COLUNAS_IMPORTACAO = {
    "id_pessoa": "Opcional. Preencha só para registrar um NOVO ATENDIMENTO de uma pessoa já cadastrada "
                 "(aí os campos da pessoa são ignorados).",
    "ine_equipe": "Obrigatório. Código INE da equipe que fez a coleta.",
    "microarea": "Obrigatório para pessoa nova. Código da microárea da equipe (01, 02...).",
    "data_hora_atendimento": "Obrigatório. DD/MM/AAAA HH:MM (ex.: 18/11/2026 09:30).",
    "tipo_atendimento": "Obrigatório. Ex.: Primeira consulta, Retorno.",
    "profissional": "Obrigatório. Ex.: ACS, Enfermeiro, Médico.",
    "nome_social": "Opcional.",
    "data_nascimento": "Opcional. DD/MM/AAAA.",
    "idade": "Opcional (usado se não houver data de nascimento).",
    "raca_cor": "Opcional. Branca, Preta, Parda, Amarela, Indígena. Vazio = não informado.",
    "orientacao_sexual": "Opcional. Valores da ficha (Heterossexual, Gay, Lésbica...). Vazio = não informado.",
    "identidade_genero": "Opcional. Valores da ficha (Mulher cisgênero, Homem transgênero, Travesti...).",
    "tem_deficiencia": "Opcional. Sim, Não ou vazio (não informado).",
    "deficiencias": "Opcional. Separe com + (ex.: Visual + Auditiva).",
}
OBRIGATORIAS = ["ine_equipe", "data_hora_atendimento", "tipo_atendimento", "profissional"]
FORMATOS_DATA_HORA = ["%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S",
                      "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"]
FORMATOS_DATA = ["%d/%m/%Y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S"]


def ler_data(valor, formatos):
    for f in formatos:
        try:
            return datetime.strptime(valor, f)
        except ValueError:
            pass
    return None


def modelo_importacao():
    eq = consultar("SELECT id_equipe FROM microarea WHERE codigo = '01' ORDER BY id_equipe LIMIT 1")
    ine = eq.iloc[0]["id_equipe"] if not eq.empty else "0000000000"
    linhas = [
        {"id_pessoa": "", "ine_equipe": ine, "microarea": "01", "data_hora_atendimento": "18/11/2026 09:30",
         "tipo_atendimento": "Primeira consulta", "profissional": "Enfermeiro", "nome_social": "",
         "data_nascimento": "20/05/1990", "idade": "", "raca_cor": "Preta", "orientacao_sexual": "Bissexual",
         "identidade_genero": "Mulher transgênero", "tem_deficiencia": "Sim", "deficiencias": "Visual + Auditiva"},
        {"id_pessoa": "", "ine_equipe": ine, "microarea": "02", "data_hora_atendimento": "18/11/2026 10:00",
         "tipo_atendimento": "Primeira consulta", "profissional": "ACS", "nome_social": "",
         "data_nascimento": "", "idade": "45", "raca_cor": "", "orientacao_sexual": "",
         "identidade_genero": "", "tem_deficiencia": "", "deficiencias": ""},
    ]
    return pd.DataFrame(linhas, columns=list(COLUNAS_IMPORTACAO)).to_csv(index=False, sep=";").encode("utf-8-sig")


def ler_csv(conteudo):
    try:
        texto = conteudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = conteudo.decode("latin-1")  # CSV salvo pelo Excel em português
    brutas = list(enumerate(texto.splitlines(), start=1))
    brutas = [(n, l) for n, l in brutas if l.strip()]
    if not brutas:
        return pd.DataFrame()
    try:
        dialeto = csv.Sniffer().sniff(brutas[0][1], delimiters=";,\t")
    except csv.Error:
        dialeto = csv.excel
    lidas = [(n, next(csv.reader([l], dialeto))) for n, l in brutas]
    cabecalho = lidas[0][1]
    ruins = [n for n, campos in lidas[1:] if len(campos) != len(cabecalho)]
    if ruins:
        raise ValueError(
            f"a(s) linha(s) {', '.join(map(str, ruins[:10]))} têm um número de colunas diferente do cabeçalho "
            f"({len(cabecalho)}). Confira se algum campo tem o separador '{dialeto.delimiter}' dentro dele."
        )
    return pd.DataFrame([campos for _, campos in lidas[1:]], columns=cabecalho)


def ler_arquivo(arquivo):
    if arquivo.name.lower().endswith((".xlsx", ".xls")):
        df = pd.read_excel(arquivo, dtype=str)
    else:
        df = ler_csv(arquivo.getvalue())
    df.columns = [str(c).strip().lower() for c in df.columns]
    return df.fillna("").astype(str).apply(lambda col: col.str.strip())


def mapa_dominio(tabela):
    df = dominio(tabela, f"id_{tabela}")
    return {d.casefold(): int(i) for i, d in zip(df["id"], df["descricao"])}


def preparar_importacao(df):
    """Valida cada linha. Devolve (registros_validos, tabela_de_conferencia)."""
    equipes = set(consultar("SELECT codigo_equipe FROM equipes_saude")["codigo_equipe"])
    micro = consultar("SELECT id_microarea, id_equipe, codigo FROM microarea")
    micro = {(e, c): int(i) for i, e, c in zip(micro["id_microarea"], micro["id_equipe"], micro["codigo"])}
    dom = {t: mapa_dominio(t) for t in ["raca_cor", "orientacao_sexual", "identidade_genero", "deficiencia",
                                         "tipo_atendimento", "tipo_profissional"]}
    ids_arquivo = [int(v) for v in df.get("id_pessoa", pd.Series(dtype=str)) if v.isdigit()]
    existentes = set()
    if ids_arquivo:
        existentes = set(consultar("SELECT id_pessoa FROM pessoa WHERE id_pessoa = ANY(:ids)",
                                   {"ids": ids_arquivo})["id_pessoa"].astype(int))

    validos, conferencia = [], []
    for n, linha in enumerate(df.to_dict("records"), start=2):  # linha 1 do arquivo = cabeçalho
        v = lambda c: linha.get(c, "") or None  # noqa: E731
        erros = []
        for c in OBRIGATORIAS:
            if not v(c):
                erros.append(f"{c} vazio")

        def buscar(tabela, coluna):
            valor = v(coluna)
            if valor is None:
                return None
            achado = dom[tabela].get(valor.casefold())
            if achado is None:
                erros.append(f"{coluna} '{valor}' não existe")
            return achado

        reg = {"linha": n}
        reg["id_equipe"] = v("ine_equipe")
        if reg["id_equipe"] and reg["id_equipe"] not in equipes:
            erros.append(f"equipe {reg['id_equipe']} não existe")
        dh = ler_data(v("data_hora_atendimento") or "", FORMATOS_DATA_HORA)
        if v("data_hora_atendimento") and dh is None:
            erros.append("data_hora_atendimento em formato inválido")
        elif dh and dh > datetime.now():
            erros.append("atendimento no futuro")
        reg["data_hora"] = dh
        reg["id_tipo_atendimento"] = buscar("tipo_atendimento", "tipo_atendimento")
        reg["id_tipo_profissional"] = buscar("tipo_profissional", "profissional")

        idp = v("id_pessoa")
        reg["id_pessoa"] = None
        if idp:
            if not idp.isdigit() or int(idp) not in existentes:
                erros.append(f"id_pessoa {idp} não existe")
            else:
                reg["id_pessoa"] = int(idp)

        nasc = None
        if v("data_nascimento"):
            nasc = ler_data(v("data_nascimento"), FORMATOS_DATA)
            if nasc is None:
                erros.append("data_nascimento em formato inválido")
            else:
                nasc = nasc.date()
                if dh and nasc > dh.date():
                    erros.append("nascimento depois do atendimento")
        idade = None
        if nasc and dh:
            idade = calcular_idade(nasc, dh.date())
        elif v("idade"):
            if v("idade").isdigit() and 0 <= int(v("idade")) <= 130:
                idade = int(v("idade"))
            else:
                erros.append("idade inválida")
        reg["idade"] = idade

        if idp is None:  # pessoa nova: campos da ficha
            cod = v("microarea")
            cod = cod.zfill(2) if cod and cod.isdigit() else cod
            reg["id_microarea"] = micro.get((reg["id_equipe"], cod))
            if not cod:
                erros.append("microarea vazia")
            elif reg["id_microarea"] is None:
                erros.append(f"microárea {cod} não existe na equipe")
            reg["nome_social"] = v("nome_social")
            reg["data_nascimento"] = nasc
            reg["id_raca_cor"] = buscar("raca_cor", "raca_cor")
            reg["id_orientacao_sexual"] = buscar("orientacao_sexual", "orientacao_sexual")
            reg["id_identidade_genero"] = buscar("identidade_genero", "identidade_genero")
            defs = [d.strip() for d in re.split(r"[+|;]", v("deficiencias") or "") if d.strip()]
            ids_def = []
            for d in defs:
                achado = dom["deficiencia"].get(d.casefold())
                if achado is None:
                    erros.append(f"deficiência '{d}' não existe")
                else:
                    ids_def.append(achado)
            reg["deficiencias"] = sorted(set(ids_def))
            tem = (v("tem_deficiencia") or "").casefold()
            if tem in ("sim", "s"):
                reg["tem_deficiencia"] = True
            elif tem in ("não", "nao", "n"):
                reg["tem_deficiencia"] = False
            elif tem == "":
                reg["tem_deficiencia"] = True if defs else None
            else:
                erros.append("tem_deficiencia deve ser Sim, Não ou vazio")
                reg["tem_deficiencia"] = None
            if reg["tem_deficiencia"] is True and not defs:
                erros.append("tem_deficiencia = Sim, mas sem deficiências")
            if reg["tem_deficiencia"] is False and defs:
                erros.append("tem_deficiencia = Não, mas com deficiências")

        acao = "Novo atendimento (pessoa existente)" if idp else "Pessoa nova + atendimento"
        conferencia.append({"linha": n, "ação": acao, "status": "OK" if not erros else "ERRO",
                            "problemas": "; ".join(erros)})
        if not erros:
            validos.append(reg)
    return validos, pd.DataFrame(conferencia)


def gravar_importacao(registros):
    pessoas = atendimentos = 0
    with obter_engine().begin() as con:  # tudo ou nada
        for r in registros:
            id_pessoa = r["id_pessoa"]
            if id_pessoa is None:
                id_pessoa = con.execute(text("""
                    INSERT INTO pessoa (id_raca_cor, id_orientacao_sexual, id_identidade_genero, id_microarea,
                                        id_equipe, data_coleta, tem_deficiencia, nome_social, data_nascimento)
                    VALUES (:raca, :orient, :ident, :micro, :equipe, :coleta, :temdef, :nome, :nasc)
                    RETURNING id_pessoa
                """), {
                    "raca": r["id_raca_cor"], "orient": r["id_orientacao_sexual"],
                    "ident": r["id_identidade_genero"], "micro": r["id_microarea"], "equipe": r["id_equipe"],
                    "coleta": r["data_hora"].date(), "temdef": r["tem_deficiencia"],
                    "nome": r["nome_social"], "nasc": r["data_nascimento"],
                }).scalar_one()
                for d in r["deficiencias"]:
                    con.execute(text("INSERT INTO pessoa_deficiencia (id_pessoa, id_deficiencia) VALUES (:p, :d)"),
                                {"p": id_pessoa, "d": d})
                pessoas += 1
            inserir_atendimento(con, id_pessoa, r["id_equipe"], {
                "id_tipo_atendimento": r["id_tipo_atendimento"], "id_tipo_profissional": r["id_tipo_profissional"],
                "data_hora": r["data_hora"], "idade": r["idade"],
            })
            atendimentos += 1
    return pessoas, atendimentos


def pagina_importar():
    st.header("Importar arquivo")
    st.caption("Importe várias fichas e atendimentos de uma vez, a partir de um CSV ou Excel. "
               "Cada linha é um formulário (pessoa nova + atendimento) ou um novo atendimento de uma "
               "pessoa já cadastrada (coluna id_pessoa preenchida).")

    c1, c2 = st.columns([1, 2])
    c1.download_button("Baixar modelo (CSV)", modelo_importacao(), "modelo_importacao.csv", "text/csv",
                       key="imp_modelo")
    with c2.expander("O que vai em cada coluna"):
        st.table(pd.DataFrame({"coluna": list(COLUNAS_IMPORTACAO), "como preencher": list(COLUNAS_IMPORTACAO.values())}))

    arquivo = st.file_uploader("Arquivo (.csv ou .xlsx)", type=["csv", "xlsx"], key="imp_arquivo")
    if arquivo is None:
        return
    try:
        df = ler_arquivo(arquivo)
    except ImportError:
        st.error("Para ler Excel, instale a biblioteca no terminal: pip install openpyxl "
                 "(ou salve o arquivo como CSV).")
        return
    except Exception as erro:
        st.error(f"Não consegui ler o arquivo: {erro}")
        return

    faltando = [c for c in OBRIGATORIAS if c not in df.columns]
    if faltando:
        st.error("Faltam colunas obrigatórias: " + ", ".join(faltando) + ". Use o modelo.")
        return
    if df.empty:
        st.warning("O arquivo não tem linhas.")
        return

    validos, conferencia = preparar_importacao(df)
    n_erro = int((conferencia["status"] == "ERRO").sum())
    m1, m2, m3 = st.columns(3)
    m1.metric("Linhas no arquivo", len(df))
    m2.metric("Prontas para importar", len(validos))
    m3.metric("Com erro", n_erro)
    st.dataframe(conferencia, hide_index=True, width="stretch")

    if not validos:
        st.error("Nenhuma linha válida. Corrija o arquivo e envie de novo.")
        return
    so_validas = True
    if n_erro:
        so_validas = st.checkbox(f"Importar só as {len(validos)} linhas válidas (as {n_erro} com erro ficam de fora)",
                                 key="imp_so_validas")
    st.caption("Atenção: importar o mesmo arquivo duas vezes cria registros repetidos.")
    if st.button(f"Importar {len(validos)} linha(s)", type="primary", disabled=not so_validas, key="imp_gravar"):
        with st.spinner("Gravando..."):
            pessoas, atendimentos = gravar_importacao(validos)
        st.cache_data.clear()
        st.success(f"Importação concluída: {pessoas} pessoa(s) nova(s) e {atendimentos} atendimento(s).")


# ---------------------------------------------------------------------------
# Página 5 — Exportar dados
# ---------------------------------------------------------------------------

DEFICIENCIAS_DA_PESSOA = """(SELECT string_agg(dx.descricao, ' + ' ORDER BY dx.descricao)
     FROM pessoa_deficiencia px JOIN deficiencia dx USING (id_deficiencia)
     WHERE px.id_pessoa = p.id_pessoa)"""
TEM_DEFICIENCIA = "CASE WHEN p.tem_deficiencia THEN 'Sim' WHEN NOT p.tem_deficiencia THEN 'Não' END"

# rótulo -> (expressão SQL, é agregação?). Os nomes seguem o modelo de importação,
# então um arquivo exportado por atendimento pode ser importado de volta.
COLUNAS_EXPORTACAO = {
    "Atendimentos": {
        "id_atendimento": ("a.id_atendimento", False),
        "data_hora_atendimento": ("to_char(a.data_hora_atendimento, 'DD/MM/YYYY HH24:MI')", False),
        "id_pessoa": ("a.id_pessoa", False),
        "tipo_atendimento": ("ta.descricao", False),
        "profissional": ("tp.descricao", False),
        "idade": ("a.idade_no_atendimento", False),
        "ine_equipe": ("e.codigo_equipe", False),
        "equipe": ("e.nome_equipe", False),
        "unidade": ("u.nome_fantasia", False),
        "distrito": ("coalesce(d.nome, d.codigo)", False),
        "microarea": ("m.codigo", False),
        "nome_social": ("p.nome_social", False),
        "data_nascimento": ("to_char(p.data_nascimento, 'DD/MM/YYYY')", False),
        "raca_cor": ("rc.descricao", False),
        "orientacao_sexual": ("os.descricao", False),
        "identidade_genero": ("ig.descricao", False),
        "tem_deficiencia": (TEM_DEFICIENCIA, False),
        "deficiencias": (DEFICIENCIAS_DA_PESSOA, False),
    },
    "Pessoas": {
        "id_pessoa": ("p.id_pessoa", False),
        "ine_equipe_cadastro": ("p.id_equipe", False),
        "microarea": ("m.codigo", False),
        "data_cadastro": ("to_char(p.data_coleta, 'DD/MM/YYYY')", False),
        "nome_social": ("p.nome_social", False),
        "data_nascimento": ("to_char(p.data_nascimento, 'DD/MM/YYYY')", False),
        "raca_cor": ("rc.descricao", False),
        "orientacao_sexual": ("os.descricao", False),
        "identidade_genero": ("ig.descricao", False),
        "tem_deficiencia": (TEM_DEFICIENCIA, False),
        "deficiencias": (DEFICIENCIAS_DA_PESSOA, False),
        "atendimentos_no_periodo": ("count(DISTINCT a.id_atendimento)", True),
        "primeiro_atendimento": ("to_char(min(a.data_hora_atendimento), 'DD/MM/YYYY HH24:MI')", True),
        "ultimo_atendimento": ("to_char(max(a.data_hora_atendimento), 'DD/MM/YYYY HH24:MI')", True),
    },
}


def periodo_exportacao():
    hoje = date.today()
    opcoes = {"Último mês": 1, "Últimos 2 meses": 2, "Últimos 3 meses": 3, "Últimos 6 meses": 6,
              "Personalizado": None}
    escolha = st.radio("Período", list(opcoes), horizontal=True, index=len(opcoes) - 1, key="exp_tipo_periodo")
    meses = opcoes[escolha]
    if meses is None:
        ini_padrao, fim_padrao = periodo_atendimentos()
        valor = st.date_input("De / até", value=(ini_padrao, fim_padrao), format="DD/MM/YYYY", key="exp_datas")
        if isinstance(valor, (list, tuple)) and len(valor) == 2:
            return valor
        st.caption("Escolha a data final do período.")
        return ini_padrao, fim_padrao
    ini = (pd.Timestamp(hoje) - pd.DateOffset(months=meses)).date()
    st.caption(f"De {ini:%d/%m/%Y} até hoje ({hoje:%d/%m/%Y}).")
    return ini, hoje


def montar_sql_exportacao(tipo, colunas, condicoes):
    defs = COLUNAS_EXPORTACAO[tipo]
    selects = [f'{defs[c][0]} AS "{c}"' for c in colunas]
    sql = "SELECT " + ",\n       ".join(selects) + "\n" + FROM_BASE
    sql += "WHERE " + "\n  AND ".join(condicoes)
    if tipo == "Pessoas":
        sem_agregacao = [str(i) for i, c in enumerate(colunas, start=1) if not defs[c][1]]
        if sem_agregacao:
            sql += "\nGROUP BY p.id_pessoa, " + ", ".join(sem_agregacao)
        else:
            sql += "\nGROUP BY p.id_pessoa"
        sql += "\nORDER BY p.id_pessoa"
    else:
        sql += "\nORDER BY a.data_hora_atendimento, a.id_atendimento"
    return sql


def gerar_excel(df):
    import io
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as escritor:
        df.to_excel(escritor, index=False, sheet_name="dados")
    return buffer.getvalue()


def pagina_exportar():
    st.header("Exportar dados")
    st.caption("Escolha o período, os filtros e as colunas, confira a prévia e baixe o arquivo. "
               "Campos não respondidos saem vazios.")

    st.markdown("**1. Período**")
    ini, fim = periodo_exportacao()

    st.markdown("**2. O que exportar**")
    tipo = st.radio("Uma linha por", ["Atendimentos", "Pessoas"], horizontal=True, key="exp_linha_por",
                    captions=["cada atendimento, com os dados da pessoa",
                              "cada pessoa atendida no período, com o nº de atendimentos"])
    todas = list(COLUNAS_EXPORTACAO[tipo])
    colunas = st.multiselect("Colunas", todas, default=todas, key=f"exp_colunas_{tipo}")
    if not colunas:
        st.warning("Escolha pelo menos uma coluna.")
        return

    st.markdown("**3. Filtros**")
    condicoes, params = filtros_avancados("exp", periodo=(ini, fim))

    sql = montar_sql_exportacao(tipo, colunas, condicoes)
    with st.spinner("Preparando..."):
        df = consultar(sql, params)

    st.markdown("**4. Conferir e baixar**")
    st.metric(f"{tipo} no arquivo", f"{len(df):,}".replace(",", "."))
    if df.empty:
        st.warning("Nada para exportar com esse período e esses filtros.")
        mostrar_sql(sql, params)
        return
    st.caption("Prévia das primeiras 20 linhas:")
    st.dataframe(df.head(20), hide_index=True, width="stretch")

    nome = f"equidados_{tipo.lower()}_{ini:%Y%m%d}_a_{fim:%Y%m%d}"
    c1, c2 = st.columns(2)
    c1.download_button("Baixar CSV", df.to_csv(index=False, sep=";").encode("utf-8-sig"),
                       f"{nome}.csv", "text/csv", type="primary", key="exp_csv")
    try:
        excel = gerar_excel(df)
        c2.download_button("Baixar Excel", excel, f"{nome}.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="exp_xlsx")
    except ImportError:
        c2.caption("Para baixar em Excel, instale no terminal: pip install openpyxl")
    if tipo == "Atendimentos":
        st.caption("O CSV por atendimento usa as mesmas colunas do modelo de importação.")
    mostrar_sql(sql, params)


# ---------------------------------------------------------------------------
# Navegação
# ---------------------------------------------------------------------------

if not DB_URL:
    st.error("Defina NEON_DATABASE_URL_MODELAGEM no arquivo .env (conexão da branch modelagem-pessoa).")
    st.stop()

st.sidebar.title("EquiDados")
st.sidebar.caption("Branch **modelagem-pessoa** do Neon")
pagina = st.sidebar.radio("Tela", ["Cadastro", "Importar arquivo", "Consultas iniciais", "Consultas avançadas",
                                   "Exportar dados"])

if pagina == "Cadastro":
    pagina_cadastro()
elif pagina == "Importar arquivo":
    pagina_importar()
elif pagina == "Exportar dados":
    pagina_exportar()
elif pagina == "Consultas iniciais":
    pagina_consultas_iniciais()
else:
    pagina_consultas_avancadas()
