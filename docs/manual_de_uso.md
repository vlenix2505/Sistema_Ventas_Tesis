# Manual de Uso — Sistema de Recomendación Híbrido

---

## 1. Requisitos Previos

```bash
# Python 3.10 o superior
python --version

# Instalar dependencias
pip install -r requirements.txt
```

---

## 2. Flujo Completo: de Cero a Sistema Activo

### Paso 1 — Generar datos sintéticos

```bash
python src/generate_source.py
```

Genera en `data/raw/`:
- `clientes.csv` — 800 clientes con rubro, subrubros y sede
- `productos.csv` — 950 productos con precios, costos, stock y caducidad
- `ventas.csv` — 7,950 transacciones de venta
- `detalle_venta.csv` — 36,003 líneas de detalle (productos por venta)

Tiempo estimado: < 30 segundos.

### Paso 2 — Preparar el dataset de ML

Abrir Jupyter y ejecutar el notebook:

```bash
jupyter notebook notebooks/01_dataset.ipynb
```

Ejecutar **todas las celdas en orden** (Kernel → Restart & Run All).

Genera: `data/processed/dataset_ml.csv` (290,064 filas × 28 columnas).

Tiempo estimado: 2-5 minutos.

### Paso 3 — Entrenar el modelo

```bash
jupyter notebook notebooks/02_modelo_recomendacion.ipynb
```

Ejecutar **todas las celdas en orden**.

Genera:
- Métricas de evaluación en pantalla (HitRate, Precision, Coverage)
- `data/processed/01_dataset_visualizaciones.png` — gráficas del dataset

Tiempo estimado: 3-8 minutos (SVD + cálculo de similitud coseno).

> **Nota:** el modelo NO requiere ser pre-entrenado y guardado en disco.
> El servidor FastAPI lo entrena en memoria al arrancar (~1 segundo).

### Paso 4 — Iniciar el backend (Terminal 1)

```bash
# Desde la raíz del proyecto
python -m uvicorn api.main:app --reload --port 8000
```

La API entrena el modelo automáticamente al arrancar.

Verificar que está activa:
```bash
curl http://localhost:8000/health
```

Respuesta esperada:
```json
{
  "status": "ok",
  "modelo_cargado": true,
  "n_clientes": 800,
  "n_productos": 950,
  "mensaje": "Servicio operativo."
}
```

### Paso 5 — Iniciar el frontend Streamlit (Terminal 2)

```bash
python -m streamlit run app/streamlit_app.py
```

Abrir en el navegador: `http://localhost:8501`

> El frontend requiere que el backend esté corriendo en `localhost:8000`.
> Siempre arrancar el backend **antes** que el frontend.

---

## 3. Usar el Frontend (Streamlit)

La interfaz Streamlit simula la pantalla de un vendedor en campo.

### 3.1 Login

Al abrir `http://localhost:8501` verás una pantalla de login.
Selecciona cualquiera de los 5 vendedores de muestra y haz clic en "Ingresar".

### 3.2 Seleccionar un cliente

En el panel lateral izquierdo:
- Escribe el nombre o rubro del cliente en el buscador
- O selecciona directamente de la lista desplegable
- El sistema carga automáticamente las recomendaciones del cliente seleccionado

### 3.3 Ver recomendaciones

Las recomendaciones aparecen en tres pestañas o secciones:

| Sección | Color | Qué muestra |
|---|---|---|
| Próximos a vencer | 🔴 Rojo | Productos con menos de 30 días de vida útil, ordenados por afinidad |
| Baja rotación | 🟡 Amarillo | Productos que se mueven poco en el inventario |
| Nuevos | 🟢 Verde | Productos incorporados al catálogo en los últimos 365 días |

Cada tarjeta de producto muestra:
- Nombre y categoría
- Precio unitario
- Stock disponible
- Días para vencer (si aplica)
- Score de recomendación

### 3.4 Agregar al carrito

Haz clic en "Agregar" en cualquier tarjeta de producto.
El carrito en el panel derecho se actualiza en tiempo real con cantidad y subtotal.

### 3.5 Filtrar por categoría

Usa el selector de categorías (Lácteos, Bebidas, Carnes, etc.) para
ver solo los productos de una categoría específica dentro de cada sección.

---

## 4. Usar los Endpoints de la API

### Documentación interactiva

Abrir en el navegador: `http://localhost:8000/docs`

Permite probar cada endpoint directamente desde el navegador sin necesidad de código.

### 4.1 Obtener un cliente_id válido

Formato: `CLI_XXXXXX` (e.g., `CLI_000001`).

Puedes obtener una lista de clientes ejecutando en Python:
```python
import pandas as pd
df = pd.read_csv("data/processed/dataset_ml.csv")
print(df["cliente_id"].unique()[:10])
```

### 4.2 Recomendación general

```bash
curl http://localhost:8000/recomendar/CLI_000001
```

Devuelve el top-10 de productos con mayor score híbrido para el cliente.
Mezcla los tres tipos (urgentes, baja rotación, nuevos) según sus pesos.

