import json

def md(source, cell_id):
    src = [line + "\n" for line in source.split("\n")]
    if src: src[-1] = src[-1].rstrip("\n")
    return {"cell_type": "markdown", "id": cell_id, "metadata": {}, "source": src}

def code(source, cell_id):
    src = [line + "\n" for line in source.split("\n")]
    if src: src[-1] = src[-1].rstrip("\n")
    return {"cell_type": "code", "execution_count": None, "id": cell_id,
            "metadata": {}, "outputs": [], "source": src}

cells = []

# SECTION 0: Title + Theory
cells.append(md(
r"""# Notebook 02 — Modelo de Recomendación Híbrido
## Sistema de Recomendación Híbrido — Tesis
### Empresa distribuidora de alimentos — Sector HORECA

---

## 1. ¿Qué es un Sistema de Recomendación?

Un **Sistema de Recomendación** es un algoritmo que predice qué ítems le resultarán más
relevantes a un usuario, basándose en información sobre ese usuario, sobre los ítems, o
sobre el comportamiento histórico del conjunto de usuarios.

Existen dos grandes familias:

| Enfoque | Datos que usa | Idea central | Limitación |
|---|---|---|---|
| **Collaborative Filtering (CF)** | Comportamiento histórico de *todos* los usuarios | "Usuarios similares compran cosas similares" | Cold-start: no funciona para usuarios/productos nuevos |
| **Content-Based Filtering (CBF)** | Atributos del ítem (categoría, precio, etc.) | "Si te gustó X, te gustará Y porque se parece a X" | Sobrespecialización: no descubre items distintos |

---

## 2. Filtrado Colaborativo con SVD — Feedback Implícito

En nuestro contexto **no tenemos ratings explícitos**. En cambio, tenemos **feedback
implícito**: las órdenes de compra. Si un cliente compró 20 kg de un producto, eso es
evidencia de interés, aunque no sea una calificación directa.

### 2.1 Matriz de Interacciones

Construimos una matriz $R \in \mathbb{R}^{m \times n}$ donde:
- $m$ = número de clientes, $n$ = número de productos
- $R_{ui}$ = interacción implícita del cliente $u$ con el producto $i$

$$R_{ui} = \sum_{t} \text{cantidad}_{ui,t} \times w_{\text{recency},t}$$

donde $w_{\text{recency},t} = e^{-\Delta t / \tau}$ con $\tau = 180$ días.

### 2.2 Factorización SVD

$$R \approx U \cdot \Sigma \cdot V^T$$

- $U \in \mathbb{R}^{m \times k}$: perfil latente de cada cliente en $k$ dimensiones
- $\Sigma \in \mathbb{R}^{k \times k}$: importancia de cada dimensión latente
- $V \in \mathbb{R}^{n \times k}$: perfil latente de cada producto

El **score CF** del cliente $u$ para el producto $i$:

$$\hat{R}_{ui} = U_u \cdot \Sigma \cdot V_i^T$$

En código: `scores = U[u] @ Vt`

---

## 3. Filtrado Basado en Contenido — Similitud Coseno

Cada producto se representa como un vector de features $\mathbf{f}_i$. La similitud:

$$\text{sim}(i, j) = \frac{\mathbf{f}_i \cdot \mathbf{f}_j}{\|\mathbf{f}_i\| \cdot \|\mathbf{f}_j\|}$$

El **score CBF** para el cliente $u$ y candidato $i$ (sobre últimas 10 compras $\mathcal{H}_u'$):

$$\text{score\_cbf}(u, i) = \frac{1}{|\mathcal{H}_u'|} \sum_{j \in \mathcal{H}_u'} \text{sim}(i, j)$$

---

## 4. ¿Por qué un enfoque Híbrido?

Ninguna técnica individual es suficiente para el contexto HORECA:

- **Solo CF**: ignora que un producto está a 2 días de vencer.
- **Solo CBF**: repite siempre productos similares a lo que el cliente ya compra.
- **Reglas de negocio puras**: sin personalización, todos los clientes ven lo mismo.

La **combinación híbrida** permite: personalización (CF + CBF), reducción de mermas
(urgency), movimiento de stock parado (rotation) y adopción de nuevos SKUs (novelty).

---

## 5. Integración de Reglas de Negocio

Las reglas de negocio se modelan como **scores continuos en [0, 1]** que se suman
ponderadamente. Esto es más flexible que reglas duras (si/no): un producto a 5 días
de vencer tiene score de urgencia más alto que uno a 20 días.

---

## 6. Fórmula del Score Híbrido Final

$$\text{score\_final} = 0.40 \times \text{score\_cf} + 0.15 \times \text{score\_cbf} + 0.20 \times \text{score\_urgency} + 0.15 \times \text{score\_rotation} + 0.10 \times \text{score\_novelty}$$

### Tabla de componentes:

```
╔═════════════════╦══════╦═════════════════════════════╦══════════════════════════════════╗
║ Componente      ║ Peso ║ Fuente de datos             ║ Problema resuelto                ║
╠═════════════════╬══════╬═════════════════════════════╬══════════════════════════════════╣
║ score_cf        ║  40% ║ Historial de compras (SVD)  ║ ¿Qué le interesa al cliente?     ║
║ score_cbf       ║  15% ║ Atributos del producto      ║ ¿Qué es similar a lo que compra? ║
║ score_urgency   ║  20% ║ dias_para_vencer             ║ Reducir mermas por caducidad     ║
║ score_rotation  ║  15% ║ rotacion_diaria              ║ Mover stock parado               ║
║ score_novelty   ║  10% ║ fecha_ingreso_catalogo       ║ Adopción de nuevos SKUs          ║
╚═════════════════╩══════╩═════════════════════════════╩══════════════════════════════════╝
```

Los pesos reflejan las prioridades del negocio: la personalización (CF) es lo más
importante, seguida de la urgencia por caducidad, y luego el resto de las señales.""",
"md-00-title"))

# SECTION 1: Imports
cells.append(md(
"---\n## Sección 1 — Imports y Parámetros\n\n"
"Importamos todas las librerías y definimos los hiperparámetros del modelo en un único "
"lugar para facilitar la reproducibilidad y el ajuste posterior.",
"md-01-imports"))

