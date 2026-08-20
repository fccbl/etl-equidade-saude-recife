import os
import re
from decimal import Decimal

import ollama
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

NEON_DATABASE_URL = os.getenv("NEON_DATABASE_URL")
MODELO_SQL = "llama3.2"
MODELO_RESPOSTA = "llama3.2"

ESQUEMA_BANCO = """
Tabelas disponíveis no banco (PostgreSQL):

unidades_saude(
    cnes TEXT, nome_fantasia TEXT, nome_empresarial TEXT, bairro TEXT,
    distrito_sanitario_codigo TEXT, distrito_sanitario_nome TEXT,
    endereco TEXT, cep TEXT, latitude DOUBLE PRECISION, longitude DOUBLE PRECISION,
    tipo_estabelecimento TEXT
)

IMPORTANTE sobre distrito_sanitario_codigo: é um texto numérico com zero à
esquerda (dois dígitos). Use exatamente esta tabela de conversão, com cuidado
especial para não confundir VII com VIII (são códigos consecutivos e
parecidos):
'01' = Distrito I
'02' = Distrito II
'03' = Distrito III
'04' = Distrito IV
'05' = Distrito V
'06' = Distrito VI
'07' = Distrito VII
'08' = Distrito VIII (NÃO é '07' — VIII tem um "I" extra no final em relação a VII)
Quando o usuário mencionar um distrito em número romano (ex: "Distrito I",
"Distrito IV"), converta para esse código numérico de dois dígitos e filtre
por distrito_sanitario_codigo. NÃO filtre por distrito_sanitario_nome usando o
número romano isolado — "I" aparece como substring dentro de "II", "III",
"VII" e "VIII", o que gera resultado errado.
Algumas unidades têm distrito_sanitario_codigo em branco (NULL) — são
hospitais, laboratórios e outros tipos que não pertencem a um Distrito
Sanitário; isso é esperado, não é erro de dado.

IMPORTANTE: a tabela unidades_saude já contém APENAS unidades de Recife —
não existe coluna de cidade/município, e o campo cep é só o CEP numérico
(não contém o nome "Recife" escrito nele). Se a pergunta mencionar "Recife",
NÃO filtre por cep, endereco ou qualquer texto — ignore a palavra "Recife" e
consulte a tabela inteira, sem filtro de cidade.

Para contar quantos distritos sanitários distintos existem, use
COUNT(DISTINCT distrito_sanitario_codigo) e sempre exclua os valores NULL com
WHERE distrito_sanitario_codigo IS NOT NULL. Preste atenção ao digitar o nome
da coluna exatamente como está definido aqui: distrito_sanitario_codigo (não
"distro_sanitario_codigo" nem outra variação).

Para perguntas de ranking/comparação entre distritos (ex: "qual distrito tem
mais unidades", "qual distrito tem menos equipes"), sempre adicione
WHERE distrito_sanitario_codigo IS NOT NULL antes do GROUP BY. Sem esse
filtro, as unidades sem distrito (hospitais, laboratórios) formam um grupo
próprio que pode aparecer como "vencedor" do ranking, o que é errado — elas
não pertencem a nenhum distrito.

equipes_saude(
    codigo_equipe TEXT, nome_equipe TEXT, tipo_equipe TEXT,
    cnes_unidade TEXT, data_ativacao TEXT, data_desativacao TEXT
)

Sobre o status da equipe: uma equipe que ainda está ativa (realmente
atendendo hoje) tem data_desativacao NULL (em branco). Uma equipe com
data_desativacao preenchida já foi desativada e não atende mais. Quando a
pergunta mencionar "ativas", "que atendem", "em funcionamento" ou "em
operação", filtre com WHERE data_desativacao IS NULL. Quando mencionar
"desativadas" ou "que não atendem mais", filtre com
WHERE data_desativacao IS NOT NULL. Quando a pergunta pedir apenas o "total"
sem menção a status, não filtre por data_desativacao — conte todas.

censo_raca_cor(
    raca_cor TEXT, populacao BIGINT, ano INTEGER
)

Os únicos valores que existem na coluna raca_cor são exatamente estes 5,
escritos assim: 'Branca', 'Preta', 'Parda', 'Amarela', 'Indígena'. Não existe
nenhum outro valor nessa coluna — nunca invente uma categoria diferente
dessas.

IMPORTANTE sobre "população negra": não existe uma categoria 'Negra' na
coluna raca_cor. Pela definição usada pelo IBGE e pelas políticas de equidade
racial, "população negra" = soma de 'Preta' + 'Parda'. Quando a pergunta
mencionar "negra", "negros" ou "pessoas negras", SOME as duas categorias
('Preta' e 'Parda') — nunca retorne apenas 'Preta' isolada, isso sub-representa
gravemente o número real.

censo_deficiencia(
    tipo_dificuldade TEXT, populacao BIGINT, ano INTEGER, e_total BOOLEAN
)

Os únicos valores que existem na coluna tipo_dificuldade são: 'Total' (quando
e_total = true) e, quando e_total = false, um destes 5 textos exatos:
'Dificuldade permanente para enxergar, mesmo usando óculos ou lentes de
contato', 'Dificuldade permanente para ouvir, mesmo usando aparelhos
auditivos', 'Dificuldade permanente para andar ou subir degraus, mesmo usando
prótese ou outro aparelho de auxílio', 'Dificuldade permanente para pegar
pequenos objetos, como botão ou lápis, ou abrir e fechar tampas de garrafas,
mesmo usando aparelho de auxílio', 'Dificuldade permanente para se comunicar,
realizar cuidados pessoais, trabalhar ou estudar por causa de alguma
limitação nas funções mentais'. Para perguntas sobre o TOTAL de pessoas com
deficiência (sem especificar um tipo), use WHERE e_total = true e NÃO filtre
por tipo_dificuldade.

Regra importante: em censo_deficiencia, a linha com e_total = true é o total
oficial de pessoas com deficiência; as linhas com e_total = false são tipos de
dificuldade específicos, que NÃO devem ser somados entre si (uma pessoa pode
ter mais de um tipo de dificuldade). Mesmo que a pergunta peça explicitamente
para "somar os tipos" ou "somar todas as dificuldades", IGNORE esse pedido e
retorne o valor de e_total = true, pois somar os tipos gera um número inflado
e estatisticamente errado — o total correto já está pronto na linha
e_total = true.

IMPORTANTE: as tabelas censo_deficiencia e censo_raca_cor NÃO têm nenhuma
coluna de território (não têm cidade, bairro, distrito). Elas já representam
o Recife inteiro. NUNCA adicione um filtro tipo "WHERE ... = 'Recife'" nessas
duas tabelas — essa coluna não existe e a consulta vai falhar. Se a pergunta
mencionar "Recife", ignore essa palavra ao montar o SQL para essas duas
tabelas, pois já é implícito.

IMPORTANTE sobre a coluna ano: em censo_raca_cor e censo_deficiencia, o único
valor existente é 2022 (dado do Censo Demográfico 2022). Não assuma outro ano
(como o ano atual) — se a pergunta não especificar um ano, não filtre por ano,
ou use ano = 2022.

Exemplos de pergunta e o SQL correto correspondente:

Pergunta: Quantas unidades de saúde tem no Distrito Sanitário I?
SQL: SELECT COUNT(*) FROM unidades_saude WHERE distrito_sanitario_codigo = '01';

Pergunta: Quantas unidades de saúde tem em Recife?
SQL: SELECT COUNT(*) FROM unidades_saude;

Pergunta: Quantos distritos sanitários existem?
SQL: SELECT COUNT(DISTINCT distrito_sanitario_codigo) FROM unidades_saude WHERE distrito_sanitario_codigo IS NOT NULL;

Pergunta: Quantas unidades de saúde tem no Distrito VIII?
SQL: SELECT COUNT(*) FROM unidades_saude WHERE distrito_sanitario_codigo = '08';

Pergunta: Qual distrito tem mais unidades de saúde?
SQL: SELECT distrito_sanitario_nome FROM unidades_saude WHERE distrito_sanitario_codigo IS NOT NULL GROUP BY distrito_sanitario_nome ORDER BY COUNT(*) DESC LIMIT 1;

Pergunta: Some todos os tipos de dificuldade e me diga o total de pessoas com deficiência
SQL: SELECT populacao FROM censo_deficiencia WHERE e_total = true;

Pergunta: Quantas pessoas com deficiência tem no Recife?
SQL: SELECT populacao FROM censo_deficiencia WHERE e_total = true;

Pergunta: Qual a população parda do Recife?
SQL: SELECT populacao FROM censo_raca_cor WHERE raca_cor = 'Parda';

Pergunta: Quantas pessoas negras tem em Recife?
SQL: SELECT SUM(populacao) FROM censo_raca_cor WHERE raca_cor IN ('Preta', 'Parda');

Pergunta: Quantas equipes de saúde da família existem no total?
SQL: SELECT COUNT(*) FROM equipes_saude;

Pergunta: Quantas equipes estão ativas, ou seja, sem data de desativação?
SQL: SELECT COUNT(*) FROM equipes_saude WHERE data_desativacao IS NULL;

Pergunta: Quantas equipes já foram desativadas?
SQL: SELECT COUNT(*) FROM equipes_saude WHERE data_desativacao IS NOT NULL;
"""


