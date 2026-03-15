"""
schemas.py — Modelos Pydantic para la API de recomendaciones.

Define las estructuras de entrada y salida de cada endpoint.
Pydantic garantiza validación automática y genera documentación
OpenAPI/Swagger sin esfuerzo adicional.
"""

from typing import Literal
from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────────────────────────────────
# MODELOS DE UN PRODUCTO RECOMENDADO
# ──────────────────────────────────────────────────────────────────────────────

class ProductoRecomendado(BaseModel):
    """Datos de un producto incluido en cualquier tipo de recomendación."""

    producto_id: str = Field(
        description="Identificador único del producto."
    )
    categoria_producto: str = Field(
        description="Categoría del producto (Lácteos, Bebidas, etc.)."
    )
    precio_unitario: float = Field(
        description="Precio de venta al cliente en soles."
    )
    stock: int = Field(
        description="Unidades disponibles en la sede del cliente."
    )
    score_final: float = Field(
        ge=0.0, le=1.0,
        description="Puntuación híbrida global del modelo (0=peor, 1=mejor)."
    )
    score_cf: float = Field(
        ge=0.0, le=1.0,
        description="Componente Collaborative Filtering (SVD). "
                    "Qué tan compatible es el cliente con este producto según historial."
    )
    score_cbf: float = Field(
        ge=0.0, le=1.0,
        description="Componente Content-Based Filtering. "
                    "Similaridad con productos que el cliente ya compró."
    )
    score_urgency: float = Field(
        ge=0.0, le=1.0,
        description="Urgencia de venta por caducidad. "
                    "Más alto = producto más próximo a vencer."
    )
    score_rotation: float = Field(
        ge=0.0, le=1.0,
        description="Penalización por baja rotación. "
                    "Más alto = producto menos vendido (necesita impulso)."
    )
    score_novelty: float = Field(
        ge=0.0, le=1.0,
        description="Boost por novedad. "
                    "Más alto = producto más reciente en el catálogo."
    )
    dias_para_vencer: int = Field(
        description="Días que quedan hasta la fecha de caducidad del lote. "
                    "Valores negativos indican producto ya vencido (no debería aparecer)."
    )
    dias_desde_ingreso: int = Field(
        description="Días desde que el producto ingresó al catálogo."
    )
    es_urgente: bool = Field(
        description="True si el producto tiene ≤ UMBRAL_URGENCIA días para vencer."
    )
    es_nuevo_catalogo: bool = Field(
        description="True si el producto ingresó al catálogo hace ≤ UMBRAL_NOVEDAD días."
    )
    es_baja_rotacion: bool = Field(
        description="True si el producto está en el cuartil inferior de rotación."
    )
    rotacion_diaria: float = Field(
        description="Velocidad de venta: unidades vendidas por día desde la primera compra."
    )


# ──────────────────────────────────────────────────────────────────────────────
# RESPUESTAS POR TIPO DE ENDPOINT
# ──────────────────────────────────────────────────────────────────────────────

class RecomendacionBase(BaseModel):
    """Campos comunes a todas las respuestas de recomendación."""

    cliente_id: str = Field(
        description="ID del cliente para quien se generan las recomendaciones."
    )
    sede: str = Field(
        description="Sede/ciudad del cliente (determina disponibilidad de stock)."
    )
    top_k: int = Field(
        description="Número máximo de productos devueltos."
    )
    productos: list[ProductoRecomendado] = Field(
        description="Lista de productos recomendados, ordenados por score_final desc."
    )


class RecomendacionGeneral(RecomendacionBase):
    """
    Respuesta del endpoint /recomendar/{cliente_id}.
    Devuelve el top-K híbrido general, combinando todos los scores.
    """
    tipo: Literal["general"] = "general"
    mensaje: str = Field(
        default="Recomendaciones personalizadas generadas correctamente.",
        description="Mensaje descriptivo del resultado."
    )


