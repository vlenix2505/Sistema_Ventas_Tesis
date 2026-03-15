# Arquitectura del Sistema de Recomendación Híbrido

**Empresa distribuidora de alimentos — Sector HORECA**

---

## 1. Visión General

El sistema resuelve tres problemas de negocio simultáneamente:

| Problema | Solución |
|---|---|
| Mermas por caducidad | Endpoint `/recomendar/proximos-vencer` prioriza lotes a vencer |
| Stock parado | Endpoint `/recomendar/baja-rotacion` promueve productos estancados |
| Adopción de nuevos SKUs | Endpoint `/recomendar/nuevos` impulsa productos recién incorporados |

Cada endpoint utiliza el **mismo motor híbrido** (CF + CBF + scores de negocio),
pero filtra el pool de candidatos al subconjunto relevante para esa categoría,
y rankea dentro de él según la afinidad personalizada del cliente.

---

## 2. Diagrama de Flujo de Datos

```
┌─────────────────────────────────────────────────────────────────────┐
│                          DATOS FUENTE                               │
│                                                                     │
│  clientes.csv       productos.csv      ventas.csv                   │
│  (800 clientes)     (950 productos)    (7,950 ventas)               │
│  - cliente_id       - producto_id      - venta_id                   │
│  - rubro_cliente    - categoria        - cliente_id                 │
│  - subrubro_1,2     - precio/costo     - fecha_venta                │
│  - sede_cliente     - stock/caducidad  - monto_total                │
│                                                                     │
│                       detalle_venta.csv                             │
│                       (36,003 líneas)                               │
│                       - venta_id / producto_id                      │
│                       - cantidad / subtotal                         │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ generate_source.py (datos sintéticos)
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    NOTEBOOK 01 — DATASET                            │
│                                                                     │
│  1. Join ventas + detalle + productos + clientes                    │
│  2. Feature Engineering:                                            │
│     - dias_para_vencer  (urgencia)                                  │
│     - rotacion_diaria   (velocidad de venta)                        │
│     - baja_rotacion     (flag cuartil inferior)                     │
│     - frecuencia_compra / ticket_promedio                           │
│     - mes, semana_anio, es_feriado                                  │
│  3. Validación: 0 nulos, 290,064 filas × 28 columnas               │
│  4. Output: data/processed/dataset_ml.csv                           │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   NOTEBOOK 02 — MODELO                              │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  COMPONENTE CF — TruncatedSVD                               │   │
│  │  Interacción = cantidad × exp(-días/τ)  (τ = 180 días)     │   │
│  │  R (800×950) ──SVD──► U (800×150) , Vt (150×950)          │   │
│  │  score_cf(u,i) = U[u] @ Vt[:,i]                            │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  COMPONENTE CBF — Cosine Similarity                         │   │
│  │  Features: categoria (OHE) + precio_bucket + rubro + precio│   │
│  │  sim(i,j) = coseno(f_i, f_j)                               │   │
│  │  score_cbf(u,i) = avg sim(i, últimas 10 compras de u)      │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  SCORES DE NEGOCIO (pre-calculados, sin re-entrenar)        │   │
│  │                                                             │   │
│  │  score_urgency  = 1 / (1 + exp(dias_para_vencer / 15))    │   │
│  │  score_rotation = 1 - normalize(rotacion_diaria)           │   │
│  │  score_novelty  = exp(-dias_desde_ingreso / 30)            │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  score_final = 0.40×CF + 0.15×CBF + 0.20×urgency                  │
│              + 0.15×rotation + 0.10×novelty                        │
│                                                                     │
│  Output: models/recommender_model.joblib                           │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      API FastAPI                                    │
│                  uvicorn api.main:app                               │
│                                                                     │
│  GET /health                        → estado del servicio          │
│                                                                     │
│  GET /recomendar/{cliente_id}        → recomendación general       │
│  GET /recomendar/proximos-vencer/{id} → lote próximo a vencer      │
│  GET /recomendar/baja-rotacion/{id}  → stock parado               │
│  GET /recomendar/nuevos/{id}         → nuevos SKUs                 │
│                                                                     │
│  Latencia: < 100ms por request (modelo en memoria)                 │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ JSON response
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   APLICACIÓN DE VENTAS                              │
│                                                                     │
│  Carrito de compra  →  Llama a los 3 endpoints en paralelo         │
│  Muestra secciones:                                                 │
│    🔴 "Por vencer — ahorra en estos productos"                      │
│    🟡 "Muévelo antes de que caduque"                                │
│    🟢 "Novedades para tu tipo de negocio"                           │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. Estructura de Directorios

```
tesis1/
│
├── generate_source.py           # Genera datos sintéticos (4 CSVs)
│
├── notebooks/
│   ├── 01_dataset.ipynb         # Limpieza y feature engineering
│   ├── 02_modelo_recomendacion.ipynb  # Entrenamiento y evaluación
│   └── build_nb.py              # Script que regenera el notebook 02
│
├── api/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app — endpoints
│   ├── recommender.py           # Motor de recomendación (HybridRecommender)
│   └── schemas.py               # Modelos Pydantic
│
├── data/
│   ├── raw/                     # CSVs generados por generate_source.py
│   │   ├── clientes.csv
│   │   ├── productos.csv
│   │   ├── ventas.csv
│   │   └── detalle_venta.csv
│   └── processed/
│       └── dataset_ml.csv       # Output del notebook 01
│
├── models/
│   └── recommender_model.joblib # Modelo serializado (output del notebook 02)
│
├── docs/
│   ├── arquitectura_sistema.md  # Este documento
│   └── manual_de_uso.md         # Guía operativa
│
├── requirements.txt             # Dependencias Python
└── README.md                    # Punto de entrada del proyecto
```

---

## 4. Flujo de Entrenamiento

```
1. python generate_source.py
         └─► data/raw/clientes.csv
             data/raw/productos.csv
             data/raw/ventas.csv
             data/raw/detalle_venta.csv

