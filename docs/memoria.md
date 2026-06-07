# Memoria del proyecto

**Predicción del precio de gafas graduadas — caso óptica**

Proyecto final del módulo de Machine Learning · The Bridge Bootcamp Data Science.
Autor: Juan Antonio M. M.

---

## 1. Resumen ejecutivo

Este proyecto desarrolla un modelo de Machine Learning capaz de **estimar el precio de mercado de unas gafas graduadas** a partir de sus atributos (marca, material, medidas, género, color, etc.). El caso de uso planteado es el de una óptica que necesita una herramienta de *pricing* asistido para fijar precios competitivos a nuevas referencias de su catálogo.

El dataset se construyó mediante webscraping ético del catálogo de **Lentiamo España**, obteniendo 2.875 productos con 16 variables. Tras un proceso completo de limpieza, EDA, enriquecimiento experto y feature engineering, se compararon 7 modelos en validación cruzada y el ganador (RandomForest) se evaluó en test obteniendo un **MAE de 17.18 €** y un **R² de 0.87** sobre un rango de precio de mercado de 19 € a 480 €.

El proyecto demuestra rigor metodológico (Pipelines + ColumnTransformer, GridSearchCV, ablaciones de variables, análisis VIF) y aporta una pieza diferencial: el **enriquecimiento del dataset con conocimiento experto de marcas y materiales** generado vía LLMs (Perplexity + NotebookLM), que convierte conocimiento del mundo real en features predictivas.

---

## 2. Caso de negocio

Una óptica que vende gafas online o en tienda física se enfrenta cada vez que recibe un nuevo modelo de un fabricante a la pregunta: *¿a qué precio debo venderlo?*. La decisión tradicional combina el PVP recomendado, el margen objetivo y la sensibilidad al precio percibido del producto. Un modelo de pricing automatizado puede:

- Establecer un **precio recomendado consistente** alineado con el mercado, basado en cientos de productos similares.
- **Detectar oportunidades de margen** (productos infraestimados respecto a sus comparables).
- **Soportar decisiones de catálogo**: si un proveedor propone una nueva colección a un coste X, el modelo estima a qué precio puede salir y qué margen permite.
- **Reducir la dependencia del PVP del fabricante**, históricamente la única referencia.

El target del modelo es el **precio actual de mercado** (no el PVP teórico), porque es lo que reflejan los competidores y lo que el cliente acepta pagar.

---

## 3. Adquisición de datos

### 3.1. Fuente seleccionada

Tras descartar dos opciones iniciales por bloqueos técnicos (Mister Spex había cerrado operaciones en España y SmartBuyGlasses presentaba un AWS WAF antibots incompatible con `requests` puro en Jupyter sobre Windows), se eligió **Lentiamo España** (`lentiamo.es`) por tres motivos:

1. Catálogo amplio (~3.000 referencias de gafas graduadas).
2. HTML estático, sin JavaScript pesado ni firewall agresivo.
3. **Catálogo multi-marca real**: 75 marcas, desde lujo (Tom Ford, Bottega Veneta) hasta marca propia low-cost (Lentiamo), pasando por premium y licencias infantiles. Esta diversidad da rango de precios y garantiza variabilidad para el modelo.

### 3.2. Estrategia de scraping

Se desarrolló un scraper en `notebooks/01_Fuentes.ipynb` con dos fases:

1. **Descubrimiento de URLs** — recorre las páginas de listado paginadas de gafas graduadas y extrae enlaces a fichas de producto. Filtro robusto que descarta páginas estáticas (políticas, cesta), categorías de lentillas, y subcategorías de la propia sección de gafas.
2. **Parseo de fichas** — para cada URL, extrae los datos estructurados de la tabla `vc-table-dotted` que Lentiamo usa de forma consistente para las especificaciones técnicas. Captura adicional del atributo `data-thname` para obtener marca + modelo limpios.

El scraping incorpora resiliencia (delays politely entre 0.8-2 s, reintentos con backoff, guardado incremental cada 50 productos) y se completó en ~75 minutos sin bloqueos.

### 3.3. Variables capturadas

Para cada producto se extrajeron 16 variables: identificadores (url, modelo), atributos categóricos (marca, género, material_montura, forma, tipo_montura, color, talla), medidas físicas (ancho_lente, ancho_puente, largo_varilla, calibre_total, peso) y target (precio).

---

## 4. Limpieza y exploración (EDA)

### 4.1. Split train/test y limpieza inicial

