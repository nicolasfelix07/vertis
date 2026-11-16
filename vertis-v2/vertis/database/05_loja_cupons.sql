-- =====================================================================
-- VÉRTIS — 05: LOJA DE PONTOS E CUPONS INTELIGENTES (rodar DEPOIS do 04)
-- =====================================================================
-- 3 tabelas novas:
--   itens_loja     → o que dá para trocar por pontos (cada item tem um
--                    modelo 3D desenhado pelo app: computação gráfica)
--   modelos_cupom  → descontos que os parceiros oferecem, por categoria
--   cupons         → cupom de cada cliente (o "inteligente" do mês e os
--                    vales da loja), com assinatura anti-fraude
--
-- CRÉDITO RESPONSÁVEL: só há cupons para gastos ESSENCIAIS (mercado,
-- transporte, saúde, educação, contas). Nada de estimular consumo por
-- impulso. E não existe sorteio: o cupom é escolhido pelas regras; a
-- raspadinha do app apenas REVELA o que já foi decidido.
-- Pode rodar mais de uma vez sem problema.
-- =====================================================================
SET NAMES utf8mb4;
USE vertis;

-- ---------------------------------------------------------------------
-- Parceiros novos (fictícios)
-- ---------------------------------------------------------------------
INSERT INTO parceiros (nome, tipo, taxa_conversao)
SELECT * FROM (SELECT 'Mobi Transporte' AS n, 'varejo' AS t, NULL AS x) AS novo
 WHERE NOT EXISTS (SELECT 1 FROM parceiros WHERE nome = 'Mobi Transporte');
INSERT INTO parceiros (nome, tipo, taxa_conversao)
SELECT * FROM (SELECT 'Conecta Recargas' AS n, 'varejo' AS t, NULL AS x) AS novo
 WHERE NOT EXISTS (SELECT 1 FROM parceiros WHERE nome = 'Conecta Recargas');
INSERT INTO parceiros (nome, tipo, taxa_conversao)
SELECT * FROM (SELECT 'Farmácia Saúde+' AS n, 'varejo' AS t, NULL AS x) AS novo
 WHERE NOT EXISTS (SELECT 1 FROM parceiros WHERE nome = 'Farmácia Saúde+');
INSERT INTO parceiros (nome, tipo, taxa_conversao)
SELECT * FROM (SELECT 'Escola Futuro Financeiro' AS n, 'varejo' AS t, NULL AS x) AS novo
 WHERE NOT EXISTS (SELECT 1 FROM parceiros WHERE nome = 'Escola Futuro Financeiro');
INSERT INTO parceiros (nome, tipo, taxa_conversao)
SELECT * FROM (SELECT 'Som Mais Eletrônicos' AS n, 'varejo' AS t, NULL AS x) AS novo
 WHERE NOT EXISTS (SELECT 1 FROM parceiros WHERE nome = 'Som Mais Eletrônicos');

