"""
train.py — Script de entrenamiento manual del modelo de recomendación

CUÁNDO EJECUTAR:
    - Una vez al día, preferiblemente antes del horario de atención.
    - Cada vez que se actualice el archivo dataset_ml.csv
      (es decir, cuando lleguen nuevas ventas al sistema).
    - La primera vez que se instale el sistema.

CÓMO EJECUTAR (desde la raíz del proyecto):
    python scripts/train.py

QUÉ HACE:
    1. Lee data/processed/dataset_ml.csv
    2. Entrena el modelo híbrido completo (SVD + CBF + scores de negocio)
    3. Guarda el resultado en data/processed/modelo_artifacts.pkl
    4. El servidor (main.py) carga ese .pkl al arrancar — sin re-entrenar.

TIEMPO ESTIMADO:
    Depende del tamaño del dataset. Con datos de ejemplo: 1-3 minutos.
    En producción con historial de 1 año: 5-10 minutos.
"""

import logging
import sys
from pathlib import Path

# Permite importar el paquete api desde la raíz del proyecto
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from api.recommender import HybridRecommender

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger(__name__)

DATASET_PATH = ROOT_DIR / "data" / "processed" / "dataset_ml.csv"
MODEL_PATH   = ROOT_DIR / "data" / "processed" / "modelo_artifacts.pkl"


def main() -> None:
    if not DATASET_PATH.exists():
        logger.error(
            "No se encontró el dataset en '%s'.\n"
            "Asegúrate de haber ejecutado el notebook 01_dataset.ipynb primero.",
            DATASET_PATH,
        )
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("ENTRENAMIENTO DEL MODELO DE RECOMENDACIÓN")
    logger.info("=" * 60)
    logger.info("Dataset : %s", DATASET_PATH)
    logger.info("Destino : %s", MODEL_PATH)
    logger.info("")

    rec = HybridRecommender()
    rec.fit(DATASET_PATH)
    rec.save(MODEL_PATH)

    stats = rec.stats()
    logger.info("")
    logger.info("Entrenamiento completado.")
    logger.info("  Clientes en el modelo : %d", stats["n_clientes"])
    logger.info("  Productos en el modelo: %d", stats["n_productos"])
    logger.info("  Componentes SVD       : %d", stats["svd_components"])
    logger.info("")
    logger.info("El servidor puede arrancar ahora con:")
    logger.info("  uvicorn api.main:app --reload --port 8000")


if __name__ == "__main__":
    main()