class RecomendacionProximosVencer(RecomendacionBase):
    """
    Respuesta del endpoint /recomendar/proximos-vencer/{cliente_id}.
    Filtra productos que vencen en los próximos N días y los rankea
    combinando urgency score con la afinidad CF del cliente.
    """
    tipo: Literal["proximos_vencer"] = "proximos_vencer"
    umbral_dias: int = Field(
        description="Días máximos para considerar un producto 'próximo a vencer'."
    )
    total_urgentes_catalogo: int = Field(
        description="Total de productos urgentes en el catálogo de la sede del cliente."
    )
    mensaje: str = Field(
        default="Productos próximos a vencer que el cliente podría comprar.",
        description="Mensaje descriptivo del resultado."
    )


class RecomendacionBajaRotacion(RecomendacionBase):
    """
    Respuesta del endpoint /recomendar/baja-rotacion/{cliente_id}.
    Filtra productos con baja rotación y los rankea según afinidad con el cliente.
    Útil para que los vendedores promuevan stock que no se mueve.
    """
    tipo: Literal["baja_rotacion"] = "baja_rotacion"
    umbral_rotacion_percentil: float = Field(
        description="Percentil usado para definir 'baja rotación' (default p25)."
    )
    total_baja_rotacion_catalogo: int = Field(
        description="Total de productos con baja rotación en el catálogo."
    )
    mensaje: str = Field(
        default="Productos de baja rotación con mayor afinidad para este cliente.",
        description="Mensaje descriptivo del resultado."
    )


class RecomendacionNuevos(RecomendacionBase):
    """
    Respuesta del endpoint /recomendar/nuevos/{cliente_id}.
    Filtra productos nuevos en el catálogo y los rankea por afinidad.
    Aborda el problema de cold-start de nuevos SKUs.
    """
    tipo: Literal["nuevos"] = "nuevos"
    umbral_dias_novedad: int = Field(
        description="Días máximos de antigüedad para considerar un producto 'nuevo'."
    )
    total_nuevos_catalogo: int = Field(
        description="Total de productos nuevos en el catálogo."
    )
    mensaje: str = Field(
        default="Nuevos productos del catálogo recomendados para este cliente.",
        description="Mensaje descriptivo del resultado."
    )


# ──────────────────────────────────────────────────────────────────────────────
# DASHBOARD UNIFICADO (deduplicado por jerarquía)
# ──────────────────────────────────────────────────────────────────────────────

class RecomendacionDashboard(BaseModel):
    """
    Respuesta del endpoint /recomendar/dashboard/{cliente_id}.

    Devuelve tres listas **sin productos repetidos**, asignando cada producto
    a la categoría de mayor prioridad de negocio:

        1. urgentes      → vencen pronto (prioridad máxima: evitar mermas)
        2. baja_rotacion → stock parado (liberar inventario)
        3. nuevos        → SKUs recientes (adopción de catálogo)

    Un producto que es urgente Y tiene baja rotación aparece solo en `urgentes`.
    """
    cliente_id: str
    sede: str
    top_k_por_seccion: int = Field(
        description="Número de productos devueltos por cada sección."
    )
    urgentes: list[ProductoRecomendado] = Field(
        description="Productos que vencen pronto, rankeados por score_final híbrido."
    )
    baja_rotacion: list[ProductoRecomendado] = Field(
        description="Productos con stock parado, excluidos los ya asignados a urgentes."
    )
    nuevos: list[ProductoRecomendado] = Field(
        description="Nuevos SKUs del catálogo, excluidos los ya asignados a las secciones anteriores."
    )
    total_recomendaciones: int = Field(
        description="Suma de productos en las tres secciones."
    )
    mensaje: str


# ──────────────────────────────────────────────────────────────────────────────
# RESPUESTA DE ESTADO / HEALTH CHECK
# ──────────────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    """Respuesta del endpoint /health."""
    status: Literal["ok", "degraded", "error"]
    modelo_cargado: bool
    n_clientes: int
    n_productos: int
    mensaje: str


# ──────────────────────────────────────────────────────────────────────────────
# RESPUESTA DE ERROR
# ──────────────────────────────────────────────────────────────────────────────

class ErrorResponse(BaseModel):
    """Estructura estándar de error."""
    error: str
    detalle: str | None = None
    cliente_id: str | None = None