2. jupyter notebook notebooks/01_dataset.ipynb
   (ejecutar todas las celdas)
         └─► data/processed/dataset_ml.csv  (290,064 filas × 28 cols)

3. jupyter notebook notebooks/02_modelo_recomendacion.ipynb
   (ejecutar todas las celdas)
         └─► models/recommender_model.joblib  (~50 MB)
             models/visualizaciones_modelo.png
```

---

## 5. Flujo de Inferencia (API)

```
Cliente envía GET /recomendar/proximos-vencer/CLI_000001

  ┌─────────────────────────────────────────────────────────────────┐
  │ HybridRecommender.recommend(cliente_id, filtro_tipo="urgentes") │
  │                                                                 │
  │  1. scores_cf = U[user_idx[CLI_000001]] @ Vt    (n_productos,) │
  │  2. Normalizar scores_cf a [0, 1]                               │
  │  3. candidatos = top-500 CF ∪ urgentes_garantizados             │
  │  4. filtrar a: productos con dias_para_vencer ≤ 30              │
  │  5. score_cbf = avg coseno con últimas 10 compras               │
  │  6. score_final = 0.40×CF + 0.15×CBF + 0.20×urgency            │
  │                 + 0.15×rotation + 0.10×novelty                  │
  │  7. Excluir vencidos y sin stock                                 │
  │  8. Retornar top-10 ordenados por score_final                   │
  └─────────────────────────────────────────────────────────────────┘

Respuesta JSON:
  {
    "cliente_id": "CLI_000001",
    "sede": "Lima",
    "tipo": "proximos_vencer",
    "umbral_dias": 30,
    "total_urgentes_catalogo": 41,
    "top_k": 5,
    "productos": [
      {
        "producto_id": "PROD_000234",
        "categoria_producto": "Lácteos",
        "precio_unitario": 12.50,
        "stock": 48,
        "score_final": 0.7823,
        "score_cf": 0.8910,
        "score_urgency": 0.9234,
        "dias_para_vencer": 7,
        "es_urgente": true,
        ...
      }
    ]
  }
