import json
import os
from datetime import datetime, timezone

import requests


CODIGO_RECIFE = "261160"

PASTA_SAIDA = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "bronze", "cnes"
)

URL_ESTABELECIMENTOS = "https://cnes.datasus.gov.br/services/estabelecimentos"


def buscar_estabelecimentos_recife():
    params = {
        "municipio": CODIGO_RECIFE,
    }
 
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://cnes.datasus.gov.br/pages/estabelecimentos/consulta.jsp",
    }
    resposta = requests.get(
        URL_ESTABELECIMENTOS, params=params, headers=headers, timeout=30
    )

    # Antes de assumir sucesso, vamos ver o que a API realmente respondeu.
    print(f"URL chamada: {resposta.url}")
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
    print("Buscando estabelecimentos de saúde do Recife no CNES...")
    dados = buscar_estabelecimentos_recife()

    data_hoje = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    nome_arquivo = f"estabelecimentos_recife_{data_hoje}.json"
    salvar_json(dados, nome_arquivo)

    print("Concluído!")
