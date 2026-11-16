"""
LOJA DE PONTOS
=============
O cliente troca PONTOS (ganhos pagando em dia, recebendo salário...)
por recompensas úteis: recarga, transporte, curso, mercado...

Cada item tem um modelo_3d: o app desenha o objeto em 3D (vitrine) com
o nosso próprio renderizador (z-buffer + iluminação) — app/cg/render3d.py.

Troca = uma transação de banco só:
  confere saldo → debita pontos (movimentacoes_recompensa) → registra o
  resgate → gera o vale (cupom da loja, com assinatura anti-fraude).
"""
from decimal import Decimal

import relogio
from db import consultar, consultar_um, executar, inserir, auditar
from servicos import cupons, gamificacao, notificacoes

D = Decimal


def itens(con, cliente_id) -> dict:
    prog = gamificacao.progresso(con, cliente_id)
    lista = consultar(con, """
        SELECT i.id, i.codigo, i.nome, i.descricao, i.tipo, i.custo_pontos, i.valor_reais, i.modelo_3d,
               i.cor_hex, i.estoque, cat.nome AS categoria, p.nome AS parceiro
          FROM itens_loja i
          LEFT JOIN categorias cat ON cat.id = i.categoria_id
          LEFT JOIN parceiros p ON p.id = i.parceiro_id
         WHERE i.ativo = TRUE AND (i.estoque IS NULL OR i.estoque > 0)
         ORDER BY i.ordem, i.custo_pontos""")
    for i in lista:
        i["pode_trocar"] = prog["saldo_pontos"] >= i["custo_pontos"]
        i["faltam"] = max(0, i["custo_pontos"] - prog["saldo_pontos"])
    return {"saldo_pontos": prog["saldo_pontos"], "nivel": prog["nivel_nome"], "itens": lista}


def trocar(con, cliente_id, item_id) -> dict:
    item = consultar_um(con, "SELECT * FROM itens_loja WHERE id=%s AND ativo=TRUE FOR UPDATE", (item_id,))
    if not item:
        raise ValueError("Item não encontrado")
    if item["estoque"] is not None and item["estoque"] <= 0:
        raise ValueError("Item esgotado")

    if item["tipo"] == "cashback":     # reaproveita o resgate de cashback que já existia
        r = gamificacao.resgatar(con, cliente_id, "cashback", item["custo_pontos"])
        notificacoes.notificar(con, cliente_id, "conquista", "Cashback na conta!",
                               f"{item['nome']} trocado por {item['custo_pontos']} pontos.")
        return {"tipo": "cashback", "item": item["nome"], "pontos_usados": item["custo_pontos"],
                "valor_reais": r["valor_reais"], "cupom": None}

    prog = gamificacao.progresso(con, cliente_id)
    if prog["saldo_pontos"] < item["custo_pontos"]:
        raise ValueError(f"Faltam {item['custo_pontos'] - prog['saldo_pontos']} pontos para este item")

    resgate_id = inserir(con, "resgates", {
        "cliente_id": cliente_id, "tipo": "produto", "parceiro_id": item["parceiro_id"], "moeda_usada": "pontos",
        "quantidade_usada": item["custo_pontos"], "valor_equivalente": item["valor_reais"], "status": "concluido",
        "solicitado_em": relogio.agora(), "concluido_em": relogio.agora()})
    gamificacao.movimentar(con, cliente_id, "pontos", item["custo_pontos"], tipo="debito",
                           descricao=f"Loja: {item['nome']}", resgate_id=resgate_id)
    if item["estoque"] is not None:
        executar(con, "UPDATE itens_loja SET estoque = estoque - 1 WHERE id=%s", (item_id,))
    vale = cupons.criar(con, cliente_id, "loja", item["nome"],
                        f"Apresente este vale ao parceiro para retirar: {item['nome']}.",
                        item=item, resgate_id=resgate_id, status="revelado", dias_validade=60)
    auditar(con, "trocou_pontos", "resgates", resgate_id, None,
            {"item": item["codigo"], "pontos": item["custo_pontos"]}, ator_tipo="cliente", ator_id=cliente_id)
    notificacoes.notificar(con, cliente_id, "conquista", "Troca feita!",
                           f"{item['nome']} — seu vale está em Meus cupons.", vale["id"])
    return {"tipo": item["tipo"], "item": item["nome"], "pontos_usados": item["custo_pontos"],
            "valor_reais": float(item["valor_reais"] or 0), "cupom": cupons.obter(con, cliente_id, vale["id"])}
