"""
Dashboard EquiDados — mesmas queries planejadas para o Metabase, renderizadas
em Streamlit, com gráficos em Plotly e mapas em Folium (GeoJSON real dos
Distritos Sanitários).

Rodar com: streamlit run src/dashboard/app_dashboard.py
"""

import json
import os

import folium
import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from streamlit_folium import st_folium

load_dotenv()

NEON_DATABASE_URL = os.getenv("NEON_DATABASE_URL")
GEOJSON_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "bronze", "dados_recife",
    "distritos_sanitarios_2026-08-13.json",
)

# Cores neutras e fixas por categoria de raça/cor — deliberadamente arbitrárias
# (não "combinam" com o nome da categoria), garantindo que cada categoria
# mantenha a mesma cor em qualquer gráfico do dashboard.
CORES_RACA_COR = {
    "Branca": "#636EFA",
    "Preta": "#EF553B",
    "Parda": "#00CC96",
    "Amarela": "#AB63FA",
    "Indígena": "#FFA15A",
}

# Cores e ordem fixas pro gráfico de inconsistências — reforça a leitura como
# uma escala (do "sem dado" ao "dado completo"), não uma lista solta.
CORES_INCONSISTENCIA = {
    "Campo em branco": "#B0B0B0",
    "Recusou informar": "#F0A03C",
    "Informou": "#2E9E5B",
}
ORDEM_INCONSISTENCIA = ["Campo em branco", "Recusou informar", "Informou"]

# Rótulos curtos pra exibir no seletor de tipo de deficiência (o texto completo
# do Censo é longo demais pra caber na caixa de seleção).
ROTULOS_DEFICIENCIA = {
    "Dificuldade permanente para enxergar, mesmo usando óculos ou lentes de contato": "Visual",
    "Dificuldade permanente para ouvir, mesmo usando aparelhos auditivos": "Auditiva",
    "Dificuldade permanente para andar ou subir degraus, mesmo usando prótese ou outro aparelho de auxílio": "Motora",
    "Dificuldade permanente para pegar pequenos objetos, como botão ou lápis, ou abrir e fechar tampas de garrafas, mesmo usando aparelho de auxílio": "Manual",
    "Dificuldade permanente para se comunicar, realizar cuidados pessoais, trabalhar ou estudar por causa de alguma limitação nas funções mentais": "Mental/Cognitiva",
}

st.set_page_config(page_title="EquiDados — Dashboards", page_icon="📊", layout="wide")


@st.cache_resource
def obter_engine():
    return create_engine(NEON_DATABASE_URL)


@st.cache_resource
def carregar_geojson():
    with open(GEOJSON_PATH, encoding="utf-8") as arquivo:
        geojson = json.load(arquivo)
    for feature in geojson["features"]:
        feature["properties"]["cdistscodi"] = str(feature["properties"]["cdistscodi"])
    return geojson


def consultar(sql, params=None):
    return pd.read_sql(text(sql), obter_engine(), params=params)


def mapa_distrito(df, coluna_valor, titulo, escala="Oranges", rotulo_valor=None):
    df = df.copy()
    df["cdistscodi"] = df["cdistscodi"].astype(str)
    rotulo = rotulo_valor or coluna_valor

    geojson = carregar_geojson()
    geojson_com_valor = json.loads(json.dumps(geojson))
    valores = dict(zip(df["cdistscodi"], df[coluna_valor]))
    for feature in geojson_com_valor["features"]:
        codigo = feature["properties"]["cdistscodi"]
        feature["properties"]["valor_tooltip"] = valores.get(codigo, 0)

    mapa = folium.Map(location=[-8.05, -34.90], zoom_start=11, tiles="OpenStreetMap")

    folium.Choropleth(
        geo_data=geojson_com_valor,
        data=df,
        columns=["cdistscodi", coluna_valor],
        key_on="feature.properties.cdistscodi",
        fill_color=escala,
        fill_opacity=0.75,
        line_opacity=0.4,
        legend_name=rotulo,
        nan_fill_color="white",
    ).add_to(mapa)

    folium.GeoJson(
        geojson_com_valor,
        style_function=lambda x: {"fillOpacity": 0, "weight": 0},
        tooltip=folium.GeoJsonTooltip(
            fields=["cdistscodi", "valor_tooltip"],
            aliases=["Distrito", rotulo],
        ),
    ).add_to(mapa)

    st.markdown(f"**{titulo}**")
    return mapa


