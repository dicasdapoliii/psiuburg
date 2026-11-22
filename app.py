# -*- coding: utf-8 -*-
import os
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, render_template_string, request, jsonify

app = Flask(__name__)

# ==========================================
# 1. CONFIGURAÇÕES DA LANCHONETE (EDITE AQUI)
# ==========================================
NOME_LOJA = "PSIU! BURG"
WHATSAPP_LOJA = "5565999999999"  # Coloque 55 + DDD + Numero (so numeros)
CHAVE_PIX = "psiuburg@pix.com.br"  # Coloque a chave Pix real aqui
FUSO_HORARIO = timezone(timedelta(hours=-4))  # Horario de MT (UTC-4)

DB_PATH = "psiuburg.db"

ADICIONAIS_PADRAO = [
    {"nome": "Bacon Crocante", "preco": 4.00},
    {"nome": "Cheddar Cremoso", "preco": 3.50},
    {"nome": "Hambúrguer Extra 150g", "preco": 8.00},
    {"nome": "Ovo na Chapa", "preco": 2.50},
    {"nome": "Molho Psiu Especial", "preco": 2.00},
]

# ==========================================
# 2. BANCO DE DADOS (SQLITE)
# ==========================================
def conectar_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = conectar_db()
    cur = conn.cursor()

    # Tabela de Produtos
    cur.execute("""
        CREATE TABLE IF NOT EXISTS produtos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            categoria TEXT NOT NULL,
            descricao TEXT,
            preco REAL NOT NULL,
            ativo INTEGER DEFAULT 1
        )
    """)

    # Tabela de Taxas por Bairro / KM
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bairros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            taxa REAL NOT NULL
        )
    """)

    # Tabela de Pedidos
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pedidos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data_hora TEXT NOT NULL,
            cliente_nome TEXT NOT NULL,
            cliente_whatsapp TEXT NOT NULL,
            tipo_entrega TEXT NOT NULL,
            bairro TEXT,
            endereco TEXT,
            forma_pagamento TEXT NOT NULL,
            troco_para TEXT,
            itens_json TEXT NOT NULL,
            subtotal REAL NOT NULL,
            taxa_entrega REAL NOT NULL,
            total REAL NOT NULL,
            status TEXT DEFAULT 'Recebido'
        )
    """)

    # Popula cardápio fictício inicial se estiver vazio
    cur.execute("SELECT COUNT(*) FROM produtos")
    if cur.fetchone()[0] == 0:
        produtos_iniciais = [
            ("Psiu! Clássico", "Burgers", "Pão brioche, blend bovino 150g, queijo prato, alface, tomate e molho especial.", 24.90),
            ("Psiu! Bacon Duplo", "Burgers", "Pão brioche, 2 blends 150g, duplo cheddar cremoso, bacon crocante e cebola caramelizada.", 34.90),
            ("Psiu! Rei da Chapa", "Burgers", "Pão australiano, blend 180g, queijo coalho grelhado, bacon, rúcula e barbecue artesanal.", 36.90),
            ("Combo Psiu! Casal", "Combos", "2 Psiu! Clássicos + 1 Batata Frita Grande com Cheddar e Bacon + 1 Refrigerante 1L.", 69.90),
            ("Combo Individual", "Combos", "1 Psiu! Bacon Duplo + Batata Frita Média + Refrigerante Lata 350ml.", 46.90),
            ("Batata Psiu! Suprema", "Porções", "400g de batata crocante coberta com cheddar cremoso e farofa de bacon.", 26.00),
            ("Anéis de Cebola (12 un)", "Porções", "Cebolas empanadas super crocantes com molho barbecue.", 19.90),
            ("Coca-Cola Lata 350ml", "Bebidas", "Bem gelada.", 6.50),
            ("Guaraná Antarctica 1L", "Bebidas", "Garrafa 1 Litro gelada.", 11.00),
            ("Suco Natural Laranja 500ml", "Bebidas", "Feito na hora.", 10.00),
        ]
        cur.executemany(
            "INSERT INTO produtos (nome, categoria, descricao, preco) VALUES (?, ?, ?, ?)",
            produtos_iniciais
        )

    # Popula taxas iniciais por Bairro / KM se estiver vazio
    cur.execute("SELECT COUNT(*) FROM bairros")
    if cur.fetchone()[0] == 0:
        bairros_iniciais = [
            ("Até 2 km (Região Central)", 5.00),
            ("De 2 km a 5 km (Bairros Próximos)", 8.00),
            ("De 5 km a 8 km (Bairros Médios)", 12.00),
            ("De 8 km a 12 km (Bairros Afastados)", 16.00),
        ]
        cur.executemany(
            "INSERT INTO bairros (nome, taxa) VALUES (?, ?)",
            bairros_iniciais
        )

    conn.commit()
    conn.close()


init_db()

