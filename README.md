# Predicción del precio de gafas graduadas con Machine Learning

## Resumen

Este proyecto desarrolla un modelo de *Machine Learning* para estimar el precio de gafas graduadas a partir de variables físicas del producto y variables comerciales ligadas al posicionamiento de marca.

La idea central no es solo predecir un número, sino entender mejor cómo se construye el valor de este tipo de producto en un catálogo real:

> el precio no depende únicamente de la geometría de la montura, sino también de la marca, el segmento y la percepción de valor asociada al producto

## Problema de negocio

En un catálogo amplio, fijar o validar precios de forma manual puede ser lento, poco consistente y difícil de escalar. Un modelo predictivo como este puede ayudar a:

- apoyar decisiones de *pricing*
- detectar productos potencialmente mal posicionados en precio
- analizar diferencias entre marcas y segmentos
- aportar una referencia objetiva para tareas de catálogo y negocio

## Objetivo del proyecto

Construir un flujo completo de proyecto de datos, desde la adquisición de la información hasta la evaluación e interpretación del modelo final.

El trabajo incluye:

- adquisición y consolidación de datos
- limpieza e imputación
- análisis exploratorio
- *feature engineering*
- entrenamiento y comparación de modelos
- selección del modelo final
- evaluación en test
- interpretación técnica y de negocio

## Dataset

El dataset se construyó a partir de datos de catálogo y enriquecimiento adicional de marca y materiales.

Variables principales:

- marca
- género
- material de montura
- forma
- color
- talla
- ancho de lente
- ancho de puente
- largo de varilla
- peso
- país de origen
- gama de marca
- segmento comercial
- `precio_medio_marca`

El proyecto utiliza las siguientes carpetas de datos:

- `data/raw`
- `data/processed`
- `data/train`
- `data/test`

## Estructura del repositorio

```text
Proyecto ML/
|-- data/
|   |-- raw/
|   |-- processed/
|   |-- train/
|   |-- test/
|
|-- notebooks/
|   |-- 01_Fuentes.ipynb
|   |-- 02_LimpiezaEDA.ipynb
|   |-- 03_Modelado.ipynb
|
|-- src/
|-- models/
|-- app_streamlit/
|-- docs/
|-- README.md
```

## Flujo de trabajo

### `01_Fuentes.ipynb`

Notebook de adquisición de datos, revisión de fuentes y consolidación del dataset base.

### `02_LimpiezaEDA.ipynb`

Notebook de limpieza, imputación, análisis exploratorio, detección de redundancias y creación de variables.

### `03_Modelado.ipynb`

Notebook de construcción de *pipelines*, comparación de modelos, validación cruzada, *grid search*, evaluación final e interpretación.

## Metodología

El proyecto se desarrolló con una lógica iterativa y orientada a toma de decisiones:

1. revisión y validación del dato
2. análisis exploratorio para entender el problema
3. creación de variables con sentido físico y comercial
4. comparación de varias familias de modelos
5. ablaciones por bloques de variables
6. selección del modelo final por rendimiento e interpretabilidad

Además, se utilizaron:

- *pipelines*
- validación cruzada
- *grid search*

Esto permite un flujo reproducible y reduce el riesgo de fugas de información entre entrenamiento y evaluación.

## Modelos evaluados

Se compararon distintos enfoques supervisados:

- `DummyRegressor`
- `Linear Regression`
- `Ridge`
- `Lasso`
- `ElasticNet`
- `RandomForestRegressor`

Los modelos lineales se trabajaron sobre `log_precio`, pero evaluando siempre en euros. Los modelos basados en árboles se entrenaron directamente sobre `precio`.

## Modelo final

El mejor modelo final fue:

- `RandomForestRegressor`

Guardado en:

- `models/final_model_randomforest.pkl`

## Resultados

Métricas del modelo final en test:

| Métrica | Valor |
| --- | ---: |
| MAE | **17.78 €** |
| RMSE | 27.78 € |
| R² | **0.84** |
| MAPE | 14.75% |

Comparativa con el finalista lineal:

| Modelo | MAE | R² |
| --- | ---: | ---: |
| Random Forest | **17.78 €** | **0.84** |
| Ridge | 21.02 € | 0.81 |

La conclusión técnica es clara: el problema presenta cierta estructura lineal, pero el modelo basado en árboles captura mejor relaciones no lineales e interacciones entre variables.

## Hallazgos principales

Los resultados del proyecto muestran varios puntos relevantes:

- `precio_medio_marca` fue la variable más influyente en el modelo final
- la marca y el posicionamiento comercial explican una parte muy importante del precio
- `peso` aportó más señal que varias variables físicas derivadas
- algunas variables intuitivas resultaron poco útiles y se descartaron tras las ablaciones
- el análisis de multicolinealidad ayudó a eliminar variables redundantes

En conjunto, el proyecto sugiere que el precio de una gafa graduada está mucho más influido por el universo de marca y su posicionamiento de mercado que por la geometría pura de la montura.

## Archivos principales

- dataset procesado: `data/processed/lentiamo_graduadas_clean.csv`
- train: `data/train/train.csv`
- test: `data/test/test.csv`
- modelo final: `models/final_model_randomforest.pkl`

## Próximos pasos

Las mejoras más naturales del proyecto serían:

- trasladar la lógica principal a scripts en `src`
- desplegar una app de predicción en Streamlit
- ampliar el dataset con nuevas fuentes o variables de negocio
- explorar técnicas de explicabilidad más avanzadas como SHAP
- comparar con modelos boosting en una siguiente iteración

## Stack utilizado

- Python
- Pandas
- NumPy
- Scikit-learn
- Matplotlib
- Seaborn
- Jupyter Notebooks

## Autor

Juan A. M.  
Proyecto individual del módulo de Machine Learning del bootcamp de Data Science.
