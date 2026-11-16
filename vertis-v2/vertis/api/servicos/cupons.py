"""
CUPONS INTELIGENTES
==================
"Inteligente" = escolhido pelo GASTO REAL do cliente, não por sorteio.

Como o cupom do mês é escolhido:
  1. Somamos os gastos dos últimos 60 dias por categoria
     (saídas da conta + compras no cartão).
  2. Para cada categoria ESSENCIAL que tem um parceiro com desconto,
     calculamos a economia possível:  min(gasto × percentual, teto).
  3. Fica o cupom que mais economiza — e o app mostra o MOTIVO
     ("Você gastou R$ 312 com Transporte..."): transparência.

Segurança (anti-fraude):
  Cada cupom tem uma ASSINATURA = HMAC-SHA256(código|cliente|validade),
  feita com a chave secreta da API. No "modo caixa", a loja confere a
  assinatura: um cupom inventado ou com o código alterado não passa.
  No app, o selo holográfico (computação gráfica) muda de cor quando o
  celular inclina — um print de tela fica parado e denuncia a cópia.
"""
import hashlib
import hmac
import random
import string
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

import config
import relogio
from db import consultar, consultar_um, executar, inserir
from servicos import notificacoes

D = Decimal
DIAS_ANALISE = 60
DIAS_VALIDADE = 30


def _codigo(con) -> str:
    while True:
        codigo = "VTS-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        if not consultar_um(con, "SELECT id FROM cupons WHERE codigo=%s", (codigo,)):
            return codigo


def assinar(codigo: str, cliente_id: str, valido_ate) -> str:
    texto = f"{codigo}|{cliente_id}|{valido_ate:%Y-%m-%d %H:%M:%S}"
    return hmac.new(config.CHAVE_TOKEN.encode(), texto.encode(), hashlib.sha256).hexdigest()


def gastos_por_categoria(con, cliente_id) -> dict:
    """{nome_da_categoria: total gasto nos últimos 60 dias}"""
    desde = relogio.agora() - timedelta(days=DIAS_ANALISE)
    linhas = consultar(con, """
        SELECT cat.nome AS categoria, SUM(x.valor) AS total FROM (
            SELECT t.categoria_id, t.valor
              FROM transacoes t JOIN contas c ON c.id = t.conta_id
             WHERE c.cliente_id = %s AND t.direcao = 'saida' AND t.status = 'concluida'
               AND t.tipo NOT IN ('pagamento_fatura', 'ted', 'pix_enviado') AND t.realizada_em >= %s
            UNION ALL
            SELECT cc.categoria_id, cc.valor_total
              FROM compras_cartao cc JOIN cartoes ca ON ca.id = cc.cartao_id JOIN contas c ON c.id = ca.conta_id
             WHERE c.cliente_id = %s AND cc.status = 'autorizada' AND cc.funcao_usada = 'credito'
               AND cc.realizada_em >= %s
        ) AS x JOIN categorias cat ON cat.id = x.categoria_id
        GROUP BY cat.nome""", (cliente_id, desde, cliente_id, desde))
    return {l["categoria"]: D(l["total"]) for l in linhas}


def _reais(v) -> str:
    return "R$ " + f"{float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def escolher(con, cliente_id) -> dict:
    """Escolhe o melhor modelo de cupom para o cliente (sem gravar nada)."""
    gastos = gastos_por_categoria(con, cliente_id)
    modelos = consultar(con, """
        SELECT m.*, cat.nome AS categoria, p.nome AS parceiro FROM modelos_cupom m
          JOIN categorias cat ON cat.id = m.categoria_id
          LEFT JOIN parceiros p ON p.id = m.parceiro_id
         WHERE m.ativo = TRUE AND m.essencial = TRUE""")
    if not modelos:
        raise ValueError("Nenhum cupom disponível no momento")
    melhor, melhor_economia = None, D(-1)
    for m in modelos:
        gasto = gastos.get(m["categoria"], D(0))
        economia = min(gasto * D(m["percentual"]) / 100, D(m["teto_reais"]))
        if economia > melhor_economia:
            melhor, melhor_economia = m, economia
    gasto = gastos.get(melhor["categoria"], D(0))
    if gasto > 0:
        motivo = (f"Você gastou {_reais(gasto)} com {melhor['categoria']} nos últimos {DIAS_ANALISE} dias. "
                  f"Com este cupom, teria economizado {_reais(melhor_economia)}.")
    else:   # cliente novo, sem gastos ainda
        melhor = next((m for m in modelos if m["categoria"] == "Alimentação"), modelos[0])
        melhor_economia = D(0)
        motivo = "Cupom de boas-vindas para o essencial: mercado. Os próximos serão escolhidos pelos seus gastos."
    return {"modelo": melhor, "economia": melhor_economia.quantize(D("0.01"), ROUND_HALF_UP),
            "motivo": motivo, "gastos": {k: float(v) for k, v in gastos.items()}}