### 4.3 Dashboard unificado

```bash
curl http://localhost:8000/recomendar/dashboard/CLI_000001
```

Devuelve las tres secciones en una sola llamada, sin duplicados entre secciones.
Los productos urgentes tienen prioridad; si ya aparecen ahí, no se repiten en baja rotación.

**Cuándo usar este endpoint:**
- Para alimentar la pantalla principal del frontend
- Cuando se necesita mostrar las tres categorías a la vez sin redundancia

### 4.4 Productos próximos a vencer

```bash
# Con umbral por defecto (30 días)
curl http://localhost:8000/recomendar/proximos-vencer/CLI_000001

# Con umbral personalizado (7 días)
curl "http://localhost:8000/recomendar/proximos-vencer/CLI_000001?umbral_dias=7"
```

**Cuándo usar este endpoint:**
- En el carrito de compra, para ofrecer descuento en productos urgentes
- En campañas de email diarias para clientes con alta afinidad a productos próximos a vencer
- En el panel del encargado de almacén, para ver qué productos urgentes no se están moviendo

**Interpretar la respuesta:**
```json
{
  "tipo": "proximos_vencer",
  "umbral_dias": 30,
  "total_urgentes_catalogo": 41,
  "top_k": 5,
  "productos": [
    {
      "producto_id": "PROD_000234",
      "dias_para_vencer": 7,
      "score_urgency": 0.9234,
      "score_cf": 0.8910,
      "score_final": 0.7823,
      "es_urgente": true
    }
  ]
}
```

- `total_urgentes_catalogo = 41`: hay 41 productos urgentes en el catálogo
- `top_k = 5`: se recomendaron 5 (puede ser menor si el cliente solo tiene afinidad con algunos urgentes disponibles en su sede)
- `score_urgency = 0.9234`: producto muy urgente (solo 7 días)
- `score_cf = 0.8910`: alta afinidad histórica del cliente con este producto
- `score_final = 0.7823`: score combinado — el más alto de su lista

### 4.5 Productos de baja rotación

```bash
curl http://localhost:8000/recomendar/baja-rotacion/CLI_000001
```

Devuelve productos con baja rotación (cuartil inferior de ventas diarias) que el
cliente tiene mayor probabilidad de comprar.

**Cuándo usar este endpoint:**
- En visitas comerciales, para que el vendedor mencione productos que "no se mueven"
- En bundles o promociones de volumen
- Para gestión de inventario: identificar qué clientes podrían absorber el stock parado

**Interpretar los campos:**
- `rotacion_diaria`: cuántas unidades se venden por día (valores bajos = producto parado)
- `score_rotation`: `1 - normalize(rotacion_diaria)`. Alto = muy poca rotación.
- `umbral_rotacion_percentil: 0.25`: se incluyen los productos en el cuartil inferior

### 4.6 Productos nuevos

```bash
# Con umbral por defecto (365 días)
curl http://localhost:8000/recomendar/nuevos/CLI_000001

# Más restrictivo: solo los últimos 90 días
curl "http://localhost:8000/recomendar/nuevos/CLI_000001?umbral_dias_novedad=90"
```

Devuelve productos ingresados recientemente al catálogo, ordenados por afinidad.

**Cuándo usar este endpoint:**
- Para introducir nuevos SKUs al portafolio de clientes existentes
- En comunicaciones de "novedades del mes"
- Para medir la adopción de nuevos productos por cliente

---

## 5. Métricas del Modelo — Cómo Interpretarlas

Las métricas se calculan en el notebook 02, sección "Evaluación del Modelo".

### 5.1 Métricas estándar de recomendación

| Métrica | Fórmula | Qué mide | Valor aceptable |
|---|---|---|---|
| **HitRate@10** | % de clientes donde el próximo producto está en top-10 | Capacidad predictiva básica | > 0.15 |
| **Precision@10** | Relevantes en top-10 / 10 | Calidad de la lista | > 0.05 |
| **Recall@10** | Relevantes encontrados / total relevantes | Cobertura del historial | > 0.05 |
| **Coverage** | Productos únicos recomendados / catálogo total | Diversidad del sistema | > 0.50 |

**Nota sobre valores bajos:** Con una densidad de matriz del 0.15% (muy sparse),
HitRate@10 = 0.15 ya es un buen resultado. Un sistema aleatorio daría ~0.01.

### 5.2 Métricas de negocio (las más importantes para la tesis)

| Métrica | Qué mide | Valor aceptable |
|---|---|---|
| **Urgency Coverage** | % de productos urgentes que se recomiendan a algún cliente | > 0.50 |
| **Rotation Coverage** | % de productos baja rotación que se recomiendan | > 0.40 |

**Urgency Coverage** es la métrica más importante: si el sistema tiene
Urgency Coverage = 0.80, significa que el 80% de los productos próximos a vencer
están siendo recomendados activamente a clientes con afinidad, lo que maximiza
la probabilidad de reducir la merma.

### 5.3 Análisis de sensibilidad

