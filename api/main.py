"""
main.py — API FastAPI del Sistema de Recomendación Híbrido

Expone endpoints RESTful para obtener recomendaciones de productos
personalizadas por cliente, con variantes para los tres casos de negocio:
    1. Recomendación general (híbrida)
    2. Productos próximos a vencer
    3. Productos de baja rotación
    4. Productos nuevos en catálogo

CÓMO EJECUTAR:
    uvicorn api.main:app --reload --port 8000

DOCUMENTACIÓN INTERACTIVA:
    http://localhost:8000/docs   (Swagger UI)
    http://localhost:8000/redoc  (ReDoc)

INTEGRACIÓN CON EL FRONTEND (carrito de compra):
    El vendedor selecciona un cliente → la app llama a GET /recomendar/{cliente_id}
    La respuesta incluye hasta 10 productos divididos por las 3 categorías:
        - urgentes (productos próximos a vencer)
        - baja_rotacion (productos que necesitan impulso)
        - nuevos (nuevos SKUs del catálogo)
    El frontend muestra estas listas en el carrito de compra como sugerencias.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.recommender import HybridRecommender, UMBRAL_URGENCIA, UMBRAL_NOVEDAD
from api.schemas import (
    ErrorResponse,
    HealthResponse,
    RecomendacionBajaRotacion,
    RecomendacionDashboard,
    RecomendacionGeneral,
    RecomendacionNuevos,
    RecomendacionProximosVencer,
)

# ──────────────────────────────────────────────────────────────────────────────
# LOGGING
# ──────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN
# ──────────────────────────────────────────────────────────────────────────────
ROOT_DIR      = Path(__file__).resolve().parent.parent
DATASET_PATH  = os.getenv(
    "DATASET_PATH",
    str(ROOT_DIR / "data" / "processed" / "dataset_ml.csv"),
)
DEFAULT_TOP_K = 10

# ──────────────────────────────────────────────────────────────────────────────
# CICLO DE VIDA DE LA APP (startup / shutdown)
# ──────────────────────────────────────────────────────────────────────────────
# El modelo se entrena UNA SOLA VEZ al arrancar el servidor y queda en memoria.
# Esto garantiza latencia de inferencia < 100ms por request.

MODEL_PATH = Path(os.getenv(
    "MODEL_PATH",
    str(ROOT_DIR / "data" / "processed" / "modelo_artifacts.pkl"),
))

recommender: HybridRecommender = HybridRecommender()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Carga el modelo pre-entrenado al arrancar el servidor.

    El modelo se entrena por separado ejecutando:
        python scripts/train.py

    Si el archivo .pkl no existe, se intenta entrenar en el momento como
    fallback (útil en entornos de desarrollo por primera vez).
    """
    global recommender
    if MODEL_PATH.exists():
        logger.info("Cargando modelo pre-entrenado desde %s ...", MODEL_PATH)
        try:
            recommender = HybridRecommender.load(MODEL_PATH)
            logger.info("Modelo listo.  Clientes: %d  |  Productos: %d",
                        recommender.n_clientes, recommender.n_productos)
        except Exception:
            logger.exception("Error al cargar el modelo. Verifica el archivo .pkl.")
    else:
        logger.warning(
            "No se encontró modelo pre-entrenado en %s. "
            "Entrenando desde el dataset (esto puede tardar varios minutos)...",
            MODEL_PATH,
        )
        try:
            recommender.fit(DATASET_PATH)
            recommender.save(MODEL_PATH)
            logger.info("Modelo entrenado y guardado.  "
                        "Clientes: %d  |  Productos: %d",
                        recommender.n_clientes, recommender.n_productos)
        except FileNotFoundError:
            logger.error(
                "No se encontró el dataset en %s. "
                "Ejecuta primero el notebook 01_dataset.ipynb y luego "
                "python scripts/train.py",
                DATASET_PATH,
            )
    yield
    logger.info("Servidor detenido.")


