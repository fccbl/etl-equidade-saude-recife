import json
import os
from datetime import datetime, timezone

import requests

PASTA_SAIDA = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "bronze", "dados_recife"
)

# Dataset "Distritos Sanitários" - dados.recife.pe.gov.br
# Recurso "Distritos Sanitários do Recife" (geoJSON com a geometria real).
RESOURCE_ID = "8d43533d-100b-4de2-9b08-65703d910320"
URL_RESOURCE_SHOW = "https://dados.recife.pe.gov.br/api/3/action/resource_show"


def buscar_url_do_arquivo():
    """O recurso pode não estar no datastore (tabela consultável), e sim
    ser um arquivo para download direto. resource_show devolve os metadados
    do recurso, incluindo a URL real do arquivo (campo "url")."""
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


def buscar_distritos_sanitarios():
    url_arquivo = buscar_url_do_arquivo()

    resposta = requests.get(url_arquivo, timeout=30)
    print(f"Status HTTP do arquivo: {resposta.status_code}")
    resposta.raise_for_status()

    return resposta.json()


def salvar_json(dados, nome_arquivo):
    os.makedirs(PASTA_SAIDA, exist_ok=True)
    caminho = os.path.join(PASTA_SAIDA, nome_arquivo)
    with open(caminho, "w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, ensure_ascii=False, indent=2)
    print(f"Arquivo salvo em: {caminho}")


if __name__ == "__main__":
    print("Buscando dados de Distritos Sanitários no portal Dados Recife...")
    dados = buscar_distritos_sanitarios()
    print(f"Tipo de conteúdo recebido: {type(dados).__name__}")

    data_hoje = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    nome_arquivo = f"distritos_sanitarios_{data_hoje}.json"
    salvar_json(dados, nome_arquivo)

    print("Concluído!")