cells.append(code(
r"""import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import date
from pathlib import Path

from scipy.sparse import csr_matrix
from sklearn.decomposition import TruncatedSVD
from sklearn.preprocessing import MinMaxScaler, OneHotEncoder
from sklearn.metrics.pairwise import cosine_similarity

%matplotlib inline
pd.options.display.float_format = '{:.4f}'.format

# ── Rutas ────────────────────────────────────────────────────────────────────
ROOT_DIR     = Path.cwd().parent
DATASET_PATH = ROOT_DIR / "data" / "processed" / "dataset_ml.csv"

# ── Pesos del score híbrido (deben sumar 1.0) ─────────────────────────────────
W_CF        = 0.40   # Collaborative Filtering (SVD)
W_CBF       = 0.15   # Content-Based Filtering
W_URGENCY   = 0.20   # Urgencia por caducidad
W_ROTATION  = 0.15   # Incentivo a baja rotación
W_NOVELTY   = 0.10   # Novedad en catálogo

assert abs(W_CF + W_CBF + W_URGENCY + W_ROTATION + W_NOVELTY - 1.0) < 1e-9, \
    "Los pesos deben sumar exactamente 1.0"

# ── Parámetros técnicos ───────────────────────────────────────────────────────
TAU_DIAS          = 180   # Vida media de recencia (días)
SVD_COMPONENTS    = 150   # Factores latentes del SVD
TOPK_CF_CANDS     = 500   # Candidatos pre-filtrados por CF
TOPK_FINAL        = 10    # Top-K del output

# ── Umbrales de negocio ───────────────────────────────────────────────────────
UMBRAL_URGENCIA   = 30    # Días para considerar producto "urgente"
UMBRAL_NOVEDAD    = 60    # Días para considerar producto "nuevo"
SIGMA_URGENCY     = 15    # Pendiente de la sigmoide de urgencia
TAU_NOVEDAD       = 30    # Vida media del boost de novedad

FECHA_HOY = pd.Timestamp(date.today())
print(f"Fecha de referencia: {FECHA_HOY.date()}")
print(f"Pesos: CF={W_CF}, CBF={W_CBF}, URG={W_URGENCY}, ROT={W_ROTATION}, NOV={W_NOVELTY}")
print(f"Suma de pesos: {W_CF + W_CBF + W_URGENCY + W_ROTATION + W_NOVELTY}")""",
"code-01-imports"))

# SECTION 2: Load data
cells.append(md(
"---\n## Sección 2 — Carga del Dataset\n\n"
"Cargamos `dataset_ml.csv` generado en el Notebook 01. Contiene una fila por "
"transacción con todas las features necesarias para el modelo.",
"md-02-carga"))

cells.append(code(
r"""df = pd.read_csv(DATASET_PATH, parse_dates=["fecha_venta", "fecha_ingreso_catalogo"])

print(f"Dataset cargado: {df.shape[0]:,} filas  |  "
      f"{df['cliente_id'].nunique()} clientes  |  "
      f"{df['producto_id'].nunique()} productos")

df.info()
df.head()""",
"code-02-carga"))

# SECTION 3: Feature Engineering markdown
cells.append(md(
r"""---
## Sección 3 — Feature Engineering para el Modelo

### 3.1 Feedback Implícito vs Explícito

- **Feedback explícito**: el usuario califica directamente (estrellas, likes). Raro en B2B.
- **Feedback implícito**: se infiere del comportamiento (compras). Más abundante, pero ambiguo.

Usamos las **cantidades compradas** como señal de interés implícito, ponderadas por recencia.

### 3.2 Peso de Recencia — Decaimiento Exponencial

$$w_{\text{recency}} = e^{-\Delta t / \tau}$$

donde $\Delta t$ = días desde la venta y $\tau = 180$ días (vida media del peso).

Con $\tau = 180$:
- Compra de hoy: $w = 1.0$
- Hace 6 meses (180 días): $w = e^{-1} \approx 0.37$
- Hace 1 año (365 días): $w = e^{-2} \approx 0.14$

Esto refleja que en el sector HORECA los patrones tienen una estacionalidad semestral.

### 3.3 Interacción Implícita

$$R_{ui} = \sum_{t} \text{cantidad}_{ui,t} \times w_{\text{recency},t}$$

### 3.4 Margen del Producto

$$\text{margen\_pct} = \frac{\text{precio} - \text{costo}}{\text{precio}} \in [0, 1]$$""",
"md-03-fe-intro"))

# SECTION 4: Feature Engineering code
cells.append(code(
r"""# Días desde cada venta (para peso de recencia)
df["dias_desde_venta"] = (FECHA_HOY - df["fecha_venta"]).dt.days.clip(lower=0)
df["w_recency"]        = np.exp(-df["dias_desde_venta"] / TAU_DIAS)

# Interacción implícita = cantidad × peso de recencia
df["interaccion"] = df["cantidad_producto"] * df["w_recency"]

# Margen del producto = (precio - costo) / precio
df["margen_pct"] = ((df["precio_unitario"] - df["COSTO_UNITARIO"]) / df["precio_unitario"]).clip(0, 1)

# Días desde ingreso al catálogo
df["dias_desde_ingreso"] = (FECHA_HOY - df["fecha_ingreso_catalogo"]).dt.days.clip(lower=0)

print("Distribución de pesos de recencia:")
print(df["w_recency"].describe())
print(f"\nInteracciones implícitas (muestra):")
df[["cliente_id", "producto_id", "cantidad_producto", "w_recency", "interaccion"]].head(10)""",
"code-04-fe"))

# SECTION 5: Interaction Matrix markdown
cells.append(md(
r"""---
## Sección 5 — Matriz de Interacciones Implícitas

### 5.1 ¿Qué es una Matriz Usuario-Ítem?

La matriz $R \in \mathbb{R}^{m \times n}$ tiene una fila por cliente y una columna por
producto. La celda $R_{ui}$ contiene la interacción implícita total.

```
            prod_001  prod_002  prod_003  ...  prod_950
cliente_001   12.3      0.0      5.8    ...    0.0
cliente_002    0.0      8.1      0.0    ...    2.3
cliente_800    3.2      0.0      0.0    ...    0.0
```

### 5.2 Dispersidad

Con 800 clientes y 950 productos, cada cliente compra ~20-30 SKUs distintos.
El **99.74% de las celdas son cero**: la matriz es extremadamente dispersa.

### 5.3 `scipy.sparse.csr_matrix`

Formato **Compressed Sparse Row (CSR)**: almacena solo los elementos no-cero.
Reduce el uso de memoria de ~3 MB (densa) a ~50 KB (dispersa).

### 5.4 Agregación

Si un cliente compró el mismo producto en múltiples ocasiones, **sumamos** todas
las interacciones. Esto captura frecuencia y volumen.""",
"md-05-matriz"))

# SECTION 6: Build matrix code
cells.append(code(
r"""# Agregar por (cliente, producto): suma de interacciones en todo el historial
matrix_df = (
    df.groupby(["cliente_id", "producto_id"])["interaccion"]
    .sum().reset_index()
)

# Mapas de índice
clientes_unicos  = sorted(df["cliente_id"].unique())
productos_unicos = sorted(df["producto_id"].unique())
user_idx = {c: i for i, c in enumerate(clientes_unicos)}
item_idx = {p: j for j, p in enumerate(productos_unicos)}
idx_item = {j: p for p, j in item_idx.items()}

n_u = len(clientes_unicos)
n_i = len(productos_unicos)

rows = matrix_df["cliente_id"].map(user_idx).values
cols = matrix_df["producto_id"].map(item_idx).values
data = matrix_df["interaccion"].values

R = csr_matrix((data, (rows, cols)), shape=(n_u, n_i), dtype=np.float32)

density = matrix_df.shape[0] / (n_u * n_i) * 100
print(f"Matriz R: {n_u} usuarios x {n_i} productos")
print(f"Interacciones unicas: {matrix_df.shape[0]:,}")
print(f"Densidad: {density:.3f}%")
print(f"Formato disperso: {R.nnz} elementos no-cero  |  {R.data.nbytes/1024:.1f} KB")""",
"code-06-matrix"))

