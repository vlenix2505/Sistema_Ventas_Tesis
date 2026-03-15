# Arquitectura de Producción — Sistema de Recomendación

## Contexto

El sistema actual (versión tesis) funciona correctamente para demostración y
validación del modelo. Sin embargo, en un entorno real con millones de
transacciones, dos componentes se vuelven inviables:

| Componente actual | Límite práctico | Por qué falla a escala |
|---|---|---|
| Re-entrenar al arrancar la API | ~50 000 interacciones | SVD sobre matriz 500k×100k tarda horas |
| Matriz CBF en RAM de la API | ~10 000 productos | Matriz 100k×100k = 40 GB por instancia |
| Dataset en CSV local | ~5 millones de filas | Lectura lenta, sin concurrencia |

---

## Arquitectura objetivo

```
┌──────────────────────────────────────────────────────────────────┐
│  CAPA DE DATOS                                                   │
│                                                                  │
│  ERP / POS  ──▶  Data Warehouse (Redshift / BigQuery)            │
│                  ventas, clientes, productos en tiempo real      │
└──────────────────────────────────────────────────────────────────┘
                          │
                          ▼ 1x día (ETL/dbt)
┌──────────────────────────────────────────────────────────────────┐
│  CAPA DE ENTRENAMIENTO          (offline)                        │
│                                                                  │
│  Job de entrenamiento  ◀──  dataset procesado (Parquet en S3)   │
│  (SageMaker / Vertex AI)                                        │
│       │                                                          │
│       │  joblib.dump()                                           │
│       ▼                                                          │
│  modelo_v{fecha}.pkl  ──▶  S3 / Azure Blob Storage              │
│                             (versionado, con rollback)           │
└──────────────────────────────────────────────────────────────────┘
                          │
                          ▼ al arrancar cada instancia
┌──────────────────────────────────────────────────────────────────┐
│  CAPA DE SERVICIO               (online)                        │
│                                                                  │
│  API FastAPI  ◀──  joblib.load("s3://bucket/modelo_latest.pkl") │
│  (ECS Fargate / Cloud Run)                                       │
│       │                                                          │
│       │  modelo pre-cargado en RAM                              │
│       ▼                                                          │
│  request llega  ──▶  lee vectores de RAM  ──▶  responde <50ms   │
│                                                                  │
│  [instancia 1]  [instancia 2]  [instancia 3]   ← escala         │
│   modelo RAM     modelo RAM     modelo RAM       horizontal      │
└──────────────────────────────────────────────────────────────────┘
```

---

## Qué se mantiene igual

- La lógica del `HybridRecommender` (SVD + CBF + scores de negocio) no cambia.
- Los endpoints FastAPI no cambian.
- La jerarquía de deduplicación del dashboard no cambia.
- El score final y sus pesos no cambian.

**Solo cambia la infraestructura que rodea al modelo, no el modelo.**

---

## Qué se tiene que modificar

### 1. Separar entrenamiento de servicio

**Hoy:**
```python
# api/main.py — lifespan
recommender.fit(DATASET_PATH)   # re-entrena al arrancar, bloqueante
```

**Producción:**
```python
# train.py — script independiente, corre en job separado
recommender.fit("s3://bucket/dataset_ml.parquet")
joblib.dump(recommender, "/tmp/modelo.pkl")
s3_client.upload_file("/tmp/modelo.pkl", "bucket", "modelos/modelo_latest.pkl")

# api/main.py — lifespan
s3_client.download_file("bucket", "modelos/modelo_latest.pkl", "/tmp/modelo.pkl")
recommender = joblib.load("/tmp/modelo.pkl")   # carga, no entrena
```

**Archivos a crear/modificar:**
- Crear `train.py` — script de entrenamiento standalone
- Modificar `api/main.py` — reemplazar `fit()` por `load()` en el lifespan
- Crear `api/model_loader.py` — abstracción para cargar desde S3/local

---

### 2. Reemplazar CSV por Parquet en Data Warehouse

**Hoy:**
```python
df = pd.read_csv("data/processed/dataset_ml.csv")
```

**Producción:**
```python
# Opción A: leer directo desde S3 con PyArrow
df = pd.read_parquet("s3://bucket/dataset_ml.parquet")

# Opción B: query directo al Data Warehouse
import sqlalchemy
df = pd.read_sql("SELECT * FROM mart_recomendaciones WHERE fecha >= ...", engine)
```

**Por qué Parquet:** compresión 5-10x mejor que CSV, lectura columnar
(solo lee las columnas que necesita), compatible con Spark para datasets
de cientos de millones de filas.

**Archivos a modificar:**
- `api/recommender.py` — el método `fit()` acepta ruta S3 o conexión DB
- `notebooks/01_dataset.ipynb` — exportar a Parquet además de CSV

---

### 3. Versionado del modelo con rollback

El modelo debe tener versión y permitir rollback si una versión nueva
produce recomendaciones de peor calidad.

```
s3://bucket/modelos/
    modelo_2026-03-14.pkl    ← versión del día
    modelo_2026-03-13.pkl
    modelo_latest.pkl        ← symlink/alias a la versión activa
    modelo_stable.pkl        ← última versión validada manualmente
```

**Cómo hacer rollback:**
```bash
# Si el modelo nuevo da resultados malos
aws s3 cp s3://bucket/modelos/modelo_2026-03-13.pkl \
          s3://bucket/modelos/modelo_latest.pkl
# Reiniciar instancias de la API → cargan la versión anterior
```

