-- =====================================================================
-- Modelagem "formulário por pessoa" (pedido do professor, aula 16/11)
--
-- Cada registro de `pessoa` representa um formulário preenchido por uma
-- mesma pessoa, com raça/cor, orientação sexual, identidade de gênero,
-- deficiência(s), microárea e equipe que fez a coleta.
--
-- Origem: mock_pec_atendimentos (cada atendimento = um formulário).
-- Valores não informados ficam NULL (a FK aceita nulo).
-- Equipe = equipes_saude (já existente). Profissional = equipe.
--
-- Microárea: SIMULADA. O dado não é público. Seguindo a PNAB 2017
-- (equipe com 2.000 a 3.500 pessoas; até 750 pessoas por ACS), cada
-- equipe recebe de 3 a 5 microáreas, e cada pessoa vai para uma
-- microárea da própria equipe. O sorteio usa hashtext(), então o
-- resultado é sempre o mesmo a cada execução.
--
-- Só CRIA tabelas novas. Nenhuma tabela existente é alterada.
-- =====================================================================

BEGIN;

-- ---------- Tabelas de domínio ----------
CREATE TABLE raca_cor (
    id_raca_cor SERIAL PRIMARY KEY,
    descricao   TEXT NOT NULL UNIQUE
);

CREATE TABLE orientacao_sexual (
    id_orientacao_sexual SERIAL PRIMARY KEY,
    descricao            TEXT NOT NULL UNIQUE
);

CREATE TABLE identidade_genero (
    id_identidade_genero SERIAL PRIMARY KEY,
    descricao            TEXT NOT NULL UNIQUE
);

CREATE TABLE deficiencia (
    id_deficiencia SERIAL PRIMARY KEY,
    descricao      TEXT NOT NULL UNIQUE
);

INSERT INTO raca_cor (descricao)
SELECT DISTINCT raca_cor FROM mock_pec_atendimentos
WHERE raca_cor IS NOT NULL ORDER BY 1;

INSERT INTO orientacao_sexual (descricao)
SELECT DISTINCT orientacao_sexual FROM mock_pec_atendimentos
WHERE orientacao_sexual IS NOT NULL ORDER BY 1;

INSERT INTO identidade_genero (descricao)
SELECT DISTINCT identidade_genero FROM mock_pec_atendimentos
WHERE identidade_genero IS NOT NULL ORDER BY 1;

-- "Nenhuma" entra como valor: diferencia quem declarou não ter
-- deficiência de quem não respondeu (sem linha em pessoa_deficiencia).
INSERT INTO deficiencia (descricao)
SELECT DISTINCT deficiencia_tipo FROM mock_pec_atendimentos
WHERE deficiencia_tipo IS NOT NULL ORDER BY 1;

-- ---------- Microárea (simulada, ligada à equipe) ----------
CREATE TABLE microarea (
    id_microarea SERIAL PRIMARY KEY,
    codigo       TEXT NOT NULL,
    id_equipe    TEXT NOT NULL REFERENCES equipes_saude (codigo_equipe),
    UNIQUE (id_equipe, codigo)
);

INSERT INTO microarea (codigo, id_equipe)
SELECT lpad(n::text, 2, '0'), e.codigo_equipe
FROM (SELECT DISTINCT codigo_equipe FROM mock_pec_atendimentos) e
CROSS JOIN LATERAL generate_series(1, 3 + abs(hashtext(e.codigo_equipe)::bigint) % 3) AS n
ORDER BY 2, 1;

-- ---------- Pessoa (o formulário) ----------
CREATE TABLE pessoa (
    id_pessoa            INTEGER PRIMARY KEY,
    id_raca_cor          INTEGER REFERENCES raca_cor (id_raca_cor),
    id_orientacao_sexual INTEGER REFERENCES orientacao_sexual (id_orientacao_sexual),
    id_identidade_genero INTEGER REFERENCES identidade_genero (id_identidade_genero),
    id_microarea         INTEGER NOT NULL REFERENCES microarea (id_microarea),
    id_equipe            TEXT    NOT NULL REFERENCES equipes_saude (codigo_equipe),
    data_coleta          DATE,
    id_atendimento       INTEGER UNIQUE REFERENCES mock_pec_atendimentos (id_atendimento)
);

INSERT INTO pessoa
SELECT a.id_atendimento,
       rc.id_raca_cor,
       os.id_orientacao_sexual,
       ig.id_identidade_genero,
       m.id_microarea,
       a.codigo_equipe,
       a.data_atendimento,
       a.id_atendimento
FROM mock_pec_atendimentos a
LEFT JOIN raca_cor          rc ON rc.descricao = a.raca_cor
LEFT JOIN orientacao_sexual os ON os.descricao = a.orientacao_sexual
LEFT JOIN identidade_genero ig ON ig.descricao = a.identidade_genero
JOIN microarea m
  ON m.id_equipe = a.codigo_equipe
 AND m.codigo = lpad((abs(hashtext(a.id_atendimento::text)::bigint)
                      % (3 + abs(hashtext(a.codigo_equipe)::bigint) % 3) + 1)::text, 2, '0');

-- ---------- Deficiência: associativa N:N ----------
CREATE TABLE pessoa_deficiencia (
    id_pessoa      INTEGER NOT NULL REFERENCES pessoa (id_pessoa),
    id_deficiencia INTEGER NOT NULL REFERENCES deficiencia (id_deficiencia),
    PRIMARY KEY (id_pessoa, id_deficiencia)
);

INSERT INTO pessoa_deficiencia (id_pessoa, id_deficiencia)
SELECT a.id_atendimento, d.id_deficiencia
FROM mock_pec_atendimentos a
JOIN deficiencia d ON d.descricao = a.deficiencia_tipo;

-- ---------- Índices nas FKs (consultas de cruzamento) ----------
CREATE INDEX idx_pessoa_raca_cor    ON pessoa (id_raca_cor);
CREATE INDEX idx_pessoa_orientacao  ON pessoa (id_orientacao_sexual);
CREATE INDEX idx_pessoa_identidade  ON pessoa (id_identidade_genero);
CREATE INDEX idx_pessoa_microarea   ON pessoa (id_microarea);
CREATE INDEX idx_pessoa_equipe      ON pessoa (id_equipe);
CREATE INDEX idx_pdef_deficiencia   ON pessoa_deficiencia (id_deficiencia);

COMMIT;