El **split train/test (80/20) es la primera operación del notebook 02**, antes de cualquier limpieza, imputación o feature engineering. Se hace así de forma deliberada para evitar *fuga de datos* (*data leakage*): cualquier estadístico que el preprocesado necesite aprender —medianas de imputación, modas, `precio_medio_marca`— se calcula **solo sobre train** y después se aplica sin recalcular sobre test. Así el conjunto de test permanece como una muestra verdaderamente no vista hasta la evaluación final.

- Drop de columnas no útiles (`url`, `tipo`, `polarizadas` siempre vacía en graduadas).
- Drop de duplicados por modelo y de filas con `precio` o `marca` nulos. La limpieza redujo el dataset de 2.875 a 2.870 filas (5 filas eliminadas — los datos venían muy limpios del scraping).
- Imputación inteligente de los ~5 % de NaN en medidas: mediana **dentro de cada marca** (las marcas tienen tamaños típicos), con fallback a mediana global. Categóricas imputadas por moda. Todas estas medianas y modas se **aprenden del train y se reaplican sobre test**, nunca al revés.

### 4.2. Reducción de multicolinealidad

Se detectó analíticamente que `calibre_total ≈ 2 · ancho_lente + ancho_puente` (correlación r > 0.99). Es una redundancia matemática, así que se eliminó `calibre_total`.

### 4.3. Decisión sobre el target

Se decidió **no winsorizar** los precios altos. Justificación de negocio: las observaciones de 400-500 € corresponden a productos premium reales (Tom Ford, Saint Laurent, Bottega Veneta), no a outliers ni errores. Recortar esos valores haría que el modelo subestimase sistemáticamente el segmento alto, justo donde la óptica más margen obtiene. En su lugar se creó `log_precio = log(1 + precio)` como target alternativo (transformación no destructiva) para los modelos lineales.

### 4.4. Hallazgos relevantes del EDA

- **Distribución de precio**: asimétrica con cola larga (mediana ~114 €, máximo ~480 €). Trabajar en log normaliza la distribución.
- **75 marcas únicas** con cola larga: ~28 marcas tienen menos de 10 productos cada una.
- **`marca` es la variable más asociada al precio** (η² ≈ 0.8), seguida de las medidas físicas y características de marca.
- Las binarias derivadas (`montura_completa`, `es_unisex`, `material_eco`, `color_basico`) tienen asociación débil con el precio.

---

## 5. Feature engineering

Se generaron 8 features derivadas con sentido de negocio:

| Feature              | Descripción                                            | Tipo     |
|----------------------|--------------------------------------------------------|----------|
| `aspect_ratio`       | `ancho_lente / largo_varilla` — proxy de estilo        | numérica |
| `area_aprox`         | `ancho_lente · ancho_puente` — para densidad           | numérica |
| `densidad`           | `peso / area_aprox` — proxy de material denso          | numérica |
| `ancho_total`        | `2·ancho_lente + ancho_puente` — calibre reconstruido  | numérica |
| `montura_completa`   | binaria, montura completa vs al aire                   | binaria  |
| `es_unisex`          | binaria, género unisex                                 | binaria  |
| `color_basico`       | binaria, color negro o marrón                          | binaria  |
| `material_eco`       | binaria, monturas Eco-friendly                         | binaria  |

En las ablaciones (sección 7) se decide cuáles realmente aportan valor predictivo y cuáles solo añaden ruido o redundancia.

---

## 6. Enriquecimiento experto (pieza diferencial)

Una marca como "Tom Ford" no significa nada para un modelo de ML por sí sola, salvo lo que aprenda por target encoding del propio dataset. Sin embargo, en el mundo real una persona experta sabe que Tom Ford pertenece al segmento de lujo, que es un fabricante italiano, y que su rango de precio típico está entre 250-400 €. Toda esta información es completamente ignorada si solo enseñamos al modelo el nombre de la marca.

Para inyectar este conocimiento del mundo real en el dataset se diseñó un flujo de dos pasos:

1. **Investigación con Perplexity AI** mediante un prompt estructurado que enviaba la lista completa de las 75 marcas y solicitaba para cada una su `tier` (lujo / premium / gama_media / gama_baja / licencia_infantil), `segmento` (moda_lujo, moda_premium, deportiva, infantil_licencia, marca_blanca_OEM, heritage_iconica), país de origen y rango de precio típico.
2. **Estructuración con NotebookLM** mediante un segundo prompt que extraía el output de Perplexity y lo convertía en un CSV limpio con separador `;` listo para `pandas.merge`.

El resultado (`data/raw/marcas_tier.csv`) se mergea con el dataset principal en el notebook 02. Esto añade **5 features nuevas de baja cardinalidad y alto poder predictivo**: `gama_marca`, `segmento_comercial`, `pais_origen`, `precio_min`, `precio_max`.

