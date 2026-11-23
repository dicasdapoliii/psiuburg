# -*- coding: utf-8 -*-
import os
import json
import math
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, render_template_string, request, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

# ==========================================
# 1. CONFIGURAÇÕES DA LANCHONETE
# ==========================================
NOME_LOJA = "PSIU! BURG"
WHATSAPP_LOJA = "5566981413953"
CHAVE_PIX = "psiuburg@pix.com.br"
ENDERECO_LOJA = "Avenida Guarapuava, 1735 - Jardim Rondônia, Rondonópolis - MT"
INSTAGRAM_LOJA = "https://www.instagram.com/psiuburg?knvt=aWxnNmx1b3F1MWV3"
FUSO_HORARIO = timezone(timedelta(hours=-4))  # Horario de MT (UTC-4)

LAT_LOJA = -16.4708
LNG_LOJA = -54.6356
TAXA_PADRAO_SE_NAO_LOCALIZAR = 8.00

WHATSAPP_API_URL = os.environ.get("WHATSAPP_API_URL", "").strip()

# Banco de Dados Permanente (PostgreSQL no Neon)
db_url = os.environ.get("DATABASE_URL", "sqlite:///psiuburg.db")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

ADICIONAIS_PADRAO = [
    {"nome": "Bacon Crocante", "preco": 4.00},
    {"nome": "Cheddar Cremoso", "preco": 3.50},
    {"nome": "Hambúrguer Extra 150g", "preco": 8.00},
    {"nome": "Ovo na Chapa", "preco": 2.50},
    {"nome": "Molho Psiu Especial", "preco": 2.00},
]

CATEGORIAS_CUSTO_PADRAO = [
    "Ingredientes",
    "Bebidas (Estoque)",
    "Embalagens",
    "Gás / Energia / Água",
    "Entregador / Frete",
    "Outros"
]

# ==========================================
# 2. MODELOS DO BANCO DE DADOS
# ==========================================
class Configuracao(db.Model):
    __tablename__ = "configuracoes"
    chave = db.Column(db.String(80), primary_key=True)
    valor = db.Column(db.Text, default="")


class Expediente(db.Model):
    __tablename__ = "expedientes"
    id = db.Column(db.Integer, primary_key=True)
    mes_ano = db.Column(db.String(10), nullable=False)
    data = db.Column(db.String(20), nullable=False)
    inicio_hora = db.Column(db.String(10), nullable=False)
    fim_hora = db.Column(db.String(10), default="")
    inicio_ts = db.Column(db.Float, nullable=False)
    fim_ts = db.Column(db.Float, nullable=True)
    duracao_minutos = db.Column(db.Integer, default=0)

    def to_dict(self):
        return {
            "id": self.id, "mes_ano": self.mes_ano, "data": self.data,
            "inicio_hora": self.inicio_hora, "fim_hora": self.fim_hora or "",
            "duracao_minutos": self.duracao_minutos or 0
        }


class Custo(db.Model):
    __tablename__ = "custos"
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.String(20), nullable=False)
    mes_ano = db.Column(db.String(10), nullable=False)
    descricao = db.Column(db.String(200), nullable=False)
    categoria = db.Column(db.String(80), default="Ingredientes")
    valor = db.Column(db.Float, nullable=False)

    def to_dict(self):
        return {
            "id": self.id, "data": self.data, "mes_ano": self.mes_ano,
            "descricao": self.descricao, "categoria": self.categoria or "Ingredientes",
            "valor": self.valor
        }


class Produto(db.Model):
    __tablename__ = "produtos"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(150), nullable=False)
    categoria = db.Column(db.String(80), nullable=False)
    descricao = db.Column(db.Text, default="")
    preco = db.Column(db.Float, nullable=False)
    imagem = db.Column(db.Text, default="")
    ativo = db.Column(db.Integer, default=1)

    def to_dict(self):
        return {
            "id": self.id, "nome": self.nome, "categoria": self.categoria,
            "descricao": self.descricao, "preco": self.preco,
            "imagem": self.imagem or "", "ativo": self.ativo
        }


class FaixaEntrega(db.Model):
    __tablename__ = "faixas_entrega"
    id = db.Column(db.Integer, primary_key=True)
    ate_km = db.Column(db.Float, nullable=False)
    taxa = db.Column(db.Float, nullable=False)

    def to_dict(self):
        return {"id": self.id, "ate_km": self.ate_km, "taxa": self.taxa}


class Entregador(db.Model):
    __tablename__ = "entregadores"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    whatsapp = db.Column(db.String(30), nullable=False)
    padrao = db.Column(db.Integer, default=0)

    def to_dict(self):
        return {
            "id": self.id, "nome": self.nome,
            "whatsapp": self.whatsapp, "padrao": self.padrao
        }


class Cliente(db.Model):
    __tablename__ = "clientes"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(150), nullable=False)
    cpf = db.Column(db.String(20), default="")
    senha = db.Column(db.String(100), default="")
    whatsapp = db.Column(db.String(30), unique=True, nullable=False)
    cep = db.Column(db.String(20), default="")
    rua = db.Column(db.String(200), default="")
    numero = db.Column(db.String(40), default="")
    bairro = db.Column(db.String(150), default="")
    complemento = db.Column(db.String(200), default="")
    endereco = db.Column(db.String(255), default="")
    enderecos_json = db.Column(db.Text, default="[]")
    lat = db.Column(db.Float, nullable=True)
    lng = db.Column(db.Float, nullable=True)
    criado_em = db.Column(db.String(30), default="")

    def get_enderecos(self):
        try:
            lista = json.loads(self.enderecos_json or "[]")
        except Exception:
            lista = []
        if not lista and self.rua:
            lista = [{
                "apelido": "Principal",
                "cep": self.cep or "", "rua": self.rua or "", "numero": self.numero or "",
                "bairro": self.bairro or "", "complemento": self.complemento or "",
                "endereco": self.endereco or f"{self.rua}, {self.numero} - {self.bairro}",
                "lat": self.lat, "lng": self.lng
            }]
        return lista

    def to_dict(self):
        return {
            "id": self.id, "nome": self.nome, "cpf": self.cpf or "",
            "whatsapp": self.whatsapp,
            "cep": self.cep or "", "rua": self.rua or "", "numero": self.numero or "",
            "bairro": self.bairro or "", "complemento": self.complemento or "",
            "endereco": self.endereco or "", "enderecos": self.get_enderecos(),
            "lat": self.lat, "lng": self.lng
        }