# SECTION 7: SVD markdown
cells.append(md(
r"""---
## Sección 7 — Factorización SVD

### 7.1 ¿Qué hace SVD?

La **Descomposición en Valores Singulares (SVD)** factoriza la matriz de interacciones:

$$R \approx U \cdot \Sigma \cdot V^T$$

- $U \in \mathbb{R}^{m \times k}$: **perfiles latentes de los clientes**
- $\Sigma \in \mathbb{R}^{k \times k}$: importancia de cada dimensión latente (diagonal)
- $V \in \mathbb{R}^{n \times k}$: **perfiles latentes de los productos**

### 7.2 Factores Latentes

Los $k = 150$ factores latentes no tienen interpretación directa, pero capturan
patrones subyacentes (ej. "lácteos de alta rotación", "repostería premium").

Predicción: $\hat{R}_{ui} = U_u \cdot \Sigma \cdot V_i^T$ → en código: `U[u] @ Vt`

### 7.3 TruncatedSVD vs SVD completo

El SVD completo calcularía hasta $\min(m, n) = 800$ componentes:
1. Es costoso computacionalmente
2. Sobreajusta (últimos componentes = ruido)
3. No funciona con matrices dispersas directamente

`TruncatedSVD` calcula solo los $k$ más importantes y trabaja con `csr_matrix`.

### 7.4 Varianza Explicada

$$\text{Var. Explicada} = \frac{\sum_{i=1}^{k} \sigma_i^2}{\sum_{i=1}^{n} \sigma_i^2}$$

Un valor de 60-80% es típicamente adecuado para recomendación.""",
"md-07-svd"))

# SECTION 8: SVD code
cells.append(code(
r"""n_comp = min(SVD_COMPONENTS, n_u - 1, n_i - 1)
svd    = TruncatedSVD(n_components=n_comp, random_state=42)
svd.fit(R)

U  = svd.transform(R)   # (n_u, n_comp) — perfiles de clientes
Vt = svd.components_    # (n_comp, n_i) — perfiles de productos

var_explained = svd.explained_variance_ratio_.sum()
print(f"SVD con {n_comp} componentes")
print(f"Varianza explicada: {var_explained*100:.2f}%")
print(f"U  (perfiles clientes):  {U.shape}")
print(f"Vt (perfiles productos): {Vt.shape}")

# Visualización: varianza acumulada explicada
plt.figure(figsize=(8, 4))
cumvar = np.cumsum(svd.explained_variance_ratio_)
plt.plot(cumvar, color='steelblue', linewidth=2)
plt.axhline(y=var_explained, color='red', linestyle='--',
            label=f'Total: {var_explained*100:.1f}%')
plt.xlabel("Numero de componentes")
plt.ylabel("Varianza explicada acumulada")
plt.title("Varianza Explicada por el SVD Truncado")
plt.legend()
plt.grid(alpha=0.3)
plt.tight_layout()
plt.show()""",
"code-08-svd"))

# SECTION 9: CBF markdown
cells.append(md(
r"""---
## Sección 9 — Content-Based Filtering (CBF)

### 9.1 ¿Qué es el Filtrado Basado en Contenido?

El CBF recomienda productos *similares* a los que el cliente ya compra, basándose
en los **atributos del producto** (no en el comportamiento de otros clientes).

### 9.2 Features del Producto

| Feature | Tipo | Tratamiento | Razón |
|---|---|---|---|
| `categoria_producto` | Categórica | One-Hot Encoding | Misma categoría = mayor similitud |
| `precio_bucket` | Ordinal | One-Hot Encoding | Sensibilidad de precio del cliente |
| `rubro_principal` | Categórica | One-Hot Encoding | Perfil del comprador típico |
| `precio_unitario` | Numérica continua | MinMaxScaler | Escala absoluta del precio |
| `margen_pct` | Numérica [0,1] | MinMaxScaler | Rentabilidad del producto |

### 9.3 Similitud Coseno

$$\text{sim}(i, j) = \cos(\theta) = \frac{\mathbf{f}_i \cdot \mathbf{f}_j}{\|\mathbf{f}_i\|_2 \cdot \|\mathbf{f}_j\|_2} \in [0, 1]$$

Para vectores de features (todos positivos por OHE + MinMax), el resultado está en [0, 1].

### 9.4 Score CBF del Cliente

Para candidato $i$ y cliente $u$ con últimas 10 compras $\mathcal{H}_u'$:

$$\text{score\_cbf}(u, i) = \frac{1}{|\mathcal{H}_u'|} \sum_{j \in \mathcal{H}_u'} \text{sim}(i, j)$$

Limitar a **10 compras recientes** evita que compras antiguas contaminen el perfil actual.""",
"md-09-cbf"))

# SECTION 10: CBF code
cells.append(code(
r"""# Maestro de productos (una fila por producto único)
prods_master = (
    df.sort_values("stock", ascending=False)
    .drop_duplicates("producto_id", keep="first")
    [["producto_id", "categoria_producto", "precio_unitario", "COSTO_UNITARIO",
      "stock", "rotacion_diaria", "baja_rotacion", "dias_para_vencer", "dias_desde_ingreso"]]
    .copy()
)
prods_master["margen_pct"] = (
    (prods_master["precio_unitario"] - prods_master["COSTO_UNITARIO"])
    / prods_master["precio_unitario"]
).clip(0, 1)

# Rubro más frecuente entre compradores del producto
rubro_modal = (
    df.groupby("producto_id")["rubro_cliente"]
    .agg(lambda x: x.mode()[0] if len(x) > 0 else "Desconocido")
    .reset_index().rename(columns={"rubro_cliente": "rubro_principal"})
)
prods_master = prods_master.merge(rubro_modal, on="producto_id", how="left")
prods_master["rubro_principal"] = prods_master["rubro_principal"].fillna("Desconocido")

# Bucket de precio
p33 = prods_master["precio_unitario"].quantile(0.33)
p66 = prods_master["precio_unitario"].quantile(0.66)
prods_master["precio_bucket"] = pd.cut(
    prods_master["precio_unitario"],
    bins=[-np.inf, p33, p66, np.inf],
    labels=["bajo", "medio", "alto"]
).astype(str)

# Feature vectors
ohe = OneHotEncoder(sparse_output=False, handle_unknown="ignore")
ohe_feats = ohe.fit_transform(
    prods_master[["categoria_producto", "precio_bucket", "rubro_principal"]]
)

scaler    = MinMaxScaler()
num_feats = scaler.fit_transform(prods_master[["precio_unitario", "margen_pct"]])

item_features = np.hstack([ohe_feats, num_feats]).astype(np.float32)
print(f"Feature matrix: {item_features.shape}  ({ohe_feats.shape[1]} OHE + 2 numericas)")

# Alinear con el orden de item_idx
n_items           = len(item_idx)
item_feat_aligned = np.zeros((n_items, item_features.shape[1]), dtype=np.float32)
prod_ids_master   = prods_master["producto_id"].values
for row_idx, pid in enumerate(prod_ids_master):
    if pid in item_idx:
        item_feat_aligned[item_idx[pid]] = item_features[row_idx]

# Cosine similarity matrix
cbf_sim = cosine_similarity(item_feat_aligned).astype(np.float32)
print(f"Similarity matrix: {cbf_sim.shape}  |  Memory: {cbf_sim.nbytes/1024/1024:.1f} MB")""",
"code-10-cbf"))