El notebook compara 4 escenarios de pesos:

| Escenario | CF | CBF | Urgency | Rotation | Novelty | Cuándo usarlo |
|---|---|---|---|---|---|---|
| **Baseline** | 0.40 | 0.15 | 0.20 | 0.15 | 0.10 | Operación normal |
| **Prioridad caducidad** | 0.30 | 0.10 | 0.45 | 0.10 | 0.05 | Alto inventario próximo a vencer |
| **Prioridad baja rotación** | 0.30 | 0.10 | 0.10 | 0.45 | 0.05 | Stock parado crítico |
| **Solo CF (ablación)** | 1.00 | 0.00 | 0.00 | 0.00 | 0.00 | Benchmark de referencia |

Si Urgency Coverage con "Prioridad caducidad" es mucho mayor que con "Baseline",
conviene ajustar los pesos según la temporada o la situación del inventario.

---

## 6. ¿Cómo Saber si el Sistema Está Funcionando Correctamente?

### Checklist de validación

| Verificación | Resultado esperado |
|---|---|
| Backend activo | `curl localhost:8000/health` → `"status": "ok"` |
| Modelo cargado | Logs de uvicorn: `Modelo listo. Clientes: 800 \| Productos: 950` |
| Frontend activo | Abrir `http://localhost:8501` → pantalla de login |
| Frontend conectado al backend | Al seleccionar un cliente, aparecen las recomendaciones |

### Señales de que algo está mal

| Síntoma | Causa probable | Solución |
|---|---|---|
| `404 Cliente no encontrado` | cliente_id inválido | Verificar formato `CLI_XXXXXX` |
| `503 Modelo no disponible` | dataset_ml.csv no existe | Ejecutar notebook 01 primero |
| Frontend muestra "Error al conectar" | Backend no está corriendo | Iniciar `python -m uvicorn api.main:app --port 8000` |
| Streamlit muestra pantalla en blanco | Puerto 8501 ocupado | Usar `--server.port 8502` |
| Urgency Coverage = 0 | No hay productos urgentes | Verificar que `dias_para_vencer` tiene valores ≤ 30 en el dataset |
| Todos los endpoints devuelven [] | Problema con filtros de stock | Verificar que `stock > 0` en el maestro de productos |

### Interpretar el log de arranque del backend

```
INFO  api.main — Iniciando servidor — cargando modelo desde data/processed/dataset_ml.csv
INFO  api.recommender — Dataset cargado: 290064 filas, 800 clientes, 950 productos
INFO  api.recommender — Matriz R: 800 clientes × 950 productos  |  43876 interacciones únicas
INFO  api.recommender — SVD: 150 componentes  |  varianza explicada: 63.45%
INFO  api.recommender — CBF: matriz de similitud 950 × 950
INFO  api.recommender — Productos urgentes (score_urgency > 0.3): 41
INFO  api.recommender — Productos nuevos   (score_novelty  > 0.5): 237
INFO  api.recommender — Baja rotación      (score_rotation > 0.75): 250
INFO  api.main — Modelo listo.  Clientes: 800  |  Productos: 950
```

- **Varianza explicada ≥ 60%**: el SVD captura bien el comportamiento de compra
- **Interacciones únicas ~44K**: densidad de ~5.8% (antes del ajuste por recencia)
- **41 productos urgentes**: número razonable para un catálogo de 950 productos

---

## 7. Variables Configurables

Las siguientes constantes en `api/recommender.py` permiten ajustar el comportamiento
sin reentrenar el modelo:

```python
# Pesos del score híbrido (deben sumar 1.0)
W_CF        = 0.40
W_CBF       = 0.15
W_URGENCY   = 0.20
W_ROTATION  = 0.15
W_NOVELTY   = 0.10

# Umbrales de clasificación
UMBRAL_URGENCIA = 30   # días para considerar "urgente"
UMBRAL_NOVEDAD  = 365  # días para considerar "nuevo"

# Parámetros del modelo
SVD_COMPONENTS     = 150   # dimensión latente (más → más memoria, más precisión)
TOPK_CF_CANDIDATES = 500   # candidatos pre-filtrados por CF
TAU_DIAS           = 180   # vida media del decaimiento de recencia (días)
TAU_NOVEDAD        = 30    # vida media del decaimiento de novedad (días)
SIGMA_URGENCY      = 15    # pendiente de la sigmoide de urgencia
```

**Para cambiar los umbrales sin redeployar**, usa los query params de la API:
```bash
# Umbral de urgencia más estricto: solo productos a 7 días o menos
curl "http://localhost:8000/recomendar/proximos-vencer/CLI_000001?umbral_dias=7"
```

---

## 8. Regenerar los Notebooks

Si necesitas cambiar el código del notebook 02 y regenerar el archivo `.ipynb`:

```bash
cd notebooks/
python build_nb.py
```

Esto sobreescribe `02_modelo_recomendacion.ipynb` con el código actualizado en
`build_nb.py`. Es el método recomendado para mantener el notebook bajo control
de versiones sin conflictos de formato JSON.