class Pedido(db.Model):
    __tablename__ = "pedidos"
    id = db.Column(db.Integer, primary_key=True)
    data_hora = db.Column(db.String(30), nullable=False)
    mes_ano = db.Column(db.String(10), nullable=False)
    cliente_nome = db.Column(db.String(150), nullable=False)
    cliente_whatsapp = db.Column(db.String(30), nullable=False)
    tipo_entrega = db.Column(db.String(30), nullable=False)
    bairro = db.Column(db.String(150), default="")
    endereco = db.Column(db.String(255), default="")
    link_maps = db.Column(db.String(350), default="")
    distancia_km = db.Column(db.Float, default=0.0)
    forma_pagamento = db.Column(db.String(80), nullable=False)
    troco_para = db.Column(db.String(40), default="")
    itens_json = db.Column(db.Text, nullable=False)
    subtotal = db.Column(db.Float, nullable=False)
    taxa_entrega = db.Column(db.Float, nullable=False)
    total = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(40), default="Recebido")
    status_pagamento = db.Column(db.String(40), default="Pagar na Entrega")
    link_pagamento = db.Column(db.String(300), default="")

    def to_dict(self):
        return {
            "id": self.id, "data_hora": self.data_hora, "mes_ano": self.mes_ano,
            "cliente_nome": self.cliente_nome, "cliente_whatsapp": self.cliente_whatsapp,
            "tipo_entrega": self.tipo_entrega, "bairro": self.bairro, "endereco": self.endereco,
            "link_maps": self.link_maps or "", "distancia_km": self.distancia_km or 0.0,
            "forma_pagamento": self.forma_pagamento, "troco_para": self.troco_para,
            "itens": json.loads(self.itens_json),
            "subtotal": self.subtotal, "taxa_entrega": self.taxa_entrega, "total": self.total,
            "status": self.status, "status_pagamento": self.status_pagamento,
            "link_pagamento": self.link_pagamento
        }


def get_config(chave, padrao=""):
    cfg = Configuracao.query.get(chave)
    return cfg.valor if cfg else padrao


def set_config(chave, valor):
    cfg = Configuracao.query.get(chave)
    if cfg:
        cfg.valor = str(valor)
    else:
        db.session.add(Configuracao(chave=chave, valor=str(valor)))
    db.session.commit()


def get_categorias_custo():
    raw = get_config("categorias_custo", "")
    if raw:
        try:
            lista = json.loads(raw)
            if isinstance(lista, list) and lista:
                return lista
        except Exception:
            pass
    return list(CATEGORIAS_CUSTO_PADRAO)


def get_loja_aberta():
    return get_config("loja_aberta", "0") == "1"


def set_loja_aberta(aberta):
    set_config("loja_aberta", "1" if aberta else "0")


def get_senha_admin():
    return get_config("senha_admin", "1234")


def limpar_numeros(valor):
    return "".join(c for c in str(valor or "") if c.isdigit())


