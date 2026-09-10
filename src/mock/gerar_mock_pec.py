"""
Gera dados FICTÍCIOS/SIMULADOS que imitam a estrutura real do PEC/e-SUS APS,
descrita pela Secretaria (campo de raça/cor obrigatório, deficiência obrigatória,
orientação sexual e identidade de gênero com filtro "deseja informar?", exclusão
de crianças de 0 a 10 anos na análise de LGBTQIAPN+).

Não representa pacientes, atendimentos ou população real de Recife. Serve para
testar o pipeline (mapas de calor, ranking de completude, modelo de ML) enquanto
o acesso ao PEC real não é liberado pela Secretaria.

Precisa de acesso ao Neon (lê equipes_saude/unidades_saude/censo_raca_cor reais
para ancorar o mock na estrutura territorial verdadeira).
"""

import json
import os
import random
from datetime import datetime

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

NEON_DATABASE_URL = os.getenv("NEON_DATABASE_URL")
PASTA_SAIDA = os.path.join(os.path.dirname(__file__), "..", "..", "data", "bronze", "mock_pec")

RACA_COR_CATEGORIAS = ["Branca", "Preta", "Parda", "Amarela", "Indígena"]
RACA_COR_PESOS = [22, 12, 48, 3, 2]

# Anomalia de cadastro injetada de propósito, imitando o caso relatado pela
# Secretaria (registro anômalo de "Amarela" no Coque) — serve para demonstrar
# o gráfico de verificação de inconsistências de cadastro por distrito.
DISTRITO_ANOMALIA_RACA_COR = "03"
RACA_COR_PESOS_ANOMALIA = [15, 10, 30, 40, 5]

DEFICIENCIA_CATEGORIAS = [
    "Dificuldade permanente para enxergar, mesmo usando óculos ou lentes de contato",
    "Dificuldade permanente para ouvir, mesmo usando aparelhos auditivos",
    "Dificuldade permanente para andar ou subir degraus, mesmo usando prótese ou outro aparelho de auxílio",
    "Dificuldade permanente para pegar pequenos objetos, como botão ou lápis, ou abrir e fechar tampas de garrafas, mesmo usando aparelho de auxílio",
    "Dificuldade permanente para se comunicar, realizar cuidados pessoais, trabalhar ou estudar por causa de alguma limitação nas funções mentais",
]

ORIENTACAO_SEXUAL_CATEGORIAS = ["Heterossexual", "Gay", "Lésbica", "Bissexual", "Assexual", "Pansexual", "Outro"]
ORIENTACAO_SEXUAL_PESOS = [70, 6, 6, 6, 3, 3, 6]

IDENTIDADE_GENERO_CATEGORIAS = ["Mulher cisgênero", "Homem cisgênero", "Mulher trans", "Homem trans", "Não-binário", "Outro"]
IDENTIDADE_GENERO_PESOS = [46, 46, 2, 2, 2, 2]

PROFISSIONAL_TIPOS = ["ACS", "Enfermeiro", "Médico"]
PROFISSIONAL_PESOS = [60, 25, 15]

MESES = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08"]

# distribuição ILUSTRATIVA da população negra por Distrito Sanitário — não é
# dado real, é só um cenário plausível pra exercitar o mapa de gap racial
PERCENTUAL_NEGRA_ESPERADO_POR_DISTRITO = {
    "01": 0.42, "02": 0.55, "03": 0.58, "04": 0.68,
    "05": 0.71, "06": 0.50, "07": 0.63, "08": 0.74,
}

random.seed(42)  # reprodutibilidade entre execuções


def buscar_equipes_esf(engine):
    sql = text("""
        SELECT e.codigo_equipe, e.cnes_unidade, u.distrito_sanitario_codigo
        FROM equipes_saude e
        JOIN unidades_saude u ON u.cnes = e.cnes_unidade
        WHERE e.tipo_equipe = 'ESF - EQUIPE DE SAUDE DA FAMILIA'
          AND e.data_desativacao IS NULL
          AND u.distrito_sanitario_codigo IS NOT NULL
    """)
    with engine.connect() as conexao:
        return [dict(linha._mapping) for linha in conexao.execute(sql)]


def gerar_taxas_por_equipe(equipes):
    """Cada equipe recebe uma taxa-base de completude/pergunta diferente e
    propositalmente desigual — é isso que simula o problema real relatado pela
    Secretaria (algumas equipes perguntam bem menos que outras)."""
    taxas = {}
    for equipe in equipes:
        taxas[equipe["codigo_equipe"]] = {
            "raca_cor": random.uniform(0.55, 0.97),
            "deficiencia": random.uniform(0.60, 0.97),
            "pergunta_orientacao": random.uniform(0.20, 0.75),
            "pergunta_genero": random.uniform(0.20, 0.75),
        }
    return taxas


