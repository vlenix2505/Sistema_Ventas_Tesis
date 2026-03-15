# Sistema de Recomendación Híbrido — Tesis

**Empresa distribuidora de alimentos | Sector HORECA | Perú**

Sistema de recomendación que combina Collaborative Filtering, Content-Based Filtering
y reglas de negocio para personalizar sugerencias de compra y reducir mermas.

---

## Objetivos del Sistema

1. **Reducir mermas** — Recomendar productos próximos a vencer a clientes con alta afinidad
2. **Mover stock parado** — Identificar productos de baja rotación y ofrecerlos estratégicamente
3. **Fomentar nuevos SKUs** — Acelerar la adopción de productos recién incorporados al catálogo

---

## Arquitectura del Score

```
score_final = 0.40 × score_cf        (Collaborative Filtering — SVD)
            + 0.15 × score_cbf       (Content-Based — similitud coseno)
            + 0.20 × score_urgency   (caducidad próxima — sigmoide inversa)
            + 0.15 × score_rotation  (baja rotación — inverso normalizado)
            + 0.10 × score_novelty   (nuevo en catálogo — decaimiento exponencial)
```

---

## Estructura del Proyecto

```
tesis1/
├── generate_source.py           # Generación de datos sintéticos
├── notebooks/
│   ├── 01_dataset.ipynb         # Limpieza y feature engineering
│   ├── 02_modelo_recomendacion.ipynb  # Entrenamiento del modelo
│   └── build_nb.py              # Regenera el notebook 02
├── api/
│   ├── main.py                  # FastAPI — endpoints de recomendación
│   ├── recommender.py           # Motor de recomendación (HybridRecommender)
│   └── schemas.py               # Modelos Pydantic
├── data/
│   ├── raw/                     # CSVs de datos fuente
│   └── processed/               # dataset_ml.csv (input del modelo)
├── models/                      # Modelo serializado (.joblib)
├── docs/
│   ├── arquitectura_sistema.md  # Diseño completo del sistema
│   └── manual_de_uso.md         # Guía operativa y métricas
└── requirements.txt
```

---

## Inicio Rápido

```bash
# 1. Instalar dependencias
pip install -r requirements.txt

# 2. Generar datos sintéticos
python generate_source.py

# 3. Preparar dataset (ejecutar 01_dataset.ipynb desde Jupyter)
jupyter notebook notebooks/01_dataset.ipynb

# 4. Entrenar modelo (ejecutar 02_modelo_recomendacion.ipynb desde Jupyter)
jupyter notebook notebooks/02_modelo_recomendacion.ipynb

# 5. Iniciar API
uvicorn api.main:app --reload --port 8000
```

---

## Endpoints de la API

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/health` | Estado del servicio y del modelo |
| GET | `/recomendar/{cliente_id}` | Top-K recomendaciones híbridas generales |
| GET | `/recomendar/proximos-vencer/{cliente_id}` | Productos próximos a caducar |
| GET | `/recomendar/baja-rotacion/{cliente_id}` | Productos con baja rotación |
| GET | `/recomendar/nuevos/{cliente_id}` | Nuevos productos del catálogo |

**Documentación interactiva:** `http://localhost:8000/docs`

### Ejemplo

```bash
curl http://localhost:8000/recomendar/proximos-vencer/CLI_000001?top_k=5
```

```json
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
      "score_cf": 0.891,
      "score_urgency": 0.923,
      "dias_para_vencer": 7,
      "es_urgente": true,
      "es_baja_rotacion": false,
      "es_nuevo_catalogo": false
    }
  ]
}
```

---

## Datos Sintéticos

| Entidad | Registros | Variables clave |
|---|---|---|
| Clientes | 800 | rubro, subrubro_1/2, sede (Lima/Piura/Arequipa/Cusco) |
| Productos | 950 únicos (1,799 con sedes) | categoría, precio, costo, stock, caducidad |
| Ventas | 7,950 | fecha, monto_total |
| Detalle | 36,003 líneas | cantidad, subtotal |
| Dataset ML | 290,064 filas × 28 cols | features de cliente, producto, tiempo |

---

## Métricas de Evaluación

| Métrica | Descripción | Valor objetivo |
|---|---|---|
| HitRate@10 | % de clientes donde el próximo producto está en top-10 | > 0.15 |
| Precision@10 | Relevantes en top-10 / 10 | > 0.05 |
| Coverage | % del catálogo que aparece en alguna recomendación | > 0.50 |
| **Urgency Coverage** | % de productos urgentes recomendados activamente | **> 0.50** |
| **Rotation Coverage** | % de productos baja rotación recomendados | **> 0.40** |

Las métricas de negocio (últimas dos) son las más relevantes para validar
que el sistema cumple su propósito principal.

---

## Stack Técnico

- **Python 3.10+**
- **pandas / numpy / scipy** — procesamiento de datos
- **scikit-learn** — SVD (TruncatedSVD), similitud coseno, encoders
- **FastAPI + uvicorn** — API REST
- **pydantic v2** — validación de schemas
- **jupyter** — notebooks de análisis y entrenamiento

---

## Documentación Adicional

- [Arquitectura del sistema](docs/arquitectura_sistema.md) — flujo de datos, diseño técnico, integración
- [Manual de uso](docs/manual_de_uso.md) — guía operativa, interpretación de métricas, troubleshooting