st.title("EquiDados — Dashboards")

aba1, aba2 = st.tabs(["Contexto Estrutural", "Equidade e Qualidade do Cadastro"])

with aba1:
    with st.container(border=True):
        col1, col2 = st.columns(2)
        with col1:
            df = consultar("SELECT COUNT(*) AS total FROM unidades_saude")
            st.metric("Total de Unidades", int(df["total"][0]))
        with col2:
            df = consultar("SELECT COUNT(*) AS total FROM equipes_saude")
            st.metric("Total de Equipes", int(df["total"][0]))

    df = consultar("""
        SELECT distrito_sanitario_nome, COUNT(*) AS total
        FROM unidades_saude
        WHERE distrito_sanitario_codigo IS NOT NULL
        GROUP BY distrito_sanitario_nome
        ORDER BY distrito_sanitario_nome
    """)
    st.subheader("Unidades por Distrito Sanitário")
    st.plotly_chart(
        px.bar(
            df, x="distrito_sanitario_nome", y="total",
            labels={"distrito_sanitario_nome": "Distrito Sanitário", "total": "Quantidade de Unidades"},
        ),
        use_container_width=True,
    )

    df = consultar("""
        SELECT tipo_equipe, COUNT(*) AS total
        FROM equipes_saude
        GROUP BY tipo_equipe
        ORDER BY total DESC
    """)
    st.subheader("Equipes por Tipo")
    st.plotly_chart(
        px.bar(
            df, x="tipo_equipe", y="total",
            labels={"tipo_equipe": "Tipo de Equipe", "total": "Quantidade de Equipes"},
        ),
        use_container_width=True,
    )

    df = consultar("SELECT raca_cor, populacao FROM censo_raca_cor ORDER BY populacao DESC")
    st.subheader("População por Raça/Cor")
    st.plotly_chart(
        px.bar(
            df, x="raca_cor", y="populacao", color="raca_cor",
            color_discrete_map=CORES_RACA_COR,
            labels={"raca_cor": "Raça/Cor", "populacao": "População"},
        ).update_layout(showlegend=False),
        use_container_width=True,
    )

    df = consultar("""
        SELECT tipo_dificuldade, populacao FROM censo_deficiencia
        WHERE e_total = false ORDER BY populacao DESC
    """)
    st.subheader("População por Deficiência, por Tipo")
    st.plotly_chart(
        px.bar(
            df, y="tipo_dificuldade", x="populacao", orientation="h",
            labels={"tipo_dificuldade": "Tipo de Dificuldade", "populacao": "População"},
        ),
        use_container_width=True,
    )

    df = consultar("""
        SELECT cnes, nome_fantasia, tipo_estabelecimento
        FROM unidades_saude WHERE distrito_sanitario_codigo IS NULL
        ORDER BY nome_fantasia
    """)
    st.subheader("Unidades sem Distrito Sanitário preenchido")
    st.dataframe(df, use_container_width=True)