-- ---------------------------------------------------------------------
-- ITENS DA LOJA
-- modelo_3d: nome do objeto 3D que o app constrói (app/cg/malhas.py)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS itens_loja (
  id              CHAR(36)      NOT NULL DEFAULT (UUID()),
  codigo          VARCHAR(40)   NOT NULL,
  nome            VARCHAR(100)  NOT NULL,
  descricao       VARCHAR(255)  NULL,
  tipo            ENUM('produto','servico','cashback') NOT NULL,
  categoria_id    CHAR(36)      NULL,
  parceiro_id     CHAR(36)      NULL,
  custo_pontos    INT           NOT NULL,
  valor_reais     DECIMAL(10,2) NULL COMMENT 'Valor de referência do item',
  modelo_3d       VARCHAR(30)   NOT NULL,
  cor_hex         CHAR(7)       NOT NULL DEFAULT '#F5B700',
  estoque         INT           NULL COMMENT 'Vazio = ilimitado',
  ordem           INT           NOT NULL DEFAULT 0,
  ativo           BOOLEAN       NOT NULL DEFAULT TRUE,
  criado_em       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  atualizado_em   DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_itens_loja_codigo (codigo),
  CONSTRAINT chk_itens_loja_custo CHECK (custo_pontos > 0),
  CONSTRAINT fk_itensloja_categoria FOREIGN KEY (categoria_id) REFERENCES categorias(id),
  CONSTRAINT fk_itensloja_parceiro  FOREIGN KEY (parceiro_id)  REFERENCES parceiros(id)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- MODELOS DE CUPOM (o que cada parceiro oferece, por categoria de gasto)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS modelos_cupom (
  id              CHAR(36)      NOT NULL DEFAULT (UUID()),
  categoria_id    CHAR(36)      NOT NULL,
  parceiro_id     CHAR(36)      NULL,
  titulo          VARCHAR(100)  NOT NULL,
  percentual      DECIMAL(5,2)  NOT NULL COMMENT '% de desconto',
  teto_reais      DECIMAL(10,2) NOT NULL COMMENT 'Desconto máximo por uso',
  essencial       BOOLEAN       NOT NULL DEFAULT TRUE,
  ativo           BOOLEAN       NOT NULL DEFAULT TRUE,
  criado_em       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  atualizado_em   DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT fk_modcupom_categoria FOREIGN KEY (categoria_id) REFERENCES categorias(id),
  CONSTRAINT fk_modcupom_parceiro  FOREIGN KEY (parceiro_id)  REFERENCES parceiros(id)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- CUPONS DOS CLIENTES
-- assinatura = HMAC-SHA256(código | cliente | validade) com a chave da API.
-- O "modo caixa" confere a assinatura: cupom inventado ou alterado não passa.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cupons (
  id              CHAR(36)      NOT NULL DEFAULT (UUID()),
  cliente_id      CHAR(36)      NOT NULL,
  origem          ENUM('inteligente','loja') NOT NULL,
  modelo_id       CHAR(36)      NULL,
  item_id         CHAR(36)      NULL,
  resgate_id      CHAR(36)      NULL,
  categoria_id    CHAR(36)      NULL,
  codigo          VARCHAR(20)   NOT NULL,
  titulo          VARCHAR(120)  NOT NULL,
  descricao       VARCHAR(255)  NULL,
  percentual      DECIMAL(5,2)  NULL,
  teto_reais      DECIMAL(10,2) NULL,
  motivo          VARCHAR(255)  NULL COMMENT 'Por que este cupom foi escolhido (transparência)',
  economia_estimada DECIMAL(10,2) NULL,
  assinatura      CHAR(64)      NOT NULL,
  status          ENUM('oculto','revelado','usado','expirado') NOT NULL DEFAULT 'oculto',
  gerado_em       DATETIME      NOT NULL,
  revelado_em     DATETIME      NULL,
  usado_em        DATETIME      NULL,
  valido_ate      DATETIME      NOT NULL,
  criado_em       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  atualizado_em   DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_cupons_codigo (codigo),
  KEY idx_cupons_cliente_status (cliente_id, status),
  CONSTRAINT fk_cupons_cliente   FOREIGN KEY (cliente_id)   REFERENCES clientes(id),
  CONSTRAINT fk_cupons_modelo    FOREIGN KEY (modelo_id)    REFERENCES modelos_cupom(id),
  CONSTRAINT fk_cupons_item      FOREIGN KEY (item_id)      REFERENCES itens_loja(id),
  CONSTRAINT fk_cupons_resgate   FOREIGN KEY (resgate_id)   REFERENCES resgates(id),
  CONSTRAINT fk_cupons_categoria FOREIGN KEY (categoria_id) REFERENCES categorias(id)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- Dados: itens da loja (recompensas úteis para o público da Vértis)
-- ---------------------------------------------------------------------
DELETE FROM itens_loja WHERE codigo IN ('RECARGA_15','TRANSPORTE_20','CURSO_FINANCAS','FONE','MOCHILA','MERCADO_50','CASHBACK_10')
  AND id NOT IN (SELECT item_id FROM (SELECT item_id FROM cupons WHERE item_id IS NOT NULL) AS usados);

INSERT IGNORE INTO itens_loja (codigo, nome, descricao, tipo, categoria_id, parceiro_id, custo_pontos, valor_reais, modelo_3d, cor_hex, ordem) VALUES
 ('CASHBACK_10', 'Cashback de R$ 10', 'O dinheiro cai na sua conta na hora.', 'cashback',
   (SELECT id FROM categorias WHERE nome='Outras receitas' AND cliente_id IS NULL), NULL, 1000, 10.00, 'moeda', '#F5B700', 1),
 ('RECARGA_15', 'Recarga de celular R$ 15', 'Crédito para qualquer operadora.', 'servico',
   (SELECT id FROM categorias WHERE nome='Contas e serviços' AND cliente_id IS NULL),
   (SELECT id FROM parceiros WHERE nome='Conecta Recargas'), 1500, 15.00, 'celular', '#2B2F36', 2),
 ('TRANSPORTE_20', 'Crédito de transporte R$ 20', 'Recarga do cartão de ônibus e metrô.', 'servico',
   (SELECT id FROM categorias WHERE nome='Transporte' AND cliente_id IS NULL),
   (SELECT id FROM parceiros WHERE nome='Mobi Transporte'), 2000, 20.00, 'cartao_transporte', '#1E8E4E', 3),
 ('CURSO_FINANCAS', 'Curso: organize seu dinheiro', '8 aulas online de educação financeira, com certificado.', 'servico',
   (SELECT id FROM categorias WHERE nome='Educação' AND cliente_id IS NULL),
   (SELECT id FROM parceiros WHERE nome='Escola Futuro Financeiro'), 1200, 60.00, 'livro', '#0E7490', 4),
 ('MERCADO_50', 'Vale-compras R$ 50 no mercado', 'Use no Mercado Bom Preço em até 60 dias.', 'servico',
   (SELECT id FROM categorias WHERE nome='Alimentação' AND cliente_id IS NULL),
   (SELECT id FROM parceiros WHERE nome='Mercado Bom Preço'), 5000, 50.00, 'sacola', '#D99A00', 5),
 ('FONE', 'Fone de ouvido', 'Fone com fio e microfone, para trabalho e estudo.', 'produto',
   (SELECT id FROM categorias WHERE nome='Compras' AND cliente_id IS NULL),
   (SELECT id FROM parceiros WHERE nome='Som Mais Eletrônicos'), 4500, 45.00, 'fone', '#2B2F36', 6),
 ('MOCHILA', 'Mochila resistente', 'Mochila impermeável com compartimento para notebook.', 'produto',
   (SELECT id FROM categorias WHERE nome='Compras' AND cliente_id IS NULL),
   (SELECT id FROM parceiros WHERE nome='Som Mais Eletrônicos'), 6500, 65.00, 'mochila', '#F5B700', 7);

-- ---------------------------------------------------------------------
-- Dados: modelos de cupom (somente categorias ESSENCIAIS)
-- ---------------------------------------------------------------------
DELETE FROM modelos_cupom WHERE id NOT IN (SELECT modelo_id FROM (SELECT modelo_id FROM cupons WHERE modelo_id IS NOT NULL) AS usados);
INSERT INTO modelos_cupom (categoria_id, parceiro_id, titulo, percentual, teto_reais)
SELECT * FROM (
  SELECT (SELECT id FROM categorias WHERE nome='Alimentação' AND cliente_id IS NULL) AS c,
         (SELECT id FROM parceiros WHERE nome='Mercado Bom Preço') AS p, '10% no Mercado Bom Preço' AS t, 10.00 AS pc, 25.00 AS teto
  UNION ALL SELECT (SELECT id FROM categorias WHERE nome='Transporte' AND cliente_id IS NULL),
         (SELECT id FROM parceiros WHERE nome='Mobi Transporte'), '15% na recarga de transporte', 15.00, 20.00
  UNION ALL SELECT (SELECT id FROM categorias WHERE nome='Saúde' AND cliente_id IS NULL),
         (SELECT id FROM parceiros WHERE nome='Farmácia Saúde+'), '12% na Farmácia Saúde+', 12.00, 25.00
  UNION ALL SELECT (SELECT id FROM categorias WHERE nome='Educação' AND cliente_id IS NULL),
         (SELECT id FROM parceiros WHERE nome='Escola Futuro Financeiro'), '20% em cursos e material escolar', 20.00, 30.00
  UNION ALL SELECT (SELECT id FROM categorias WHERE nome='Contas e serviços' AND cliente_id IS NULL),
         (SELECT id FROM parceiros WHERE nome='Conecta Recargas'), '10% na recarga de celular', 10.00, 10.00
) AS novos
WHERE NOT EXISTS (SELECT 1 FROM modelos_cupom);