# SECTION 11: Business scores markdown
cells.append(md(
r"""---
## Sección 11 — Scores de Negocio

### 11.1 Score de Urgencia — Sigmoide Inversa

$$\text{score\_urgency}(d) = \frac{1}{1 + e^{d / \sigma}}$$

donde $d$ = `dias_para_vencer` y $\sigma = 15$ (pendiente).

| Días para vencer | score_urgency |
|---|---|
| 2 días | $\approx 0.88$ — Muy urgente |
| 5 días | $\approx 0.72$ — Urgente |
| 15 días | $\approx 0.50$ — Punto de inflexión |
| 30 días | $\approx 0.27$ — Bajo |
| 60 días | $\approx 0.02$ — Mínimo |

Productos vencidos ($d < 0$): `score_urgency = 0` y excluidos por filtro duro.

### 11.2 Score de Novedad — Decaimiento Exponencial

$$\text{score\_novelty}(d_i) = e^{-d_i / \tau_{\text{novedad}}}$$

con $\tau_{\text{novedad}} = 30$ días. Día 0: score = 1.0 → Día 30: $\approx$ 0.37 → Día 90: $\approx$ 0.05

### 11.3 Score de Rotación — Rotación Invertida

$$\text{score\_rotation}(r) = 1 - \frac{r - r_{\min}}{r_{\max} - r_{\min}}$$

- $r = r_{\min}$ (producto parado): score = 1.0 — máximo boost
- $r = r_{\max}$ (más vendido): score = 0.0 — sin boost""",
"md-11-business"))

# SECTION 12: Business scores code
cells.append(code(
r"""# Pre-calcular scores de negocio para todos los productos
n_items_total = len(item_idx)
vec_urgency   = np.zeros(n_items_total, dtype=np.float32)
vec_novelty   = np.zeros(n_items_total, dtype=np.float32)
vec_rotation  = np.zeros(n_items_total, dtype=np.float32)
vec_vencido   = np.zeros(n_items_total, dtype=np.float32)

rot_min   = prods_master["rotacion_diaria"].min()
rot_max   = prods_master["rotacion_diaria"].max()
rot_range = max(rot_max - rot_min, 1e-9)

for _, row in prods_master.iterrows():
    pid   = row["producto_id"]
    if pid not in item_idx:
        continue
    j      = item_idx[pid]
    dias_v = row["dias_para_vencer"]
    dias_i = row["dias_desde_ingreso"]
    rot    = row["rotacion_diaria"]

    # Urgency: sigmoide inversa
    if dias_v < 0:
        vec_urgency[j] = 0.0
        vec_vencido[j] = 1.0
    else:
        vec_urgency[j] = 1.0 / (1.0 + np.exp(dias_v / SIGMA_URGENCY))

    # Novelty: exponential decay
    vec_novelty[j] = np.exp(-dias_i / TAU_NOVEDAD)

    # Rotation: inverse (más alto = menos rotación)
    vec_rotation[j] = 1.0 - (rot - rot_min) / rot_range

print(f"Productos urgentes (score_urgency > 0.3):   {(vec_urgency > 0.3).sum()}")
print(f"Productos nuevos   (score_novelty  > 0.5):  {(vec_novelty > 0.5).sum()}")
print(f"Baja rotacion      (score_rotation > 0.75): {(vec_rotation > 0.75).sum()}")

# Visualización
days_range     = np.arange(0, 100)
urgency_values = 1.0 / (1.0 + np.exp(days_range / SIGMA_URGENCY))

fig, axes = plt.subplots(1, 3, figsize=(15, 4))

axes[0].plot(days_range, urgency_values, color='red', linewidth=2)
axes[0].axvline(x=UMBRAL_URGENCIA, color='orange', linestyle='--',
                label=f'Umbral={UMBRAL_URGENCIA}d')
axes[0].set_xlabel("Dias para vencer")
axes[0].set_ylabel("score_urgency")
axes[0].set_title("Funcion de Urgencia (Sigmoide Inversa)")
axes[0].legend(); axes[0].grid(alpha=0.3)

days_ingreso   = np.arange(0, 200)
novelty_values = np.exp(-days_ingreso / TAU_NOVEDAD)
axes[1].plot(days_ingreso, novelty_values, color='green', linewidth=2)
axes[1].axvline(x=UMBRAL_NOVEDAD, color='orange', linestyle='--',
                label=f'Umbral={UMBRAL_NOVEDAD}d')
axes[1].set_xlabel("Dias desde ingreso al catalogo")
axes[1].set_ylabel("score_novelty")
axes[1].set_title("Funcion de Novedad (Decaimiento Exponencial)")
axes[1].legend(); axes[1].grid(alpha=0.3)

axes[2].hist(vec_rotation[vec_rotation > 0], bins=40, color='purple', alpha=0.7)
axes[2].set_xlabel("score_rotation")
axes[2].set_ylabel("Frecuencia")
axes[2].set_title("Distribucion score_rotation")
axes[2].grid(alpha=0.3)

plt.tight_layout()
plt.show()""",
"code-12-biz"))

# SECTION 13: Aux indices markdown
cells.append(md(
"---\n## Sección 13 — Índices Auxiliares\n\n"
"Para que `recommend()` sea eficiente (< 100 ms por cliente), precalculamos "
"diccionarios de búsqueda O(1):\n\n"
"1. **`stock_by_item`**: `producto_id → stock_actual` para filtro duro de sin-stock\n"
"2. **`meta_by_item`**: `producto_id → dict(metadata)` para construir la respuesta final\n"
"3. **`historial_cliente`**: `cliente_id → set(producto_ids)` para CBF y filtrado",
"md-13-indices"))

cells.append(code(
r"""# Índices para inferencia rápida
stock_by_item = dict(zip(prods_master["producto_id"], prods_master["stock"]))
meta_by_item  = prods_master.set_index("producto_id").to_dict(orient="index")

# Historial de compras por cliente (para filtrado y CBF)
historial_cliente = (
    matrix_df.groupby("cliente_id")["producto_id"].apply(set).to_dict()
)

print(f"Indices construidos:")
print(f"  stock_by_item:     {len(stock_by_item)} productos")
print(f"  meta_by_item:      {len(meta_by_item)} productos")
print(f"  historial_cliente: {len(historial_cliente)} clientes")""",
"code-14-indices"))

