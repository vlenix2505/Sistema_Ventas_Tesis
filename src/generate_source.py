"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  generate_source.py — Generador de datos sintéticos                         ║
║  Sistema de Recomendación Híbrido — Tesis                                   ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Genera 4 archivos CSV que simulan el entorno de datos de una empresa        ║
║  distribuidora de alimentos y productos para el canal HORECA/retail.        ║
║                                                                              ║
║  ARCHIVOS GENERADOS:                                                         ║
║  ┌──────────────────┬────────┬──────────────────────────────────────────┐   ║
║  │ Archivo          │ Filas  │ Descripción                              │   ║
║  ├──────────────────┼────────┼──────────────────────────────────────────┤   ║
║  │ clientes.csv     │   800  │ Maestro de clientes con rubro y sede     │   ║
║  │ productos.csv    │ ~1 800 │ Catálogo (una fila por producto × sede)  │   ║
║  │ ventas.csv       │  7 950 │ Cabeceras de pedidos                     │   ║
║  │ detalle_venta.csv│ ~36 000│ Líneas de pedido (item × cantidad)       │   ║
║  └──────────────────┴────────┴──────────────────────────────────────────┘   ║
║                                                                              ║
║  RELACIONES ENTRE TABLAS:                                                    ║
║                                                                              ║
║   clientes ──┐                                                               ║
║              ├──> ventas ──> detalle_venta <── productos                    ║
║   productos ─┘                                                               ║
║                                                                              ║
║  REALISMO SIMULADO:                                                          ║
║  • Cada cliente tiene un perfil de productos favoritos (15-40 productos).   ║
║  • 80% de compras provienen de favoritos, 20% son exploraciones.            ║
║  • Los favoritos se asignan respetando el rubro y la sede del cliente.      ║
║  • Patrones estacionales: mayor volumen en meses de alta temporada.         ║
║  • Stock con distribución realista: 15% agotado, 25% bajo, 60% normal.     ║
║  • Productos con cobertura geográfica variable (local, regional, nacional). ║
║  • Precios coherentes: precio de venta siempre > costo (margen 25-60%).     ║
║  • Fechas de caducidad con distribución realista (algunos ya vencidos).     ║
╚══════════════════════════════════════════════════════════════════════════════╝

USO:
    python src/generate_source.py

    Los archivos se guardan en data/raw/ (relativo a la raíz del proyecto).
    La raíz del proyecto se detecta automáticamente como el directorio padre
    de este script.