# ──────────────────────────────────────────────────────────────────────────────
# INSTANCIA DE LA APP
# ──────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="API de Recomendaciones — Sistema Híbrido",
    description="""
## Sistema de Recomendación Híbrido para distribuidora de alimentos

Este servicio genera recomendaciones de productos personalizadas para cada cliente,
combinando tres enfoques:

| Componente              | Peso | Descripción                                              |
|-------------------------|------|----------------------------------------------------------|
| Collaborative Filtering | 40%  | Basado en historial de compras de clientes similares     |
| Content-Based Filtering | 15%  | Basado en similitud de atributos de productos            |
| Score de Urgencia       | 20%  | Prioriza productos próximos a vencer                     |
| Score de Rotación       | 15%  | Prioriza productos con baja rotación                     |
| Score de Novedad        | 10%  | Prioriza nuevos productos en el catálogo                 |

### Casos de uso principales
- **Carrito de compra**: mostrar recomendaciones mientras el vendedor arma el pedido
- **Gestión de inventario**: identificar qué productos ofrecer para reducir mermas
- **Introducción de nuevos SKUs**: fomentar la adopción de productos nuevos
    """,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS: permitir acceso desde el frontend de ventas
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # En producción: limitar a dominios específicos
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────────────────────────────────────
# HELPER: obtener sede del cliente desde el modelo
# ──────────────────────────────────────────────────────────────────────────────

def _get_sede_cliente(cliente_id: str) -> str:
    """Recupera la sede del cliente desde los metadatos del dataset."""
    if recommender._df is not None and "sede_cliente" in recommender._df.columns:
        fila = recommender._df[recommender._df["cliente_id"] == cliente_id]
        if not fila.empty:
            return str(fila["sede_cliente"].iloc[0])
    return "Desconocida"


def _cliente_valido(cliente_id: str) -> None:
    """Valida que el cliente exista en el modelo. Lanza HTTPException si no."""
    if not recommender.is_fitted:
        raise HTTPException(
            status_code=503,
            detail="Modelo no disponible. El servidor está iniciando o el dataset no fue encontrado.",
        )
    if cliente_id not in recommender._user_idx:
        raise HTTPException(
            status_code=404,
            detail=f"Cliente '{cliente_id}' no encontrado. "
                   "Solo se admiten clientes con historial de compras en el sistema.",
        )


# ──────────────────────────────────────────────────────────────────────────────
# ENDPOINTS
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["Sistema"])
def health_check():
    """
    Verifica el estado del servicio y del modelo.

    **Uso típico:** monitoreo automático, health check de Kubernetes/Docker.
    """
    return HealthResponse(
        status="ok" if recommender.is_fitted else "degraded",
        modelo_cargado=recommender.is_fitted,
        n_clientes=recommender.n_clientes,
        n_productos=recommender.n_productos,
        mensaje="Servicio operativo." if recommender.is_fitted
                else "El modelo no está cargado. Revisa los logs.",
    )


@app.get(
    "/recomendar/{cliente_id}",
    response_model=RecomendacionGeneral,
    responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    tags=["Recomendaciones"],
    summary="Recomendación general híbrida",
)
def recomendar_general(
    cliente_id: str,
    top_k: int = Query(default=DEFAULT_TOP_K, ge=1, le=50,
                       description="Número de productos a recomendar (máx. 50)."),
):
    """
    Genera las **top-K recomendaciones híbridas** para un cliente específico.

    ### Cuándo usar este endpoint
    - En el carrito de compra, para mostrar una lista general de sugerencias.
    - Combina todos los criterios: historial del cliente + urgencia + rotación + novedad.

    ### Cómo funciona
    1. Calcula score_cf usando la factorización SVD del historial de compras.
    2. Enriquece con score_cbf (similitud de contenido con lo que ya compró).
    3. Suma los scores de negocio (urgencia, rotación, novedad).
    4. Filtra productos sin stock o vencidos.
    5. Devuelve los top-K por score_final.

    ### Ejemplo de respuesta
    Cada producto incluye su score desglosado y flags de negocio
    (es_urgente, es_nuevo_catalogo, es_baja_rotacion) para que el vendedor
    pueda contextualizar la recomendación.
    """
    _cliente_valido(cliente_id)
    try:
        productos = recommender.recommend(cliente_id, top_k=top_k)
    except Exception as e:
        logger.exception("Error en recomendación para %s", cliente_id)
        raise HTTPException(status_code=500, detail=str(e))

    return RecomendacionGeneral(
        cliente_id=cliente_id,
        sede=_get_sede_cliente(cliente_id),
        top_k=len(productos),
        productos=productos,
        mensaje=f"{len(productos)} recomendaciones generadas para el cliente {cliente_id}.",
    )


