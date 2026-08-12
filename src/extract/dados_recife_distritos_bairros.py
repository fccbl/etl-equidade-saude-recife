import csv
import io
import json
import os
from datetime import datetime, timezone

import requests

PASTA_SAIDA = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "bronze", "dados_recife"
)

# Dataset "Distritos Sanitários" - dados.recife.pe.gov.br
# Recurso "Distritos Sanitários – descrição dos bairros" (CSV com bairro -> distrito).
RESOURCE_ID = "d8d649d6-5bf7-44af-9686-436162766037"
URL_RESOURCE_SHOW = "https://dados.recife.pe.gov.br/api/3/action/resource_show"


def buscar_url_do_arquivo():
    resposta = requests.get(
        URL_RESOURCE_SHOW, params={"id": RESOURCE_ID}, timeout=30
    )
    print(f"URL chamada: {resposta.url}")
    print(f"Status HTTP: {resposta.status_code}")
    resposta.raise_for_status()
    corpo = resposta.json()

    if not corpo.get("success"):
        raise RuntimeError(f"A API respondeu sem sucesso: {corpo}")

    metadados = corpo["result"]
    print(f"Formato do arquivo: {metadados.get('format')}")
    print(f"URL do arquivo: {metadados.get('url')}")
    return metadados["url"]


def buscar_bairros_por_distrito():
    url_arquivo = buscar_url_do_arquivo()

    resposta = requests.get(url_arquivo, timeout=30)
    print(f"Status HTTP do arquivo: {resposta.status_code}")
    resposta.raise_for_status()

    # O arquivo vem como texto CSV (separado por ";"), não JSON pronto —
    # convertemos aqui para uma lista de dicionários, um por linha.
    texto_csv = resposta.content.decode("utf-8-sig")
    leitor = csv.DictReader(io.StringIO(texto_csv), delimiter=";")
    return list(leitor)


def salvar_json(dados, nome_arquivo):
    os.makedirs(PASTA_SAIDA, exist_ok=True)
    caminho = os.path.join(PASTA_SAIDA, nome_arquivo)
    with open(caminho, "w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, ensure_ascii=False, indent=2)
    print(f"Arquivo salvo em: {caminho}")


if __name__ == "__main__":
    print("Buscando bairros por distrito sanitário no portal Dados Recife...")
    dados = buscar_bairros_por_distrito()
    print(f"Linhas encontradas: {len(dados)}")
    if dados:
        print(f"Exemplo da primeira linha: {dados[0]}")

    data_hoje = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    nome_arquivo = f"distritos_bairros_{data_hoje}.json"
    salvar_json(dados, nome_arquivo)

    print("Concluído!")