"""

import csv
import random
import string
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
# RUTAS
# ──────────────────────────────────────────────────────────────────────────────
# Directorio raíz del proyecto (un nivel arriba de /src)
ROOT_DIR   = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT_DIR / "data" / "raw"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ──────────────────────────────────────────────────────────────────────────────
# PARÁMETROS CONFIGURABLES
# ──────────────────────────────────────────────────────────────────────────────
N_CLIENTES               = 800    # Número total de clientes
N_PRODUCTOS              = 950    # Número de productos únicos en el catálogo
N_VENTAS                 = 7_950  # Número total de pedidos (cabeceras)
N_DETALLE_MIN            = 1      # Mínimo de líneas por pedido
N_DETALLE_MAX            = 8      # Máximo de líneas por pedido
FECHA_INICIO_VENTAS      = date(2025, 1, 1)
FECHA_FIN_VENTAS         = date(2026, 2, 27)
SEED                     = 42     # Semilla para reproducibilidad

# Perfil de favoritos por cliente
FAVORITOS_MIN  = 15    # Mínimo de productos favoritos
FAVORITOS_MAX  = 40    # Máximo de productos favoritos
PROB_FAVORITO  = 0.80  # Probabilidad de elegir de favoritos en cada compra

random.seed(SEED)


# ──────────────────────────────────────────────────────────────────────────────
# FUNCIONES AUXILIARES
# ──────────────────────────────────────────────────────────────────────────────

def rand_id(prefix: str, n: int = 6) -> str:
    """Genera un ID alfanumérico con prefijo: ej. CLI_123456."""
    return f"{prefix}_{''.join(random.choices(string.digits, k=n))}"


def rand_date(start: date, end: date, weights: list | None = None) -> date:
    """
    Genera una fecha aleatoria en [start, end].

    Args:
        weights: lista de pesos por mes (len=12). Si se proporciona, aplica
                 sesgo estacional. Meses con mayor peso tienen más probabilidad.
                 Ejemplo: weights=[1,1,1,1.5,2,2,2,1.5,1,1,2,2] → alta temp.
                 en mayo-agosto y nov-dic.
    """
    if weights is None:
        delta = (end - start).days
        return start + timedelta(days=random.randint(0, delta))

    # Construir lista de días con pesos por mes
    all_days = []
    day_weights = []
    current = start
    while current <= end:
        all_days.append(current)
        day_weights.append(weights[current.month - 1])
        current += timedelta(days=1)

    return random.choices(all_days, weights=day_weights, k=1)[0]


def round2(x: float) -> float:
    """Redondea a 2 decimales."""
    return round(x, 2)


def dedup_ids(records: list, field: str, prefix: str) -> None:
    """Garantiza IDs únicos en la lista de registros (in-place)."""
    seen: set = set()
    for r in records:
        while r[field] in seen:
            r[field] = rand_id(prefix)
        seen.add(r[field])


# ──────────────────────────────────────────────────────────────────────────────
# SEDES (distribución geográfica)
# ──────────────────────────────────────────────────────────────────────────────
# La empresa opera en 4 ciudades del Perú. Cada cliente pertenece a una sola
# sede. Los productos pueden estar disponibles en 1, 2 o las 4 sedes,
# con su propio stock independiente por sede.
#
# Distribución de cobertura de sedes:
#   50% → solo 1 sede  (producto local / perecedero de corta distribución)
#   30% → 2 sedes      (producto regional, distribución media)
#   20% → todas las sedes (producto de distribución nacional)

SEDES              = ["Lima", "Piura", "Arequipa", "Cusco"]
PROB_UNA_SEDE      = 0.50
PROB_DOS_SEDES     = 0.30
# PROB_TODAS_SEDES = 0.20  (el resto)


def elegir_sedes_producto(sede_origen: str) -> list[str]:
    """
    Determina en qué sedes estará disponible un producto.
    La sede de origen siempre está incluida.

    Returns:
        Lista de sedes donde el producto tiene stock.
    """
    r = random.random()
    if r < PROB_UNA_SEDE:
        return [sede_origen]
    elif r < PROB_UNA_SEDE + PROB_DOS_SEDES:
        otras = [s for s in SEDES if s != sede_origen]
        segunda = random.choice(otras)
        return sorted([sede_origen, segunda])
    else:
        return list(SEDES)  # distribución nacional


# ──────────────────────────────────────────────────────────────────────────────
# 1. CLIENTES
# ──────────────────────────────────────────────────────────────────────────────
# Rubros: tipo de negocio del cliente (ej. Restaurante, Hotel, etc.)
# subrubro_1: especialidad principal dentro del rubro
# subrubro_2: formato de servicio/atención
# sede_cliente: ciudad donde opera el cliente

RUBROS = [
    "Restaurante", "Panadería", "Supermercado", "Minimarket",
    "Cafetería", "Hotel", "Catering", "Bodega", "Farmacia",
    "Ferretería", "Bar", "Fast Food",
]

# Distribución no uniforme de rubros (simula realidad del mercado HORECA)
PESO_RUBROS = {
    "Restaurante":   0.20,   # Mayor segmento
    "Bodega":        0.15,
    "Minimarket":    0.13,
    "Fast Food":     0.10,
    "Panadería":     0.08,
    "Cafetería":     0.08,
    "Supermercado":  0.07,
    "Hotel":         0.06,
    "Catering":      0.05,
    "Bar":           0.04,
    "Farmacia":      0.02,
    "Ferretería":    0.02,
}

# subrubro_1: especialidad principal del negocio (qué tipo de cocina, formato, etc.)
SUBRUBRO_1_POR_RUBRO = {
    "Restaurante":  ["Chifa", "Pollería", "Criollo", "Carnes", "Marino",
                     "Italiano", "Japonés", "Vegetariano", "Fusión", "Buffet"],
    "Panadería":    ["Artesanal", "Industrial", "Pastelería", "Francesa",
                     "Integral", "Repostería"],
    "Supermercado": ["Formato Grande", "Formato Mediano", "Gourmet",
                     "Mayorista", "Orgánico"],
    "Minimarket":   ["Barrio", "24 Horas", "Gasolinera", "Express", "Universitario"],
    "Cafetería":    ["Tradicional", "Moderna", "Temática", "Saludable", "Especialidad"],
    "Hotel":        ["Boutique", "Business", "Turístico", "Resort", "Hostal", "Apart-hotel"],
    "Catering":     ["Eventos Corporativos", "Matrimonios", "Escolar", "Industrial", "Social"],
    "Bodega":       ["Barrio", "Mayorista", "Abarrotes", "Licorería", "Mixta"],
    "Farmacia":     ["Independiente", "Cadena", "Naturista", "Homeopática"],
    "Ferretería":   ["General", "Especializada", "Mayorista", "Industrial"],
    "Bar":          ["Karaoke", "Sports Bar", "Cocteles", "Cervecería",
                     "Vinos", "Lounge", "Pub"],
    "Fast Food":    ["Hamburguesas", "Pollo", "Pizza", "Tacos",
                     "Sándwiches", "Wraps", "Árabe"],
}

# subrubro_2: formato de servicio del negocio
SUBRUBRO_2_POR_RUBRO = {
    "Restaurante":  ["Salón", "Delivery", "Para Llevar", "Delivery + Salón", "Dark Kitchen"],
    "Panadería":    ["Local Propio", "Distribución", "Local + Distribución"],
    "Supermercado": ["Tienda Física", "Online + Tienda", "Solo Online"],
    "Minimarket":   ["Tienda Física", "24 Horas", "Tienda + Delivery"],
    "Cafetería":    ["Salón", "Para Llevar", "Co-Working", "Salón + Delivery"],
    "Hotel":        ["Restaurante Propio", "Desayuno Incluido", "Solo Alojamiento", "Todo Incluido"],
    "Catering":     ["On-Site", "Off-Site", "Mixto"],
    "Bodega":       ["Mostrador", "Autoservicio", "Mostrador + Delivery"],
    "Farmacia":     ["Mostrador", "Autoservicio", "Drive-Thru"],
    "Ferretería":   ["Mostrador", "Autoservicio", "Catálogo Online"],
    "Bar":          ["Presencial", "Reservas", "Presencial + Eventos"],
    "Fast Food":    ["Salón", "Drive-Thru", "Delivery", "Salón + Delivery", "Solo Delivery"],
}


def asignar_subrubros(rubro: str) -> tuple[str, str]:
    """Asigna subrubro_1 y subrubro_2 coherentes con el rubro dado."""
    sr1 = random.choice(SUBRUBRO_1_POR_RUBRO.get(rubro, ["General"]))
    sr2 = random.choice(SUBRUBRO_2_POR_RUBRO.get(rubro, ["Presencial"]))
    return sr1, sr2


print("Generando clientes...")
rubros_lista   = list(PESO_RUBROS.keys())
rubros_pesos   = list(PESO_RUBROS.values())

clientes = []
for _ in range(N_CLIENTES):
    rubro      = random.choices(rubros_lista, weights=rubros_pesos, k=1)[0]
    sr1, sr2   = asignar_subrubros(rubro)
    clientes.append({
        "cliente_id":    rand_id("CLI"),
        "rubro_cliente": rubro,
        "subrubro_1":    sr1,
        "subrubro_2":    sr2,
        "sede_cliente":  random.choice(SEDES),
    })

dedup_ids(clientes, "cliente_id", "CLI")
clientes_ids = [c["cliente_id"] for c in clientes]

with open(OUTPUT_DIR / "clientes.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(
        f, fieldnames=["cliente_id", "rubro_cliente", "subrubro_1",
                        "subrubro_2", "sede_cliente"]
    )
    writer.writeheader()
    writer.writerows(clientes)

print(f"  ✔ clientes.csv  ({len(clientes)} filas)")


# ──────────────────────────────────────────────────────────────────────────────
# 2. PRODUCTOS
# ──────────────────────────────────────────────────────────────────────────────
# El catálogo tiene N_PRODUCTOS productos únicos.
# Como cada producto puede estar disponible en 1–4 sedes con stock independiente,
# productos.csv tiene UNA FILA por (producto_id, sede) → clave compuesta.
#
# Columnas del catálogo:
#   producto_id            → ID único del producto
#   sede                   → Sede donde está disponible este stock
#   categoria_producto     → Categoría de producto (Lácteos, Bebidas, etc.)
#   precio_unitario        → Precio de venta al cliente (soles)
#   COSTO_UNITARIO         → Costo de adquisición del producto (soles)
#   stock                  → Unidades disponibles en esta sede
#   dias_en_stock          → Días que lleva el lote actual en almacén
#   fecha_ingreso_catalogo → Fecha en que el producto se agregó al catálogo
#   fecha_min_caducidad    → Fecha de caducidad más próxima del lote actual

CATEGORIAS = [
    "Lácteos", "Panadería", "Bebidas", "Carnes", "Verduras",
    "Frutas", "Abarrotes", "Limpieza", "Snacks", "Congelados",
]

# Distribución de categorías (simula importancia en catálogo real)
PESO_CATEGORIAS = {
    "Abarrotes":   0.18,
    "Bebidas":     0.15,
    "Snacks":      0.12,
    "Lácteos":     0.12,
    "Carnes":      0.10,
    "Panadería":   0.09,
    "Verduras":    0.08,
    "Frutas":      0.07,
    "Congelados":  0.05,
    "Limpieza":    0.04,
}

# Rangos de precio por categoría (simula diferencias reales)
PRECIO_RANGO_POR_CATEGORIA = {
    "Lácteos":     (2.5,  45.0),
    "Panadería":   (1.5,  30.0),
    "Bebidas":     (2.0,  80.0),
    "Carnes":      (8.0, 150.0),
    "Verduras":    (1.5,  25.0),
    "Frutas":      (2.0,  35.0),
    "Abarrotes":   (1.5,  60.0),
    "Limpieza":    (3.0,  90.0),
    "Snacks":      (1.5,  40.0),
    "Congelados":  (5.0, 120.0),
}

# Rangos de caducidad por categoría (días desde hoy)
# Negativos = ya vencidos (simulamos lotes con vencimiento pasado)
CADUCIDAD_RANGO_POR_CATEGORIA = {
    "Lácteos":     (-5,   60),   # Muy perecedero
    "Panadería":   (-3,   30),   # Perecedero
    "Verduras":    (-5,   21),   # Muy perecedero
    "Frutas":      (-3,   30),   # Perecedero
    "Carnes":      (-5,   45),   # Perecedero
    "Congelados":  (60,  365),   # Larga duración
    "Bebidas":     (30,  365),   # Larga duración
    "Snacks":      (15,  270),   # Duración media
    "Abarrotes":   (30,  365),   # Larga duración
    "Limpieza":    (90,  730),   # Muy larga duración
}


def generar_stock() -> int:
    """
    Genera unidades en stock con distribución realista:
      15% → agotado (0 unidades)
      25% → stock bajo (1-9 unidades) — riesgo de quiebre
      60% → stock normal (10-300 unidades)
    """
    r = random.random()
    if r < 0.15:
        return 0
    elif r < 0.40:
        return random.randint(1, 9)
    else:
        return random.randint(10, 300)


print("Generando productos...")
cats_lista  = list(PESO_CATEGORIAS.keys())
cats_pesos  = list(PESO_CATEGORIAS.values())

# Productos base: atributos intrínsecos (iguales en todas las sedes)
productos_base = []
for _ in range(N_PRODUCTOS):
    categoria       = random.choices(cats_lista, weights=cats_pesos, k=1)[0]
    p_min, p_max    = PRECIO_RANGO_POR_CATEGORIA[categoria]
    precio_unitario = round2(random.uniform(p_min, p_max))
    costo_unitario  = round2(precio_unitario * random.uniform(0.40, 0.75))

    # Fecha de ingreso al catálogo: entre 2022 y finales de 2025
    fecha_ingreso   = rand_date(date(2022, 1, 1), date(2025, 12, 31))

    # Fecha de caducidad: según categoría
    d_min, d_max    = CADUCIDAD_RANGO_POR_CATEGORIA[categoria]
    fecha_caducidad = date.today() + timedelta(days=random.randint(d_min, d_max))

    sede_origen  = random.choice(SEDES)
    sedes_prod   = elegir_sedes_producto(sede_origen)

    productos_base.append({
        "producto_id":            rand_id("PROD"),
        "categoria_producto":     categoria,
        "precio_unitario":        precio_unitario,
        "COSTO_UNITARIO":         costo_unitario,
        "fecha_ingreso_catalogo": fecha_ingreso.isoformat(),
        "fecha_min_caducidad":    fecha_caducidad.isoformat(),
        "_sedes_list":            sedes_prod,   # interno — no se escribe al CSV
    })

dedup_ids(productos_base, "producto_id", "PROD")

# Expandir a una fila por (producto_id, sede)
productos = []
for p in productos_base:
    for sede in p["_sedes_list"]:
        productos.append({
            "producto_id":            p["producto_id"],
            "sede":                   sede,
            "categoria_producto":     p["categoria_producto"],
            "precio_unitario":        p["precio_unitario"],
            "COSTO_UNITARIO":         p["COSTO_UNITARIO"],
            "stock":                  generar_stock(),
            "dias_en_stock":          random.randint(0, 180),
            "fecha_ingreso_catalogo": p["fecha_ingreso_catalogo"],
            "fecha_min_caducidad":    p["fecha_min_caducidad"],
        })

# Índices para acceso rápido
productos_ids  = [p["producto_id"] for p in productos_base]
precio_map     = {p["producto_id"]: p["precio_unitario"] for p in productos_base}
stock_por_sede = {
    (row["producto_id"], row["sede"]): row["stock"]
    for row in productos
}

PROD_FIELDNAMES = [
    "producto_id", "sede", "categoria_producto", "precio_unitario",
    "COSTO_UNITARIO", "stock", "dias_en_stock",
    "fecha_ingreso_catalogo", "fecha_min_caducidad",
]

with open(OUTPUT_DIR / "productos.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=PROD_FIELDNAMES)
    writer.writeheader()
    writer.writerows(productos)

n_base = len(productos_base)
n_rows = len(productos)
print(f"  ✔ productos.csv  ({n_base} productos únicos → {n_rows} filas con sede)")

# Índices de productos disponibles por sede
prods_por_sede       = {s: [] for s in SEDES}
prods_con_stock_sede = {s: [] for s in SEDES}

for row in productos:
    prods_por_sede[row["sede"]].append(row["producto_id"])
    if row["stock"] > 0:
        prods_con_stock_sede[row["sede"]].append(row["producto_id"])

for sede in SEDES:
    total  = len(prods_por_sede[sede])
    con_st = len(prods_con_stock_sede[sede])
    print(f"    {sede:<12}: {total:>4} disponibles  |  {con_st:>4} con stock > 0")


# ──────────────────────────────────────────────────────────────────────────────
# PERFILES DE FAVORITOS POR CLIENTE
# ──────────────────────────────────────────────────────────────────────────────
# Cada cliente tiene un conjunto de productos favoritos que compra regularmente.
# Los favoritos se seleccionan respetando:
#   - El rubro del cliente (un Restaurante prefiere Carnes, Verduras, etc.)
#   - La sede del cliente (solo productos disponibles en su ciudad)
# 70% de favoritos son de categorías afines al rubro, 30% de otras categorías.

CATEGORIAS_POR_RUBRO = {
    "Restaurante":  ["Carnes", "Verduras", "Abarrotes", "Bebidas", "Lácteos", "Frutas"],
    "Panadería":    ["Panadería", "Lácteos", "Abarrotes", "Bebidas"],
    "Supermercado": ["Lácteos", "Bebidas", "Snacks", "Abarrotes", "Limpieza", "Congelados"],
    "Minimarket":   ["Bebidas", "Snacks", "Abarrotes", "Limpieza"],
    "Cafetería":    ["Panadería", "Bebidas", "Lácteos", "Snacks"],
    "Hotel":        ["Lácteos", "Bebidas", "Frutas", "Carnes", "Limpieza", "Abarrotes"],
    "Catering":     ["Carnes", "Verduras", "Frutas", "Abarrotes", "Bebidas", "Lácteos"],
    "Bodega":       ["Abarrotes", "Bebidas", "Snacks", "Limpieza"],
    "Farmacia":     ["Limpieza", "Abarrotes", "Bebidas"],
    "Ferretería":   ["Limpieza", "Abarrotes", "Bebidas"],
    "Bar":          ["Bebidas", "Snacks", "Abarrotes", "Lácteos"],
    "Fast Food":    ["Carnes", "Panadería", "Bebidas", "Snacks", "Abarrotes", "Verduras"],
}

# Índice: productos agrupados por (categoría, sede)
prods_cat_sede: dict[tuple, list] = {}
for p in productos_base:
    cat = p["categoria_producto"]
    for sede in p["_sedes_list"]:
        prods_cat_sede.setdefault((cat, sede), []).append(p["producto_id"])


def asignar_favoritos(rubro: str, sede: str) -> list[str]:
    """
    Construye el perfil de productos favoritos para un cliente.

    Lógica:
        - n_favs: número de favoritos a asignar (entre FAVORITOS_MIN y MAX)
        - 70% de favoritos de categorías afines al rubro del cliente
        - 30% de favoritos de otras categorías (simula necesidades secundarias)
        - Solo se incluyen productos disponibles en la sede del cliente

    Args:
        rubro: Tipo de negocio del cliente.
        sede: Ciudad del cliente.

    Returns:
        Lista de producto_ids favoritos.
    """
    n_favs = random.randint(FAVORITOS_MIN, FAVORITOS_MAX)

    cats_afines = CATEGORIAS_POR_RUBRO.get(rubro, CATEGORIAS)
    cats_otras  = [c for c in CATEGORIAS if c not in cats_afines]

    n_afines = max(1, int(n_favs * 0.70))
    n_otras  = n_favs - n_afines

    pool_afines = list({
        pid
        for cat in cats_afines
        for pid in prods_cat_sede.get((cat, sede), [])
    })
    pool_otras = list({
        pid
        for cat in cats_otras
        for pid in prods_cat_sede.get((cat, sede), [])
    })

    favoritos = random.sample(pool_afines, k=min(n_afines, len(pool_afines)))
    if pool_otras and n_otras > 0:
        favoritos += random.sample(pool_otras, k=min(n_otras, len(pool_otras)))

    return favoritos


perfil_cliente: dict[str, dict] = {}
for c in clientes:
    perfil_cliente[c["cliente_id"]] = {
        "rubro":     c["rubro_cliente"],
        "sede":      c["sede_cliente"],
        "favoritos": asignar_favoritos(c["rubro_cliente"], c["sede_cliente"]),
    }

total_favs = sum(len(v["favoritos"]) for v in perfil_cliente.values())
print(f"\n  Promedio de favoritos por cliente: {total_favs / N_CLIENTES:.1f}")


# ──────────────────────────────────────────────────────────────────────────────
# 3. VENTAS + 4. DETALLE_VENTA
# ──────────────────────────────────────────────────────────────────────────────
# Patrones estacionales simulados (índice por mes 1-12):
#   Alta temporada: mayo-agosto (meses de verano austral y festividades)
#   y noviembre-diciembre (fiestas de fin de año).
#   Baja temporada: enero-marzo (inicio de año, menor actividad comercial).

PESOS_ESTACIONALES = [
    0.7,   # Enero
    0.7,   # Febrero
    0.8,   # Marzo
    0.9,   # Abril
    1.2,   # Mayo     (Día del Trabajador, Día de la Madre)
    1.3,   # Junio    (Día del Padre, Fiestas Patrias)
    1.4,   # Julio    (Fiestas Patrias, alta temporada)
    1.3,   # Agosto   (Santa Rosa)
    1.0,   # Septiembre
    1.0,   # Octubre
    1.2,   # Noviembre (pre-Navidad)
    1.5,   # Diciembre (Navidad, Año Nuevo)
]

print("\nGenerando ventas y detalle_venta...")
ventas         = []
detalle_venta  = []
seen_venta_ids: set = set()

for _ in range(N_VENTAS):
    # Generar ID de venta único
    venta_id = rand_id("VTA", 8)
    while venta_id in seen_venta_ids:
        venta_id = rand_id("VTA", 8)
    seen_venta_ids.add(venta_id)

    cliente_id  = random.choice(clientes_ids)
    fecha_venta = rand_date(
        FECHA_INICIO_VENTAS,
        FECHA_FIN_VENTAS,
        weights=PESOS_ESTACIONALES,
    )

    perfil          = perfil_cliente[cliente_id]
    favoritos       = perfil["favoritos"]
    sede_cli        = perfil["sede"]
    # Para exploración (20% del tiempo), elegimos de productos con stock en la sede
    candidatos_sede = prods_con_stock_sede[sede_cli] or prods_por_sede[sede_cli]

    n_items = random.randint(N_DETALLE_MIN, N_DETALLE_MAX)

    seleccionados: set = set()
    prods_venta: list  = []

    intentos = 0
    while len(prods_venta) < n_items and intentos < n_items * 15:
        intentos += 1
        if favoritos and random.random() < PROB_FAVORITO:
            candidato = random.choice(favoritos)
        else:
            candidato = (
                random.choice(candidatos_sede)
                if candidatos_sede
                else random.choice(productos_ids)
            )

        if candidato not in seleccionados:
            seleccionados.add(candidato)
            prods_venta.append(candidato)

    # Cantidad por línea: distribución asimétrica (la mayoría piden 1-10 unidades,
    # pero pedidos grandes son posibles para distribuidores)
    monto_total = 0.0
    for prod_id in prods_venta:
        # 70% pedidos pequeños (1-10), 30% pedidos grandes (11-50)
        if random.random() < 0.70:
            cantidad = random.randint(1, 10)
        else:
            cantidad = random.randint(11, 50)

        precio   = precio_map[prod_id]
        subtotal = round2(cantidad * precio)
        monto_total += subtotal

        detalle_venta.append({
            "venta_id":          venta_id,
            "producto_id":       prod_id,
            "cantidad_producto": cantidad,
            "subtotal":          subtotal,
        })

    ventas.append({
        "venta_id":    venta_id,
        "cliente_id":  cliente_id,
        "fecha_venta": fecha_venta.isoformat(),
        "monto_total": round2(monto_total),
    })

with open(OUTPUT_DIR / "ventas.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(
        f, fieldnames=["venta_id", "cliente_id", "fecha_venta", "monto_total"]
    )
    writer.writeheader()
    writer.writerows(ventas)

print(f"  ✔ ventas.csv        ({len(ventas)} filas)")

with open(OUTPUT_DIR / "detalle_venta.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(
        f, fieldnames=["venta_id", "producto_id", "cantidad_producto", "subtotal"]
    )
    writer.writeheader()
    writer.writerows(detalle_venta)

print(f"  ✔ detalle_venta.csv ({len(detalle_venta)} filas)")


# ──────────────────────────────────────────────────────────────────────────────
# VERIFICACIONES
# ──────────────────────────────────────────────────────────────────────────────
print("\n── Verificaciones ──────────────────────────────────────────────────────────")

# 1. Tasa de recompra
cliente_por_venta = {v["venta_id"]: v["cliente_id"] for v in ventas}
cp_counter = Counter()
for d in detalle_venta:
    cid = cliente_por_venta[d["venta_id"]]
    cp_counter[(cid, d["producto_id"])] += 1

recompras   = sum(1 for v in cp_counter.values() if v > 1)
total_pares = len(cp_counter)
pct_recompra = recompras / total_pares * 100

print(f"  Pares únicos (cliente, producto):   {total_pares:,}")
print(f"  Pares con recompra (> 1 vez):       {recompras:,}  ({pct_recompra:.1f}%)")
print(f"  Pares con compra única:             {total_pares - recompras:,}  ({100 - pct_recompra:.1f}%)")
print(f"  Densidad matriz (cliente × prod):   {total_pares / (N_CLIENTES * N_PRODUCTOS) * 100:.2f}%")

# 2. Consistencia de sede
sede_cli_map   = {c["cliente_id"]: c["sede_cliente"] for c in clientes}
sedes_prod_map = {p["producto_id"]: set(p["_sedes_list"]) for p in productos_base}

violaciones_sede = sum(
    1
    for d in detalle_venta
    if sede_cli_map[cliente_por_venta[d["venta_id"]]]
    not in sedes_prod_map.get(d["producto_id"], set())
)

print(f"\n  Violaciones sede cliente ↔ producto: {violaciones_sede}  (esperado: 0)")

# 3. Distribución mensual de ventas (validar estacionalidad)
meses_ventas = Counter(v["fecha_venta"][:7] for v in ventas)
meses_ord    = sorted(meses_ventas.items())
print("\n  Distribución mensual de ventas (valida estacionalidad):")
for ym, cnt in meses_ord:
    bar = "█" * (cnt // 20)
    print(f"    {ym}: {cnt:>4} ventas  {bar}")

# 4. Distribución de rubros
rubros_dist = Counter(c["rubro_cliente"] for c in clientes)
print(f"\n  Distribución de rubros:")
for rubro, cnt in sorted(rubros_dist.items(), key=lambda x: -x[1]):
    print(f"    {rubro:<18}: {cnt:>3} clientes")

print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║  VARIABLES GENERADAS                                                         ║
╠══════════════════════════════╦══════════════╦══════════════════════════════╣
║ Variable                     ║ Tipo         ║ Archivo                      ║
╠══════════════════════════════╬══════════════╬══════════════════════════════╣
║ cliente_id                   ║ string (PK)  ║ clientes.csv                 ║
║ rubro_cliente                ║ categórica   ║ clientes.csv                 ║
║ subrubro_1                   ║ categórica   ║ clientes.csv                 ║
║ subrubro_2                   ║ categórica   ║ clientes.csv                 ║
║ sede_cliente                 ║ categórica   ║ clientes.csv                 ║
╠══════════════════════════════╬══════════════╬══════════════════════════════╣
║ producto_id  ┐ clave         ║ string (PK)  ║ productos.csv                ║
║ sede         ┘ compuesta     ║ categórica   ║ productos.csv                ║
║ categoria_producto           ║ categórica   ║ productos.csv                ║
║ precio_unitario              ║ float (soles)║ productos.csv                ║
║ COSTO_UNITARIO               ║ float (soles)║ productos.csv                ║
║ stock                        ║ entero (ud.) ║ productos.csv                ║
║ dias_en_stock                ║ entero (días)║ productos.csv                ║
║ fecha_ingreso_catalogo       ║ date         ║ productos.csv                ║
║ fecha_min_caducidad          ║ date         ║ productos.csv                ║
╠══════════════════════════════╬══════════════╬══════════════════════════════╣
║ venta_id                     ║ string (PK)  ║ ventas.csv                   ║
║ cliente_id (FK → clientes)   ║ string       ║ ventas.csv                   ║
║ fecha_venta                  ║ date         ║ ventas.csv                   ║
║ monto_total                  ║ float (soles)║ ventas.csv                   ║
╠══════════════════════════════╬══════════════╬══════════════════════════════╣
║ venta_id (FK → ventas)       ║ string       ║ detalle_venta.csv            ║
║ producto_id (FK → productos) ║ string       ║ detalle_venta.csv            ║
║ cantidad_producto            ║ entero (ud.) ║ detalle_venta.csv            ║
║ subtotal                     ║ float (soles)║ detalle_venta.csv            ║
╠══════════════════════════════╬══════════════╬══════════════════════════════╣
║ VARIABLES DE FEATURE ENGINEERING (calculadas en 01_dataset.ipynb):          ║
║  mes, semana_anio, es_feriado   → temporalidad de la venta                  ║
║  frecuencia_compra              → compras/mes del cliente                   ║
║  ticket_promedio                → gasto promedio por pedido del cliente      ║
║  descuento_aplicado             → % diferencia precio_unitario vs subtotal   ║
║  dias_para_vencer               → días hasta vencimiento del lote            ║
║  rotacion_diaria                → unidades vendidas por día desde 1ª venta   ║
║  baja_rotacion                  → flag: cuartil inferior de rotación         ║
╚══════════════════════════════════════════════════════════════════════════════╝
""")

print(f"\nArchivos guardados en: {OUTPUT_DIR}")
print("Listo. Ejecuta el notebook notebooks/01_dataset.ipynb para el siguiente paso.")