@app.get(
    "/recomendar/proximos-vencer/{cliente_id}",
    response_model=RecomendacionProximosVencer,
    responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    tags=["Recomendaciones"],
    summary="Productos próximos a vencer",
)
def recomendar_proximos_vencer(
    cliente_id: str,
    top_k: int = Query(default=DEFAULT_TOP_K, ge=1, le=50),
    umbral_dias: int = Query(
        default=UMBRAL_URGENCIA, ge=1, le=180,
        description="Días máximos para considerar un producto urgente.",
    ),
):
    """
    Recomienda productos del catálogo que **vencen próximamente** y que,
    según el historial del cliente, éste podría comprar.

    ### Problema de negocio que resuelve
    - Reduce mermas por caducidad priorizando la venta de lotes próximos a vencer.
    - El sistema no recomienda cualquier producto urgente, sino aquellos que
      tienen alta afinidad con el cliente específico (CF + CBF).

    ### Lógica de ranking
    - Pre-filtra productos con `dias_para_vencer ≤ umbral_dias`.
    - Rankea dentro del filtro usando score_final completo (no solo urgencia).
    - Esto garantiza que el cliente reciba urgentes que realmente compraría.

    ### Caso de uso
    - Vendedor puede usar esta lista para ofrecer productos urgentes con descuento.
    - La app puede mostrar un badge "¡Por vencer!" en el carrito de compra.
    """
    _cliente_valido(cliente_id)
    try:
        productos = recommender.recommend(
            cliente_id,
            top_k=top_k,
            filtro_tipo="urgentes",
            umbral_urgencia=umbral_dias,
        )
    except Exception as e:
        logger.exception("Error en recomendación urgentes para %s", cliente_id)
        raise HTTPException(status_code=500, detail=str(e))

    # Contar total de urgentes en el catálogo
    total_urgentes = sum(
        1 for meta in recommender._meta_by_item.values()
        if 0 <= meta.get("dias_para_vencer", 999) <= umbral_dias
    )

    return RecomendacionProximosVencer(
        cliente_id=cliente_id,
        sede=_get_sede_cliente(cliente_id),
        top_k=len(productos),
        umbral_dias=umbral_dias,
        total_urgentes_catalogo=total_urgentes,
        productos=productos,
        mensaje=(
            f"{len(productos)} productos próximos a vencer recomendados para {cliente_id}. "
            f"Total urgentes en catálogo: {total_urgentes}."
        ),
    )


