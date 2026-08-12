import json
import os
from datetime import datetime, timezone

import requests

CODIGO_RECIFE = "2611606"

PASTA_SAIDA = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "bronze", "ibge"
)

# Censo 2022 - "Pessoas residentes de 2 anos ou mais de idade com deficiência
# por tipos de dificuldades funcionais" (visual, auditiva, motora, cognitiva)
TABELA_TIPO_DEFICIENCIA = "10127"

# Censo 2022 - "Pessoas residentes de 2 anos ou mais de idade, total e
# pessoas com deficiência, por cor ou raça"
TABELA_DEFICIENCIA_RACA_COR = "10126"


def buscar_tabela_sidra(numero_tabela, classificacao):
    url = (
        f"https://apisidra.ibge.gov.br/values"
        f"/t/{numero_tabela}/n6/{CODIGO_RECIFE}/v/allxp/p/last/{classificacao}/all"
    )
    resposta = requests.get(url, timeout=30)

    print(f"URL chamada: {url}")
    print(f"Status HTTP: {resposta.status_code}")

    resposta.raise_for_status()
    return resposta.json()


def salvar_json(dados, nome_arquivo):
    os.makedirs(PASTA_SAIDA, exist_ok=True)
    caminho = os.path.join(PASTA_SAIDA, nome_arquivo)
    with open(caminho, "w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, ensure_ascii=False, indent=2)
    print(f"Arquivo salvo em: {caminho}")


if __name__ == "__main__":
    data_hoje = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    print("Buscando dados de deficiência por tipo de dificuldade funcional...")
    dados_tipo = buscar_tabela_sidra(TABELA_TIPO_DEFICIENCIA, "c1509")
    salvar_json(dados_tipo, f"censo_deficiencia_tipo_recife_{data_hoje}.json")

    print("\nConcluído!")