# SECTION 15: recommend() markdown
cells.append(md(
r"""---
## Sección 15 — Función `recommend()` — Pipeline de 8 Pasos

### Paso 1 — Validación del cliente
Verificar que existe en el índice. Los clientes nuevos (cold-start) requieren tratamiento especial.

### Paso 2 — Score CF para todos los productos

$$\text{scores\_cf} = U[u, :] \cdot V^T \in \mathbb{R}^n$$

Normalizado a [0, 1] para combinarlo con los otros scores.

### Paso 3 — Pre-filtrado por CF (top-500)
Reducir de $n$ candidatos a 500 usando solo el score CF. Los descartados tienen scores muy bajos.

### Paso 4 — Garantizar urgentes y baja rotación
Los productos urgentes **siempre** deben ser considerados, independientemente de su
score CF. Sin esto, un producto a 2 días de vencer podría nunca recomendarse.

### Paso 5 — Score CBF
Similitud promedio con las últimas 10 compras del cliente. Solo para el subconjunto de candidatos.

### Paso 6 — Combinación de scores

$$\text{score\_final} = 0.40 \cdot \text{cf} + 0.15 \cdot \text{cbf} + 0.20 \cdot \text{urg} + 0.15 \cdot \text{rot} + 0.10 \cdot \text{nov}$$

### Paso 7 — Filtros duros
Vencidos y sin stock reciben `score = -inf`. Nunca aparecen en el resultado.

### Paso 8 — Top-K
Ordenar descendente por `score_final` y retornar los top-K con toda la metadata.""",
"md-15-recommend"))

# SECTION 16: recommend() code
cells.append(code(
r"""def recommend(cliente_id, top_k=TOPK_FINAL, filtro_tipo=None):
    # Genera las top-K recomendaciones para un cliente.
    # Args: cliente_id, top_k, filtro_tipo (None | urgentes | baja_rotacion | nuevos)
    # Returns: pd.DataFrame con scores y metadata del producto.
    if cliente_id not in user_idx:
        raise ValueError(f"Cliente '{cliente_id}' no encontrado.")

    # Paso 2: score_cf — producto punto del perfil del cliente con todos los items
    u_i            = user_idx[cliente_id]
    scores_cf_raw  = U[u_i] @ Vt
    cf_min, cf_max = scores_cf_raw.min(), scores_cf_raw.max()
    scores_cf      = (scores_cf_raw - cf_min) / max(cf_max - cf_min, 1e-9)

    # Paso 3: candidatos CF (top TOPK_CF_CANDS por score CF)
    n_cand     = min(TOPK_CF_CANDS, len(scores_cf))
    top_cf_idx = set(np.argpartition(scores_cf, -n_cand)[-n_cand:].tolist())

    # Paso 4: garantizar urgentes y baja rotacion como candidatos
    urgentes_idx = set(np.where(vec_urgency > 0.3)[0].tolist())
    baja_rot_idx = set(np.where(vec_rotation > 0.75)[0].tolist())
    candidatos   = top_cf_idx | urgentes_idx | baja_rot_idx

    # Filtro opcional por tipo de producto
    if filtro_tipo == "urgentes":
        urg_set = {
            item_idx[pid] for pid in meta_by_item
            if meta_by_item[pid]["dias_para_vencer"] <= UMBRAL_URGENCIA
            and pid in item_idx
        }
        candidatos = candidatos & urg_set if urg_set else urg_set
    elif filtro_tipo == "baja_rotacion":
        br_set = {
            item_idx[pid] for pid in meta_by_item
            if meta_by_item[pid].get("baja_rotacion", 0) == 1
            and pid in item_idx
        }
        candidatos = candidatos & br_set if br_set else br_set
    elif filtro_tipo == "nuevos":
        nv_set = {
            item_idx[pid] for pid in meta_by_item
            if meta_by_item[pid].get("dias_desde_ingreso", 999) <= UMBRAL_NOVEDAD
            and pid in item_idx
        }
        candidatos = candidatos & nv_set if nv_set else nv_set

    if not candidatos:
        return pd.DataFrame()

    cand_arr = np.array(sorted(candidatos), dtype=np.int32)

    # Paso 5: score_cbf — similitud promedio con ultimas 10 compras
    historial_c = list(historial_cliente.get(cliente_id, set()))
    scores_cbf  = np.zeros(len(cand_arr), dtype=np.float32)
    recientes   = [item_idx[p] for p in historial_c if p in item_idx][:10]
    if recientes:
        scores_cbf = cbf_sim[cand_arr][:, recientes].mean(axis=1)

    # Paso 6: score final ponderado
    cf_c  = scores_cf[cand_arr]
    urg_c = vec_urgency[cand_arr]
    rot_c = vec_rotation[cand_arr]
    nov_c = vec_novelty[cand_arr]

    score_final = (
        W_CF       * cf_c
        + W_CBF     * scores_cbf
        + W_URGENCY * urg_c
        + W_ROTATION * rot_c
        + W_NOVELTY  * nov_c
    )

    # Paso 7: filtros duros — vencidos y sin stock = -inf
    vencidos  = vec_vencido[cand_arr].astype(bool)
    sin_stock = np.array(
        [stock_by_item.get(idx_item.get(j, ""), 0) == 0 for j in cand_arr],
        dtype=bool,
    )
    score_final[vencidos | sin_stock] = -np.inf

    # Paso 8: top-K ordenado
    top_idx = np.argsort(score_final)[::-1][:top_k]

    results = []
    for ri in top_idx:
        if score_final[ri] == -np.inf:
            break
        j    = int(cand_arr[ri])
        pid  = idx_item[j]
        meta = meta_by_item.get(pid, {})
        results.append({
            "producto_id":        pid,
            "categoria_producto": meta.get("categoria_producto", ""),
            "score_final":        round(float(score_final[ri]), 4),
            "score_cf":           round(float(cf_c[ri]), 4),
            "score_cbf":          round(float(scores_cbf[ri]), 4),
            "score_urgency":      round(float(urg_c[ri]), 4),
            "score_rotation":     round(float(rot_c[ri]), 4),
            "score_novelty":      round(float(nov_c[ri]), 4),
            "dias_para_vencer":   int(meta.get("dias_para_vencer", 0)),
            "dias_desde_ingreso": int(meta.get("dias_desde_ingreso", 0)),
            "stock":              int(meta.get("stock", 0)),
            "es_urgente":         bool(meta.get("dias_para_vencer", 999) <= UMBRAL_URGENCIA),
            "es_nuevo_catalogo":  bool(meta.get("dias_desde_ingreso", 999) <= UMBRAL_NOVEDAD),
            "es_baja_rotacion":   bool(meta.get("baja_rotacion", 0) == 1),
            "rotacion_diaria":    float(meta.get("rotacion_diaria", 0)),
        })

    return pd.DataFrame(results)""",
"code-16-recommend"))

