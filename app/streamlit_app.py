"""
streamlit_app.py — Demo del Sistema de Recomendación Híbrido

Ejecutar:
    # Terminal 1 — backend
    cd <raiz_proyecto>
    python -m uvicorn api.main:app --port 8000

    # Terminal 2 — frontend
    cd <raiz_proyecto>
    python -m streamlit run app/streamlit_app.py
"""

import requests
import pandas as pd
import streamlit as st
from pathlib import Path
from datetime import date

# ──────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN
# ──────────────────────────────────────────────────────────────────────────────

API_BASE = "http://localhost:8000"
ROOT_DIR = Path(__file__).resolve().parent.parent
RAW_DIR  = ROOT_DIR / "data" / "raw"

VENDEDORES = [
    "Carlos Mendoza", "Ana Torres", "Luis Quispe",
    "María Flores",   "Jorge Huamán",
]

CATEGORIA_EMOJI = {
    "Lácteos":    "🥛", "Panadería":  "🍞", "Bebidas":    "🥤",
    "Carnes":     "🥩", "Verduras":   "🥦", "Frutas":     "🍎",
    "Abarrotes":  "🛒", "Limpieza":   "🧴", "Snacks":     "🍪",
    "Congelados": "🧊",
}

# Colores suaves para fondos — semi-transparentes para que funcionen en dark/light
CATEGORIA_COLOR = {
    "Lácteos":    "rgba(59,130,246,0.12)",
    "Panadería":  "rgba(245,158,11,0.12)",
    "Bebidas":    "rgba(16,185,129,0.12)",
    "Carnes":     "rgba(239,68,68,0.12)",
    "Verduras":   "rgba(34,197,94,0.12)",
    "Frutas":     "rgba(234,179,8,0.12)",
    "Abarrotes":  "rgba(139,92,246,0.12)",
    "Limpieza":   "rgba(6,182,212,0.12)",
    "Snacks":     "rgba(249,115,22,0.12)",
    "Congelados": "rgba(99,102,241,0.12)",
}

RUBRO_EMOJI = {
    "Restaurante": "🍽️", "Panadería":    "🥐", "Supermercado": "🏪",
    "Minimarket":  "🏬", "Cafetería":    "☕", "Hotel":        "🏨",
    "Catering":    "🍱", "Bodega":       "📦", "Farmacia":     "💊",
    "Ferretería":  "🔧", "Bar":          "🍺", "Fast Food":    "🍔",
}


# ──────────────────────────────────────────────────────────────────────────────
# ESTADO
# ──────────────────────────────────────────────────────────────────────────────