El mismo flujo se aplicó al campo `material_montura` (`materiales_tier.csv`) para obtener `categoria_material`, `gama_material` y `peso_relativo`.

**Por qué esto suma:** el modelo ahora entiende implícitamente que dos productos de marcas distintas pero del mismo `tier` y `segmento` son comparables. Sin enriquecimiento, el modelo solo podría aprender esta relación si tuviese suficientes ejemplos de cada marca individualmente, lo cual no es el caso para las marcas de cola larga.

---

## 7. Modelado

### 7.1. Familias comparadas

Se evaluaron 7 modelos en validación cruzada (KFold = 5) sobre el conjunto de train, todos integrados en `Pipeline` con `ColumnTransformer` para evitar leakage:

- `DummyRegressor` (baseline trivial).
- `LinearRegression`, `Ridge`, `Lasso`, `ElasticNet` — entrenados sobre `log_precio` con `TransformedTargetRegressor` (la transformación inversa devuelve euros, así las métricas son comparables).
- `RandomForestRegressor`, `HistGradientBoostingRegressor` — entrenados sobre `precio` directo.

Las métricas reportadas son **siempre en euros** para que sean interpretables a nivel de negocio.

### 7.2. Ablaciones de variables

Se diseñaron 4 bloques de ablación, ejecutados con un modelo representativo de cada familia (Ridge para lineales, HistGradientBoosting para árboles):

| Bloque | Pregunta                                | Decisión                                |
|--------|-----------------------------------------|-----------------------------------------|
| **A**  | ¿precio_min/max o solo precio_medio?    | Quedarse solo con `precio_medio_marca`  |
| **B**  | ¿originales o `ancho_total`?            | Originales (ancho_lente + puente + varilla) |
| **C**  | ¿peso, densidad o ambas?                | Solo `peso`                              |
| **D**  | ¿binarias débiles aportan?              | Eliminarlas                              |

### 7.3. Análisis de multicolinealidad

Se calculó VIF sobre las features numéricas. Se confirmó la decisión de tirar `calibre_total`, `ancho_total`, `area_aprox`, `densidad`, `precio_min`, `precio_max` por VIF > 10 o redundancia evidente. La eliminación de estas features mejora la estabilidad de los coeficientes en los modelos lineales sin penalizar a los árboles.

### 7.4. Configuración final

Tras las ablaciones se fijó un set minimalista de **5 features numéricas + 10 categóricas**:

- **Numéricas:** `ancho_lente`, `ancho_puente`, `largo_varilla`, `peso`, `precio_medio_marca`.
- **Categóricas:** `marca`, `genero`, `material_montura`, `forma`, `tipo_montura`, `color`, `talla`, `gama_marca`, `segmento_comercial`, `pais_origen` (+ `categoria_material`, `gama_material`, `peso_relativo` si están disponibles).

Sobre este set se ejecutó `GridSearchCV` para hiperparámetros (`alpha` en Ridge, `n_estimators × max_depth × min_samples_leaf × max_features` en RandomForest).

---

## 8. Resultados

Los dos finalistas (Ridge en log y RandomForest en €) se evaluaron **una sola vez** en el conjunto de test (20 % del total = 575 productos), un conjunto separado al inicio del pipeline y no usado en ninguna fase de entrenamiento ni de selección de modelo.

| Modelo                                 | MAE (€) | RMSE (€) |   R²  | MAPE (%) |
|----------------------------------------|--------:|---------:|------:|---------:|
| Ridge (log) — finalista lineal         |  20.59  |   28.73  | 0.84  |  17.03   |
| **RandomForest — finalista árboles**   | **17.18** | **25.85** | **0.87** | **15.11** |

### 8.1. Lectura de los resultados

- **MAE = 17.18 €** sobre una mediana de mercado de 114 €: el modelo se equivoca en promedio ~15 % del precio. Para un caso de pricing asistido en óptica es una precisión muy razonable — quedaría dentro del margen típico de negociación con el fabricante o de ajuste manual del responsable de catálogo.
- **R² = 0.87**: el modelo explica el 87 % de la varianza del precio, lo que confirma que las features capturan los drivers reales (marca, materiales, medidas, gama).
- **MAPE = 15.11 %**: el error relativo medio es bajo, y se distribuye de forma equilibrada entre productos baratos y premium (gracias a la decisión de no winsorizar).
- **RandomForest gana al lineal en todas las métricas** (~3.4 € menos de MAE, ~2.9 € menos de RMSE, +0.03 de R², ~1.9 puntos menos de MAPE). La diferencia confirma que el problema tiene interacciones no-lineales (marca × material × tamaño) que el modelo lineal no captura aunque trabaje en log.
- **El RMSE (25.85 €) es ~50 % mayor que el MAE (17.18 €)**, lo que indica una distribución de errores con cola: la mayoría de predicciones están muy cerca del valor real, pero hay un puñado de casos extremos. Coincide con el análisis cualitativo de los top-10 errores absolutos: suelen ser ediciones limitadas o productos con descuentos puntuales no codificados en el modelo.

