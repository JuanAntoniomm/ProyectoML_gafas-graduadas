# Scrapers

Captura de los catálogos de gafas graduadas de Óptica 2000 y General Óptica.

## Instalación

```bash
pip install -r src/scraping/requirements.txt
```

General Óptica necesita además Google Chrome instalado. Selenium 4.6+ se descarga el driver solo.

## Cómo se ejecuta

```bash
# 1. Prueba que el parser funciona (no toca la red)
python src/scraping/optica2000.py autotest

# 2. Enumerar: sitemap -> cola SQLite
python src/scraping/optica2000.py enumerar
python src/scraping/generaloptica.py enumerar

# 3. Prueba corta antes del rastreo largo
python src/scraping/optica2000.py rastrear --limite 20
python src/scraping/generaloptica.py rastrear --limite 3 --espera 5

# 4. Rastreo completo
python src/scraping/optica2000.py rastrear          # ~20 min
python src/scraping/generaloptica.py rastrear       # ~15 h

# 5. Ver por dónde va (desde otra terminal, mientras corre)
python src/scraping/cola.py

# 6. Exportar a CSV
python src/scraping/exportar.py
```

Se puede parar con Ctrl+C y continuar relanzando el mismo comando. El estado vive en `data/raw/scrape.db`.

Para el rastreo largo conviene lanzarlo como proceso suelto (Programador de tareas de Windows, o `nohup` en WSL). Un notebook abierto en VS Code muere al cerrar el portátil.

## Por qué dos scrapers distintos

| | Óptica 2000 | General Óptica |
|---|---|---|
| Renderizado | servidor | JavaScript |
| Herramienta | `requests` + BeautifulSoup | Selenium |
| `Crawl-delay` en robots.txt | ninguno (se usa 1 s) | 30 s |
| Fichas capturadas | 1.296 | 4.825 |
| Tiempo | ~20 min | ~15 h |
| Datos estructurados | etiquetas de texto | JSON-LD completo |

General Óptica devuelve la página vacía a una petición normal, sin precio ni atributos. Por eso lleva navegador.

## Cumplimiento

Comprobado el 1 ago 2026:

- Óptica 2000: su `robots.txt` solo prohíbe `/cancela-tu-cita` y `/reprograma-tu-cita` para `User-agent: *`. Fichas y categorías permitidas.
- General Óptica: `Crawl-delay: 30` para todos, y se respeta. Las fichas no están prohibidas, solo la ruta interna `/catalog/product/view/`.

En los dos casos las URLs se enumeran desde el `sitemap.xml` y no desde listados de categoría, y el `User-Agent` se identifica con el nombre del proyecto y un correo de contacto en vez de hacerse pasar por un navegador.

## Diseño

La cola vive en SQLite y el dataset en CSV. `data/raw/scrape.db` es solo el registro de trabajo: qué URLs faltan, cuáles están hechas y cuáles fallaron. Se eligió SQLite y no un fichero de texto porque las escrituras son atómicas; un `.txt` cortado a media línea deja el progreso ilegible.

La columna `payload` guarda el HTML crudo. Si aparece un fallo en un parser, se corrige y se ejecuta `exportar.py`: el dataset se regenera en segundos en lugar de repetir 15 horas de rastreo.

El dato se escribe antes de marcar la ficha como hecha, en la misma transacción. Si el proceso muere en medio, la peor consecuencia es repetir una ficha en vez de saltársela sin enterarse.

Cada fila lleva `ts_captura`. Un rastreo de 15 horas puede cruzarse con un cambio de campaña promocional, y sin marca de tiempo por fila no habría forma de detectarlo.

## Campos que se capturan

Comunes a las dos tiendas: `url`, `tienda`, `ean`, `marca`, `nombre`, `mpn`, `color`, `material_montura`, `genero`, `ancho_lente`, `ancho_puente`, `precio_actual`, `precio_anterior`, `pvp`, `en_oferta`, `descuento_pct`, `precio_solo_montura`, `ts_captura`.

Solo Óptica 2000: `forma`, `tipo_montura`, `ancho_montura`, `largo_varilla`, `modelo`.
Solo General Óptica: `sku`, `disponibilidad`.