def gerar_sql(pergunta):
    prompt = f"""{ESQUEMA_BANCO}

Escreva APENAS um comando SQL (PostgreSQL) que responda à pergunta abaixo.
Não escreva explicações, não use blocos de markdown, escreva somente o SQL puro.

Pergunta: {pergunta}
SQL:"""

    resposta = ollama.chat(
        model=MODELO_SQL,
        messages=[{"role": "user", "content": prompt}],
        options={"temperature": 0},
    )
    sql_bruto = resposta["message"]["content"]
    return re.sub(r"```sql|```", "", sql_bruto).strip()


def rodar_sql(sql):
    if not sql.strip().upper().startswith("SELECT"):
        raise ValueError(
            "Por segurança, só executo comandos SELECT. "
            f"O modelo gerou: {sql}"
        )

    engine = create_engine(NEON_DATABASE_URL)
    with engine.connect() as conexao:
        resultado = conexao.execute(text(sql))
        linhas = resultado.fetchall()
        colunas = resultado.keys()
    return colunas, linhas


def gerar_resposta_em_texto(pergunta, colunas, linhas):
    dados_formatados = "\n".join(
        ", ".join(f"{col}: {valor}" for col, valor in zip(colunas, linha))
        for linha in linhas
    )
    print(f"[Dados retornados pelo Neon]: {dados_formatados}\n")

    if not linhas:
        return "Não encontrei nenhum resultado para essa pergunta no banco de dados."

    if len(linhas) == 1 and len(colunas) == 1:
        valor = linhas[0][0]
        if isinstance(valor, (int, float, Decimal)):
            valor = f"{int(valor):,}".replace(",", ".")
        return f"A resposta é {valor}."

    prompt = f"""Reescreva os dados abaixo como uma frase em português, de forma
direta e objetiva. Não adicione opiniões, ressalvas ou comentários — apenas
transcreva os números em uma frase.

Pergunta: {pergunta}
Dados: {dados_formatados}

Frase:"""

    resposta = ollama.chat(
        model=MODELO_RESPOSTA,
        messages=[{"role": "user", "content": prompt}],
    )
    return resposta["message"]["content"]


def responder_pergunta(pergunta):
    sql = gerar_sql(pergunta)
    print(f"[SQL gerado pelo modelo]: {sql}\n")

    colunas, linhas = rodar_sql(sql)
    return gerar_resposta_em_texto(pergunta, colunas, linhas)


if __name__ == "__main__":
    pergunta = input("Pergunte sobre os dados: ")
    print("\n" + responder_pergunta(pergunta))
