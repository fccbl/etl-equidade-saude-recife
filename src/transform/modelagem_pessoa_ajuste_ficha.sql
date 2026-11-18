-- =====================================================================
-- Ajuste das tabelas de domínio para seguir a Ficha de Cadastro
-- Individual do e-SUS APS (CI/e-SUS AB v5.3).
-- Rodar DEPOIS de modelagem_pessoa.sql.
--
-- Identidade de gênero: nomes da ficha + opção "Travesti".
-- Deficiência: troca os textos do Censo/IBGE pelas opções da ficha
--   ouvir -> Auditiva | enxergar -> Visual | andar e pegar objetos -> Física
--   funções mentais -> Intelectual/Cognitiva | (TEA e Outra sem casos)
-- "Nenhuma" sai do domínio e vira pessoa.tem_deficiencia (pergunta
--   "TEM ALGUMA DEFICIÊNCIA?" da ficha): NULL = não informado,
--   false = Não, true = Sim.
--
-- Altera só as tabelas novas. Se algo falhar, nada é gravado.
-- =====================================================================

BEGIN;

-- ---------- Identidade de gênero ----------
UPDATE identidade_genero SET descricao = 'Homem transgênero'  WHERE descricao = 'Homem trans';
UPDATE identidade_genero SET descricao = 'Mulher transgênero' WHERE descricao = 'Mulher trans';
UPDATE identidade_genero SET descricao = 'Não-Binário'        WHERE descricao = 'Não-binário';
INSERT INTO identidade_genero (descricao) VALUES ('Travesti');

-- ---------- Deficiência ----------
ALTER TABLE pessoa ADD COLUMN tem_deficiencia BOOLEAN;

UPDATE pessoa p
SET tem_deficiencia = (d.descricao <> 'Nenhuma')
FROM pessoa_deficiencia pd
JOIN deficiencia d ON d.id_deficiencia = pd.id_deficiencia
WHERE pd.id_pessoa = p.id_pessoa;

INSERT INTO deficiencia (descricao) VALUES
    ('Auditiva'), ('Visual'), ('Física'),
    ('Intelectual/Cognitiva'), ('TEA'), ('Outra');

UPDATE pessoa_deficiencia pd
SET id_deficiencia = n.id_deficiencia
FROM (VALUES
        ('Dificuldade permanente para ouvir%',         'Auditiva'),
        ('Dificuldade permanente para enxergar%',      'Visual'),
        ('Dificuldade permanente para andar%',         'Física'),
        ('Dificuldade permanente para pegar%',         'Física'),
        ('Dificuldade permanente para se comunicar%',  'Intelectual/Cognitiva')
     ) AS m (antigo, novo)
JOIN deficiencia o ON o.descricao LIKE m.antigo
JOIN deficiencia n ON n.descricao = m.novo
WHERE pd.id_deficiencia = o.id_deficiencia;

DELETE FROM pessoa_deficiencia
WHERE id_deficiencia = (SELECT id_deficiencia FROM deficiencia WHERE descricao = 'Nenhuma');

-- A FK impede apagar um valor ainda usado: se algum texto antigo
-- ficou sem conversão, este DELETE falha e a transação é desfeita.
DELETE FROM deficiencia
WHERE descricao = 'Nenhuma' OR descricao LIKE 'Dificuldade permanente%';

COMMIT;