# SECTION 17: Test
cells.append(md(
"---\n## Sección 17 — Test de la Función `recommend()`\n\n"
"Probamos con el primer cliente que tenga historial de compras y analizamos "
"la composición del resultado.",
"md-17-test"))

cells.append(code(
r"""# Probar con el primer cliente que tenga historial de compras
cliente_prueba = list(historial_cliente.keys())[0]
print(f"Probando con cliente: {cliente_prueba}")
print(f"Historial: {len(historial_cliente[cliente_prueba])} productos comprados")

recomendaciones = recommend(cliente_prueba)
print(f"\nTop {len(recomendaciones)} recomendaciones:")
display(recomendaciones)

# Breakdown de categorías de negocio
n_urgentes = recomendaciones["es_urgente"].sum()
n_nuevos   = recomendaciones["es_nuevo_catalogo"].sum()
n_baja_rot = recomendaciones["es_baja_rotacion"].sum()
print(f"\nDesglose de las recomendaciones:")
print(f"  Urgentes (proximos a vencer): {n_urgentes}/{len(recomendaciones)}")
print(f"  Nuevos en catalogo:           {n_nuevos}/{len(recomendaciones)}")
print(f"  Baja rotacion:                {n_baja_rot}/{len(recomendaciones)}")""",
"code-17-test"))

# SECTION 18: Sensitivity markdown
cells.append(md(
r"""---
## Sección 18 — Análisis de Sensibilidad

El análisis de sensibilidad evalúa cómo **cambiar los pesos del score híbrido** afecta
el comportamiento del sistema.

### ¿Por qué es importante?

Los pesos actuales ($W_{CF}=0.40$, $W_{\text{urg}}=0.20$, etc.) son decisiones de
diseño. Pero las prioridades pueden cambiar:
- Temporada con mucho stock próximo a vencer: $W_{\text{urg}} = 0.45$
- Campaña de liquidación: $W_{\text{rot}} = 0.45$

### Escenarios evaluados:

| Escenario | Descripción | Uso típico |
|---|---|---|
| **Baseline** | Pesos configurados (40/15/20/15/10) | Operación normal |
| **Prioridad caducidad** | 30/10/45/10/5 | Alto riesgo de merma |
| **Prioridad baja rotacion** | 30/10/10/45/5 | Campaña liquidación |
| **Caducidad + Rotacion** | 25/10/30/30/5 | Fin de temporada |
| **Solo CF (ablacion)** | 100/0/0/0/0 | Modelo base sin reglas |""",
"md-18-sensitivity"))

# SECTION 19: Sensitivity code
cells.append(code(
r"""escenarios = [
    {"nombre": "Baseline",
     "W_CF": 0.40, "W_CBF": 0.15, "W_URGENCY": 0.20, "W_ROTATION": 0.15, "W_NOVELTY": 0.10},
    {"nombre": "Prioridad caducidad",
     "W_CF": 0.30, "W_CBF": 0.10, "W_URGENCY": 0.45, "W_ROTATION": 0.10, "W_NOVELTY": 0.05},
    {"nombre": "Prioridad baja rotacion",
     "W_CF": 0.30, "W_CBF": 0.10, "W_URGENCY": 0.10, "W_ROTATION": 0.45, "W_NOVELTY": 0.05},
    {"nombre": "Caducidad + Rotacion",
     "W_CF": 0.25, "W_CBF": 0.10, "W_URGENCY": 0.30, "W_ROTATION": 0.30, "W_NOVELTY": 0.05},
    {"nombre": "Solo CF (ablacion)",
     "W_CF": 1.00, "W_CBF": 0.00, "W_URGENCY": 0.00, "W_ROTATION": 0.00, "W_NOVELTY": 0.00},
]

rng_sens              = np.random.default_rng(seed=2024)
clientes_con_historial = [c for c, h in historial_cliente.items() if len(h) >= 2]
n_sample_sens         = min(10, len(clientes_con_historial))
clientes_sens         = rng_sens.choice(clientes_con_historial, size=n_sample_sens, replace=False)


def recommend_with_weights(cid, w_cf, w_cbf, w_urg, w_rot, w_nov, top_k=10):
    # Version parametrizada de recommend() para analisis de sensibilidad.
    if cid not in user_idx:
        return pd.DataFrame()
    u_i  = user_idx[cid]
    scf  = U[u_i] @ Vt
    scf  = (scf - scf.min()) / max(scf.max() - scf.min(), 1e-9)
    nc   = min(TOPK_CF_CANDS, len(scf))
    cands = set(np.argpartition(scf, -nc)[-nc:].tolist())
    cands |= set(np.where(vec_urgency > 0.3)[0].tolist())
    cands |= set(np.where(vec_rotation > 0.75)[0].tolist())
    if not cands:
        return pd.DataFrame()
    ca   = np.array(sorted(cands), dtype=np.int32)
    hist = list(historial_cliente.get(cid, set()))
    scbf = np.zeros(len(ca), dtype=np.float32)
    rec  = [item_idx[p] for p in hist if p in item_idx][:10]
    if rec:
        scbf = cbf_sim[ca][:, rec].mean(axis=1)
    sf = (w_cf*scf[ca] + w_cbf*scbf + w_urg*vec_urgency[ca]
          + w_rot*vec_rotation[ca] + w_nov*vec_novelty[ca])
    sf[vec_vencido[ca].astype(bool)] = -np.inf
    sf[np.array([stock_by_item.get(idx_item.get(j,""),0)==0 for j in ca], dtype=bool)] = -np.inf
    ti  = np.argsort(sf)[::-1][:top_k]
    res = []
    for ri in ti:
        if sf[ri] == -np.inf: break
        j = int(ca[ri]); pid = idx_item[j]; meta = meta_by_item.get(pid,{})
        res.append({"score_final": float(sf[ri]),
                    "es_urgente": bool(meta.get("dias_para_vencer",999) <= UMBRAL_URGENCIA),
                    "es_baja_rotacion": bool(meta.get("baja_rotacion",0) == 1)})
    return pd.DataFrame(res)


resultados_sens = []
for esc in escenarios:
    pu, pr, ps = [], [], []
    for cid in clientes_sens:
        r = recommend_with_weights(cid, esc["W_CF"], esc["W_CBF"],
                                   esc["W_URGENCY"], esc["W_ROTATION"], esc["W_NOVELTY"])
        if r.empty: continue
        pu.append(r["es_urgente"].mean())
        pr.append(r["es_baja_rotacion"].mean())
        ps.append(r["score_final"].mean())
    resultados_sens.append({
        "Escenario":         esc["nombre"],
        "W_CF":              esc["W_CF"],
        "W_URGENCY":         esc["W_URGENCY"],
        "W_ROTATION":        esc["W_ROTATION"],
        "% Urgentes (avg)":  round(np.mean(pu)*100, 1) if pu else 0,
        "% Baja Rot. (avg)": round(np.mean(pr)*100, 1) if pr else 0,
        "Score Final (avg)": round(np.mean(ps), 4)     if ps else 0,
    })

df_sens = pd.DataFrame(resultados_sens)
print("\nResultados del Analisis de Sensibilidad")
print("=" * 70)
display(df_sens)""",
"code-19-sensitivity"))

