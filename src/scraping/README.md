# Scrapers

Captura de catálogos de gafas graduadas de **Óptica 2000** y **General Óptica**.

## Instalación

```bash
pip install -r src/scraping/requirements.txt
```

General Óptica necesita además **Google Chrome instalado**. Selenium 4.6+ se descarga el driver solo.

## Cómo se ejecuta

```bash
# 1. Prueba que el parser funciona (no toca la red)
python src/scraping/optica2000.py autotest

# 2. Enumerar: sitemap -> cola SQLite
python src/scraping/optica2000.py enumerar
python src/scraping/generaloptica.py enumerar

# 3. Prueba corta antes de lanzar el rastreo largo
python src/scraping/optica2000.py rastrear --limite 20
python src/scraping/generaloptica.py rastrear --limite 3 --espera 5

# 4. Rastreo completo
python src/scraping/optica2000.py rastrear          # ~20 min
python src/scraping/generaloptica.py rastrear       # ~15 h

# 5. Ver por dónde va (se puede lanzar en otra terminal mientras corre)
python src/scraping/cola.py

# 6. Exportar a CSV
python src/scraping/exportar.py
```

**Se puede parar con Ctrl+C y continuar relanzando el mismo comando.** El estado vive en `data/raw/scrape.db`.

Para el rastreo largo, lánzalo como proceso suelto (Programador de tareas de Windows, o `nohup` en WSL). Un notebook abierto en VS Code muere al cerrar el portátil.

## Por qué dos scrapers distintos

| | Óptica 2000 | General Óptica |
|---|---|---|
| Renderizado | servidor | **JavaScript** |
| Herramienta | `requests` + BeautifulSoup | **Selenium** |
| `Crawl-delay` en robots.txt | ninguno (se usa 1 s) | **30 s** |
| Fichas | ~1.330 | ~4.938 en sitemap, ~1.770 en catálogo |
| Tiempo | ~20 min | **~15 h** |
| Datos estructurados | etiquetas de texto | **JSON-LD completo** |

General Óptica devuelve la página vacía a una petición normal: sin precio, sin atributos, sin nada. Por eso lleva navegador.

## Cumplimiento

Comprobado el 1 ago 2026:

- **Óptica 2000** — `robots.txt` solo prohíbe `/cancela-tu-cita` y `/reprograma-tu-cita` para `User-agent: *`. Fichas y categorías permitidas.
- **General Óptica** — `Crawl-delay: 30` para todos. Las fichas no están prohibidas (solo la ruta interna `/catalog/product/view/`). **Se respeta.** Son las 15 horas.

En los dos casos: las URLs se enumeran desde el `sitemap.xml`, no desde listados de categoría, y el `User-Agent` se identifica con nombre del proyecto y correo de contacto en vez de hacerse pasar por un navegador.

## Diseño

**La cola vive en SQLite, el dataset en CSV.** `data/raw/scrape.db` es solo el cuaderno de bitácora: qué URLs faltan, cuáles están hechas y cuáles fallaron. Se eligió SQLite y no un fichero de texto porque las escrituras son atómicas: si el ordenador se apaga a media línea, un `.txt` queda corrupto y no sabes por dónde ibas.

**Se guarda el HTML crudo.** La columna `payload` conserva la respuesta tal cual. Si aparece un fallo en un parser, se corrige y se ejecuta `exportar.py`: el dataset se regenera en segundos en lugar de repetir 15 horas de rastreo.

**Se escribe el dato antes de marcar la ficha como hecha**, en la misma transacción. Si el proceso muere en medio, la peor consecuencia es repetir una ficha (inofensivo) en vez de saltársela (silencioso y difícil de detectar después).

**Cada fila lleva `ts_captura`.** Un rastreo de 15 horas puede cruzarse con un cambio de campaña promocional. Sin la marca de tiempo por fila no habría forma de detectarlo.

## Campos que se capturan

Comunes a las dos tiendas: `url`, `tienda`, `ean`, `marca`, `nombre`, `mpn`, `color`, `material_montura`, `genero`, `ancho_lente`, `ancho_puente`, `precio_actual`, `precio_anterior`, `en_oferta`, `descuento_pct`, `precio_solo_montura`, `ts_captura`.

Solo Óptica 2000: `forma`, `tipo_montura`, `ancho_montura`, `largo_varilla`.
Solo General Óptica: `sku`, `disponibilidad`.

Ninguna de las dos publica el **peso**. Se puede recuperar desde el dataset antiguo de Lentiamo cruzando por `mpn`, que es el código de modelo del fabricante.

