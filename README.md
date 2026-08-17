# ¿Qué determina el precio de unas gafas graduadas?

Análisis de 6.121 monturas graduadas de las dos grandes cadenas de óptica que venden online en España, con datos capturados por scrapers propios en agosto de 2026.

La marca explica el 81 % de la varianza del precio. La geometría de la montura, el 16 %.

---

## La pregunta

Las dos cadenas analizadas pertenecen a fabricantes de gafas rivales entre sí:

| Cadena | Propietario |
|---|---|
| Óptica 2000 | Grandvisión Spain, es decir EssilorLuxottica |
| General Óptica | Grupo De Rigo |

Comprobado el 1 ago 2026 en el pie de `optica2000.com` y el comunicado de EssilorLuxottica sobre el cierre de la compra de GrandVision (1 jul 2021), y en `derigo.com` para General Óptica.

Eso permite plantear algo que no es una pregunta de producto sino de estructura de mercado:

> ¿Condiciona la propiedad del minorista lo que vende y a qué precio?

Es falsable y se responde contando referencias.

## Lo que este proyecto NO es

No es una herramienta de pricing para ópticas, y conviene decirlo antes que nada. El precio de unas gafas graduadas lo dominan la lente, el laboratorio, el local y el tiempo del optometrista, no la montura. Un modelo de precios de montura no le ahorra dinero a una óptica.

Lo que hace es medir cómo la concentración del sector se refleja en el surtido y en el precio de catálogo.

---

## Los tres hallazgos

### 1. La exclusión entre cadenas va en una sola dirección

| Grupo | Óptica 2000 | General Óptica |
|---|---:|---:|
| EssilorLuxottica | 71,1 % | 36,5 % |
| GrandVision (marca blanca propia) | 19,1 % | 0 % |
| De Rigo | 0,6 % | 27,6 % |
| Kering Eyewear | 3,3 % | 4,7 % |
| Safilo | 0,5 % | 8,4 % |
| Marchon | 0 % | 3,5 % |
| Marcolin | 2,2 % | 3,7 % |
| Thélios (LVMH) | 0 % | 0,7 % |

El 90,2 % del catálogo de Óptica 2000 pertenece a su propietario o a su propia marca blanca. Todos los fabricantes rivales juntos suman 6,6 %, y cuatro grupos completos están en cero, entre ellos Marchon, que licencia Nike, Lacoste, Calvin Klein y Ferragamo.

La hipótesis de partida era simétrica, cada cadena favorece lo suyo, y los datos la desmienten: General Óptica dedica a EssilorLuxottica un 36,5 % de lo que lista y un 24,5 % de lo que tiene en stock, muy por encima del 6,6 % que Óptica 2000 dedica a todos sus rivales.

De Rigo no puede sostener una cadena de ópticas en España sin Ray-Ban. EssilorLuxottica sí puede sostener una sin Police.

### 2. El precio de catálogo está alineado; lo que cambia es el descuento

Cruzando por EAN los 110 productos físicamente idénticos presentes en las dos cadenas, el mismo día:

```
PRECIO DE CATÁLOGO (PVP)     diferencia mediana  +0,7 %   ·   |dif| < 5 % en el 99 % de los casos
PRECIO QUE PAGA EL CLIENTE   diferencia mediana −23,8 %
```

El precio nominal es prácticamente el mismo la venda quien la venda. La competencia entre estas cadenas no ocurre en el precio de tarifa, sino en el surtido y en la política de descuento.

### 3. El precio lo pone el nombre, no la montura

R² en test de un modelo entrenado solo con cada bloque de variables:

| Con solo… | R² |
|---|---:|
| la marca | 0,81 |
| el grupo propietario | 0,24 |
| la geometría (calibre y puente) | 0,16 |
| la tienda | 0,00 |

Que `tienda` dé 0,00 no es un fallo: es la confirmación independiente del hallazgo 2. Se observó primero sobre 110 productos y luego el modelo lo verificó por su cuenta sobre 6.120.

---

## El modelo

RandomForest sobre el PVP (precio de catálogo). Métricas en test, leídas de [`models/metricas.json`](models/metricas.json):

| | MAE | RMSE | R² | MAPE |
|---|---:|---:|---:|---:|
| RandomForest | 18,90 € | 30,81 € | 0,850 | 10,64 % |
| Ridge (sobre log) | 19,71 € | 31,23 € | 0,846 | 11,33 % |
| HistGradientBoosting | 22,77 € | 36,75 € | 0,787 | 13,42 % |
| *Baseline: predecir la media* | *61,74 €* | *79,71 €* | *−0,003* | *46,52 %* |

Reduce el error del baseline un 69 %, sobre una mediana de precio de 158 €.

---

## Tres decisiones que condicionan todo lo demás

### El objetivo es el PVP, no el precio del día

El 99,9 % del catálogo de General Óptica estaba rebajado el día de la captura, con un descuento uniforme del 25 %, incluido el 100 % de los productos agotados. No es una liquidación de stock: es una campaña aplicada a la tarifa.

Modelar `precio_actual` sería modelar el calendario de marketing de una cadena, y ese calendario cambia cada semana. Por eso el objetivo es:

```python
pvp = precio_anterior if en_oferta else precio_actual
```

Medido: predecir el precio pagado da R² 0,72 frente al 0,85 del PVP. La diferencia es la capa promocional, que no está codificada en ninguna característica del producto.