El modelo final está serializado en `models/final_model.pkl` y se carga con `joblib.load` en cualquier script o app downstream.

---

## 9. Interpretabilidad

El notebook 03 incluye dos análisis de interpretabilidad:

- **Permutation importance** sobre el RandomForest finalista, calculada con `scoring='neg_mean_absolute_error'` para que las importancias se expresen en aumento esperado de MAE en € al permutar cada feature. Esto permite contar a un stakeholder de negocio frases como *"si quitamos la información de marca, el error promedio aumenta en X €"*.
- **Coeficientes del Ridge** con su signo y magnitud (en escala log), útiles como sanity check: las features que esperaríamos ver con coeficiente positivo (gama_marca = lujo, marca = Tom Ford) lo tienen; las que esperaríamos con coeficiente negativo (gama_marca = gama_baja, licencia_infantil) también.

Los gráficos diagnósticos (real vs predicho, residuos) revelan que el modelo ajusta razonablemente bien en todo el rango de precio, sin sesgo sistemático en la zona alta — confirmación de que la decisión de no winsorizar fue correcta.

---

## 10. Limitaciones y próximos pasos

### Limitaciones reconocidas

- **Cobertura geográfica única**: el dataset proviene de un solo retailer (Lentiamo). Productos disponibles en otros retailers pueden tener un rango de precio distinto.
- **Snapshot temporal**: el scraping captura el precio en un momento concreto. Las ofertas y promociones pueden haber distorsionado parcialmente el target.
- **Fuente de las features expertas**: el enriquecimiento via LLMs introduce posible sesgo según el conocimiento del modelo. Para producción se recomendaría validación humana de la clasificación de marcas.
- **Solo gafas graduadas**: el modelo de gafas de sol queda fuera de este entregable (existe el dataset `data/raw/lentiamo_sol.csv` para futuro trabajo).

### Próximos pasos

- **Re-scrape periódico** para mantener el modelo actualizado con la dinámica del mercado.
- **Modelo separado de gafas de sol** que incluya feature `polarizadas` y filtros UV.
- **Detección de promociones** como feature explícita (`en_oferta`, `descuento_pct`) extraídos del precio tachado.
- **Despliegue en Streamlit** como interfaz web para validación cualitativa por parte del equipo de la óptica.
- **Validación A/B** una vez en producción: comparar precios sugeridos por el modelo vs precios fijados por el equipo humano y medir impacto en margen y rotación.

---

## 11. Estructura del repositorio

```
Proyecto ML/
├── data/
│   ├── raw/                    # CSVs del scraping + clasificaciones expertas
│   ├── processed/              # Dataset limpio listo para modelar
│   ├── train/                  # Split de entrenamiento
│   └── test/                   # Split de test
├── notebooks/
│   ├── 01_Fuentes.ipynb        # Scraping de Lentiamo
│   ├── 02_LimpiezaEDA.ipynb    # Limpieza, EDA, feature engineering
│   └── 03_Modelado.ipynb       # Comparación de modelos, ablaciones, evaluación
├── src/
│   ├── data_processing.py      # Replica el notebook 02 en script ejecutable
│   ├── training.py             # Entrena el modelo final con GridSearch
│   └── evaluation.py           # Evalúa contra test y reporta métricas
├── models/
│   └── final_model.pkl         # Modelo entrenado (RandomForest + ColumnTransformer)
├── docs/
│   ├── memoria.md              # Este documento
│   └── negocio.pptx            # Presentación de negocio
└── README.md
```

---

## 12. Cómo reproducir el pipeline

Desde la raíz del proyecto:

```bash
# 1. Procesar datos crudos → split train/test + dataset limpio
python src/data_processing.py

# 2. Entrenar el modelo final con GridSearch
python src/training.py

# 3. Evaluar en test
python src/evaluation.py
```

Cada script es independiente y solo depende del anterior por los archivos en disco. El pipeline completo se ejecuta en menos de 5 minutos en una máquina local estándar.

Para una exploración más visual (gráficos de EDA, ablaciones, diagnósticos), ejecutar los notebooks en orden:

```bash
jupyter lab notebooks/
```

---

*Fin de la memoria.*