Ninguna de las dos publica el peso. Se podría recuperar del dataset antiguo de Lentiamo cruzando por `mpn`.

## Los dos formatos de número

Los precios llegan de dos sitios y con convenciones opuestas:

```
JSON-LD (schema.org):  "125.250000"  -> el punto es DECIMAL     -> 125,25 €
DOM visible (español): "1.234,50 €"  -> el punto es de MILLARES -> 1234,50 €
```

Pasar el primero por el parser del segundo convierte 125,25 € en 125.250 €. No da error: multiplica los precios por mil. De ahí que haya dos funciones separadas y que el `autotest` compruebe las dos.

## Qué encontraron los tests antes de tocar la red

El parser se escribió contra fichas sintéticas copiadas del maquetado real, y esa pasada previa sacó cinco fallos que habrían contaminado el dataset entero sin dar ni un error:

- Los dos formatos de número mezclados, con el ×1000 silencioso de arriba.
- `precio_anterior` solo existía cuando había oferta, así que el CSV salía con esquemas distintos según la ficha. Ahora todas las claves se declaran de entrada.
- Al declarar todas las claves a `None`, la comprobación de existencia dejó de cumplirse nunca y no se extraía ningún atributo.
- `OUTLET` es también una entrada del menú de navegación, así que buscarlo en toda la página daba `True` en el 100 % de las fichas. El fixture del autotest incluye el menú a propósito, para que el test lo vuelva a detectar.
- `marca` salía a `None` en buena parte del catálogo. La primera versión la sacaba del enlace `/gafas-graduadas/{marca}`, que solo existe para las 9 marcas del menú: Arnette, DbyD, Nanovista y el resto no tienen página de categoría. Como `marca` es la variable más importante del modelo, eso habría inutilizado el dataset.

La marca acabó saliendo de los `<li>` hijos directos de las migas de pan, donde el penúltimo es la marca y el último el modelo. Hay respaldo por el prefijo del slug de la URL si no hay migas. En el catálogo final: 0 % de nulos en `marca` y en `modelo`.

## Validación contra páginas reales (1 ago 2026)

Muestra determinista de 12 fichas repartidas por el catálogo de Óptica 2000:

| Comprobación | Resultado |
|---|---|
| Fichas con precio extraído | 12/12 |
| Fichas con "solo montura" | 12/12 |
| Fichas en oferta | 0/12 |
| Fallos de descarga | 0 |
| `Frente de color`, `Material`, `Género`, las 4 medidas | 12/12 |
| `Forma de la montura`, `Tipo de montura` | 11/12 |

En el catálogo completo eso se tradujo en un 3,1 % de nulos en `forma` y un 6,6 % en `tipo_montura`, y prácticamente ninguno en el resto. Que 0 de 12 estuvieran en oferta encaja con lo observado: Óptica 2000 no tenía campaña general, al contrario que el 25 % a catálogo completo de General Óptica.

También se comprobó que etiqueta y valor caen en nodos de texto consecutivos en las 9 etiquetas, y que Óptica 2000 no publica JSON-LD de producto, que es por lo que ese parser va por texto.

## El campo `pvp`

El target del modelo es el precio de catálogo, no el promocional. Los scrapers lo calculan ya:

```python
pvp = precio_anterior if en_oferta else precio_actual
```

Importa sobre todo en General Óptica, que tenía una campaña del 25 % a catálogo completo: ahí `precio_actual` es la promoción de la semana y el de catálogo es el tachado. Si la campaña termina a mitad del rastreo, `precio_anterior` desaparece y `precio_actual` pasa a ser el PVP; la fórmula da lo mismo en los dos escenarios.

## Sobre el tamaño del catálogo de General Óptica

El sitemap trae 4.938 URLs de graduadas mientras la categoría navegable declaraba 1.770 artículos, lo que hacía pensar que unas 3.100 estaban descatalogadas. El rastreo lo desmintió: salieron 4.825 fichas con precio, así que las de baja eran unas 113. El universo bueno era el sitemap, no el contador de la categoría. Las fichas sin precio se marcan como error con el motivo `sin precio (descatalogado?)`, que las filtra sin necesidad de una pasada previa.