### El split se agrupa por EAN, no es aleatorio

Hay 110 productos idénticos presentes en las dos cadenas. Con `train_test_split` normal, un Ray-Ban concreto podía caer en *train* por Óptica 2000 y su gemelo exacto en *test* por General Óptica: el modelo lo habría visto durante el entrenamiento y la métrica sería mentira.

Se usa `GroupShuffleSplit` agrupando por EAN, y el notebook imprime la comprobación: 0 productos compartidos entre train y test.

### La tabla de grupos se construyó desde fuentes primarias

[`marcas_grupo.csv`](marcas_grupo.csv) asigna 208 marcas a su grupo propietario, con fuente y fecha en cada fila. Sale de las webs corporativas de EssilorLuxottica, De Rigo, Safilo, Marcolin, Kering Eyewear, Marchon, Thélios y Mondottica.

Una versión anterior de este proyecto usaba una tabla de gamas de marca generada con un modelo de lenguaje. Al contrastarla con los precios reales observados: correlación 0,642 y error mediano del 66,8 %, con casos como Max Mara estimada en 260 € frente a 92,90 € reales sobre 43 productos. Se eliminó por completo.

Al reconstruirla desde fuentes primarias aparecieron cuatro asignaciones que se habrían hecho mal de memoria: Swarovski y Moncler son licencias de EssilorLuxottica y no de Marcolin; Rodenstock es socio de marca de De Rigo; y Bvlgari pasó de EssilorLuxottica a Thélios en enero de 2024.

---

## Cómo reproducirlo

```bash
pip install -r requirements.txt

# 1. Captura (opcional: los CSV ya están en data/raw/)
python src/scraping/optica2000.py enumerar
python src/scraping/optica2000.py rastrear --mezclar      # ~20 min
python src/scraping/generaloptica.py enumerar
python src/scraping/generaloptica.py rastrear             # ~15 h (Crawl-delay 30 s)
python src/scraping/exportar.py

# 2. Modelo
python src/modelado/entrenar.py                           # ~5 s

# 3. App
streamlit run app_streamlit/app.py
```

Los notebooks se ejecutan de principio a fin con los datos incluidos en el repositorio.

## Estructura

```
data/raw/          los dos catálogos capturados (6.121 productos)
marcas_grupo.csv   marca -> grupo propietario, con fuente y fecha
notebooks/
  01_Adquisicion_y_Surtido.ipynb    fuentes, calidad del dato y análisis de surtido
  02_Modelado_PVP.ipynb             fusión, split por EAN, modelado y ablaciones
src/scraping/      scrapers con cola reanudable en SQLite
src/modelado/      carga, features, split y entrenamiento
app_streamlit/     demostrador interactivo
models/            modelo entrenado y sus métricas
```

## Sobre el scrapeo

Las condiciones de cada sitio se comprobaron antes de escribir una línea de código:

- Óptica 2000: su `robots.txt` solo prohíbe `/cancela-tu-cita` y `/reprograma-tu-cita`. Renderiza en servidor, así que basta `requests` con BeautifulSoup y 1 s entre peticiones.
- General Óptica: declara `Crawl-delay: 30` y se respeta, lo que supone unas 15 horas de rastreo. Renderiza con JavaScript, así que requiere Selenium.
- En ambos casos las URLs se enumeran desde el `sitemap.xml` y no desde listados de categoría, y el `User-Agent` identifica el proyecto con un correo de contacto en lugar de hacerse pasar por un navegador.

La cola vive en SQLite y guarda el HTML crudo, de modo que un fallo del parser se corrige y se reexporta sin repetir el rastreo. Los detalles están en [`src/scraping/README.md`](src/scraping/README.md).

## Limitaciones

1. **Comercio online.** En España la venta presencial supone en torno al 85-90 % del mercado de gafas graduadas. Esto describe el catálogo web de dos cadenas concretas, no el mercado español.
2. **Foto de agosto de 2026.** Los precios de catálogo son estables, pero no eternos. Cada fila lleva su `ts_captura`.
3. **Listar y tener no es lo mismo.** El 63 % del catálogo de General Óptica está agotado, y el 25 % del de Óptica 2000 solo se vende en tienda física. El notebook 01 presenta las dos vistas por separado.
4. **16 productos (0,26 %) sin grupo asignado.** No se eliminan: borrar filas por una variable ausente sesgaría el recuento.
5. **El listado de marcas de EssilorLuxottica dice "including"**, así que no es exhaustivo. Solo se contó lo demostrable: su cuota real podría ser mayor, nunca menor.
6. **El modelo infraestima las monturas caras.** Por encima de 300 € hay pocos datos y muy heterogéneos.
7. **Correlación, no causalidad.** Que la marca prediga el precio no demuestra que lo cause; ambos podrían responder a un posicionamiento comercial anterior que estos datos no observan.

---

**Juan Antonio Muñoz Moreno** · [github.com/JuanAntoniomm](https://github.com/JuanAntoniomm)

Sociología (UGR) + Data Science.

Este proyecto es la reconstrucción de una versión anterior que tenía tres defectos: el target mezclaba precios de catálogo con precios promocionales sin forma de distinguirlos, la variable más influyente del modelo salía de una tabla de estimaciones generada con un LLM, y las métricas del README no coincidían con las del notebook. Los tres se arreglaron rehaciendo la captura de datos desde cero.