**Archivos a crear:**
- `train.py` — incluir fecha en el nombre del archivo al guardar
- Agregar variable de entorno `MODEL_VERSION` en la API para controlar
  qué versión cargar sin cambiar código

---

### 4. Matriz CBF para catálogos grandes

Con 100 000 productos, la matriz de similitud coseno (100k × 100k × 4 bytes)
ocupa **40 GB de RAM** — inviable en una sola instancia.

**Soluciones según tamaño del catálogo:**

| Productos | Solución | Costo RAM |
|---|---|---|
| < 10 000 | Matriz densa completa (actual) | < 400 MB ✓ |
| 10k – 100k | Matriz dispersa (solo top-K vecinos por producto) | ~2 GB |
| > 100k | Approximate Nearest Neighbors (FAISS / Annoy) | configurable |

**Cambio en `recommender.py`:**
```python
# Hoy: similitud coseno completa O(n²)
self._cbf_sim = cosine_similarity(aligned)   # 950×950, OK

# Producción con catálogo grande: solo top-50 vecinos por producto
from sklearn.neighbors import NearestNeighbors
nn = NearestNeighbors(n_neighbors=50, metric="cosine", algorithm="brute")
nn.fit(aligned)
# guardar solo los índices de vecinos, no la matriz completa
self._cbf_neighbors = nn.kneighbors(aligned, return_distance=False)
```

---

### 5. SVD para millones de interacciones

Con 500k clientes × 100k productos, el SVD de scikit-learn falla por memoria.

**Alternativas:**

| Escala | Biblioteca | Notas |
|---|---|---|
| < 1M interacciones | `sklearn.TruncatedSVD` (actual) | Sin cambios |
| 1M – 50M | `implicit` (ALS implícito) | Más rápido, GPU-ready |
| > 50M | `Spark MLlib ALS` | Distribuido, cluster |

**Cambio en `recommender.py` con `implicit`:**
```python
# pip install implicit
import implicit

model = implicit.als.AlternatingLeastSquares(factors=150, iterations=20)
model.fit(R_sparse)   # R_sparse = matriz csr de interacciones

self._U  = model.user_factors    # (n_clientes × 150)
self._Vt = model.item_factors.T  # (150 × n_productos)
# El resto del código no cambia — los vectores tienen la misma forma
```

---

### 6. Infraestructura en la nube (opción AWS)

```
Componente          Servicio AWS            Costo estimado
──────────────────  ──────────────────────  ───────────────
Base de datos       RDS PostgreSQL          ~$15/mes (t3.micro)
Data Warehouse      Redshift Serverless     pago por uso
Almacén de modelos  S3                      ~$0.50/mes
Job de entrena.     SageMaker Training Job  ~$1/ejecución (ml.m5.large, 1h)
API                 ECS Fargate             ~$10/mes (0.5 vCPU, 1GB RAM)
Load Balancer       ALB                     ~$16/mes
──────────────────────────────────────────  ───────────────
Total estimado                              ~$45/mes (producción pequeña)
```

**Alternativa Azure (si la empresa ya usa Microsoft):**
- Entrenamiento → Azure ML Compute
- Almacén → Azure Blob Storage
- API → Azure Container Apps
- BD → Azure Database for PostgreSQL

---

### 7. Reentrenamiento automático (MLOps básico)

El modelo debe re-entrenarse automáticamente con los datos más recientes
sin intervención manual.

```
Cron diario (EventBridge / Cloud Scheduler)
      │
      ▼
Lanzar job de entrenamiento (SageMaker / Vertex AI)
      │
      ▼
Validar métricas (precision@10, coverage)
      │
      ├── métricas OK  ──▶  modelo_latest.pkl = nuevo modelo
      │                     API carga en el próximo restart
      │
      └── métricas malas ──▶  alerta (SNS / PagerDuty)
                               modelo_latest.pkl sin cambios
```

**Archivos a crear:**
- `train.py` — incluir cálculo de métricas al final del entrenamiento
- `scripts/validate_model.py` — comparar métricas nueva vs. versión anterior
- `.github/workflows/retrain.yml` o equivalente en AWS — cron de reentrenamiento

---

## Resumen de archivos a crear/modificar

| Archivo | Acción | Prioridad |
|---|---|---|
| `train.py` | Crear — entrenamiento standalone con joblib.dump | Alta |
| `api/main.py` | Modificar — reemplazar fit() por load() en lifespan | Alta |
| `api/recommender.py` | Modificar — fit() acepta S3/Parquet; CBF disperso si >10k productos | Media |
| `api/model_loader.py` | Crear — abstracción S3/local para cargar el modelo | Media |
| `notebooks/01_dataset.ipynb` | Modificar — exportar Parquet además de CSV | Baja |
| `scripts/validate_model.py` | Crear — validación automática de métricas | Baja |
| `docker/Dockerfile` | Crear — contenedor para ECS/Cloud Run | Alta |
| `docker/docker-compose.yml` | Crear — entorno local equivalente a producción | Media |

---

## Lo que NO cambia al ir a producción

- `api/recommender.py` — lógica del modelo (SVD, CBF, scores, recommend())
- `api/main.py` — endpoints y esquemas de respuesta
- `api/schemas.py` — modelos Pydantic
- La jerarquía de deduplicación del dashboard
- Los pesos del score híbrido (W_CF, W_CBF, W_URGENCY, W_ROTATION, W_NOVELTY)