@app.get(
    "/recomendar/baja-rotacion/{cliente_id}",
    response_model=RecomendacionBajaRotacion,
    responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    tags=["Recomendaciones"],
    summary="Productos de baja rotación",
)
def recomendar_baja_rotacion(
    cliente_id: str,
    top_k: int = Query(default=DEFAULT_TOP_K, ge=1, le=50),
):
    """
    Recomienda productos con **baja rotación de inventario** que el cliente
    tiene mayor probabilidad de comprar.

    ### Problema de negocio que resuelve
    - La empresa tiene productos con stock detenido que acumulan costos de almacén.
    - Este endpoint identifica los productos de baja rotación que, según el perfil
      del cliente, tienen mayor probabilidad de ser adquiridos.

    ### Definición de "baja rotación"
    - Productos en el cuartil inferior de `rotacion_diaria` (p25 del catálogo).
    - `rotacion_diaria` = unidades_vendidas / días_activo_en_catálogo.

    ### Caso de uso
    - El vendedor puede ofrecer estos productos como parte de un bundle o con
      incentivo de precio durante la visita al cliente.
    - La gestión comercial puede usar esta lista para diseñar promociones.
    """
    _cliente_valido(cliente_id)
    try:
        productos = recommender.recommend(
            cliente_id,
            top_k=top_k,
            filtro_tipo="baja_rotacion",
        )
    except Exception as e:
        logger.exception("Error en recomendación baja rotación para %s", cliente_id)
        raise HTTPException(status_code=500, detail=str(e))

    total_baja = sum(
        1 for meta in recommender._meta_by_item.values()
        if meta.get("baja_rotacion", 0) == 1
    )

    return RecomendacionBajaRotacion(
        cliente_id=cliente_id,
        sede=_get_sede_cliente(cliente_id),
        top_k=len(productos),
        umbral_rotacion_percentil=0.25,
        total_baja_rotacion_catalogo=total_baja,
        productos=productos,
        mensaje=(
            f"{len(productos)} productos de baja rotación recomendados para {cliente_id}. "
            f"Total en catálogo: {total_baja}."
        ),
    )


@app.get(
    "/recomendar/nuevos/{cliente_id}",
    response_model=RecomendacionNuevos,
    responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    tags=["Recomendaciones"],
    summary="Productos nuevos en catálogo",
)
def recomendar_nuevos(
    cliente_id: str,
    top_k: int = Query(default=DEFAULT_TOP_K, ge=1, le=50),
    umbral_dias_novedad: int = Query(
        default=UMBRAL_NOVEDAD, ge=1, le=365,
        description="Días desde ingreso para considerar un producto 'nuevo'.",
    ),
):
    """
    Recomienda **productos nuevos del catálogo** que podrían interesar al cliente.

    ### Problema de negocio que resuelve
    - Los nuevos SKUs tienen el problema del "cold-start": sin historial de ventas,
      los sistemas CF tradicionales no los recomiendan.
    - El score de novedad (`score_novelty`) compensa este problema dando un boost
      exponencial a productos recién ingresados al catálogo.
    - El sistema filtra los nuevos que, por contenido (CBF), son similares a lo
      que el cliente ya compra, haciendo la recomendación coherente.

    ### Caso de uso
    - La app puede mostrar una sección "Novedades para ti" en el carrito de compra.
    - El área comercial puede medir la adopción de nuevos productos por cliente.
    """
    _cliente_valido(cliente_id)
    try:
        productos = recommender.recommend(
            cliente_id,
            top_k=top_k,
            filtro_tipo="nuevos",
            umbral_novedad=umbral_dias_novedad,
        )
    except Exception as e:
        logger.exception("Error en recomendación nuevos para %s", cliente_id)
        raise HTTPException(status_code=500, detail=str(e))

    total_nuevos = sum(
        1 for meta in recommender._meta_by_item.values()
        if meta.get("dias_desde_ingreso", 999) <= umbral_dias_novedad
    )

    return RecomendacionNuevos(
        cliente_id=cliente_id,
        sede=_get_sede_cliente(cliente_id),
        top_k=len(productos),
        umbral_dias_novedad=umbral_dias_novedad,
        total_nuevos_catalogo=total_nuevos,
        productos=productos,
        mensaje=(
            f"{len(productos)} nuevos productos recomendados para {cliente_id}. "
            f"Total nuevos en catálogo: {total_nuevos}."
        ),
    )


# ──────────────────────────────────────────────────────────────────────────────
# DASHBOARD UNIFICADO — jerarquía con exclusión en cascada
# ──────────────────────────────────────────────────────────────────────────────