def init_state():
    defaults = {
        "page":         "login",
        "vendedor":     None,
        "cliente_id":   None,
        "cliente_info": {},
        "carrito":      {},
        "dash_data":    None,
        "cat_filter":   "Todas",
        "search_prod":  "",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ──────────────────────────────────────────────────────────────────────────────
# DATOS
# ──────────────────────────────────────────────────────────────────────────────

@st.cache_data
def load_clientes() -> pd.DataFrame:
    return pd.read_csv(RAW_DIR / "clientes.csv")

@st.cache_data
def load_productos() -> pd.DataFrame:
    df = pd.read_csv(RAW_DIR / "productos.csv", parse_dates=["fecha_min_caducidad"])
    today = pd.Timestamp(date.today())
    df["dias_para_vencer"] = (df["fecha_min_caducidad"] - today).dt.days
    return df


# ──────────────────────────────────────────────────────────────────────────────
# API CLIENT
# ──────────────────────────────────────────────────────────────────────────────

def api_health():
    try:
        r = requests.get(f"{API_BASE}/health", timeout=3)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None

def api_dashboard(cliente_id: str, top_k: int = 5) -> dict | None:
    try:
        r = requests.get(
            f"{API_BASE}/recomendar/dashboard/{cliente_id}",
            params={"top_k": top_k},
            timeout=10,
        )
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────────────
# CSS — compatible con light y dark mode
# ──────────────────────────────────────────────────────────────────────────────

def inject_css():
    st.markdown("""
    <style>
    /* ── General ── */
    .block-container { padding-top: 1.2rem; padding-bottom: 2rem; }

    /* ── Header de página ── */
    .page-header {
        background: linear-gradient(135deg, #1e40af 0%, #3b82f6 100%);
        color: white !important;
        border-radius: 12px; padding: 1.2rem 1.8rem; margin-bottom: 1.2rem;
    }
    .page-header h2 { margin: 0; font-size: 1.4rem; font-weight: 700; color: white !important; }
    .page-header p  { margin: 0; opacity: 0.88; font-size: 0.88rem; color: white !important; }

    /* ── Carril header ── */
    .carril-header {
        display: flex; align-items: center; gap: 10px;
        padding: 0.5rem 0; border-bottom: 2px solid; margin-bottom: 0.8rem;
    }
    .carril-urgente  { border-color: #ef4444; }
    .carril-baja-rot { border-color: #f59e0b; }
    .carril-nuevo    { border-color: #10b981; }
    .carril-urgente  span.ch { color: #ef4444; font-weight: 700; font-size: 1rem; }
    .carril-baja-rot span.ch { color: #d97706; font-weight: 700; font-size: 1rem; }
    .carril-nuevo    span.ch { color: #059669; font-weight: 700; font-size: 1rem; }
    .carril-sub { font-size: 0.76rem; opacity: 0.65; }

    /* ── Tarjeta de producto (reemplaza prod-card con estilos inline) ── */
    .prod-wrap {
        border: 1px solid rgba(128,128,128,0.2);
        border-radius: 10px;
        overflow: hidden;
        margin-bottom: 4px;
    }
    .prod-emoji-area {
        text-align: center;
        font-size: 2.4rem;
        padding: 10px 0;
        border-radius: 8px 8px 0 0;
    }
    .prod-body { padding: 6px 8px 4px; }
    .prod-id   { font-size: 0.75rem; font-weight: 600; opacity: 0.9; margin-bottom: 2px; }
    .prod-cat  { font-size: 0.68rem; opacity: 0.6; margin-bottom: 4px; }
    .prod-price { font-size: 1.05rem; font-weight: 700; color: #2563eb; margin-bottom: 2px; }
    .prod-stock { font-size: 0.70rem; opacity: 0.55; }

    /* ── Badges ── */
    .bdg {
        display: inline-block; font-size: 0.62rem; font-weight: 600;
        padding: 1px 6px; border-radius: 99px; margin-right: 3px; margin-bottom: 3px;
    }
    .bdg-urg  { background: rgba(239,68,68,0.15);  color: #dc2626; }
    .bdg-baja { background: rgba(245,158,11,0.15); color: #d97706; }
    .bdg-new  { background: rgba(16,185,129,0.15); color: #059669; }

    /* ── Score bar ── */
    .sbar-wrap { margin-top: 5px; }
    .sbar-lbl  { font-size: 0.62rem; opacity: 0.55; margin-bottom: 1px; }
    .sbar-bg   { background: rgba(128,128,128,0.2); border-radius: 99px; height: 4px; }
    .sbar-fill { height: 4px; border-radius: 99px; }

    /* ── Métrica box ── */
    .metric-box {
        border: 1px solid rgba(128,128,128,0.2);
        border-radius: 10px; padding: 0.8rem; text-align: center;
        margin-bottom: 8px;
    }
    .metric-val { font-size: 1.6rem; font-weight: 700; color: #2563eb; }
    .metric-lbl { font-size: 0.72rem; opacity: 0.55; }

    /* ── Login ── */
    .login-wrap { max-width: 420px; margin: 3rem auto; }
    .login-logo  { text-align: center; font-size: 3rem; }
    .login-title { text-align: center; font-size: 1.35rem; font-weight: 700; margin-bottom: 4px; }
    .login-sub   { text-align: center; font-size: 0.85rem; opacity: 0.6; margin-bottom: 1.5rem; }

    /* ── Sidebar total ── */
    .carrito-total {
        background: #1d4ed8; color: white; border-radius: 8px;
        padding: 8px 12px; text-align: center; font-weight: 700;
        font-size: 0.92rem; margin-top: 6px;
    }
    </style>
    """, unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────────
# HELPERS CARRITO
# ──────────────────────────────────────────────────────────────────────────────

def agregar_al_carrito(prod_id, categoria, precio, stock):
    c = st.session_state.carrito
    if prod_id in c:
        if c[prod_id]["cantidad"] < stock:
            c[prod_id]["cantidad"] += 1
    else:
        c[prod_id] = {"producto_id": prod_id, "categoria": categoria,
                      "precio": precio, "stock": stock, "cantidad": 1}
    st.session_state.carrito   = c
    st.session_state.dash_data = None   # invalidar cache de recomendaciones

def total_carrito():
    return sum(v["precio"] * v["cantidad"] for v in st.session_state.carrito.values())

def n_items_carrito():
    return sum(v["cantidad"] for v in st.session_state.carrito.values())


# ──────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ──────────────────────────────────────────────────────────────────────────────

def render_sidebar():
    with st.sidebar:
        st.markdown("### 🏢 DistribuFood")
        st.caption("Sistema de Ventas · Demo Tesis")
        st.divider()

        st.markdown(f"**👤 Vendedor:** {st.session_state.vendedor}")

        if st.session_state.cliente_id:
            ci = st.session_state.cliente_info
            emoji = RUBRO_EMOJI.get(ci.get("rubro_cliente", ""), "🏪")
            st.markdown(
                f"**{emoji} Cliente:** `{st.session_state.cliente_id}`  \n"
                f"{ci.get('rubro_cliente','')} · 📍 {ci.get('sede_cliente','')}"
            )

        st.divider()
        st.markdown("**Navegación**")

        pages = [("clientes", "👥 Clientes"), ("catalogo", "📦 Catálogo"), ("carrito", "🛒 Carrito")]
        for key, label in pages:
            if key == "carrito":
                n = n_items_carrito()
                label = f"🛒 Carrito ({n})" if n else "🛒 Carrito"
            if st.button(label, use_container_width=True, key=f"nav_{key}"):
                st.session_state.page = key
                st.rerun()

        st.divider()

        carrito = st.session_state.carrito
        if carrito:
            st.markdown("**Resumen del carrito**")
            for pid, item in carrito.items():
                e = CATEGORIA_EMOJI.get(item["categoria"], "📦")
                ca, cb = st.columns([3, 1])
                ca.caption(f"{e} {pid[-6:]} ×{item['cantidad']}")
                cb.caption(f"S/{item['precio']*item['cantidad']:.0f}")
            st.markdown(
                f'<div class="carrito-total">Total: S/ {total_carrito():.2f}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.caption("Carrito vacío.")

        st.divider()
        h = api_health()
        if h and h.get("modelo_cargado"):
            st.success("API activa ✓", icon="🟢")
        else:
            st.error("API no disponible", icon="🔴")

        if st.button("🚪 Cerrar sesión", use_container_width=True):
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()


# ──────────────────────────────────────────────────────────────────────────────
# COMPONENTE: tarjeta de producto
# Usa HTML solo para el área emoji (color de fondo) + Streamlit nativo para data
# ──────────────────────────────────────────────────────────────────────────────

def render_card(pid, categoria, precio, stock, dias_para_vencer=999,
                score_final=None, score_cf=None, color_bar=None,
                es_urgente=False, es_baja_rotacion=False, es_nuevo_catalogo=False,
                key_prefix="card"):
    """
    Renderiza una tarjeta de producto usando HTML mínimo para el área de color
    y widgets nativos de Streamlit para texto y botón.
    Compatible con dark mode y light mode.
    """
    emoji  = CATEGORIA_EMOJI.get(categoria, "📦")
    color  = CATEGORIA_COLOR.get(categoria, "rgba(128,128,128,0.1)")
    stock_ok = stock > 0

    # Área emoji con color de fondo (solo HTML, sin texto de datos)
    st.markdown(
        f'<div class="prod-emoji-area" style="background:{color};">{emoji}</div>',
        unsafe_allow_html=True,
    )

    # Badges en una línea (HTML simple)
    badges = ""
    if es_urgente:        badges += '<span class="bdg bdg-urg">⚡ Urgente</span>'
    if es_baja_rotacion:  badges += '<span class="bdg bdg-baja">📉 Baja rot.</span>'
    if es_nuevo_catalogo: badges += '<span class="bdg bdg-new">✨ Nuevo</span>'
    if badges:
        st.markdown(badges, unsafe_allow_html=True)

    # Datos con widgets nativos (compatibles con dark mode)
    st.markdown(f"**`{pid}`**")
    st.caption(categoria)
    st.markdown(f"### S/ {precio:.2f}")

    if not stock_ok:
        st.caption("❌ Sin stock")
    elif dias_para_vencer <= 30:
        st.caption(f"⚡ Vence en {dias_para_vencer}d · Stock: {stock}")
    else:
        st.caption(f"Stock: {stock}")

    # Score bar (solo si se pasa)
    if score_final is not None and color_bar:
        pct = int(score_final * 100)
        st.markdown(
            f'<div class="sbar-wrap">'
            f'<div class="sbar-lbl">Score {pct}%</div>'
            f'<div class="sbar-bg"><div class="sbar-fill" '
            f'style="width:{pct}%;background:{color_bar};"></div></div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # Botón agregar
    en_carrito = pid in st.session_state.carrito
    cant = st.session_state.carrito.get(pid, {}).get("cantidad", 0)
    label = f"✓ En carrito ({cant})" if en_carrito else "＋ Agregar"
    if st.button(label, key=f"{key_prefix}_{pid}", use_container_width=True,
                 disabled=not stock_ok):
        agregar_al_carrito(pid, categoria, precio, stock)
        st.rerun()


# ──────────────────────────────────────────────────────────────────────────────
# PAGE: LOGIN
# ──────────────────────────────────────────────────────────────────────────────

def page_login():
    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.markdown('<div class="login-wrap">', unsafe_allow_html=True)
        st.markdown('<div class="login-logo">🏢</div>', unsafe_allow_html=True)
        st.markdown('<div class="login-title">DistribuFood</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="login-sub">Sistema de Ventas con Recomendación Inteligente</div>',
            unsafe_allow_html=True,
        )

        vendedor = st.selectbox(
            "Selecciona tu nombre",
            VENDEDORES, index=None,
            placeholder="— Elige un vendedor —",
        )
        if st.button("Entrar al sistema", type="primary", use_container_width=True):
            if vendedor:
                st.session_state.vendedor = vendedor
                st.session_state.page     = "clientes"
                st.rerun()
            else:
                st.warning("Selecciona un vendedor para continuar.")

        st.divider()
        h = api_health()
        if h and h.get("modelo_cargado"):
            st.success(
                f"Modelo activo — {h['n_clientes']} clientes · {h['n_productos']} productos",
                icon="🟢",
            )
        else:
            st.error(
                "Backend no disponible.  \n"
                "Ejecuta: `python -m uvicorn api.main:app --port 8000`",
                icon="🔴",
            )
        st.markdown("</div>", unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────────
# PAGE: CLIENTES
# ──────────────────────────────────────────────────────────────────────────────

def page_cliente():
    st.markdown("""
    <div class="page-header">
      <h2>👥 Selección de Cliente</h2>
      <p>Elige el cliente que estás atendiendo para comenzar la venta.</p>
    </div>
    """, unsafe_allow_html=True)

    df = load_clientes()

    c1, c2, c3 = st.columns(3)
    with c1:
        sede_f = st.selectbox("📍 Sede", ["Todas"] + sorted(df["sede_cliente"].unique()))
    with c2:
        rubro_f = st.selectbox("🏪 Rubro", ["Todos"] + sorted(df["rubro_cliente"].unique()))
    with c3:
        search = st.text_input("🔍 Buscar ID", placeholder="CLI_...")

    if sede_f  != "Todas": df = df[df["sede_cliente"]  == sede_f]
    if rubro_f != "Todos": df = df[df["rubro_cliente"] == rubro_f]
    if search.strip():     df = df[df["cliente_id"].str.contains(search.strip(), case=False)]

    df = df.head(50).reset_index(drop=True)
    st.caption(f"{len(df)} clientes encontrados (máx. 50)")

    N = 5
    for i in range(0, len(df), N):
        cols = st.columns(N)
        for col, (_, c) in zip(cols, df.iloc[i:i+N].iterrows()):
            with col:
                emoji  = RUBRO_EMOJI.get(c["rubro_cliente"], "🏪")
                active = st.session_state.cliente_id == c["cliente_id"]
                border = "2px solid #2563eb" if active else "1px solid rgba(128,128,128,0.25)"

                # Tarjeta: solo HTML para contenedor/emoji, datos con st.write
                st.markdown(
                    f'<div style="border:{border};border-radius:10px;'
                    f'padding:8px;text-align:center;margin-bottom:4px;">'
                    f'<div style="font-size:1.8rem;">{emoji}</div></div>',
                    unsafe_allow_html=True,
                )
                st.caption(f"**{c['cliente_id']}**")
                st.caption(f"{c['rubro_cliente']}  \n📍 {c['sede_cliente']}")

                if st.button("Seleccionar", key=f"sel_{c['cliente_id']}",
                             use_container_width=True):
                    st.session_state.cliente_id   = c["cliente_id"]
                    st.session_state.cliente_info = c.to_dict()
                    st.session_state.carrito      = {}
                    st.session_state.dash_data    = None
                    st.session_state.page         = "catalogo"
                    st.rerun()


# ──────────────────────────────────────────────────────────────────────────────
# PAGE: CATÁLOGO
# ──────────────────────────────────────────────────────────────────────────────

def page_catalogo():
    if not st.session_state.cliente_id:
        st.warning("Primero selecciona un cliente.")
        if st.button("Ir a clientes"):
            st.session_state.page = "clientes"; st.rerun()
        return

    ci   = st.session_state.cliente_info
    sede = ci.get("sede_cliente", "")

    st.markdown(f"""
    <div class="page-header">
      <h2>📦 Catálogo · {sede}</h2>
      <p>Cliente: {st.session_state.cliente_id} · {ci.get('rubro_cliente','')} — {ci.get('subrubro_1','')}</p>
    </div>
    """, unsafe_allow_html=True)

    prods_df = load_productos()
    df = prods_df[prods_df["sede"] == sede].drop_duplicates("producto_id").copy()

    # Filtros
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        search = st.text_input("🔍 Buscar", placeholder="ID o categoría…",
                               value=st.session_state.search_prod)
        st.session_state.search_prod = search
    with c2:
        cats = ["Todas"] + sorted(df["categoria_producto"].unique())
        cat_f = st.selectbox("Categoría", cats)
        st.session_state.cat_filter = cat_f
    with c3:
        solo_stock = st.checkbox("Solo con stock", value=True)

    if search.strip():
        df = df[
            df["producto_id"].str.contains(search.strip(), case=False) |
            df["categoria_producto"].str.contains(search.strip(), case=False)
        ]
    if cat_f != "Todas":
        df = df[df["categoria_producto"] == cat_f]
    if solo_stock:
        df = df[df["stock"] > 0]

    df = df.reset_index(drop=True)

    # Métricas
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Productos", len(df))
    m2.metric("Por vencer ≤30d", int((df["dias_para_vencer"] <= 30).sum()))
    m3.metric("Sin stock", int((df["stock"] == 0).sum()))
    m4.metric("Categorías", df["categoria_producto"].nunique())

    st.divider()

    N = 4
    for i in range(0, len(df), N):
        cols = st.columns(N)
        for col, (_, prod) in zip(cols, df.iloc[i:i+N].iterrows()):
            with col:
                render_card(
                    pid=prod["producto_id"],
                    categoria=prod["categoria_producto"],
                    precio=prod["precio_unitario"],
                    stock=int(prod["stock"]),
                    dias_para_vencer=int(prod["dias_para_vencer"]),
                    key_prefix=f"cat{i}",
                )

    if len(df) == 0:
        st.info("No hay productos con estos filtros.")

    st.divider()
    if st.button("🛒 Ver carrito y recomendaciones", type="primary"):
        st.session_state.page = "carrito"; st.rerun()


# ──────────────────────────────────────────────────────────────────────────────
# PAGE: CARRITO
# ──────────────────────────────────────────────────────────────────────────────

def render_carril(titulo, subtitulo, icono, clase_css, color_titulo,
                  productos, color_bar, key_prefix):
    st.markdown(
        f'<div class="carril-header {clase_css}">'
        f'<span style="font-size:1.3rem;">{icono}</span>'
        f'<div><span class="ch">{titulo}</span>'
        f'<div class="carril-sub">{subtitulo} · {len(productos)} productos</div>'
        f'</div></div>',
        unsafe_allow_html=True,
    )

    if not productos:
        st.caption("Sin productos en esta sección para este cliente.")
        return

    cols = st.columns(min(len(productos), 5))
    for col, prod in zip(cols, productos):
        with col:
            render_card(
                pid=prod["producto_id"],
                categoria=prod["categoria_producto"],
                precio=prod["precio_unitario"],
                stock=prod["stock"],
                dias_para_vencer=prod.get("dias_para_vencer", 999),
                score_final=prod.get("score_final"),
                color_bar=color_bar,
                es_urgente=prod.get("es_urgente", False),
                es_baja_rotacion=prod.get("es_baja_rotacion", False),
                es_nuevo_catalogo=prod.get("es_nuevo_catalogo", False),
                key_prefix=key_prefix,
            )


def page_carrito():
    if not st.session_state.cliente_id:
        st.warning("Primero selecciona un cliente.")
        return

    st.markdown(f"""
    <div class="page-header">
      <h2>🛒 Carrito de Compra</h2>
      <p>Revisa el pedido y explora las recomendaciones personalizadas.</p>
    </div>
    """, unsafe_allow_html=True)

    carrito = st.session_state.carrito

    # ── Tabla del carrito ──────────────────────────────────────────────────────
    col_cart, col_summary = st.columns([2, 1])

    with col_cart:
        st.markdown("#### Productos en el pedido")
        if not carrito:
            st.info("El carrito está vacío. Agrega productos desde el catálogo.")
        else:
            h1, h2, h3, h4, h5 = st.columns([3, 1, 1, 1, 0.5])
            for h, t in zip([h1,h2,h3,h4,h5], ["Producto","Precio","Cant.","Subtotal",""]):
                h.markdown(f"**{t}**")
            st.divider()

            for pid, item in list(carrito.items()):
                e = CATEGORIA_EMOJI.get(item["categoria"], "📦")
                c1, c2, c3, c4, c5 = st.columns([3, 1, 1, 1, 0.5])
                c1.write(f"{e} `{pid}` · {item['categoria']}")
                c2.write(f"S/ {item['precio']:.2f}")
                nueva = c3.number_input("", 1, item["stock"], item["cantidad"],
                                        key=f"qty_{pid}", label_visibility="collapsed")
                if nueva != item["cantidad"]:
                    st.session_state.carrito[pid]["cantidad"] = nueva
                    st.rerun()
                c4.write(f"**S/ {item['precio']*item['cantidad']:.2f}**")
                if c5.button("🗑️", key=f"del_{pid}"):
                    del st.session_state.carrito[pid]
                    st.session_state.dash_data = None
                    st.rerun()

    with col_summary:
        st.markdown("#### Resumen")
        st.markdown(
            f'<div class="metric-box"><div class="metric-val">{len(carrito)}</div>'
            f'<div class="metric-lbl">SKUs distintos</div></div>'
            f'<div class="metric-box"><div class="metric-val">{n_items_carrito()}</div>'
            f'<div class="metric-lbl">Unidades totales</div></div>'
            f'<div class="metric-box"><div class="metric-val">S/ {total_carrito():.2f}</div>'
            f'<div class="metric-lbl">Total del pedido</div></div>',
            unsafe_allow_html=True,
        )
        st.markdown("")
        if st.button("✅ Confirmar pedido", type="primary",
                     use_container_width=True, disabled=(not carrito)):
            st.success("¡Pedido confirmado! (simulación)")
            st.balloons()
        if st.button("📦 Seguir comprando", use_container_width=True):
            st.session_state.page = "catalogo"; st.rerun()

    # ── Recomendaciones ────────────────────────────────────────────────────────
    st.divider()
    st.markdown("## 🤖 Recomendaciones personalizadas")
    st.caption(
        f"Modelo híbrido (CF + CBF + reglas de negocio) · "
        f"Cliente **{st.session_state.cliente_id}** · "
        f"Sede **{st.session_state.cliente_info.get('sede_cliente','')}**"
    )

    if st.session_state.dash_data is None:
        with st.spinner("Consultando modelo de recomendación…"):
            st.session_state.dash_data = api_dashboard(
                st.session_state.cliente_id, top_k=5
            )

    data = st.session_state.dash_data

    if data is None:
        st.error(
            "No se pudo conectar al backend.  \n"
            "Verifica que FastAPI esté corriendo: "
            "`python -m uvicorn api.main:app --port 8000`"
        )
        if st.button("🔄 Reintentar"):
            st.session_state.dash_data = None; st.rerun()
        return

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("⚡ Urgentes",      len(data.get("urgentes", [])))
    m2.metric("📉 Baja rotación", len(data.get("baja_rotacion", [])))
    m3.metric("✨ Nuevos",        len(data.get("nuevos", [])))
    m4.metric("Total sin dupl.",  data.get("total_recomendaciones", 0))

    st.markdown("")
    render_carril("Próximos a vencer",
                  "Prioridad máxima — evitar mermas por caducidad", "⚡",
                  "carril-urgente", "#ef4444",
                  data.get("urgentes", []), "#ef4444", "urg")

    st.markdown("")
    render_carril("Stock de baja rotación",
                  "Liberar inventario parado — impulso de venta", "📉",
                  "carril-baja-rot", "#d97706",
                  data.get("baja_rotacion", []), "#f59e0b", "br")

    st.markdown("")
    render_carril("Nuevos en catálogo",
                  "Adopción de nuevos SKUs — cold-start resuelto por CBF", "✨",
                  "carril-nuevo", "#059669",
                  data.get("nuevos", []), "#10b981", "nv")

    with st.expander("🔬 Respuesta completa de la API"):
        st.json(data)


# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────

def main():
    st.set_page_config(
        page_title="DistribuFood · Sistema de Ventas",
        page_icon="🏢",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    init_state()
    inject_css()

    if st.session_state.page != "login":
        render_sidebar()

    {
        "login":    page_login,
        "clientes": page_cliente,
        "catalogo": page_catalogo,
        "carrito":  page_carrito,
    }.get(st.session_state.page, page_login)()


if __name__ == "__main__":
    main()