## Trampa que ya costó un bug

Los precios llegan en **dos formatos distintos y hay que tratarlos por separado**:

```
JSON-LD (schema.org):  "125.250000"  -> el punto es DECIMAL     -> 125,25 €
DOM visible (español): "1.234,50 €"  -> el punto es de MILLARES -> 1234,50 €
```

Pasar el primero por el parser del segundo convierte 125,25 € en 125.250 €. **No revienta: simplemente multiplica los precios por mil.** De ahí que existan `_num_es()` y `_num_maquina()` separadas, y que `autotest` compruebe las dos.

## Validación contra páginas reales (1 ago 2026)

Muestra determinista de **12 fichas repartidas por todo el catálogo** de Óptica 2000, aplicando las mismas reglas del parser:

| Comprobación | Resultado |
|---|---|
| Fichas con precio extraído | 12/12 |
| Fichas con "solo montura" | 12/12 |
| Fichas en oferta | 0/12 |
| Fallos de descarga | 0 |
| `Frente de color`, `Material`, `Género`, las 4 medidas | 12/12 |
| `Forma de la montura`, `Tipo de montura` | **11/12** |

Es decir: espera en torno a un **8 % de nulos en forma y tipo de montura**, y prácticamente ninguno en el resto. Que 0 de 12 estén en oferta encaja con lo observado: Óptica 2000 no tenía campaña general, a diferencia del 25 % a catálogo completo de General Óptica.

Además se verificó en la ficha real que **etiqueta y valor caen en nodos de texto consecutivos** (las 9 etiquetas) y que **Óptica 2000 no publica JSON-LD de producto** — de ahí que el parser vaya por texto y no por datos estructurados.

## Cinco fallos que encontraron los tests antes de tocar la red

1. **Formatos de número mezclados.** Ver la sección anterior. Multiplicaba los precios por mil sin dar error.
2. **Columnas variables.** `precio_anterior` solo existía cuando había oferta, así que el CSV salía con esquemas distintos según la ficha. Ahora todas las claves se declaran de entrada.
3. **Extracción de atributos rota por el arreglo del 2.** Al declarar todas las claves a `None`, la condición `campo not in d` dejó de cumplirse nunca. Ahora es `d.get(campo) is None`.
4. **`OUTLET` en el menú de navegación.** La primera versión buscaba la palabra en toda la página y salía `True` en las 12 fichas de la muestra: un campo constante e inútil. Ahora solo cuenta si hay descuento y la etiqueta aparece a menos de 120 caracteres del precio. **El fixture del autotest incluye el menú a propósito**, para que el test pueda volver a detectarlo.
5. **`marca` a `None` en buena parte del catálogo.** La primera versión la sacaba del enlace `/gafas-graduadas/{marca}`, que **solo existe para las 9 marcas del menú**. Arnette, DbyD, Miraflex y el resto no tienen página de categoría. Como `marca` es la variable más importante del modelo, esto habría inutilizado el dataset.

   La solución sale de comparar H1 y breadcrumb en 10 fichas reales:

   ```
   h1         = "Arnette Nakki AN7208 2803"
   breadcrumb = "Nakki AN7208 2803"        <- el último elemento es el modelo
   marca      = h1 menos breadcrumb        -> "Arnette"
   ```

   Con respaldo por el prefijo del slug de la URL si no hay breadcrumb. Verificado en los cuatro casos reales observados.

## El campo `pvp`

El target decidido para el modelo es el **precio de catálogo**, no el promocional (ver `decisiones_mlgafas.md`, D5bis). Los scrapers lo calculan ya:

```python
pvp = precio_anterior if en_oferta else precio_actual
```

Importa sobre todo en General Óptica, que el 1 ago 2026 tenía una campaña del **25 % a catálogo completo**: ahí `precio_actual` es la promoción de esa semana y el precio de catálogo es el tachado. Si la campaña termina a mitad del rastreo, `precio_anterior` desaparece y `precio_actual` pasa a ser el PVP. La fórmula da 167,00 € en los dos escenarios — comprobado en el autotest.

## El sitemap de General Óptica miente sobre el tamaño del catálogo

Trae 4.938 URLs de graduadas, pero la categoría navegable declara 1.770 artículos. Las ~3.168 de diferencia son producto descatalogado o sin stock. El scraper las detecta porque no tienen precio y las marca como error con el motivo `sin precio (descatalogado?)`, que es la forma barata de filtrarlas sin una pasada previa.