def gerar_atendimento(id_atendimento, equipe, taxas, mes_index, mes):
    dia = random.randint(1, 28)
    data_atendimento = f"{mes}-{dia:02d}"

    # leve tendência de melhora ao longo dos meses (efeito de capacitação)
    fator_evolucao = 1 + (mes_index * 0.02)

    idade = random.choices(
        [random.randint(0, 9), random.randint(10, 17), random.randint(18, 59), random.randint(60, 95)],
        weights=[0.12, 0.10, 0.55, 0.23],
    )[0]

    raca_cor = None
    if random.random() < min(taxas["raca_cor"] * fator_evolucao, 0.99):
        pesos_raca_cor = (
            RACA_COR_PESOS_ANOMALIA
            if equipe["distrito_sanitario_codigo"] == DISTRITO_ANOMALIA_RACA_COR
            else RACA_COR_PESOS
        )
        raca_cor = random.choices(RACA_COR_CATEGORIAS, weights=pesos_raca_cor)[0]

    deficiencia_tipo = None
    if random.random() < min(taxas["deficiencia"] * fator_evolucao, 0.99):
        deficiencia_tipo = random.choice(DEFICIENCIA_CATEGORIAS) if random.random() < 0.18 else "Nenhuma"

    deseja_informar_orientacao = None
    orientacao_sexual = None
    deseja_informar_genero = None
    identidade_genero = None
    nome_social = None

    if idade >= 10:  # regra da Secretaria: crianças de 0 a 10 anos ficam fora da análise LGBTQIAPN+
        perguntou_orientacao = random.random() < min(taxas["pergunta_orientacao"] * fator_evolucao, 0.99)
        if perguntou_orientacao:
            deseja_informar_orientacao = "Sim" if random.random() < 0.55 else "Não"
            if deseja_informar_orientacao == "Sim":
                orientacao_sexual = random.choices(ORIENTACAO_SEXUAL_CATEGORIAS, weights=ORIENTACAO_SEXUAL_PESOS)[0]

        perguntou_genero = random.random() < min(taxas["pergunta_genero"] * fator_evolucao, 0.99)
        if perguntou_genero:
            deseja_informar_genero = "Sim" if random.random() < 0.55 else "Não"
            if deseja_informar_genero == "Sim":
                identidade_genero = random.choices(IDENTIDADE_GENERO_CATEGORIAS, weights=IDENTIDADE_GENERO_PESOS)[0]
                if identidade_genero in ("Mulher trans", "Homem trans"):
                    nome_social = "Preenchido"

    return {
        "id_atendimento": id_atendimento,
        "codigo_equipe": equipe["codigo_equipe"],
        "cnes_unidade": equipe["cnes_unidade"],
        "distrito_sanitario_codigo": equipe["distrito_sanitario_codigo"],
        "data_atendimento": data_atendimento,
        "tipo_atendimento": random.choices(["Primeira consulta", "Retorno"], weights=[35, 65])[0],
        "profissional_tipo": random.choices(PROFISSIONAL_TIPOS, weights=PROFISSIONAL_PESOS)[0],
        "idade": idade,
        "raca_cor": raca_cor,
        "deficiencia_tipo": deficiencia_tipo,
        "deseja_informar_orientacao_sexual": deseja_informar_orientacao,
        "orientacao_sexual": orientacao_sexual,
        "deseja_informar_identidade_genero": deseja_informar_genero,
        "identidade_genero": identidade_genero,
        "nome_social": nome_social,
    }


def gerar_populacao_negra_distrito(equipes):
    distritos = sorted(set(eq["distrito_sanitario_codigo"] for eq in equipes))
    return [
        {
            "distrito_sanitario_codigo": cod,
            "populacao_negra_pct_esperado": PERCENTUAL_NEGRA_ESPERADO_POR_DISTRITO.get(cod, 0.60),
        }
        for cod in distritos
    ]


if __name__ == "__main__":
    engine = create_engine(NEON_DATABASE_URL)

    print("Buscando equipes ESF ativas no Neon...")
    equipes = buscar_equipes_esf(engine)
    print(f"  {len(equipes)} equipes encontradas.")

    taxas_por_equipe = gerar_taxas_por_equipe(equipes)

    atendimentos = []
    id_atendimento = 1
    for mes_index, mes in enumerate(MESES):
        for equipe in equipes:
            n_atendimentos = random.randint(8, 25)
            for _ in range(n_atendimentos):
                atendimentos.append(
                    gerar_atendimento(id_atendimento, equipe, taxas_por_equipe[equipe["codigo_equipe"]], mes_index, mes)
                )
                id_atendimento += 1

    populacao_negra_distrito = gerar_populacao_negra_distrito(equipes)

    os.makedirs(PASTA_SAIDA, exist_ok=True)
    data_hoje = datetime.now().strftime("%Y-%m-%d")

    caminho_atendimentos = os.path.join(PASTA_SAIDA, f"atendimentos_mock_{data_hoje}.json")
    with open(caminho_atendimentos, "w", encoding="utf-8") as arquivo:
        json.dump(atendimentos, arquivo, ensure_ascii=False, indent=2)

    caminho_populacao = os.path.join(PASTA_SAIDA, f"populacao_negra_distrito_mock_{data_hoje}.json")
    with open(caminho_populacao, "w", encoding="utf-8") as arquivo:
        json.dump(populacao_negra_distrito, arquivo, ensure_ascii=False, indent=2)

    print(f"\n{len(atendimentos)} atendimentos fictícios gerados em:\n  {caminho_atendimentos}")
    print(f"{len(populacao_negra_distrito)} distritos gerados em:\n  {caminho_populacao}")
    print("\nATENÇÃO: dados 100% fictícios/simulados — não representam pacientes, "
          "atendimentos ou população real de Recife.")