with aba2:
    st.caption("⚠️ Dados fictícios/simulados — não representam a população real de Recife.")

    st.subheader("KPIs de Preenchimento")
    with st.container(border=True):
        c1, c2, c3, c4 = st.columns(4)
        campos_completude = [
            ("raca_cor", "Preenchimento Raça/Cor", c1),
            ("deficiencia_tipo", "Preenchimento Deficiência", c2),
            ("deseja_informar_orientacao_sexual", "Preenchimento Orient. Sexual", c3),
            ("deseja_informar_identidade_genero", "Preenchimento Ident. Gênero", c4),
        ]
        for coluna, rotulo, coluna_ui in campos_completude:
            df = consultar(f"""
                SELECT ROUND(COUNT({coluna})::numeric / COUNT(*) * 100, 1) AS pct
                FROM mock_pec_atendimentos
            """)
            coluna_ui.metric(rotulo, f"{df['pct'][0]}%")

    st.divider()
    st.subheader("Mapas de Concentração")
    colm1, colm2, colm3 = st.columns(3)
    with colm1:
        df = consultar("""
            SELECT CAST(distrito_sanitario_codigo AS INTEGER) AS cdistscodi,
                   COUNT(*) FILTER (
                       WHERE (orientacao_sexual IS NOT NULL AND orientacao_sexual != 'Heterossexual')
                          OR identidade_genero IN ('Mulher trans', 'Homem trans', 'Não-binário')
                   ) AS total
            FROM mock_pec_atendimentos
            GROUP BY distrito_sanitario_codigo ORDER BY distrito_sanitario_codigo
        """)
        _ = st_folium(
            mapa_distrito(df, "total", "Concentração LGBTQIAPN+", rotulo_valor="Pessoas LGBTQIAPN+"),
            width=380, height=320, returned_objects=[], key="mapa_lgbt",
        )
    with colm2:
        tipos_deficiencia = consultar("""
            SELECT DISTINCT deficiencia_tipo FROM mock_pec_atendimentos
            WHERE deficiencia_tipo IS NOT NULL AND deficiencia_tipo != 'Nenhuma'
            ORDER BY deficiencia_tipo
        """)["deficiencia_tipo"].tolist()
        tipo_selecionado = st.selectbox(
            "Filtrar por tipo de deficiência",
            ["Todos os tipos"] + tipos_deficiencia,
            format_func=lambda x: ROTULOS_DEFICIENCIA.get(x, x),
            key="filtro_pcd",
        )
        if tipo_selecionado == "Todos os tipos":
            df = consultar("""
                SELECT CAST(distrito_sanitario_codigo AS INTEGER) AS cdistscodi,
                       COUNT(*) FILTER (WHERE deficiencia_tipo IS NOT NULL AND deficiencia_tipo != 'Nenhuma') AS total
                FROM mock_pec_atendimentos
                GROUP BY distrito_sanitario_codigo ORDER BY distrito_sanitario_codigo
            """)
        else:
            df = consultar("""
                SELECT CAST(distrito_sanitario_codigo AS INTEGER) AS cdistscodi,
                       COUNT(*) FILTER (WHERE deficiencia_tipo = :tipo) AS total
                FROM mock_pec_atendimentos
                GROUP BY distrito_sanitario_codigo ORDER BY distrito_sanitario_codigo
            """, params={"tipo": tipo_selecionado})
        _ = st_folium(
            mapa_distrito(
                df, "total",
                f"Concentração PCD — {ROTULOS_DEFICIENCIA.get(tipo_selecionado, tipo_selecionado)}",
                rotulo_valor="Pessoas com deficiência",
            ),
            width=380, height=320, returned_objects=[], key="mapa_pcd",
        )
    with colm3:
        df = consultar("""
            SELECT CAST(a.distrito_sanitario_codigo AS INTEGER) AS cdistscodi,
                   ROUND(p.populacao_negra_pct_esperado * 100
                         - (COUNT(*) FILTER (WHERE a.raca_cor IN ('Preta','Parda'))::numeric / COUNT(a.raca_cor) * 100), 1) AS gap_pp
            FROM mock_pec_atendimentos a
            JOIN mock_populacao_negra_distrito p ON p.distrito_sanitario_codigo = a.distrito_sanitario_codigo
            GROUP BY a.distrito_sanitario_codigo, p.populacao_negra_pct_esperado
            ORDER BY a.distrito_sanitario_codigo
        """)
        _ = st_folium(
            mapa_distrito(
                df, "gap_pp",
                "População Negra: Censo x Registrado no Atendimento",
                escala="Reds", rotulo_valor="Diferença (p.p.)",
            ),
            width=380, height=320, returned_objects=[], key="mapa_gap_racial",
        )
        st.caption(
            "Quanto mais escuro, maior a diferença entre a % de população negra "
            "esperada pelo Censo naquele distrito e a % de fato registrada nos "
            "atendimentos — um sinal de sub-registro ou baixo acesso a investigar."
        )

    df = consultar("""
        SELECT distrito_sanitario_codigo, raca_cor, COUNT(*) AS total
        FROM mock_pec_atendimentos
        WHERE raca_cor IS NOT NULL
        GROUP BY distrito_sanitario_codigo, raca_cor
        ORDER BY distrito_sanitario_codigo, raca_cor
    """)
    st.subheader("Distribuição de Raça/Cor por Distrito")
    st.plotly_chart(
        px.bar(
            df, x="distrito_sanitario_codigo", y="total", color="raca_cor",
            barmode="group", color_discrete_map=CORES_RACA_COR,
            category_orders={"raca_cor": ["Branca", "Preta", "Parda", "Amarela", "Indígena"]},
            labels={"distrito_sanitario_codigo": "Distrito", "total": "Atendimentos", "raca_cor": "Raça/Cor"},
        ),
        use_container_width=True,
    )

    df = consultar("""
        SELECT codigo_equipe AS "Equipe",
               distrito_sanitario_codigo,
               COUNT(*) AS "Total de Atendimentos",
               ROUND(COUNT(deseja_informar_orientacao_sexual)::numeric / COUNT(*) * 100, 1) AS "% Preenchimento"
        FROM mock_pec_atendimentos
        WHERE profissional_tipo = 'ACS'
          AND data_atendimento > (SELECT MAX(data_atendimento) FROM mock_pec_atendimentos) - INTERVAL '3 months'
        GROUP BY codigo_equipe, distrito_sanitario_codigo
    """)
    df["Distrito"] = df["distrito_sanitario_codigo"].map({
        "01": "Distrito I", "02": "Distrito II", "03": "Distrito III", "04": "Distrito IV",
        "05": "Distrito V", "06": "Distrito VI", "07": "Distrito VII", "08": "Distrito VIII",
    })
    df = df.sort_values("% Preenchimento").head(15).reset_index(drop=True)
    df = df[["Equipe", "Distrito", "Total de Atendimentos", "% Preenchimento"]]

    st.subheader("Ranking de Equipes por Preenchimento (últimos 3 meses)")
    st.dataframe(df, use_container_width=True)

    df = consultar("""
        SELECT DATE_TRUNC('month', data_atendimento) AS mes,
               ROUND(COUNT(raca_cor)::numeric / COUNT(*) * 100, 1) AS "Raça/Cor",
               ROUND(COUNT(deseja_informar_orientacao_sexual)::numeric / COUNT(*) * 100, 1) AS "Orientação Sexual"
        FROM mock_pec_atendimentos
        GROUP BY mes ORDER BY mes
    """)
    df_evolucao = df.melt(id_vars="mes", var_name="Campo", value_name="Preenchimento (%)")
    st.subheader("Evolução do Preenchimento")
    st.plotly_chart(
        px.line(
            df_evolucao, x="mes", y="Preenchimento (%)", color="Campo",
            labels={"mes": "Mês"},
        ),
        use_container_width=True,
    )

    df = consultar("""
        SELECT
          COUNT(*) FILTER (WHERE deseja_informar_orientacao_sexual IS NULL) AS "Campo em branco",
          COUNT(*) FILTER (WHERE deseja_informar_orientacao_sexual = 'Não') AS "Recusou informar",
          COUNT(*) FILTER (WHERE deseja_informar_orientacao_sexual = 'Sim') AS "Informou"
        FROM mock_pec_atendimentos
    """)
    df_inconsistencias = df.melt(var_name="Categoria", value_name="Atendimentos")
    st.subheader("Inconsistências — Orientação Sexual")
    st.plotly_chart(
        px.bar(
            df_inconsistencias, x="Categoria", y="Atendimentos", color="Categoria",
            color_discrete_map=CORES_INCONSISTENCIA,
            category_orders={"Categoria": ORDEM_INCONSISTENCIA},
        ).update_layout(showlegend=False),
        use_container_width=True,
    )