def enviar_whatsapp_automatico(telefone, mensagem):
    if not WHATSAPP_API_URL:
        return False, "WHATSAPP_API_URL não configurada no Render."
    if not telefone:
        return False, "Telefone do destinatário vazio."

    num = limpar_numeros(telefone)
    if len(num) < 10:
        return False, f"Telefone inválido (sem DDD): {num}"
    if not num.startswith("55"):
        num = "55" + num

    if len(num) == 13 and num.startswith("55") and int(num[2:4]) > 28 and num[4] == "9":
        num_sem_9 = num[:4] + num[5:]
    else:
        num_sem_9 = num

    try:
        payload = json.dumps({"chatId": f"{num_sem_9}@c.us", "message": mensagem}).encode("utf-8")
        req = urllib.request.Request(
            WHATSAPP_API_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            corpo = resp.read().decode("utf-8", errors="ignore")
            print(f"[GREEN-API OK] Para {num_sem_9}: {resp.status} - {corpo}", flush=True)
            return True, "Enviado com sucesso"
    except urllib.error.HTTPError as e:
        corpo_erro = e.read().decode("utf-8", errors="ignore")
        print(f"[GREEN-API ERRO HTTP {e.code}] Para {num_sem_9}: {corpo_erro}", flush=True)
        return False, f"Green-API retornou erro {e.code}: {corpo_erro[:120]}"
    except Exception as e:
        print(f"[GREEN-API EXCECAO] Para {num_sem_9}: {e}", flush=True)
        return False, str(e)


def montar_mensagem_entregador(p):
    total_fmt = f"R$ {p.total:.2f}".replace(".", ",")
    if p.status_pagamento == "Pago":
        aviso_pag = "✅ *JÁ PAGO ONLINE (NÃO COBRAR)*"
    else:
        troco = f" — Troco p/ R$ {p.troco_para}" if p.troco_para else ""
        aviso_pag = f"💰 *COBRAR NA ENTREGA:* {total_fmt} ({p.forma_pagamento}){troco}"

    link_mapa = p.link_maps or (
        "https://www.google.com/maps/search/?api=1&query="
        + urllib.parse.quote(f"{p.endereco}, Rondonópolis - MT")
    )
    return (
        f"🛵 *ENTREGA — PEDIDO #{p.id}*\n\n"
        f"👤 *Cliente:* {p.cliente_nome}\n"
        f"📞 *Telefone:* {p.cliente_whatsapp}\n"
        f"🏠 *Endereço:* {p.endereco}\n\n"
        f"📍 *Localização no Mapa:*\n{link_mapa}\n\n"
        f"{aviso_pag}"
    )


def calcular_distancia_km(lat1, lng1, lat2, lng2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c * 1.25, 2)


def geocodificar_endereco(rua, numero, bairro):
    try:
        consulta = f"{rua}, {numero}, {bairro}, Rondonópolis, MT, Brasil"
        url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({
            "q": consulta, "format": "json", "limit": 1
        })
        req = urllib.request.Request(url, headers={"User-Agent": "PsiuBurgDelivery/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            dados = json.loads(resp.read().decode("utf-8"))
            if dados:
                return float(dados[0]["lat"]), float(dados[0]["lon"])
    except Exception:
        pass
    return None, None


def obter_taxa_por_km(distancia_km):
    faixas = FaixaEntrega.query.order_by(FaixaEntrega.ate_km.asc()).all()
    if not faixas:
        return TAXA_PADRAO_SE_NAO_LOCALIZAR
    for f in faixas:
        if distancia_km <= f.ate_km:
            return f.taxa
    return faixas[-1].taxa


def init_db():
    with app.app_context():
        db.create_all()

        colunas_novas = [
            "ALTER TABLE produtos ADD COLUMN imagem TEXT DEFAULT ''",
            "ALTER TABLE clientes ADD COLUMN cpf VARCHAR(20) DEFAULT ''",
            "ALTER TABLE clientes ADD COLUMN senha VARCHAR(100) DEFAULT ''",
            "ALTER TABLE clientes ADD COLUMN enderecos_json TEXT DEFAULT '[]'",
            "ALTER TABLE clientes ADD COLUMN cep VARCHAR(20) DEFAULT ''",
            "ALTER TABLE clientes ADD COLUMN rua VARCHAR(200) DEFAULT ''",
            "ALTER TABLE clientes ADD COLUMN numero VARCHAR(40) DEFAULT ''",
            "ALTER TABLE clientes ADD COLUMN complemento VARCHAR(200) DEFAULT ''",
            "ALTER TABLE clientes ADD COLUMN lat DOUBLE PRECISION",
            "ALTER TABLE clientes ADD COLUMN lng DOUBLE PRECISION",
            "ALTER TABLE pedidos ADD COLUMN link_maps VARCHAR(350) DEFAULT ''",
            "ALTER TABLE pedidos ADD COLUMN distancia_km DOUBLE PRECISION DEFAULT 0"
        ]
        for sql in colunas_novas:
            try:
                db.session.execute(db.text(sql))
                db.session.commit()
            except Exception:
                db.session.rollback()

        if not Configuracao.query.get("loja_aberta"):
            db.session.add(Configuracao(chave="loja_aberta", valor="0"))
        if not Configuracao.query.get("senha_admin"):
            db.session.add(Configuracao(chave="senha_admin", valor="1234"))

        if Produto.query.count() == 0:
            produtos_iniciais = [
                Produto(nome="Psiu! Clássico", categoria="Burgers", descricao="Pão brioche, blend bovino 150g, queijo prato, alface, tomate e molho especial.", preco=24.90),
                Produto(nome="Psiu! Bacon Duplo", categoria="Burgers", descricao="Pão brioche, 2 blends 150g, duplo cheddar cremoso, bacon crocante e cebola caramelizada.", preco=34.90),
                Produto(nome="Psiu! Rei da Chapa", categoria="Burgers", descricao="Pão australiano, blend 180g, queijo coalho grelhado, bacon, rúcula e barbecue artesanal.", preco=36.90),
                Produto(nome="Combo Psiu! Casal", categoria="Combos", descricao="2 Psiu! Clássicos + 1 Batata Frita Grande com Cheddar e Bacon + 1 Refrigerante 1L.", preco=69.90),
                Produto(nome="Combo Individual", categoria="Combos", descricao="1 Psiu! Bacon Duplo + Batata Frita Média + Refrigerante Lata 350ml.", preco=46.90),
                Produto(nome="Batata Psiu! Suprema", categoria="Porções", descricao="400g de batata crocante coberta com cheddar cremoso e farofa de bacon.", preco=26.00),
                Produto(nome="Anéis de Cebola (12 un)", categoria="Porções", descricao="Cebolas empanadas super crocantes com molho barbecue.", preco=19.90),
                Produto(nome="Coca-Cola Lata 350ml", categoria="Bebidas", descricao="Bem gelada.", preco=6.50),
                Produto(nome="Guaraná Antarctica 1L", categoria="Bebidas", descricao="Garrafa 1 Litro gelada.", preco=11.00),
                Produto(nome="Suco Natural Laranja 500ml", categoria="Bebidas", descricao="Feito na hora.", preco=10.00),
            ]
            db.session.add_all(produtos_iniciais)

        if FaixaEntrega.query.count() == 0:
            faixas_iniciais = [
                FaixaEntrega(ate_km=2.0, taxa=5.00),
                FaixaEntrega(ate_km=5.0, taxa=8.00),
                FaixaEntrega(ate_km=8.0, taxa=12.00),
                FaixaEntrega(ate_km=15.0, taxa=16.00),
            ]
            db.session.add_all(faixas_iniciais)

        db.session.commit()


init_db()

# ==========================================
# 3. ROTAS DE PÁGINAS E LOGO
# ==========================================
@app.route("/")
def pagina_cliente():
    return render_template("index.html", nome_loja=NOME_LOJA)


@app.route("/painel")
def pagina_admin():
    return render_template("admin.html", nome_loja=NOME_LOJA)


@app.route("/logo")
def servir_logo():
    for nome in ["logo.png", "logo.jpg", "logo.jpeg", "logo.png.png", "logo.jpg.jpeg"]:
        if os.path.exists(nome):
            return send_from_directory(".", nome)
    return "", 404


# ==========================================
# 4. API DO CARDÁPIO, FRETE, CLIENTES E PEDIDOS
# ==========================================
@app.route("/api/dados")
def api_dados():
    produtos = [p.to_dict() for p in Produto.query.filter_by(ativo=1).order_by(Produto.categoria, Produto.nome).all()]
    return jsonify({
        "loja": NOME_LOJA,
        "loja_aberta": get_loja_aberta(),
        "whatsapp": WHATSAPP_LOJA,
        "chave_pix": CHAVE_PIX,
        "endereco_loja": ENDERECO_LOJA,
        "instagram": INSTAGRAM_LOJA,
        "produtos": produtos,
        "adicionais": ADICIONAIS_PADRAO
    })


@app.route("/api/calcular-frete", methods=["POST"])
def calcular_frete():
    d = request.json or {}
    lat = d.get("lat")
    lng = d.get("lng")
    rua = d.get("rua", "").strip()
    numero = d.get("numero", "").strip()
    bairro = d.get("bairro", "").strip()

    if lat is not None and lng is not None:
        lat, lng = float(lat), float(lng)
    elif rua:
        lat, lng = geocodificar_endereco(rua, numero, bairro)

    if lat is not None and lng is not None:
        dist = calcular_distancia_km(LAT_LOJA, LNG_LOJA, lat, lng)
        taxa = obter_taxa_por_km(dist)
        link_maps = f"https://www.google.com/maps?q={lat},{lng}"
        return jsonify({
            "sucesso": True, "distancia_km": dist, "taxa": taxa,
            "lat": lat, "lng": lng, "link_maps": link_maps
        })

    q = urllib.parse.quote(f"{rua}, {numero} - {bairro}, Rondonópolis - MT")
    return jsonify({
        "sucesso": True, "distancia_km": 0.0, "taxa": TAXA_PADRAO_SE_NAO_LOCALIZAR,
        "lat": None, "lng": None,
        "link_maps": f"https://www.google.com/maps/search/?api=1&query={q}"
    })


@app.route("/api/clientes/login", methods=["POST"])
def login_cliente():
    d = request.json or {}
    cpf_dig = limpar_numeros(d.get("cpf", ""))
    senha = str(d.get("senha", "")).strip()
    if not cpf_dig:
        return jsonify({"sucesso": False, "erro": "Informe o CPF."})

    cli = None
    for c in Cliente.query.all():
        if limpar_numeros(c.cpf) == cpf_dig:
            cli = c
            break

    if not cli:
        return jsonify({"sucesso": False, "nao_encontrado": True, "erro": "CPF não cadastrado."})

    if cli.senha and cli.senha != senha:
        return jsonify({"sucesso": False, "erro": "Senha incorreta."})
    if not cli.senha and senha:
        cli.senha = senha
        db.session.commit()

    pedidos = Pedido.query.filter_by(cliente_whatsapp=cli.whatsapp).order_by(Pedido.id.desc()).limit(10).all()
    return jsonify({"sucesso": True, "cliente": cli.to_dict(), "pedidos": [p.to_dict() for p in pedidos]})


@app.route("/api/clientes/buscar", methods=["POST"])
def buscar_cliente():
    fone = limpar_numeros((request.json or {}).get("whatsapp", ""))
    if not fone:
        return jsonify({"encontrado": False})
    cli = Cliente.query.filter_by(whatsapp=fone).first()
    if not cli:
        return jsonify({"encontrado": False})
    pedidos = Pedido.query.filter_by(cliente_whatsapp=fone).order_by(Pedido.id.desc()).limit(10).all()
    return jsonify({"encontrado": True, "cliente": cli.to_dict(), "pedidos": [p.to_dict() for p in pedidos]})


@app.route("/api/clientes/salvar", methods=["POST"])
def salvar_cliente():
    d = request.json or {}
    fone = limpar_numeros(d.get("whatsapp", ""))
    nome = d.get("nome", "").strip()
    cpf = d.get("cpf", "").strip()
    senha = str(d.get("senha", "")).strip()
    if not fone or not nome:
        return jsonify({"sucesso": False, "erro": "Informe nome e WhatsApp."}), 400

    rua = d.get("rua", "").strip()
    numero = d.get("numero", "").strip()
    bairro = d.get("bairro", "").strip()
    complemento = d.get("complemento", "").strip()
    cep = d.get("cep", "").strip()
    lat = d.get("lat")
    lng = d.get("lng")

    endereco_fmt = f"{rua}, {numero} - {bairro}" + (f" ({complemento})" if complemento else "")
    novo_end = {
        "apelido": d.get("apelido", "Principal"),
        "cep": cep, "rua": rua, "numero": numero, "bairro": bairro,
        "complemento": complemento, "endereco": endereco_fmt,
        "lat": float(lat) if lat is not None else None,
        "lng": float(lng) if lng is not None else None
    }

    cli = Cliente.query.filter_by(whatsapp=fone).first()
    agora = datetime.now(FUSO_HORARIO).strftime("%d/%m/%Y %H:%M")

    if cli:
        cli.nome = nome
        if cpf:
            cli.cpf = cpf
        if senha:
            cli.senha = senha
        cli.cep = cep
        cli.rua = rua
        cli.numero = numero
        cli.bairro = bairro
        cli.complemento = complemento
        cli.endereco = endereco_fmt
        if lat is not None and lng is not None:
            cli.lat = float(lat)
            cli.lng = float(lng)
        lista = cli.get_enderecos()
        if lista:
            lista[0] = novo_end
        else:
            lista = [novo_end]
        cli.enderecos_json = json.dumps(lista, ensure_ascii=False)
    else:
        cli = Cliente(
            nome=nome, cpf=cpf, senha=senha, whatsapp=fone, cep=cep, rua=rua, numero=numero,
            bairro=bairro, complemento=complemento, endereco=endereco_fmt,
            enderecos_json=json.dumps([novo_end], ensure_ascii=False),
            lat=float(lat) if lat is not None else None,
            lng=float(lng) if lng is not None else None,
            criado_em=agora
        )
        db.session.add(cli)

    db.session.commit()
    return jsonify({"sucesso": True, "cliente": cli.to_dict()})


@app.route("/api/clientes/adicionar-endereco", methods=["POST"])
def adicionar_endereco_cliente():
    d = request.json or {}
    fone = limpar_numeros(d.get("whatsapp", ""))
    cli = Cliente.query.filter_by(whatsapp=fone).first()
    if not cli:
        return jsonify({"sucesso": False, "erro": "Cliente não encontrado."}), 404

    rua = d.get("rua", "").strip()
    numero = d.get("numero", "").strip()
    bairro = d.get("bairro", "").strip()
    complemento = d.get("complemento", "").strip()
    cep = d.get("cep", "").strip()
    lat = d.get("lat")
    lng = d.get("lng")
    endereco_fmt = f"{rua}, {numero} - {bairro}" + (f" ({complemento})" if complemento else "")

    lista = cli.get_enderecos()
    lista.append({
        "apelido": d.get("apelido", f"Endereço {len(lista) + 1}"),
        "cep": cep, "rua": rua, "numero": numero, "bairro": bairro,
        "complemento": complemento, "endereco": endereco_fmt,
        "lat": float(lat) if lat is not None else None,
        "lng": float(lng) if lng is not None else None
    })
    cli.enderecos_json = json.dumps(lista, ensure_ascii=False)
    db.session.commit()
    return jsonify({"sucesso": True, "cliente": cli.to_dict()})


@app.route("/api/pedidos", methods=["POST"])
def criar_pedido():
    if not get_loja_aberta():
        return jsonify({"sucesso": False, "erro": "A PSIU! BURG está fechada para pedidos no momento."}), 400

    dados = request.json or {}
    agora_dt = datetime.now(FUSO_HORARIO)
    agora_str = agora_dt.strftime("%d/%m/%Y %H:%M")
    mes_ano = agora_dt.strftime("%Y-%m")

    fone = limpar_numeros(dados.get("cliente_whatsapp", ""))
    nome = dados.get("cliente_nome", "").strip()
    forma_pag = dados.get("forma_pagamento", "Pix")
    status_pag = "Aguardando Pagamento" if forma_pag in ["Pix", "Cartão Online (Link)"] else "Pagar na Entrega"

    novo = Pedido(
        data_hora=agora_str,
        mes_ano=mes_ano,
        cliente_nome=nome,
        cliente_whatsapp=fone,
        tipo_entrega=dados.get("tipo_entrega", "Entrega"),
        bairro=dados.get("bairro", ""),
        endereco=dados.get("endereco", ""),
        link_maps=dados.get("link_maps", ""),
        distancia_km=float(dados.get("distancia_km", 0)),
        forma_pagamento=forma_pag,
        troco_para=dados.get("troco_para", ""),
        itens_json=json.dumps(dados.get("itens", []), ensure_ascii=False),
        subtotal=float(dados.get("subtotal", 0)),
        taxa_entrega=float(dados.get("taxa_entrega", 0)),
        total=float(dados.get("total", 0)),
        status="Recebido",
        status_pagamento=status_pag,
        link_pagamento=""
    )
    db.session.add(novo)
    db.session.commit()
    return jsonify({"sucesso": True, "pedido_id": novo.id, "pedido": novo.to_dict()})


@app.route("/api/pedidos/<int:pedido_id>")
def consultar_pedido(pedido_id):
    p = Pedido.query.get(pedido_id)
    if not p:
        return jsonify({"erro": "Pedido não encontrado"}), 404
    return jsonify(p.to_dict())


# ==========================================
# 5. API DO PAINEL (LOGIN, CUSTOS, CATEGORIAS, EXPEDIENTE, BALANÇO)
# ==========================================
@app.route("/api/admin/login", methods=["POST"])
def login_admin():
    senha = str((request.json or {}).get("senha", "")).strip()
    if senha == get_senha_admin():
        return jsonify({"sucesso": True})
    return jsonify({"sucesso": False, "erro": "Senha incorreta!"}), 401


@app.route("/api/admin/alterar-senha", methods=["POST"])
def alterar_senha_admin():
    d = request.json or {}
    atual = str(d.get("senha_atual", "")).strip()
    nova = str(d.get("nova_senha", "")).strip()
    if atual != get_senha_admin():
        return jsonify({"sucesso": False, "erro": "Senha atual incorreta."}), 400
    if len(nova) < 4:
        return jsonify({"sucesso": False, "erro": "A nova senha precisa ter pelo menos 4 caracteres."}), 400
    set_config("senha_admin", nova)
    return jsonify({"sucesso": True})


@app.route("/api/admin/limpar-pedidos", methods=["POST"])
def limpar_todos_pedidos():
    Pedido.query.delete()
    db.session.commit()
    try:
        db.session.execute(db.text("ALTER SEQUENCE pedidos_id_seq RESTART WITH 1"))
        db.session.commit()
    except Exception:
        db.session.rollback()
    return jsonify({"sucesso": True})


@app.route("/api/admin/categorias-custo", methods=["GET", "POST"])
def gerenciar_categorias_custo():
    lista = get_categorias_custo()
    if request.method == "POST":
        nova = (request.json or {}).get("nome", "").strip()
        if not nova:
            return jsonify({"sucesso": False, "erro": "Informe o nome da categoria."}), 400
        if nova not in lista:
            lista.append(nova)
            set_config("categorias_custo", json.dumps(lista, ensure_ascii=False))
        return jsonify({"sucesso": True, "categorias": lista})
    return jsonify({"categorias": lista})


@app.route("/api/admin/custos", methods=["GET", "POST"])
def gerenciar_custos():
    if request.method == "POST":
        d = request.json or {}
        data_str = (d.get("data") or datetime.now(FUSO_HORARIO).strftime("%Y-%m-%d")).strip()
        mes_ano = data_str[:7]
        novo = Custo(
            data=data_str,
            mes_ano=mes_ano,
            descricao=d.get("descricao", "").strip(),
            categoria=d.get("categoria", "Ingredientes"),
            valor=float(d.get("valor", 0))
        )
        db.session.add(novo)
        db.session.commit()
        return jsonify({"sucesso": True, "custo": novo.to_dict()})

    mes = request.args.get("mes") or datetime.now(FUSO_HORARIO).strftime("%Y-%m")
    lista = Custo.query.filter_by(mes_ano=mes).order_by(Custo.data.desc(), Custo.id.desc()).all()
    total_mes = sum(c.valor for c in lista)
    por_categoria = {}
    for c in lista:
        cat = c.categoria or "Outros"
        por_categoria[cat] = por_categoria.get(cat, 0.0) + c.valor

    return jsonify({
        "mes": mes,
        "total_mes": total_mes,
        "por_categoria": por_categoria,
        "categorias": get_categorias_custo(),
        "custos": [c.to_dict() for c in lista]
    })


@app.route("/api/admin/custos/<int:custo_id>", methods=["PUT", "DELETE"])
def editar_ou_excluir_custo(custo_id):
    c = Custo.query.get_or_404(custo_id)
    if request.method == "PUT":
        d = request.json or {}
        data_str = (d.get("data") or c.data).strip()
        c.data = data_str
        c.mes_ano = data_str[:7]
        c.descricao = d.get("descricao", c.descricao).strip()
        c.categoria = d.get("categoria", c.categoria)
        c.valor = float(d.get("valor", c.valor))
        db.session.commit()
        return jsonify({"sucesso": True})

    db.session.delete(c)
    db.session.commit()
    return jsonify({"sucesso": True})


@app.route("/api/admin/loja-status", methods=["GET", "POST"])
def status_loja_admin():
    if request.method == "POST":
        aberta = bool((request.json or {}).get("aberta", True))
        set_loja_aberta(aberta)
        agora_dt = datetime.now(FUSO_HORARIO)
        agora_ts = agora_dt.timestamp()

        if aberta:
            exp_aberto = Expediente.query.filter_by(fim_hora="").order_by(Expediente.id.desc()).first()
            if not exp_aberto:
                exp_aberto = Expediente(
                    mes_ano=agora_dt.strftime("%Y-%m"),
                    data=agora_dt.strftime("%d/%m/%Y"),
                    inicio_hora=agora_dt.strftime("%H:%M"),
                    fim_hora="",
                    inicio_ts=agora_ts,
                    duracao_minutos=0
                )
                db.session.add(exp_aberto)
                db.session.commit()
            return jsonify({"sucesso": True, "loja_aberta": True, "expediente": exp_aberto.to_dict()})
        else:
            exp_aberto = Expediente.query.filter_by(fim_hora="").order_by(Expediente.id.desc()).first()
            if exp_aberto:
                exp_aberto.fim_hora = agora_dt.strftime("%H:%M")
                exp_aberto.fim_ts = agora_ts
                exp_aberto.duracao_minutos = max(1, int((agora_ts - exp_aberto.inicio_ts) // 60))
                db.session.commit()
            return jsonify({
                "sucesso": True,
                "loja_aberta": False,
                "expediente": exp_aberto.to_dict() if exp_aberto else None
            })

    ultimo_exp = Expediente.query.order_by(Expediente.id.desc()).first()
    return jsonify({
        "loja_aberta": get_loja_aberta(),
        "expediente": ultimo_exp.to_dict() if ultimo_exp else None
    })


@app.route("/api/admin/pedidos")
def listar_pedidos_admin():
    pedidos = Pedido.query.order_by(Pedido.id.desc()).limit(60).all()
    return jsonify([p.to_dict() for p in pedidos])


@app.route("/api/admin/pedidos/<int:pedido_id>/status", methods=["POST"])
def atualizar_status(pedido_id):
    p = Pedido.query.get_or_404(pedido_id)
    novo_status = (request.json or {}).get("status", "Recebido")
    p.status = novo_status
    db.session.commit()

    whats_ok, whats_msg = True, ""
    msgs = {
        "Aceito": f"Olá {p.cliente_nome}! 👍 *Seu pedido #{p.id} foi aceito* na {NOME_LOJA}!",
        "Em Preparo": f"Olá {p.cliente_nome}! 🔥 *Seu pedido #{p.id} está sendo preparado* com todo capricho na chapa! 🍔",
        "Saiu para Entrega": f"Olá {p.cliente_nome}! 🛵 *Seu pedido #{p.id} saiu para entrega!* Já já chega aí! 🍔🔥"
    }
    if novo_status in msgs:
        whats_ok, whats_msg = enviar_whatsapp_automatico(p.cliente_whatsapp, msgs[novo_status])

    ent_ok, ent_msg = False, ""
    if novo_status == "Aceito" and p.tipo_entrega == "Entrega":
        fixo = Entregador.query.filter_by(padrao=1).first()
        if fixo:
            ent_ok, ent_msg = enviar_whatsapp_automatico(fixo.whatsapp, montar_mensagem_entregador(p))

    return jsonify({
        "sucesso": True,
        "whats_ok": whats_ok,
        "whats_msg": whats_msg,
        "entregador_avisado_auto": ent_ok,
        "ent_msg": ent_msg
    })


@app.route("/api/admin/pedidos/<int:pedido_id>/enviar-entregador", methods=["POST"])
def enviar_pedido_entregador(pedido_id):
    p = Pedido.query.get_or_404(pedido_id)
    d = request.json or {}
    ent_id = d.get("entregador_id")
    msg = montar_mensagem_entregador(p)

    fone = ""
    if ent_id:
        ent = Entregador.query.get(int(ent_id))
        if ent:
            fone = limpar_numeros(ent.whatsapp)
            if not fone.startswith("55"):
                fone = "55" + fone

    enviado_auto, detalhe = False, ""
    if fone and WHATSAPP_API_URL:
        enviado_auto, detalhe = enviar_whatsapp_automatico(fone, msg)

    return jsonify({
        "sucesso": True,
        "enviado_auto": enviado_auto,
        "detalhe": detalhe,
        "whatsapp": fone,
        "mensagem": msg
    })


@app.route("/api/admin/pedidos/<int:pedido_id>/pagamento", methods=["POST"])
def atualizar_pagamento(pedido_id):
    p = Pedido.query.get_or_404(pedido_id)
    d = request.json or {}
    whats_ok, whats_msg = True, ""
    if "status_pagamento" in d:
        p.status_pagamento = d["status_pagamento"]
        if d["status_pagamento"] == "Pago":
            whats_ok, whats_msg = enviar_whatsapp_automatico(
                p.cliente_whatsapp,
                f"Olá {p.cliente_nome}! ✅ *Pagamento realizado com sucesso!* Recebemos a confirmação do seu pedido #{p.id} na {NOME_LOJA} 🍔"
            )
    if "link_pagamento" in d:
        p.link_pagamento = d["link_pagamento"].strip()
    db.session.commit()
    return jsonify({"sucesso": True, "whats_ok": whats_ok, "whats_msg": whats_msg})


@app.route("/api/admin/financeiro")
def relatorio_financeiro():
    mes_atual = datetime.now(FUSO_HORARIO).strftime("%Y-%m")
    mes_unico = request.args.get("mes")
    mes_inicio = request.args.get("mes_inicio") or mes_unico or mes_atual
    mes_fim = request.args.get("mes_fim") or mes_unico or mes_inicio

    if mes_inicio > mes_fim:
        mes_inicio, mes_fim = mes_fim, mes_inicio

    pedidos = (
        Pedido.query
        .filter(Pedido.mes_ano >= mes_inicio, Pedido.mes_ano <= mes_fim)
        .order_by(Pedido.id.desc())
        .all()
    )
    expedientes = (
        Expediente.query
        .filter(Expediente.mes_ano >= mes_inicio, Expediente.mes_ano <= mes_fim)
        .order_by(Expediente.id.desc())
        .all()
    )
    custos = (
        Custo.query
        .filter(Custo.mes_ano >= mes_inicio, Custo.mes_ano <= mes_fim)
        .order_by(Custo.data.desc(), Custo.id.desc())
        .all()
    )

    total_pago = qtd_pago = total_nao_pago = qtd_nao_pago = total_cancelado = qtd_cancelado = 0
    por_forma = {}
    por_mes = {}

    def garantir_mes(m):
        if m not in por_mes:
            por_mes[m] = {
                "mes": m, "pago": 0.0, "qtd_pago": 0,
                "nao_pago": 0.0, "cancelado": 0.0, "qtd_cancelado": 0,
                "custos": 0.0, "lucro": 0.0, "minutos": 0
            }

    for p in pedidos:
        garantir_mes(p.mes_ano)
        if p.status == "Cancelado":
            total_cancelado += p.total
            qtd_cancelado += 1
            por_mes[p.mes_ano]["cancelado"] += p.total
            por_mes[p.mes_ano]["qtd_cancelado"] += 1
        elif p.status_pagamento == "Pago":
            total_pago += p.total
            qtd_pago += 1
            por_forma[p.forma_pagamento] = por_forma.get(p.forma_pagamento, 0.0) + p.total
            por_mes[p.mes_ano]["pago"] += p.total
            por_mes[p.mes_ano]["qtd_pago"] += 1
        else:
            total_nao_pago += p.total
            qtd_nao_pago += 1
            por_mes[p.mes_ano]["nao_pago"] += p.total

    for c in custos:
        garantir_mes(c.mes_ano)
        por_mes[c.mes_ano]["custos"] += c.valor

    for e in expedientes:
        garantir_mes(e.mes_ano)
        por_mes[e.mes_ano]["minutos"] += (e.duracao_minutos or 0)

    for m in por_mes.values():
        m["lucro"] = m["pago"] - m["custos"]

    total_custos = sum(c.valor for c in custos)
    lucro_real = total_pago - total_custos
    total_minutos_abertos = sum((e.duracao_minutos or 0) for e in expedientes)
    resumo_mensal = [por_mes[k] for k in sorted(por_mes.keys())]

    return jsonify({
        "mes_inicio": mes_inicio, "mes_fim": mes_fim,
        "total_pedidos": len(pedidos),
        "total_pago": total_pago, "qtd_pago": qtd_pago,
        "total_nao_pago": total_nao_pago, "qtd_nao_pago": qtd_nao_pago,
        "total_cancelado": total_cancelado, "qtd_cancelado": qtd_cancelado,
        "total_custos": total_custos, "qtd_custos": len(custos),
        "lucro_real": lucro_real,
        "por_forma_pagamento": por_forma,
        "resumo_mensal": resumo_mensal,
        "total_minutos_abertos": total_minutos_abertos,
        "expedientes": [e.to_dict() for e in expedientes],
        "pedidos": [p.to_dict() for p in pedidos]
    })


@app.route("/api/webhook/pagamento", methods=["POST"])
def webhook_pagamento():
    dados = request.json or {}
    pedido_id = dados.get("pedido_id") or dados.get("external_reference")
    status_evento = str(dados.get("status", "")).lower()
    if pedido_id and status_evento in ["approved", "paid", "pago"]:
        p = Pedido.query.get(int(pedido_id))
        if p:
            p.status_pagamento = "Pago"
            db.session.commit()
            return jsonify({"sucesso": True}), 200
    return jsonify({"recebido": True}), 200


@app.route("/api/admin/produtos", methods=["GET", "POST"])
def gerenciar_produtos():
    if request.method == "POST":
        d = request.json or {}
        db.session.add(Produto(
            nome=d["nome"], categoria=d["categoria"],
            descricao=d.get("descricao", ""), preco=float(d["preco"]),
            imagem=d.get("imagem", ""), ativo=1
        ))
        db.session.commit()
        return jsonify({"sucesso": True})

    produtos = [p.to_dict() for p in Produto.query.order_by(Produto.categoria, Produto.nome).all()]
    faixas = [f.to_dict() for f in FaixaEntrega.query.order_by(FaixaEntrega.ate_km.asc()).all()]
    entregadores = [e.to_dict() for e in Entregador.query.order_by(Entregador.nome).all()]
    return jsonify({"produtos": produtos, "faixas": faixas, "entregadores": entregadores})


@app.route("/api/admin/produtos/<int:prod_id>", methods=["PUT", "DELETE"])
def editar_ou_excluir_produto(prod_id):
    p = Produto.query.get_or_404(prod_id)
    if request.method == "PUT":
        d = request.json or {}
        p.nome = d.get("nome", p.nome).strip()
        p.categoria = d.get("categoria", p.categoria)
        p.descricao = d.get("descricao", p.descricao).strip()
        p.preco = float(d.get("preco", p.preco))
        if "imagem" in d:
            p.imagem = d["imagem"]
        db.session.commit()
        return jsonify({"sucesso": True})

    db.session.delete(p)
    db.session.commit()
    return jsonify({"sucesso": True})


@app.route("/api/admin/produtos/<int:prod_id>/toggle", methods=["POST"])
def alternar_produto(prod_id):
    p = Produto.query.get_or_404(prod_id)
    p.ativo = 0 if p.ativo == 1 else 1
    db.session.commit()
    return jsonify({"sucesso": True})


@app.route("/api/admin/entregadores", methods=["GET", "POST"])
def gerenciar_entregadores():
    if request.method == "POST":
        d = request.json or {}
        db.session.add(Entregador(
            nome=d["nome"].strip(),
            whatsapp=limpar_numeros(d["whatsapp"]),
            padrao=0
        ))
        db.session.commit()
        return jsonify({"sucesso": True})
    return jsonify([e.to_dict() for e in Entregador.query.order_by(Entregador.nome).all()])


@app.route("/api/admin/entregadores/<int:ent_id>", methods=["PUT", "DELETE"])
def editar_ou_excluir_entregador(ent_id):
    ent = Entregador.query.get_or_404(ent_id)
    if request.method == "PUT":
        d = request.json or {}
        ent.nome = d.get("nome", ent.nome).strip()
        ent.whatsapp = limpar_numeros(d.get("whatsapp", ent.whatsapp))
        db.session.commit()
        return jsonify({"sucesso": True})

    db.session.delete(ent)
    db.session.commit()
    return jsonify({"sucesso": True})


@app.route("/api/admin/entregadores/<int:ent_id>/padrao", methods=["POST"])
def definir_entregador_padrao(ent_id):
    ent = Entregador.query.get_or_404(ent_id)
    novo_valor = 0 if ent.padrao == 1 else 1
    Entregador.query.update({Entregador.padrao: 0})
    ent.padrao = novo_valor
    db.session.commit()
    return jsonify({"sucesso": True})


@app.route("/api/admin/faixas", methods=["POST"])
def adicionar_faixa():
    d = request.json or {}
    db.session.add(FaixaEntrega(ate_km=float(d["ate_km"]), taxa=float(d["taxa"])))
    db.session.commit()
    return jsonify({"sucesso": True})


@app.route("/api/admin/faixas/<int:faixa_id>", methods=["PUT", "DELETE"])
def editar_ou_excluir_faixa(faixa_id):
    f = FaixaEntrega.query.get_or_404(faixa_id)
    if request.method == "PUT":
        d = request.json or {}
        f.ate_km = float(d.get("ate_km", f.ate_km))
        f.taxa = float(d.get("taxa", f.taxa))
        db.session.commit()
        return jsonify({"sucesso": True})

    db.session.delete(f)
    db.session.commit()
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
            width: 72mm; margin: 0 auto; padding: 4mm 2mm;
            color: #000; font-size: 13px; line-height: 1.3;
        }
        .centro { text-align: center; }
        .negrito { font-weight: bold; }
        .grande { font-size: 18px; }
        .linha { border-top: 1px dashed #000; margin: 6px 0; }
        .item { margin-bottom: 6px; }
        .sub { font-size: 12px; padding-left: 8px; }
        .total-box { font-size: 16px; font-weight: bold; margin-top: 4px; }
        .aviso-pag { border: 2px solid #000; padding: 4px; text-align: center; font-weight: bold; margin: 6px 0; }
        .rodape { margin-top: 12px; text-align: center; font-size: 11px; }
    </style>
</head>
<body>
    <div class="centro negrito grande">{{ loja }}</div>
    <div class="centro" style="font-size: 11px;">{{ endereco_loja }}</div>
    <div class="centro">COMANDA DE COZINHA / DELIVERY</div>
    <div class="linha"></div>
    <div class="negrito grande centro">PEDIDO #{{ p.id }}</div>
    <div class="centro">{{ p.data_hora }}</div>
    <div class="linha"></div>
    <div><span class="negrito">CLIENTE:</span> {{ p.cliente_nome }}</div>
    <div><span class="negrito">WHATS:</span> {{ p.cliente_whatsapp }}</div>
    <div><span class="negrito">TIPO:</span> {{ p.tipo_entrega | upper }}</div>
    {% if p.tipo_entrega == 'Entrega' %}
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
    <div><span class="negrito">FORMA PAG.:</span> {{ p.forma_pagamento }}</div>
    {% if p.troco_para %}
    <div class="negrito">TROCO PARA: R$ {{ p.troco_para }}</div>
    {% endif %}
    <div class="aviso-pag">
        {% if p.status_pagamento == 'Pago' %}
            *** PEDIDO JÁ PAGO ONLINE ***<br>NÃO COBRAR NA ENTREGA
        {% else %}
            *** {{ p.status_pagamento | upper }} ***
            {% if 'Cartão na entrega' in p.forma_pagamento %}<br>LEVAR MAQUININHA TON{% endif %}
        {% endif %}
    </div>
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
    p = Pedido.query.get_or_404(pedido_id)
    return render_template_string(
        TEMPLATE_RECIBO_80MM,
        p=p.to_dict(),
        loja=NOME_LOJA,
        endereco_loja=ENDERECO_LOJA
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
