"""
recommender.py — Motor del Sistema de Recomendación Híbrido

Este módulo encapsula toda la lógica del modelo de recomendación.
Es el núcleo del sistema: se entrena una vez y luego sirve predicciones
en tiempo real para la API FastAPI.

ARQUITECTURA DEL SCORE FINAL:
──────────────────────────────
    score_final = W_CF       × score_cf         (Collaborative Filtering)
                + W_CBF      × score_cbf         (Content-Based Filtering)
                + W_URGENCY  × score_urgency     (Caducidad / urgencia de venta)
                + W_ROTATION × score_rotation    (Baja rotación / stock parado)
                + W_NOVELTY  × score_novelty     (Productos nuevos en catálogo)

COMPONENTES:
─────────────
  score_cf:       SVD sobre matriz implícita (cantidad × peso_recencia)
  score_cbf:      Coseno entre vectores de contenido del producto
  score_urgency:  Sigmoide inversa sobre días_para_vencer
  score_rotation: Inverso normalizado de rotación_diaria
  score_novelty:  Decaimiento exponencial sobre días_desde_ingreso
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from sklearn.decomposition import TruncatedSVD
from sklearn.preprocessing import MinMaxScaler, OneHotEncoder

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# PARÁMETROS DEL MODELO
# ──────────────────────────────────────────────────────────────────────────────

# Pesos del score híbrido (deben sumar 1.0)
W_CF        = 0.40   # Collaborative Filtering
W_CBF       = 0.15   # Content-Based Filtering
W_URGENCY   = 0.20   # Urgencia por caducidad
W_ROTATION  = 0.15   # Incentivo a baja rotación
W_NOVELTY   = 0.10   # Novedad en catálogo

# Parámetros de la función de urgencia (sigmoide inversa)
SIGMA_URGENCY = 15   # Pendiente de la curva; menor = curva más abrupta

# Decaimiento de recencia en interacciones (media-vida: 180 días)
TAU_DIAS = 180

# Decaimiento de novedad (media-vida: 30 días desde ingreso)
TAU_NOVEDAD = 30

# Dimensiones SVD (factores latentes)
SVD_COMPONENTS = 150

# Umbral para clasificar un producto como "urgente" (días para vencer)
UMBRAL_URGENCIA = 30

# Umbral para clasificar un producto como "nuevo" (días desde ingreso)
UMBRAL_NOVEDAD = 60

# Candidatos pre-filtrados por CF antes de aplicar los demás scores
TOPK_CF_CANDIDATES = 500

# Número de productos en el output final
TOPK_FINAL = 10

# Últimas N compras para calcular score_cbf
N_COMPRAS_RECIENTES = 10


class HybridRecommender:
    """
    Sistema de recomendación híbrido que combina:
      - Collaborative Filtering (SVD implícito)
      - Content-Based Filtering (coseno sobre features del producto)
      - Scores de negocio: urgencia, rotación y novedad

    Uso típico:
        rec = HybridRecommender()
        rec.fit(dataset_path="data/processed/dataset_ml.csv")
        recomendaciones = rec.recommend("CLI_123456", top_k=10)
    """

    def __init__(self) -> None:
        self.is_fitted = False

        # Datos maestros
        self._df: pd.DataFrame | None = None
        self._productos_df: pd.DataFrame | None = None

        # Matrices CF
        self._U: np.ndarray | None = None         # (n_clientes × SVD_COMPONENTS)
        self._Vt: np.ndarray | None = None        # (SVD_COMPONENTS × n_productos)
        self._user_idx: dict[str, int] = {}       # cliente_id → índice fila
        self._item_idx: dict[str, int] = {}       # producto_id → índice columna
        self._idx_item: dict[int, str] = {}       # índice → producto_id

        # Matriz CBF
        self._item_features: np.ndarray | None = None  # (n_productos × n_features)
        self._cbf_sim: np.ndarray | None = None        # (n_productos × n_productos)

        # Vectores de scores de negocio (indexados por columna en la matriz)
        self._vec_urgency:  np.ndarray | None = None
        self._vec_novelty:  np.ndarray | None = None
        self._vec_rotation: np.ndarray | None = None
        self._vec_vencido:  np.ndarray | None = None   # máscara: 1 = vencido

        # Índices auxiliares
        self._stock_by_item:     dict[str, int] = {}
        self._meta_by_item:      dict[str, dict] = {}
        self._historial_cliente: dict[str, set[str]] = {}

    # ──────────────────────────────────────────────────────────────────────────
    # ENTRENAMIENTO
    # ──────────────────────────────────────────────────────────────────────────

    def fit(self, dataset_path: str | Path) -> "HybridRecommender":
        """
        Entrena todos los componentes del modelo a partir del dataset procesado.

        Args:
            dataset_path: Ruta al archivo dataset_ml.csv generado por
                          el notebook 01_dataset.ipynb.

        Returns:
            self (para encadenamiento).
        """
        logger.info("Cargando dataset desde %s ...", dataset_path)
        df = pd.read_csv(dataset_path, parse_dates=["fecha_venta", "fecha_ingreso_catalogo"])
        self._df = df
        logger.info("Dataset cargado: %d filas, %d clientes, %d productos",
                    len(df),
                    df["cliente_id"].nunique(),
                    df["producto_id"].nunique())

        self._build_product_master()
        self._build_cf_matrix()
        self._build_cbf_matrix()
        self._build_business_scores()
        self._build_aux_indices()

        self.is_fitted = True
        logger.info("Modelo entrenado correctamente.")
        return self

    def _build_product_master(self) -> None:
        """
        Construye el maestro de productos (una fila por producto único).
        Cuando un producto aparece en varias sedes, tomamos la fila con
        mayor stock para los metadatos de negocio.
        """
        df = self._df
        FECHA_HOY = pd.Timestamp(date.today())

        cols_producto = [
            "producto_id", "categoria_producto", "precio_unitario", "COSTO_UNITARIO",
            "stock", "dias_en_stock", "fecha_ingreso_catalogo", "fecha_min_caducidad",
            "dias_para_vencer", "rotacion_diaria", "baja_rotacion",
        ]
        # Tomar la fila con más stock por producto (máximo disponibilidad)
        prods = (
            df[cols_producto]
            .sort_values("stock", ascending=False)
            .drop_duplicates(subset="producto_id", keep="first")
            .copy()
        )

        prods["dias_desde_ingreso"] = (
            FECHA_HOY - prods["fecha_ingreso_catalogo"]
        ).dt.days.clip(lower=0)

        prods["margen_pct"] = (
            (prods["precio_unitario"] - prods["COSTO_UNITARIO"])
            / prods["precio_unitario"]
        ).clip(0, 1)

        self._productos_df = prods.reset_index(drop=True)
        logger.info("Maestro de productos: %d productos únicos.",
                    len(self._productos_df))

    def _build_cf_matrix(self) -> None:
        """
        Construye la matriz de interacciones implícitas y la factoriza con SVD.

        Interacción implícita = cantidad_producto × peso_recencia
            donde peso_recencia = exp(-días_desde_venta / TAU_DIAS)

        Esto da más peso a las compras recientes, modelando la evolución
        de las preferencias del cliente en el tiempo.
        """
        df = self._df
        FECHA_HOY = pd.Timestamp(date.today())

        logger.info("Construyendo matriz de interacciones (CF)...")
        df = df.copy()
        df["dias_desde_venta"] = (FECHA_HOY - df["fecha_venta"]).dt.days.clip(lower=0)
        df["w_recency"] = np.exp(-df["dias_desde_venta"] / TAU_DIAS)
        df["interaccion"] = df["cantidad_producto"] * df["w_recency"]

        # Agregar por (cliente, producto)
        matrix_df = (
            df.groupby(["cliente_id", "producto_id"])["interaccion"]
            .sum()
            .reset_index()
        )

        # Mapas de índice
        clientes = sorted(matrix_df["cliente_id"].unique())
        productos = sorted(self._productos_df["producto_id"].unique())
        self._user_idx = {c: i for i, c in enumerate(clientes)}
        self._item_idx = {p: j for j, p in enumerate(productos)}
        self._idx_item = {j: p for p, j in self._item_idx.items()}

        # Guardar historial por cliente (productos que ya compró)
        self._historial_cliente = (
            matrix_df.groupby("cliente_id")["producto_id"]
            .apply(set)
            .to_dict()
        )

        # Construir matriz dispersa
        rows = matrix_df["cliente_id"].map(self._user_idx).values
        cols = matrix_df["producto_id"].map(self._item_idx).values
        data = matrix_df["interaccion"].values

        n_u = len(clientes)
        n_i = len(productos)
        R = csr_matrix((data, (rows, cols)), shape=(n_u, n_i), dtype=np.float32)

        logger.info("Matriz R: %d clientes × %d productos  |  %d interacciones únicas",
                    n_u, n_i, matrix_df.shape[0])

        # SVD
        n_comp = min(SVD_COMPONENTS, n_u - 1, n_i - 1)
        svd = TruncatedSVD(n_components=n_comp, random_state=42)
        svd.fit(R)

        self._U  = svd.transform(R)   # (n_u, n_comp) — perfiles de clientes
        self._Vt = svd.components_    # (n_comp, n_i) — perfiles de productos

        var_explained = svd.explained_variance_ratio_.sum()
        logger.info("SVD: %d componentes  |  varianza explicada: %.2f%%",
                    n_comp, var_explained * 100)

    def _build_cbf_matrix(self) -> None:
        """
        Construye vectores de features de contenido por producto y
        calcula la matriz de similitud coseno.

        Features usadas (25 dimensiones aprox.):
          - categoria_producto  → OneHot (10 categorías)
          - precio_bucket       → OneHot (bajo/medio/alto)
          - rubro_principal     → OneHot (12 rubros) — rubro más frecuente entre compradores
          - precio_unitario     → MinMaxScaled
          - margen_pct          → MinMaxScaled
        """
        from sklearn.metrics.pairwise import cosine_similarity

        logger.info("Construyendo vectores CBF...")
        df   = self._df
        prods = self._productos_df.copy()

        # Rubro más frecuente entre compradores del producto (afinidad de negocio)
        rubro_modal = (
            df.groupby("producto_id")["rubro_cliente"]
            .agg(lambda x: x.mode()[0] if len(x) > 0 else "Desconocido")
            .reset_index()
            .rename(columns={"rubro_cliente": "rubro_principal"})
        )
        prods = prods.merge(rubro_modal, on="producto_id", how="left")
        prods["rubro_principal"] = prods["rubro_principal"].fillna("Desconocido")

        # Bucket de precio por percentiles
        p33 = prods["precio_unitario"].quantile(0.33)
        p66 = prods["precio_unitario"].quantile(0.66)
        prods["precio_bucket"] = pd.cut(
            prods["precio_unitario"],
            bins=[-np.inf, p33, p66, np.inf],
            labels=["bajo", "medio", "alto"],
        ).astype(str)

        # OneHot encoding
        ohe = OneHotEncoder(sparse_output=False, handle_unknown="ignore")
        cat_cols = ["categoria_producto", "precio_bucket", "rubro_principal"]
        ohe_feats = ohe.fit_transform(prods[cat_cols])

        # Scaling numérico
        scaler = MinMaxScaler()
        num_feats = scaler.fit_transform(prods[["precio_unitario", "margen_pct"]])

        # Concatenar
        item_features = np.hstack([ohe_feats, num_feats]).astype(np.float32)
        self._item_features = item_features

        # Alinear filas con el orden de self._item_idx
        n_items = len(self._item_idx)
        aligned = np.zeros((n_items, item_features.shape[1]), dtype=np.float32)
        prod_ids = prods["producto_id"].values
        for row_idx, prod_id in enumerate(prod_ids):
            if prod_id in self._item_idx:
                col_idx = self._item_idx[prod_id]
                aligned[col_idx] = item_features[row_idx]

        # Similitud coseno full (n_items × n_items)
        self._cbf_sim = cosine_similarity(aligned).astype(np.float32)
        logger.info("CBF: matriz de similitud %d × %d", n_items, n_items)

    def _build_business_scores(self) -> None:
        """
        Pre-calcula los vectores de scores de negocio para todos los productos.
        Se calculan una vez en fit() y se reutilizan en cada llamada a recommend().

        vec_urgency:  sigmoide inversa sobre días_para_vencer
        vec_novelty:  decaimiento exponencial sobre días_desde_ingreso
        vec_rotation: inverso normalizado de rotación_diaria
        vec_vencido:  máscara booleana (1 = producto vencido → excluir)
        """
        logger.info("Calculando scores de negocio...")
        n_items = len(self._item_idx)

        vec_urgency  = np.zeros(n_items, dtype=np.float32)
        vec_novelty  = np.zeros(n_items, dtype=np.float32)
        vec_rotation = np.zeros(n_items, dtype=np.float32)
        vec_vencido  = np.zeros(n_items, dtype=np.float32)

        prods = self._productos_df
        rot_min = prods["rotacion_diaria"].min()
        rot_max = prods["rotacion_diaria"].max()
        rot_range = max(rot_max - rot_min, 1e-9)

        for _, row in prods.iterrows():
            pid = row["producto_id"]
            if pid not in self._item_idx:
                continue
            j = self._item_idx[pid]
            dias_vencer  = row["dias_para_vencer"]
            dias_ingreso = row["dias_desde_ingreso"]
            rot          = row["rotacion_diaria"]

            # Urgencia: sigmoide inversa (alto cuando días_para_vencer → 0)
            if dias_vencer < 0:
                vec_urgency[j] = 0.0
                vec_vencido[j] = 1.0   # excluir de recomendaciones
            else:
                vec_urgency[j] = float(1.0 / (1.0 + np.exp(dias_vencer / SIGMA_URGENCY)))

            # Novedad: decaimiento exponencial desde ingreso
            vec_novelty[j] = float(np.exp(-dias_ingreso / TAU_NOVEDAD))

            # Rotación inversa: más alto = menos rotación = mayor impulso necesario
            vec_rotation[j] = float(1.0 - (rot - rot_min) / rot_range)

        self._vec_urgency  = vec_urgency
        self._vec_novelty  = vec_novelty
        self._vec_rotation = vec_rotation
        self._vec_vencido  = vec_vencido

        n_urgentes = int((vec_urgency > 0.3).sum())
        n_nuevos   = int((vec_novelty  > 0.5).sum())
        n_baja_rot = int((vec_rotation > 0.75).sum())
        logger.info("  Productos urgentes (score_urgency > 0.3): %d", n_urgentes)
        logger.info("  Productos nuevos   (score_novelty  > 0.5): %d", n_nuevos)
        logger.info("  Baja rotación      (score_rotation > 0.75): %d", n_baja_rot)

    def _build_aux_indices(self) -> None:
        """
        Construye índices de acceso rápido para stock y metadatos de productos.
        Evita búsquedas en DataFrame durante la inferencia.
        """
        prods = self._productos_df
        self._stock_by_item = dict(zip(prods["producto_id"], prods["stock"]))
        self._meta_by_item  = prods.set_index("producto_id").to_dict(orient="index")

    # ──────────────────────────────────────────────────────────────────────────
    # INFERENCIA
    # ──────────────────────────────────────────────────────────────────────────

    def recommend(
        self,
        cliente_id: str,
        top_k: int = TOPK_FINAL,
        filtro_tipo: str | None = None,
        umbral_urgencia: int = UMBRAL_URGENCIA,
        umbral_novedad: int = UMBRAL_NOVEDAD,
        pesos_custom: dict[str, float] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Genera recomendaciones personalizadas para un cliente.

        PROCESO (8 pasos):
          1. Verificar que el cliente existe en el modelo.
          2. Calcular score_cf para todos los productos (U[cliente] · Vt).
          3. Pre-filtrar top TOPK_CF_CANDIDATES por score_cf.
          4. Garantizar que productos urgentes y de baja rotación sean candidatos.
          5. Calcular score_cbf (similitud con las últimas N compras del cliente).
          6. Combinar los 5 scores con los pesos configurados.
          7. Aplicar filtros duros (sin stock, vencidos, ya comprados si se desea).
          8. Devolver top-K ordenados por score_final.

        Args:
            cliente_id:      ID del cliente.
            top_k:           Número de recomendaciones a devolver.
            filtro_tipo:     "urgentes" | "baja_rotacion" | "nuevos" | None.
                             Restringe el pool de candidatos al tipo indicado.
            umbral_urgencia: Días máximos para considerar urgente.
            umbral_novedad:  Días máximos de antigüedad para considerar nuevo.
            pesos_custom:    Diccionario opcional para sobrescribir pesos por defecto.
                             Ej: {"W_CF": 0.30, "W_URGENCY": 0.45}

        Returns:
            Lista de dicts con los campos definidos en ProductoRecomendado.

        Raises:
            ValueError: Si el cliente no existe en el modelo.
        """
        if not self.is_fitted:
            raise RuntimeError("El modelo no ha sido entrenado. Llame a fit() primero.")

        if cliente_id not in self._user_idx:
            raise ValueError(
                f"Cliente '{cliente_id}' no encontrado en el modelo. "
                "Solo se pueden recomendar clientes con historial de compras."
            )

        # ── Pesos (custom o por defecto) ──────────────────────────────────────
        w_cf       = (pesos_custom or {}).get("W_CF",       W_CF)
        w_cbf      = (pesos_custom or {}).get("W_CBF",      W_CBF)
        w_urgency  = (pesos_custom or {}).get("W_URGENCY",  W_URGENCY)
        w_rotation = (pesos_custom or {}).get("W_ROTATION", W_ROTATION)
        w_novelty  = (pesos_custom or {}).get("W_NOVELTY",  W_NOVELTY)

        # ── Paso 2: score_cf para todos los productos ─────────────────────────
        u_idx     = self._user_idx[cliente_id]
        user_vec  = self._U[u_idx]                     # (SVD_COMPONENTS,)
        scores_cf = user_vec @ self._Vt                # (n_productos,) — broadcast
        # Normalizar a [0, 1]
        cf_min, cf_max = scores_cf.min(), scores_cf.max()
        scores_cf_norm = (scores_cf - cf_min) / max(cf_max - cf_min, 1e-9)

        # ── Paso 3: pre-filtro por CF ─────────────────────────────────────────
        n_cand  = min(TOPK_CF_CANDIDATES, len(scores_cf_norm))
        top_cf  = set(np.argpartition(scores_cf_norm, -n_cand)[-n_cand:].tolist())

        # ── Paso 4: garantizar urgentes y baja rotación en candidatos ─────────
        urgentes   = set(np.where(self._vec_urgency > 0.3)[0].tolist())
        baja_rot   = set(np.where(self._vec_rotation > 0.75)[0].tolist())
        candidatos = top_cf | urgentes | baja_rot

        # ── Filtro por tipo (si se especifica) ───────────────────────────────
        if filtro_tipo == "urgentes":
            # Solo productos que vencen en umbral_urgencia días
            FECHA_HOY = pd.Timestamp(date.today())
            urgentes_tipo = set()
            for prod_id, meta in self._meta_by_item.items():
                if meta["dias_para_vencer"] <= umbral_urgencia:
                    j = self._item_idx.get(prod_id)
                    if j is not None:
                        urgentes_tipo.add(j)
            candidatos = candidatos & urgentes_tipo if urgentes_tipo else urgentes_tipo

        elif filtro_tipo == "baja_rotacion":
            baja_rot_tipo = set()
            for prod_id, meta in self._meta_by_item.items():
                if meta.get("baja_rotacion", 0) == 1:
                    j = self._item_idx.get(prod_id)
                    if j is not None:
                        baja_rot_tipo.add(j)
            candidatos = candidatos & baja_rot_tipo if baja_rot_tipo else baja_rot_tipo

        elif filtro_tipo == "nuevos":
            nuevos_tipo = set()
            for prod_id, meta in self._meta_by_item.items():
                if meta.get("dias_desde_ingreso", 999) <= umbral_novedad:
                    j = self._item_idx.get(prod_id)
                    if j is not None:
                        nuevos_tipo.add(j)
            candidatos = candidatos & nuevos_tipo if nuevos_tipo else nuevos_tipo

        if not candidatos:
            return []

        candidatos_arr = np.array(sorted(candidatos), dtype=np.int32)

        # ── Paso 5: score_cbf ─────────────────────────────────────────────────
        # Similitud promedio con las últimas N_COMPRAS_RECIENTES del cliente
        historial = list(self._historial_cliente.get(cliente_id, set()))
        scores_cbf_cand = np.zeros(len(candidatos_arr), dtype=np.float32)

        if historial and self._cbf_sim is not None:
            compras_recientes = [
                self._item_idx[p] for p in historial
                if p in self._item_idx
            ][:N_COMPRAS_RECIENTES]

            if compras_recientes:
                sim_recientes = self._cbf_sim[candidatos_arr][:, compras_recientes]
                scores_cbf_cand = sim_recientes.mean(axis=1)

        # ── Paso 6: score final ───────────────────────────────────────────────
        cf_cand       = scores_cf_norm[candidatos_arr]
        urgency_cand  = self._vec_urgency[candidatos_arr]
        rotation_cand = self._vec_rotation[candidatos_arr]
        novelty_cand  = self._vec_novelty[candidatos_arr]

        score_final = (
            w_cf       * cf_cand
            + w_cbf      * scores_cbf_cand
            + w_urgency  * urgency_cand
            + w_rotation * rotation_cand
            + w_novelty  * novelty_cand
        )

        # ── Paso 7: filtros duros ─────────────────────────────────────────────
        vencidos_cand = self._vec_vencido[candidatos_arr].astype(bool)
        sin_stock_cand = np.array(
            [self._stock_by_item.get(self._idx_item.get(j, ""), 0) == 0
             for j in candidatos_arr],
            dtype=bool,
        )
        excluir = vencidos_cand | sin_stock_cand
        score_final[excluir] = -np.inf

        # ── Paso 8: top-K ─────────────────────────────────────────────────────
        top_indices = np.argsort(score_final)[::-1][:top_k]
        FECHA_HOY = pd.Timestamp(date.today())

        resultados = []
        for rank_idx in top_indices:
            if score_final[rank_idx] == -np.inf:
                break
            j       = int(candidatos_arr[rank_idx])
            prod_id = self._idx_item[j]
            meta    = self._meta_by_item.get(prod_id, {})

            dias_ingreso = int(meta.get("dias_desde_ingreso", 0))
            dias_vencer  = int(meta.get("dias_para_vencer", 0))

            resultados.append({
                "producto_id":          prod_id,
                "categoria_producto":   str(meta.get("categoria_producto", "")),
                "precio_unitario":      float(meta.get("precio_unitario", 0)),
                "stock":                int(meta.get("stock", 0)),
                "score_final":          float(round(score_final[rank_idx], 6)),
                "score_cf":             float(round(float(cf_cand[rank_idx]), 6)),
                "score_cbf":            float(round(float(scores_cbf_cand[rank_idx]), 6)),
                "score_urgency":        float(round(float(urgency_cand[rank_idx]), 6)),
                "score_rotation":       float(round(float(rotation_cand[rank_idx]), 6)),
                "score_novelty":        float(round(float(novelty_cand[rank_idx]), 6)),
                "dias_para_vencer":     dias_vencer,
                "dias_desde_ingreso":   dias_ingreso,
                "es_urgente":           bool(dias_vencer <= umbral_urgencia and dias_vencer >= 0),
                "es_nuevo_catalogo":    bool(dias_ingreso <= umbral_novedad),
                "es_baja_rotacion":     bool(meta.get("baja_rotacion", 0) == 1),
                "rotacion_diaria":      float(meta.get("rotacion_diaria", 0)),
            })

        return resultados

    # ──────────────────────────────────────────────────────────────────────────
    # PROPIEDADES / STATS
    # ──────────────────────────────────────────────────────────────────────────

    @property
    def n_clientes(self) -> int:
        return len(self._user_idx)

    @property
    def n_productos(self) -> int:
        return len(self._item_idx)

    def stats(self) -> dict:
        """Resumen del estado del modelo."""
        if not self.is_fitted:
            return {"fitted": False}
        return {
            "fitted":      True,
            "n_clientes":  self.n_clientes,
            "n_productos": self.n_productos,
            "svd_components": SVD_COMPONENTS,
            "pesos": {
                "W_CF": W_CF, "W_CBF": W_CBF, "W_URGENCY": W_URGENCY,
                "W_ROTATION": W_ROTATION, "W_NOVELTY": W_NOVELTY,
            },
            "umbrales": {
                "urgencia_dias": UMBRAL_URGENCIA,
                "novedad_dias":  UMBRAL_NOVEDAD,
            },
        }