```

---

## 6. Decisiones de Diseño

### 6.1 ¿Por qué filtro_tipo en lugar de 3 modelos distintos?

Los 3 endpoints usan el **mismo modelo entrenado una sola vez**. La diferencia está en
el *pool de candidatos*:

| Endpoint | Pool de candidatos | Ranking |
|---|---|---|
| General | Top-500 CF ∪ urgentes ∪ baja rotación | score_final híbrido |
| Próximos a vencer | Solo productos con `dias_para_vencer ≤ umbral` | score_final híbrido |
| Baja rotación | Solo productos con `baja_rotacion = True` | score_final híbrido |
| Nuevos | Solo productos con `dias_desde_ingreso ≤ umbral` | score_final híbrido |

Esto garantiza que **cada categoría siempre tenga candidatos**, incluso si su score
híbrido es bajo (lo que pasaría con un pool único top-K).

### 6.2 ¿Por qué incluir score_urgency/rotation/novelty en todos los endpoints?

Porque personalización y urgencia no son mutuamente excluyentes. En el endpoint
de próximos a vencer, entre dos productos urgentes se prefiere el que tiene mayor
afinidad con el cliente (CF + CBF). El score de urgencia está incluido para que
productos *más* urgentes tengan ventaja dentro del grupo.

### 6.3 Modelo en memoria vs. carga por request

El modelo se carga una sola vez en el `lifespan` de FastAPI y permanece en memoria.
Esto permite latencia de inferencia < 100ms. El tamaño en RAM es ~200 MB
(matriz U: 800×150, Vt: 150×950, matriz CBF: 950×950).

### 6.4 Scores de negocio pre-calculados

`vec_urgency`, `vec_novelty` y `vec_rotation` se calculan durante `fit()` y se
almacenan como arrays NumPy. En cada request se indexan directamente, sin recalcular.
Excepción: si el umbral de urgencia es personalizado por request, se aplica un
post-filtro sobre los candidatos (no recalcula el score).

---

## 7. Integración con la Aplicación de Ventas

### Escenario: Carrito de Compra

```
Vendedor selecciona cliente CLI_000001
        │
        ▼
App de ventas hace 3 llamadas en paralelo:
    ├── GET /recomendar/proximos-vencer/CLI_000001?top_k=3
    ├── GET /recomendar/baja-rotacion/CLI_000001?top_k=3
    └── GET /recomendar/nuevos/CLI_000001?top_k=3
        │
        ▼ (respuestas < 300ms en total)
App muestra panel lateral en el carrito:

  ┌─────────────────────────────────────────────┐
  │  Sugerencias para este cliente              │
  │                                             │
  │  🔴 POR VENCER (descuento especial)         │
  │     • Queso fresco 1kg  — vence en 7 días  │
  │     • Mantequilla 250g  — vence en 12 días │
  │     • Crema de leche    — vence en 18 días │
  │                                             │
  │  🟡 MOVER STOCK                             │
  │     • Harina integral 5kg                  │
  │     • Aceite de oliva 1L                   │
  │                                             │
  │  🟢 NOVEDADES                               │
  │     • Leche de avena 1L  (nuevo)           │
  └─────────────────────────────────────────────┘
```

### Campos clave que consume el frontend

| Campo | Uso |
|---|---|
| `producto_id` | Agregar al carrito |
| `categoria_producto` | Icono y agrupación visual |
| `precio_unitario` | Precio sugerido |
| `stock` | "Quedan X unidades" |
| `dias_para_vencer` | "Vence en X días" (badge urgencia) |
| `score_final` | Orden de presentación |
| `es_urgente / es_nuevo_catalogo` | Badges visuales |

---

## 8. Consideraciones para Producción

| Aspecto | Recomendación |
|---|---|
| **Re-entrenamiento** | Re-entrenar semanalmente con datos frescos |
| **Escala** | Agregar Redis para caché de requests frecuentes |
| **Monitoreo** | Registrar qué porcentaje de recomendaciones se convierten en ventas |
| **A/B Testing** | Comparar escenarios de pesos para maximizar conversión |
| **Cold Start** | Para clientes nuevos: usar solo CBF + scores de negocio (sin CF) |