@app.get(
    "/recomendar/dashboard/{cliente_id}",
    response_model=RecomendacionDashboard,
    responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    tags=["Recomendaciones"],
    summary="Dashboard unificado sin duplicados (jerarquía urgentes → baja rotación → nuevos)",
)
def recomendar_dashboard(
    cliente_id: str,
    top_k: int = Query(default=DEFAULT_TOP_K, ge=1, le=50,
                       description="Productos por sección (máx. 50)."),
    umbral_dias: int = Query(default=UMBRAL_URGENCIA, ge=1, le=180),
    umbral_dias_novedad: int = Query(default=UMBRAL_NOVEDAD, ge=1, le=365),
):
    """
    Genera **tres listas sin productos repetidos** para mostrar en el dashboard
    del vendedor.

    ### Jerarquía de asignación
    Cada producto se asigna a la categoría de **mayor prioridad de negocio**:

    1. **urgentes** — vencen en ≤ `umbral_dias` días (prioridad máxima)
    2. **baja_rotacion** — stock parado, excluyendo los ya en urgentes
    3. **nuevos** — SKUs recientes, excluyendo los ya en las secciones anteriores

    ### Por qué esto importa
    Sin esta jerarquía, un producto que es urgente Y tiene baja rotación
    aparecería en dos secciones, confundiendo al vendedor sobre qué argumento
    usar para ofrecerlo.

    ### Caso de uso
    - Frontend del vendedor: mostrar tres secciones claramente diferenciadas.
    - El argumento de venta cambia según la sección:
      - Urgente → "Este producto vence pronto, te lo ofrezco con descuento"
      - Baja rotación → "Este producto tiene buena disponibilidad, ideal para stock"
      - Nuevo → "Acabamos de incorporar esto al catálogo, pruébalo"
    """
    _cliente_valido(cliente_id)

    # Pedimos un pool más amplio (top_k * 3) para tener margen tras la deduplicación
    pool = top_k * 3

    try:
        candidatos_urgentes  = recommender.recommend(
            cliente_id, top_k=pool,
            filtro_tipo="urgentes", umbral_urgencia=umbral_dias,
        )
        candidatos_baja_rot  = recommender.recommend(
            cliente_id, top_k=pool,
            filtro_tipo="baja_rotacion",
        )
        candidatos_nuevos    = recommender.recommend(
            cliente_id, top_k=pool,
            filtro_tipo="nuevos", umbral_novedad=umbral_dias_novedad,
        )
    except Exception as e:
        logger.exception("Error en dashboard para %s", cliente_id)
        raise HTTPException(status_code=500, detail=str(e))

    # ── Cascada de exclusión ──────────────────────────────────────────────────
    # Paso 1: urgentes (sin filtro adicional, todos son válidos)
    urgentes = candidatos_urgentes[:top_k]
    ids_usados = {p["producto_id"] for p in urgentes}

    # Paso 2: baja rotación — excluir los que ya están en urgentes
    baja_rotacion = [
        p for p in candidatos_baja_rot
        if p["producto_id"] not in ids_usados
    ][:top_k]
    ids_usados |= {p["producto_id"] for p in baja_rotacion}

    # Paso 3: nuevos — excluir los que ya aparecen en las dos secciones anteriores
    nuevos = [
        p for p in candidatos_nuevos
        if p["producto_id"] not in ids_usados
    ][:top_k]

    total = len(urgentes) + len(baja_rotacion) + len(nuevos)

    return RecomendacionDashboard(
        cliente_id=cliente_id,
        sede=_get_sede_cliente(cliente_id),
        top_k_por_seccion=top_k,
        urgentes=urgentes,
        baja_rotacion=baja_rotacion,
        nuevos=nuevos,
        total_recomendaciones=total,
        mensaje=(
            f"Dashboard generado para {cliente_id}: "
            f"{len(urgentes)} urgentes | "
            f"{len(baja_rotacion)} baja rotación | "
            f"{len(nuevos)} nuevos. "
            f"Sin duplicados entre secciones."
        ),
    )


# ──────────────────────────────────────────────────────────────────────────────
# PUNTO DE ENTRADA DIRECTO
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