def criar(con, cliente_id, origem, titulo, descricao=None, modelo=None, item=None, resgate_id=None,
          motivo=None, economia=None, status="oculto", dias_validade=DIAS_VALIDADE) -> dict:
    agora = relogio.agora()
    valido_ate = agora + timedelta(days=dias_validade)
    codigo = _codigo(con)
    cupom = {
        "cliente_id": cliente_id, "origem": origem, "codigo": codigo, "titulo": titulo[:120],
        "descricao": (descricao or "")[:255] or None,
        "modelo_id": modelo["id"] if modelo else None, "item_id": item["id"] if item else None,
        "resgate_id": resgate_id,
        "categoria_id": (modelo or item or {}).get("categoria_id"),
        "percentual": modelo["percentual"] if modelo else None, "teto_reais": modelo["teto_reais"] if modelo else None,
        "motivo": (motivo or "")[:255] or None, "economia_estimada": economia,
        "assinatura": assinar(codigo, cliente_id, valido_ate), "status": status, "gerado_em": agora,
        "revelado_em": agora if status == "revelado" else None, "valido_ate": valido_ate,
    }
    cupom["id"] = inserir(con, "cupons", cupom)
    return cupom


def cupom_do_mes(con, cliente_id) -> dict:
    """Um cupom inteligente a cada 30 dias. Se já existe um válido, devolve o mesmo."""
    expirar(con, cliente_id)
    agora = relogio.agora()
    atual = consultar_um(con, """
        SELECT id FROM cupons WHERE cliente_id=%s AND origem='inteligente'
           AND gerado_em > %s ORDER BY gerado_em DESC LIMIT 1""", (cliente_id, agora - timedelta(days=30)))
    if atual:
        return obter(con, cliente_id, atual["id"])
    e = escolher(con, cliente_id)
    m = e["modelo"]
    descricao = f"{m['titulo']} (desconto de até {_reais(m['teto_reais'])} por compra)"
    c = criar(con, cliente_id, "inteligente", m["titulo"], descricao, modelo=m, motivo=e["motivo"],
              economia=e["economia"])
    notificacoes.notificar(con, cliente_id, "promocao", "Seu cupom do mês chegou!",
                           "Raspe para revelar. Ele foi escolhido pelos seus gastos essenciais.", c["id"])
    return obter(con, cliente_id, c["id"])


def expirar(con, cliente_id):
    executar(con, """UPDATE cupons SET status='expirado'
                      WHERE cliente_id=%s AND status IN ('oculto','revelado') AND valido_ate < %s""",
             (cliente_id, relogio.agora()))


def obter(con, cliente_id, cupom_id) -> dict:
    c = consultar_um(con, """
        SELECT cu.*, cat.nome AS categoria, p.nome AS parceiro, i.modelo_3d, i.cor_hex
          FROM cupons cu
          LEFT JOIN categorias cat ON cat.id = cu.categoria_id
          LEFT JOIN modelos_cupom m ON m.id = cu.modelo_id
          LEFT JOIN itens_loja i ON i.id = cu.item_id
          LEFT JOIN parceiros p ON p.id = COALESCE(m.parceiro_id, i.parceiro_id)
         WHERE cu.id=%s AND cu.cliente_id=%s""", (cupom_id, cliente_id))
    if not c:
        raise ValueError("Cupom não encontrado")
    if c["status"] == "oculto":          # enquanto não foi raspado, o app não recebe o conteúdo
        c = {**c, "titulo": "Cupom surpresa", "descricao": None, "percentual": None, "teto_reais": None,
             "codigo": None, "assinatura": None, "conteudo_oculto": True}
    return c


def listar(con, cliente_id) -> list:
    expirar(con, cliente_id)
    ids = consultar(con, """SELECT id FROM cupons WHERE cliente_id=%s
                             ORDER BY FIELD(status,'oculto','revelado','usado','expirado'), gerado_em DESC""",
                    (cliente_id,))
    return [obter(con, cliente_id, i["id"]) for i in ids]


def revelar(con, cliente_id, cupom_id) -> dict:
    executar(con, """UPDATE cupons SET status='revelado', revelado_em=%s
                      WHERE id=%s AND cliente_id=%s AND status='oculto'""", (relogio.agora(), cupom_id, cliente_id))
    return obter(con, cliente_id, cupom_id)


def validar(con, codigo: str, assinatura: str | None = None) -> dict:
    """MODO CAIXA: a loja confere se o cupom é verdadeiro e ainda vale."""
    c = consultar_um(con, "SELECT * FROM cupons WHERE codigo=%s", (codigo.strip().upper(),))
    if not c:
        return {"valido": False, "motivo": "Código inexistente"}
    esperado = assinar(c["codigo"], c["cliente_id"], c["valido_ate"])
    if not hmac.compare_digest(esperado, c["assinatura"]) or (assinatura and assinatura != c["assinatura"]):
        return {"valido": False, "motivo": "Assinatura não confere: cupom adulterado"}
    if c["status"] == "usado":
        return {"valido": False, "motivo": f"Cupom já usado em {c['usado_em']:%d/%m/%Y}"}
    if c["status"] == "oculto":
        return {"valido": False, "motivo": "Cupom ainda não revelado pelo cliente"}
    if c["valido_ate"] < relogio.agora() or c["status"] == "expirado":
        return {"valido": False, "motivo": "Cupom vencido"}
    return {"valido": True, "motivo": "Cupom autêntico", "titulo": c["titulo"],
            "valido_ate": c["valido_ate"], "assinatura_inicio": c["assinatura"][:12]}


def usar(con, codigo: str) -> dict:
    r = validar(con, codigo)
    if r["valido"]:
        executar(con, "UPDATE cupons SET status='usado', usado_em=%s WHERE codigo=%s",
                 (relogio.agora(), codigo.strip().upper()))
        r["motivo"] = "Cupom aplicado no caixa"
    return r
