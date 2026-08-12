import json
import os
import time
from datetime import datetime, timezone

import requests

PASTA_ENTRADA = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "bronze", "cnes"
)
PASTA_SAIDA = PASTA_ENTRADA

URL_EQUIPES = "https://cnes.datasus.gov.br/services/estabelecimentos-equipes"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://cnes.datasus.gov.br/pages/estabelecimentos/consulta.jsp",
}


def carregar_estabelecimentos_mais_recentes():
    arquivos = [
        f for f in os.listdir(PASTA_ENTRADA) if f.startswith("estabelecimentos_")
    ]
    arquivo_mais_recente = sorted(arquivos)[-1]
    caminho = os.path.join(PASTA_ENTRADA, arquivo_mais_recente)
    print(f"Lendo estabelecimentos de: {caminho}")
    with open(caminho, "r", encoding="utf-8") as arquivo:
        return json.load(arquivo)


def buscar_equipes_da_unidade(id_estabelecimento):
    url = f"{URL_EQUIPES}/{id_estabelecimento}"
    resposta = requests.get(url, headers=HEADERS, timeout=30)
    if resposta.status_code != 200:
        print(f"  aviso: {id_estabelecimento} respondeu {resposta.status_code}, pulando")
        return []
    return resposta.json()


def salvar_json(dados, nome_arquivo):
    os.makedirs(PASTA_SAIDA, exist_ok=True)
    caminho = os.path.join(PASTA_SAIDA, nome_arquivo)
    with open(caminho, "w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, ensure_ascii=False, indent=2)
    print(f"Arquivo salvo em: {caminho}")


if __name__ == "__main__":
    estabelecimentos = carregar_estabelecimentos_mais_recentes()
    unidades_sus = [e for e in estabelecimentos if e.get("atendeSus") == "S"]
    print(f"Unidades que atendem SUS: {len(unidades_sus)}")

    todas_equipes = []
    for indice, unidade in enumerate(unidades_sus, start=1):
        id_unidade = unidade["id"]
        print(f"[{indice}/{len(unidades_sus)}] Buscando equipes de {unidade['noFantasia']} ({id_unidade})")

        equipes = buscar_equipes_da_unidade(id_unidade)
        for equipe in equipes:
            equipe["_cnes_unidade"] = unidade["cnes"]
            equipe["_nome_unidade"] = unidade["noFantasia"]
        todas_equipes.extend(equipes)

        time.sleep(0.3)  # pausa curta entre chamadas, por respeito ao servidor público

    data_hoje = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    nome_arquivo = f"equipes_recife_{data_hoje}.json"
    salvar_json(todas_equipes, nome_arquivo)

    print(f"Concluído! Total de equipes encontradas: {len(todas_equipes)}")