# ==========================================
# 3. ROTAS DE PÁGINAS (CLIENTE E PAINEL)
# ==========================================
@app.route("/")
def pagina_cliente():
    return render_template("index.html", nome_loja=NOME_LOJA)


@app.route("/painel")
def pagina_admin():
    return render_template("admin.html", nome_loja=NOME_LOJA)


# ==========================================
# 4. API DO CARDÁPIO E PEDIDOS
# ==========================================
@app.route("/api/dados")
def api_dados():
    conn = conectar_db()
    produtos = [dict(r) for r in conn.execute("SELECT * FROM produtos WHERE ativo = 1 ORDER BY categoria, nome")]
    bairros = [dict(r) for r in conn.execute("SELECT * FROM bairros ORDER BY taxa")]
    conn.close()
    return jsonify({
        "loja": NOME_LOJA,
        "whatsapp": WHATSAPP_LOJA,
        "chave_pix": CHAVE_PIX,
        "produtos": produtos,
        "bairros": bairros,
        "adicionais": ADICIONAIS_PADRAO
    })


@app.route("/api/pedidos", methods=["POST"])
def criar_pedido():
    dados = request.json
    agora = datetime.now(FUSO_HORARIO).strftime("%d/%m/%Y %H:%M")

    conn = conectar_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO pedidos (
            data_hora, cliente_nome, cliente_whatsapp, tipo_entrega,
            bairro, endereco, forma_pagamento, troco_para,
            itens_json, subtotal, taxa_entrega, total, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Recebido')
    """, (
        agora,
        dados.get("cliente_nome", "").strip(),
        dados.get("cliente_whatsapp", "").strip(),
        dados.get("tipo_entrega", "Entrega"),
        dados.get("bairro", ""),
        dados.get("endereco", ""),
        dados.get("forma_pagamento", "Pix"),
        dados.get("troco_para", ""),
        json.dumps(dados.get("itens", []), ensure_ascii=False),
        float(dados.get("subtotal", 0)),
        float(dados.get("taxa_entrega", 0)),
        float(dados.get("total", 0))
    ))
    pedido_id = cur.lastrowid
    conn.commit()
    conn.close()
    return jsonify({"sucesso": True, "pedido_id": pedido_id})


@app.route("/api/pedidos/<int:pedido_id>")
def consultar_pedido(pedido_id):
    conn = conectar_db()
    row = conn.execute("SELECT * FROM pedidos WHERE id = ?", (pedido_id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({"erro": "Pedido não encontrado"}), 404
    p = dict(row)
    p["itens"] = json.loads(p["itens_json"])
    return jsonify(p)


# ==========================================
# 5. API DO PAINEL DA COZINHA / ADMIN
# ==========================================
@app.route("/api/admin/pedidos")
def listar_pedidos_admin():
    conn = conectar_db()
    rows = conn.execute("SELECT * FROM pedidos ORDER BY id DESC LIMIT 50").fetchall()
    conn.close()
    pedidos = []
    for r in rows:
        p = dict(r)
        p["itens"] = json.loads(p["itens_json"])
        pedidos.append(p)
    return jsonify(pedidos)


@app.route("/api/admin/pedidos/<int:pedido_id>/status", methods=["POST"])
def atualizar_status(pedido_id):
    novo_status = request.json.get("status", "Recebido")
    conn = conectar_db()
    conn.execute("UPDATE pedidos SET status = ? WHERE id = ?", (novo_status, pedido_id))
    conn.commit()
    conn.close()
    return jsonify({"sucesso": True})


@app.route("/api/admin/produtos", methods=["GET", "POST"])
def gerenciar_produtos():
    conn = conectar_db()
    if request.method == "POST":
        d = request.json
        conn.execute(
            "INSERT INTO produtos (nome, categoria, descricao, preco, ativo) VALUES (?, ?, ?, ?, 1)",
            (d["nome"], d["categoria"], d.get("descricao", ""), float(d["preco"]))
        )
        conn.commit()
        conn.close()
        return jsonify({"sucesso": True})

    produtos = [dict(r) for r in conn.execute("SELECT * FROM produtos ORDER BY categoria, nome")]
    bairros = [dict(r) for r in conn.execute("SELECT * FROM bairros ORDER BY taxa")]
    conn.close()
    return jsonify({"produtos": produtos, "bairros": bairros})


@app.route("/api/admin/produtos/<int:prod_id>/toggle", methods=["POST"])
def alternar_produto(prod_id):
    conn = conectar_db()
    conn.execute("UPDATE produtos SET ativo = CASE WHEN ativo = 1 THEN 0 ELSE 1 END WHERE id = ?", (prod_id,))
    conn.commit()
    conn.close()
    return jsonify({"sucesso": True})


@app.route("/api/admin/produtos/<int:prod_id>", methods=["DELETE"])
def excluir_produto(prod_id):
    conn = conectar_db()
    conn.execute("DELETE FROM produtos WHERE id = ?", (prod_id,))
    conn.commit()
    conn.close()
    return jsonify({"sucesso": True})


@app.route("/api/admin/bairros", methods=["POST"])
def adicionar_bairro():
    d = request.json
    conn = conectar_db()
    conn.execute("INSERT INTO bairros (nome, taxa) VALUES (?, ?)", (d["nome"], float(d["taxa"])))
    conn.commit()
    conn.close()
    return jsonify({"sucesso": True})


@app.route("/api/admin/bairros/<int:bairro_id>", methods=["DELETE"])
def excluir_bairro(bairro_id):
    conn = conectar_db()
    conn.execute("DELETE FROM bairros WHERE id = ?", (bairro_id,))
    conn.commit()
    conn.close()
    return jsonify({"sucesso": True})


# ==========================================
# 6. COMANDA FORMATADA PARA IMPRESSORA 80MM
# ==========================================
TEMPLATE_RECIBO_80MM = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>Pedido #{{ p.id }}</title>
    <style>
        @page { size: 80mm auto; margin: 0; }
        body {
            font-family: 'Courier New', Courier, monospace;
            width: 72mm;
            margin: 0 auto;
            padding: 4mm 2mm;
            color: #000;
            font-size: 13px;
            line-height: 1.3;
        }
        .centro { text-align: center; }
        .negrito { font-weight: bold; }
        .grande { font-size: 18px; }
        .linha { border-top: 1px dashed #000; margin: 6px 0; }
        .item { margin-bottom: 6px; }
        .sub { font-size: 12px; padding-left: 8px; }
        .total-box { font-size: 16px; font-weight: bold; margin-top: 4px; }
        .rodape { margin-top: 12px; text-align: center; font-size: 11px; }
    </style>
</head>
<body>
    <div class="centro negrito grande">{{ loja }}</div>
    <div class="centro">COMANDA DE COZINHA / DELIVERY</div>
    <div class="linha"></div>

    <div class="negrito grande centro">PEDIDO #{{ p.id }}</div>
    <div class="centro">{{ p.data_hora }}</div>
    <div class="linha"></div>

    <div><span class="negrito">CLIENTE:</span> {{ p.cliente_nome }}</div>
    <div><span class="negrito">WHATS:</span> {{ p.cliente_whatsapp }}</div>
    <div><span class="negrito">TIPO:</span> {{ p.tipo_entrega | upper }}</div>
    {% if p.tipo_entrega == 'Entrega' %}
    <div><span class="negrito">BAIRRO/KM:</span> {{ p.bairro }}</div>
    <div><span class="negrito">ENDEREÇO:</span> {{ p.endereco }}</div>
    {% else %}
    <div class="negrito">*** RETIRADA NO BALCÃO ***</div>
    {% endif %}

    <div class="linha"></div>
    <div class="negrito">ITENS DO PEDIDO:</div>
    <br>
    {% for it in p.itens %}
    <div class="item">
        <div class="negrito">{{ it.qtd }}x {{ it.nome }} - R$ {{ "%.2f"|format(it.total_item) }}</div>
        {% if it.adicionais %}
            {% for ad in it.adicionais %}
            <div class="sub">+ {{ ad.nome }} (R$ {{ "%.2f"|format(ad.preco) }})</div>
            {% endfor %}
        {% endif %}
        {% if it.obs %}
        <div class="sub negrito">OBS: {{ it.obs }}</div>
        {% endif %}
    </div>
    {% endfor %}

    <div class="linha"></div>
    <div>Subtotal: R$ {{ "%.2f"|format(p.subtotal) }}</div>
    <div>Taxa Entrega: R$ {{ "%.2f"|format(p.taxa_entrega) }}</div>
    <div class="total-box">TOTAL: R$ {{ "%.2f"|format(p.total) }}</div>

    <div class="linha"></div>
    <div><span class="negrito">PAGAMENTO:</span> {{ p.forma_pagamento }}</div>
    {% if p.troco_para %}
    <div class="negrito">TROCO PARA: R$ {{ p.troco_para }}</div>
    {% endif %}

    <div class="rodape">Obrigado pela preferência!<br>{{ loja }}</div>
    <br><br>
    <script>
        window.onload = function() {
            window.print();
            setTimeout(function() { window.close(); }, 600);
        };
    </script>
</body>
</html>
"""

@app.route("/imprimir/<int:pedido_id>")
def imprimir_pedido(pedido_id):
    conn = conectar_db()
    row = conn.execute("SELECT * FROM pedidos WHERE id = ?", (pedido_id,)).fetchone()
    conn.close()
    if not row:
        return "Pedido não encontrado", 404
    p = dict(row)
    p["itens"] = json.loads(p["itens_json"])
    return render_template_string(TEMPLATE_RECIBO_80MM, p=p, loja=NOME_LOJA)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
