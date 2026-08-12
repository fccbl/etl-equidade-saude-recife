import json
import os
from datetime import datetime, timezone

import requests

# Código do IBGE para o município do Recife
CODIGO_RECIFE = "2611606"

PASTA_SAIDA = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "bronze", "ibge"
)

# Censo 2022 - "População residente, por cor ou raça, nos Censos Demográficos"
TABELA_RACA_COR = "9605"


def buscar_populacao_por_raca_cor():
    url = (
        f"https://apisidra.ibge.gov.br/values"
        f"/t/{TABELA_RACA_COR}/n6/{CODIGO_RECIFE}/v/allxp/p/last/c86/all"
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
    print("Buscando dados de população por raça/cor (Censo) no SIDRA...")
    dados = buscar_populacao_por_raca_cor()

    data_hoje = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    nome_arquivo = f"censo_raca_cor_recife_{data_hoje}.json"
    salvar_json(dados, nome_arquivo)

    print("Concluído!")