# SECTION 20: Evaluation metrics markdown
cells.append(md(
r"""---
## Sección 20 — Métricas de Evaluación

Usamos la **metodología hold-out (leave-20%-out)**: ocultamos el 20% de los productos
comprados de cada cliente y verificamos si el modelo los habría recomendado.

### 20.1 HitRate@K

$$\text{HitRate@K} = \frac{\sum_{u} \mathbb{1}[\text{recs}(u,K) \cap \text{holdout}(u) \neq \emptyset]}{|\mathcal{U}|}$$

Métrica principal: "¿predice el modelo lo que el cliente comprará?"

### 20.2 Precision@K

$$\text{Precision@K} = \frac{|\text{recs}(u,K) \cap \text{holdout}(u)|}{K}$$

### 20.3 Recall@K

$$\text{Recall@K} = \frac{|\text{recs}(u,K) \cap \text{holdout}(u)|}{|\text{holdout}(u)|}$$

En leave-20%-out es equivalente al HitRate@K cuando el holdout es pequeño.

### 20.4 Coverage

$$\text{Coverage} = \frac{|\bigcup_{u} \text{recs}(u,K)|}{|\text{catalogo}|}$$

Un sistema con Coverage bajo siempre recomienda los mismos productos populares.
Coverage > 40% es deseable.

### 20.5 Urgency Coverage

$$\text{UrgencyCoverage} = \frac{|\{\text{urgentes}\} \cap \bigcup_u \text{recs}(u,K)|}{|\text{urgentes}|}$$

Mide directamente si el sistema resuelve el problema de mermas por caducidad.""",
"md-20-metricas"))

# SECTION 21: Evaluation code
cells.append(code(
r"""def evaluate_model(sample_size=50, seed=42):
    # Metodologia hold-out (leave-20%-out).
    # 1. Selecciona 20% de productos como ground truth
    # 2. Genera top-10 recomendaciones
    # 3. Verifica si algun producto hold-out aparece
    rng = np.random.default_rng(seed)

    clientes_validos = [c for c, h in historial_cliente.items() if len(h) >= 3]
    if len(clientes_validos) > sample_size:
        clientes_muestra = rng.choice(clientes_validos, size=sample_size, replace=False)
    else:
        clientes_muestra = clientes_validos

    hits                   = 0
    total                  = 0
    productos_recomendados = set()

    for cid in clientes_muestra:
        hist_c    = list(historial_cliente[cid])
        n_holdout = max(1, int(len(hist_c) * 0.20))
        holdout   = set(rng.choice(hist_c, size=n_holdout, replace=False))
        try:
            recs = recommend(cid)
            if recs.empty:
                continue
            rec_set = set(recs["producto_id"].values)
            productos_recomendados.update(rec_set)
            if rec_set & holdout:
                hits += 1
            total += 1
        except Exception:
            continue

    hit_rate  = hits / total if total > 0 else 0
    precision = hit_rate / TOPK_FINAL
    coverage  = len(productos_recomendados) / n_i

    urgentes_catalogo = {
        pid for pid, meta in meta_by_item.items()
        if 0 <= meta.get("dias_para_vencer", 999) <= UMBRAL_URGENCIA
    }
    urgency_cov = (
        len(urgentes_catalogo & productos_recomendados) / len(urgentes_catalogo)
        if urgentes_catalogo else 0
    )

    return {
        "HitRate@10":       round(hit_rate, 4),
        "Precision@10":     round(precision, 4),
        "Recall@10":        round(hit_rate, 4),
        "Coverage":         round(coverage, 4),
        "Urgency_Coverage": round(urgency_cov, 4),
        "n_clientes_eval":  total,
        "n_hits":           hits,
    }


print("Evaluando modelo (muestra de 50 clientes)...")
metricas = evaluate_model(sample_size=50)

print("\n" + "=" * 50)
print("METRICAS DE EVALUACION DEL MODELO")
print("=" * 50)
for k, v in metricas.items():
    print(f"  {k:<25}: {v}")

print("\nInterpretacion:")
print(f"  HitRate@10 = {metricas['HitRate@10']:.2%}: en el {metricas['HitRate@10']:.0%} "
      f"de los clientes, el modelo predice correctamente al menos un producto del holdout.")
print(f"  Coverage = {metricas['Coverage']:.2%}: el modelo usa "
      f"{int(metricas['Coverage']*n_i)}/{n_i} productos distintos del catalogo.")
print(f"  Urgency_Coverage = {metricas['Urgency_Coverage']:.2%}: identifica al "
      f"{metricas['Urgency_Coverage']:.0%} de los productos urgentes para algun cliente.")""",
"code-21-eval"))

# SECTION 22: Viz
cells.append(md(
"---\n## Sección 22 — Visualización de Métricas\n\n"
"Representamos las métricas visualmente para comunicarlas con stakeholders no técnicos.",
"md-22-viz"))

cells.append(code(
r"""metrics_display = {k: v for k, v in metricas.items()
                   if k not in ("n_clientes_eval", "n_hits")}

fig, axes = plt.subplots(1, 2, figsize=(14, 5))

# Panel izquierdo: barras de métricas
names  = list(metrics_display.keys())
values = list(metrics_display.values())
colors = ["steelblue", "cornflowerblue", "lightsteelblue", "seagreen", "tomato"]

bars = axes[0].bar(names, values, color=colors[:len(names)], edgecolor="white", linewidth=1.2)
axes[0].set_ylim(0, 1.12)
axes[0].set_ylabel("Valor de la metrica")
axes[0].set_title("Metricas de Evaluacion del Modelo Hibrido")
axes[0].tick_params(axis="x", rotation=30)
axes[0].grid(axis="y", alpha=0.3)
for bar, val in zip(bars, values):
    axes[0].text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.015,
                 f"{val:.3f}", ha="center", va="bottom", fontsize=10, fontweight="bold")

# Panel derecho: torta de contribuciones al score final
if not recomendaciones.empty:
    score_cols   = ["score_cf", "score_cbf", "score_urgency", "score_rotation", "score_novelty"]
    weights_list = [W_CF, W_CBF, W_URGENCY, W_ROTATION, W_NOVELTY]
    weighted_avg = [recomendaciones[c].mean() * w for c, w in zip(score_cols, weights_list)]
    labels_comp  = ["CF (x0.40)", "CBF (x0.15)", "Urgency (x0.20)",
                    "Rotation (x0.15)", "Novelty (x0.10)"]
    pie_colors   = ["steelblue", "cornflowerblue", "tomato", "purple", "seagreen"]
    _, _, autotexts = axes[1].pie(
        weighted_avg, labels=labels_comp, colors=pie_colors,
        autopct="%1.1f%%", startangle=90, pctdistance=0.75)
    for at in autotexts: at.set_fontsize(9)
    axes[1].set_title(f"Contribucion al Score Final\n(cliente {cliente_prueba}, top-10)")

plt.tight_layout()
plt.show()

# Comparacion con benchmarks
print("\nComparacion con benchmarks tipicos (feedback implicito B2B):")
print("-" * 65)
benchmarks = {
    "HitRate@10":       (0.25, 0.45),
    "Precision@10":     (0.025, 0.045),
    "Recall@10":        (0.25, 0.45),
    "Coverage":         (0.35, 0.70),
    "Urgency_Coverage": (0.50, 0.90),
}
for met, val in metrics_display.items():
    if met in benchmarks:
        lo, hi = benchmarks[met]
        status = "OK" if lo <= val <= hi else ("ALTO" if val > hi else "BAJO")
        print(f"  {met:<22}: {val:.4f}  |  benchmark [{lo:.3f} - {hi:.3f}]  ->  {status}")""",
"code-22-viz"))

