"""
Mostra a estrutura do banco no Neon: tabelas, colunas, tipos,
chaves primárias, chaves estrangeiras, total de linhas e exemplos.

Rodar com: python src/utils/mostrar_banco_neon.py
"""

import os

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()
engine = create_engine(os.getenv("NEON_DATABASE_URL"))

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 20)
pd.set_option("display.max_colwidth", 30)

SQL_TABELAS = """
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_type = 'BASE TABLE'
  AND table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY table_schema, table_name;
"""

SQL_COLUNAS = """
SELECT c.column_name AS coluna,
       c.data_type   AS tipo,
       c.is_nullable AS aceita_nulo,
       CASE WHEN pk.column_name IS NOT NULL THEN 'PK' ELSE '' END AS pk
FROM information_schema.columns c
LEFT JOIN (
    SELECT kcu.table_schema, kcu.table_name, kcu.column_name
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
      ON tc.constraint_name = kcu.constraint_name
     AND tc.table_schema = kcu.table_schema
    WHERE tc.constraint_type = 'PRIMARY KEY'
) pk ON pk.table_schema = c.table_schema
    AND pk.table_name = c.table_name
    AND pk.column_name = c.column_name
WHERE c.table_schema = :schema AND c.table_name = :tabela
ORDER BY c.ordinal_position;
"""

SQL_FKS = """
SELECT tc.table_schema || '.' || tc.table_name AS tabela,
       kcu.column_name AS coluna,
       ccu.table_schema || '.' || ccu.table_name AS referencia_tabela,
       ccu.column_name AS referencia_coluna
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
  ON tc.constraint_name = kcu.constraint_name
 AND tc.table_schema = kcu.table_schema
JOIN information_schema.constraint_column_usage ccu
  ON tc.constraint_name = ccu.constraint_name
 AND tc.table_schema = ccu.table_schema
WHERE tc.constraint_type = 'FOREIGN KEY'
ORDER BY 1, 2;
"""

SQL_VIEWS = """
SELECT table_schema, table_name
FROM information_schema.views
WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY 1, 2;
"""


def linha(titulo):
    print("\n" + "=" * 80)
    print(titulo)
    print("=" * 80)


with engine.connect() as con:
    tabelas = pd.read_sql(text(SQL_TABELAS), con)

    linha(f"BANCO NO NEON — {len(tabelas)} TABELAS")
    resumo = []
    for _, t in tabelas.iterrows():
        nome = f'"{t.table_schema}"."{t.table_name}"'
        total = con.execute(text(f"SELECT COUNT(*) FROM {nome}")).scalar()
        resumo.append({"schema": t.table_schema, "tabela": t.table_name, "linhas": total})
    print(pd.DataFrame(resumo).to_string(index=False))

    for _, t in tabelas.iterrows():
        nome = f'"{t.table_schema}"."{t.table_name}"'
        linha(f"TABELA {t.table_schema}.{t.table_name}")
        colunas = pd.read_sql(
            text(SQL_COLUNAS), con,
            params={"schema": t.table_schema, "tabela": t.table_name},
        )
        print(colunas.to_string(index=False))
        print("\nExemplo (5 linhas):")
        exemplo = pd.read_sql(text(f"SELECT * FROM {nome} LIMIT 5"), con)
        print(exemplo.to_string(index=False) if not exemplo.empty else "(tabela vazia)")

    linha("CHAVES ESTRANGEIRAS (relacionamentos)")
    fks = pd.read_sql(text(SQL_FKS), con)
    print(fks.to_string(index=False) if not fks.empty else "(nenhuma chave estrangeira definida)")

    views = pd.read_sql(text(SQL_VIEWS), con)
    if not views.empty:
        linha("VIEWS")
        print(views.to_string(index=False))