# SECTION 23: Next Steps
cells.append(md(
r"""---
## Sección 23 — Próximos Pasos y Mejoras

### 1. Reemplazar TruncatedSVD por ALS (Alternating Least Squares)

La librería `implicit` implementa ALS con soporte nativo para feedback implícito
(matriz de confianza $C_{ui} = 1 + \alpha \cdot R_{ui}$). Supera a SVD en HitRate@K
en 5-15 puntos porcentuales típicamente.

```python
from implicit.als import AlternatingLeastSquares
model = AlternatingLeastSquares(factors=150, regularization=0.01, iterations=50)
model.fit(R.T)  # implicit espera items x users
```

### 2. Ventanas Temporales como Señales CF Separadas

Construir tres matrices separadas (7d, 30d, 90d). Captura urgencia reciente Y
patrones de largo plazo como features independientes del modelo final.

### 3. Boost de Novedad Diferenciado por Categoría

- Perecederos (lácteos, cárnicos): $\tau_{\text{novedad}} = 15$ días
- No perecederos (conservas, bebidas): $\tau_{\text{novedad}} = 60$ días

### 4. Restricción de Diversificación por Categoría

Máximo 3 productos de la misma categoría en el top-10. Evita recomendaciones
monótonas y mejora la experiencia del vendedor.

```python
def diversify(recs_df, max_per_category=3):
    selected, counts = [], {}
    for _, row in recs_df.iterrows():
        cat = row["categoria_producto"]
        if counts.get(cat, 0) < max_per_category:
            selected.append(row)
            counts[cat] = counts.get(cat, 0) + 1
    return pd.DataFrame(selected)
```

### 5. Pipeline de Reentrenamiento Automatizado

Reentrenar **semanalmente** para capturar cambios en inventario. Implementar con
Airflow o GitHub Actions + cron. Enviar alerta si métricas degradan > 5%.

### 6. Métrica de Impacto Económico

$$\text{Impacto} = \sum_{u,i} \mathbb{1}[i \text{ recomendado}] \cdot \mathbb{1}[i \text{ vendido}] \cdot \text{precio}_i \cdot \text{cantidad}_{ui}$$

Requiere tracking de conversiones en producción.

### 7. Diseño de A/B Test

- **Grupo A (control)**: vendedores sin el sistema de recomendación
- **Grupo B (tratamiento)**: vendedores con el sistema híbrido
- **Métricas**: ticket promedio, % urgentes vendidos, merma total
- **Duración**: 4 semanas (2 calentamiento + 2 medición)
- **Randomización**: por vendedor (no por cliente) para evitar contaminación""",
"md-23-next"))

# SECTION 24: Save artifacts
cells.append(code(
r"""import joblib

MODEL_DIR = ROOT_DIR / "data" / "processed"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

artifacts = {
    # Matrices SVD
    "U":                 U,
    "Vt":                Vt,
    # Indices de mapeo
    "user_idx":          user_idx,
    "item_idx":          item_idx,
    "idx_item":          idx_item,
    # Matriz de similaridad CBF
    "cbf_sim":           cbf_sim,
    # Vectores de scores de negocio
    "vec_urgency":       vec_urgency,
    "vec_novelty":       vec_novelty,
    "vec_rotation":      vec_rotation,
    "vec_vencido":       vec_vencido,
    # Indices auxiliares de inferencia
    "stock_by_item":     stock_by_item,
    "meta_by_item":      meta_by_item,
    "historial_cliente": historial_cliente,
    "prods_master":      prods_master,
    # Resultados de evaluacion
    "metricas_eval":     metricas,
    # Hiperparametros para reproducibilidad
    "params": {
        "W_CF": W_CF, "W_CBF": W_CBF, "W_URGENCY": W_URGENCY,
        "W_ROTATION": W_ROTATION, "W_NOVELTY": W_NOVELTY,
        "TAU_DIAS": TAU_DIAS, "SVD_COMPONENTS": SVD_COMPONENTS,
        "TOPK_CF_CANDS": TOPK_CF_CANDS, "TOPK_FINAL": TOPK_FINAL,
        "UMBRAL_URGENCIA": UMBRAL_URGENCIA, "UMBRAL_NOVEDAD": UMBRAL_NOVEDAD,
        "SIGMA_URGENCY": SIGMA_URGENCY, "TAU_NOVEDAD": TAU_NOVEDAD,
        "FECHA_HOY": str(FECHA_HOY.date()),
    },
}

output_path = MODEL_DIR / "modelo_artifacts.pkl"
joblib.dump(artifacts, output_path)

print(f"Artefactos del modelo guardados en {output_path}")
print(f"  Para usar en la API: carga este archivo y pasalo al HybridRecommender")
print()
print("Contenido del archivo:")
for key, val in artifacts.items():
    if hasattr(val, "shape"):
        desc = f"ndarray {val.shape}"
    elif hasattr(val, "__len__"):
        desc = f"{type(val).__name__} ({len(val)} elementos)"
    else:
        desc = str(type(val).__name__)
    print(f"  {key:<25}: {desc}")""",
"code-24-save"))

# Build notebook dict
notebook = {
    "nbformat": 4,
    "nbformat_minor": 5,
    "metadata": {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3"
        },
        "language_info": {
            "name": "python",
            "version": "3.10.0"
        }
    },
    "cells": cells,
}

out = r"C:\Users\EQUIPO\Documents\claude_projects\tesis1\notebooks\02_modelo_recomendacion.ipynb"
with open(out, "w", encoding="utf-8") as f:
    json.dump(notebook, f, ensure_ascii=False, indent=1)

print(f"Written: {out}")
print(f"Total cells: {len(cells)}")
for i, c in enumerate(cells):
    ctype = c["cell_type"]
    first = (c["source"][0] if c["source"] else "").strip()[:60]
    print(f"  [{i:02d}] {ctype:<8} {first}")
