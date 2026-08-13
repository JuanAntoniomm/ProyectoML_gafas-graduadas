# Decisiones — Reconstrucción del proyecto ML de precios de gafas

Registro de decisiones tomadas y de la evidencia que las respalda.
Repo: `github.com/JuanAntoniomm/ProyectoML_gafas-graduadas`

**Regla de este archivo:** todo dato numérico que aparezca aquí está calculado o verificado en sesión, con la fecha al lado. Lo que sea inferencia o suposición va marcado como tal.

Última actualización: **1 ago 2026**

---

## 0. Por qué se reconstruye

El proyecto entregado funciona pero tiene tres defectos que no aguantan una revisión técnica:

1. El target mezcla precios de catálogo con precios de oferta, sin forma de distinguirlos.
2. La variable más influyente del modelo procede de una tabla de estimaciones generada con un LLM.
3. Las métricas del README no coinciden con las del notebook.

Los tres se arreglan rehaciendo la captura de datos. El código de `src/` y la estructura del proyecto se conservan.

---

## 1. Decisiones tomadas

### D1 · Eliminar el enriquecimiento generado por IA — **DECIDIDO (1 ago 2026)**

Se eliminan `precio_min`, `precio_max`, `precio_medio_marca`, `gama_marca`, `segmento_comercial`, `pais_origen`, `categoria_material`, `gama_material` y `peso_relativo`, junto con los ficheros `clasf_marcas.md`, `clasf_mat.md`, `marcas_tier.csv` y `materiales_tier.csv`.

**Evidencia (verificado 1 ago 2026):** comparando la estimación de la IA con el precio real observado por marca, en las 61 marcas con 5 o más productos:

- correlación estimación vs. mediana real: **0,642**
- error mediano de la estimación: **66,8 %**
- error absoluto medio: **82,90 €**

Peores casos: Moschino Love 200 € estimado / 62,80 € real (+218 %); Max Mara 260 € / 92,90 € sobre 43 productos (+180 %); Carolina Herrera 235 € / 79,90 € (+194 %).

`clasf_marcas.md` marca solo 10 de 75 filas como "(estimación)", pero las no marcadas fallan igual. La etiqueta no distingue nada.

**Coste medido de eliminarlo:**

| Configuración | MAE test | R² |
|---|---:|---:|
| Con `precio_medio_marca` | 17,18 € | 0,869 |
| Sin `precio_medio_marca` | **17,08 €** | **0,872** |
| Sin ningún enriquecimiento IA | 18,33 € | 0,859 |

Quitar la variable "más importante" **mejora** el modelo. Todo el bloque de enriquecimiento vale 1,25 € de MAE.

**Nota técnica que conviene saber explicar:** el README decía que `precio_medio_marca` era la variable más influyente, con 26,4 € de permutation importance. Es cierto *para ese modelo entrenado*, pero no para el problema: al reentrenar sin ella, el bosque se reencamina por `marca` y no pierde nada. La permutation importance mide dependencia del modelo, no información del problema.

### D2 · Sustituto: target encoding de marca — **DECIDIDO (1 ago 2026)**

Mediana de precio por marca, aprendida **solo en train** y ajustada **dentro del pipeline**, con validación cruzada interna.

Expectativa honesta: **no va a mejorar la métrica**. Con 75 marcas y ~2.300 filas, el one-hot de `marca` ya rinde igual. Lo que aporta es procedencia limpia, reducción de 75 columnas a 1, y manejo de marcas no vistas en train.

### D3 · Probar "grupo licenciante" como variable — **DECIDIDO (1 ago 2026)**

Sustituir la idea de `gama_marca` por **qué grupo posee o licencia la marca** (EssilorLuxottica, Safilo, Marcolin, Kering Eyewear, De Rigo…).

Ventaja sobre lo anterior: está publicado en las webs corporativas de esos grupos, así que es **citable**. Y encaja con el ángulo de la carrera: el precio lo fija una estructura de licencias concentrada, no el material de la montura.

**Pendiente:** construir la tabla desde los portafolios oficiales, citando la fuente de cada asignación. No darla por memoria.

### D4 · Capturar siempre los cuatro campos de precio — **DECIDIDO (1 ago 2026)**

Sea cual sea el target final, el scraper guarda siempre:

| Campo | Definición |
|---|---|
| `precio_actual` | Lo que paga el cliente hoy |
| `precio_anterior` | El tachado; nulo si no hay oferta |
| `en_oferta` | `precio_anterior is not null` |
| `descuento_pct` | Derivado |

**Motivo:** la ficha solo muestra el tachado cuando hay descuento. Para saber si el número que lees es PVP o precio rebajado hay que detectar la presencia del elemento tachado igualmente. **El coste de scrapeo es idéntico en los dos escenarios**, así que la elección de target se pospone al notebook y se prueban las dos.

**Contexto legal (verificado 1 ago 2026):** el artículo 20.1 de la Ley de Ordenación del Comercio Minorista, redactado por el Real Decreto-ley 24/2021 y en vigor desde el 28 de mayo de 2022, obliga a que el "precio anterior" anunciado sea el más bajo aplicado en los 30 días previos. El tachado es por tanto un precio realmente cobrado hace poco, no un PVP inventado. Matiz: es el *mínimo* de esos 30 días, no el precio de catálogo habitual. Verificada la norma, no el cumplimiento de cada tienda.

### D5bis · El target es el PVP — **DECIDIDO (1 ago 2026)**

Se modela el **precio de catálogo (PVP)**, no el precio promocional.

Motivos:

- La pregunta de negocio es "¿a cuánto debería posicionarse esta montura?", que es la que dice el README.
- Los descuentos dejan de ser varianza inexplicable: se excluyen a propósito en vez de comerse el error.
- **H2** demuestra que General Óptica aplica un 25 % a catálogo completo: capturar el precio actual sería capturar la campaña de esa semana, no una propiedad del producto, y `en_oferta` saldría casi constante.
- El PVP es estable en el tiempo, así que un scrapeo repartido en varias sesiones no mezcla regímenes de precio.

La información de oferta se sigue capturando (**D4**) y pasa a tener tres usos: control de calidad del scrapeo, limitación declarada en el README, y posible segundo entregable (clasificador de qué productos entran en oferta).

### D5 · Solo gafas graduadas, sin gafas de sol — **DECIDIDO (1 ago 2026), REVISABLE**

Decisión de Juan Antonio: centrar el proyecto en graduadas.

**Coste medido:** Óptica 2000 tiene 1.351 fichas de sol además de las 1.058 graduadas. Incluirlas llevaría el dataset a 2.409 productos, que en la curva de aprendizaje corresponde a un MAE en torno a 18 € en lugar de ~22 €. Además convertiría `tipo` en una variable real: en el dataset actual `tipo` es constante ('graduadas' en el 100 % de las filas) y por tanto inútil.

Es el mismo scraper con otra URL de categoría. Queda registrado como la palanca de mayor impacto y menor coste que está sin usar.

---

## 2. Fuente de datos

### P1 · Óptica 2000 + General Óptica — **DECIDIDO (1 ago 2026)**

**Las dos tiendas.** Decisión tomada sobre un criterio explícito: **el proyecto se optimiza para conseguir entrevistas, no para ser un producto vendible.**

Esa distinción se planteó y se resolvió así:

- **¿Le ahorra dinero a una óptica?** No. El coste de unas gafas graduadas está en la lente, el laboratorio, el local y el tiempo del optometrista, no en la montura. Un modelo de precios no reduce ninguno de esos costes. Como mucho mejora ingresos, y solo por una vía: detectar producto infravalorado en el propio escaparate.
- **Para una cadena, valor cero:** tienen sus ventas reales, sus contratos y sus márgenes.
- **Para una óptica pequeña, valor limitado:** si quiere saber a cuánto vende la competencia cinco monturas, lo mira en la web.
- **La segunda tienda no mejora el valor de negocio**, lo empeora ligeramente: "el mismo Ray-Ban cuesta 125 € aquí y 163 € allá porque sus dueños son fabricantes rivales" no es accionable para una tienda independiente.
- **Lo que sí aporta la segunda tienda es una hipótesis.** "Predigo el precio" no tiene hipótesis, tiene un R². "¿La propiedad del minorista condiciona lo que vende y a qué precio?" es falsable, se contrasta con datos y aprovecha la formación en Sociología.

**Condición que forma parte de la decisión:** el README **no promete valor de negocio**. No se escribe "esto ayuda a las ópticas a fijar precios" — un entrevistador con experiencia en retail lo desmonta en dos preguntas. Se escribe que analiza cómo la concentración del sector se refleja en el surtido y en el precio.

*(Fuera de alcance de esta conversación: hay una óptica real recién abierta de un conocido. El caso de uso comercial —detección de producto mal posicionado en precio— se tratará por separado. No mezclarlo con este repo.)*

### Estructura del proyecto resultante

| Pata | N | Solidez |
|---|---:|---|
| Surtido: qué marcas vende cada cadena | 2.828 productos | fuerte |
| Regresión de precio con `tienda` y `grupo_licenciante` | 2.828 | fuerte |
| Diferencia de precio en el mismo producto (cruce por EAN) | ~100-250 pares | descriptivo |

La regresión es la columna vertebral técnica. El surtido aporta la pregunta. El cruce por EAN es la guinda, no el cimiento.

### Propiedad de las cadenas — el motivo de elegir estas dos

| Tienda | Propietario | Marcas del grupo |
|---|---|---|
| Óptica 2000 | Grandvisión Spain → EssilorLuxottica | Ray-Ban, Oakley, Persol, Vogue, Arnette + licencias de Prada, Versace, Armani… |
| General Óptica | **Grupo De Rigo** (desde 2000, 160 M€) | Police, Sting, Lozza + licencias de Tous, Furla, Fila, Trussardi, Chopard… |

**Dos cadenas propiedad de fabricantes de gafas rivales.** Eso no es un confusor: es la pregunta de investigación. Hipótesis falsable: *¿cada cadena posiciona mejor las marcas de su propio grupo?* Con el EAN se controla producto, día y atributos; lo único que varía es el vendedor y su relación de propiedad con la marca.

**✅ VERIFICADO EN FUENTE PRIMARIA (1 ago 2026).** Se puede escribir en el README.

**General Óptica → De Rigo.** Web corporativa de De Rigo SpA, página de inicio:

> "The Group is one of the top players in the retail field thanks to its chains **General Optica**, Mais Optica and Opmar Optik, and its affiliate Boots Opticians."

Marcas propias de De Rigo según su propia página de marcas: **Police, Lozza, Sting, Yalea**. Las licenciadas (Tous, Furla, Fila, Trussardi, Chopard, Nina Ricci…) están en otra sección y quedan por catalogar.

**Óptica 2000 → GrandVision → EssilorLuxottica.** Tres eslabones, los tres comprobados:

1. Pie de página de `optica2000.com`: "Grandvisión Spain Grupo Óptico, S.A.U. | C.I.F.: A81195844". Fuente primaria directa.
2. Comunicado de EssilorLuxottica: adquisición de GrandVision **cerrada el 1 de julio de 2021**, 7.200 M€, 76,72 % del capital comprado a HAL Optical Investments.
3. **Los remedios exigidos por la Comisión Europea afectaron a Bélgica, Países Bajos e Italia** (unas 350 tiendas). **España no estuvo entre las desinversiones**, así que GrandVision Spain sigue en el grupo.

El tercer punto era el riesgo real: si España hubiera entrado en los remedios, la hipótesis del proyecto se caía. No fue el caso.

### Solape entre catálogos (medido 1 ago 2026)

Matching por código de modelo extraído de las URLs de ambos sitemaps — sin visitar ninguna ficha. Muestra aleatoria de 130 modelos de Óptica 2000 (semilla fija):

```
32 de 130 encontrados en General Óptica = 24,6 %
IC 95 %: [17,2 % – 32,0 %]

Modelos en común (N=850):            ~209    IC95%: [146 – 272]
Fichas de General Óptica afectadas:  ~517
```

| | Fichas (categoría) | Fichas (sitemap) | Modelos únicos |
|---|---:|---:|---:|
| Óptica 2000 | 1.058 | 1.330 | 850 |
| General Óptica | 1.770 | 4.938 | 3.066 |

**Es una cota superior.** El cruce es por *modelo*, no por producto: el mismo modelo puede estar en cada tienda en distinto color o calibre. Para el mismo EAN hacen falta modelo + color + calibre iguales. Con ~1,6 variantes por modelo en cada tienda, la estimación de pares exactos es **100-250 productos**.

El EAN exacto sale del JSON-LD de cada ficha, así que el emparejamiento definitivo se obtiene gratis al terminar el scrapeo ya previsto.

### Observación sin confirmar: la integración vertical puede verse antes en el surtido

Los modelos que cruzan son casi todos Luxottica: `an7183` (Arnette), `rx0298v` (Ray-Ban), `vo5702`/`vo5703u`/`vo5518` (Vogue), `ra7158u`/`ra7182u` (Ralph), `dg5031` (Dolce & Gabbana).

El menú de marcas destacadas de Óptica 2000 es: Ray-Ban, Oakley, Prada, Versace, Dolce & Gabbana, Arnette, Michael Kors, Vogue, Ralph Lauren. **Las nueve son propiedad o licencia de EssilorLuxottica.** De las marcas De Rigo no aparece ninguna salvo una mención suelta a Tous.

Si se confirma, cada cadena vende principalmente las marcas de su dueño, y esa pregunta se responde con los catálogos completos sin necesitar ningún cruce de EAN — con mucha más N que la comparación de precios.

**⚠️ Esto salía del menú de navegación.** Se hizo el censo completo — ver abajo. **Confirmado, y más fuerte de lo previsto.**

### H6 · Censo de marcas: la exclusión va en una sola dirección — **CONFIRMADO (1 ago 2026)**

Recuento sobre los sitemaps completos de las dos tiendas, sin visitar ninguna ficha.

| | Óptica 2000 (EssilorLuxottica) | General Óptica (De Rigo) |
|---|---:|---:|
| Fichas de graduadas | 1.330 | 4.938 |
| Marcas distintas | 113 | 233 |
| **Marcas propias de De Rigo** (Police, Sting, Lozza, Yalea) | **0 (0,0 %)** | 444 (9,0 %) |
| **Licencias de De Rigo** (Furla, Fila, Trussardi, Nina Ricci, Blumarine, Zadig&Voltaire…) | **0** | 645 (13,1 %) |
| **Marcas propias de Luxottica** (Ray-Ban, Oakley, Persol, Vogue, Arnette) | 221 (16,6 %) | **849 (17,2 %)** |
| Marca blanca del propio minorista (UNOFFICIAL, DbyD, SEEN) | 251 (18,9 %) | — |

**El cero está verificado por dos vías independientes**, porque una ausencia deducida de parsear URLs no prueba nada:

1. Cero coincidencias de `police`, `sting`, `lozza`, `yalea`, `furla`, `fila`, `trussardi`, `nina-ricci`, `blumarine`, `zadig` en **el sitemap completo** de Óptica 2000 — las 4.888 URLs, gafas de sol incluidas.
2. Las URLs de categoría de marca devuelven **404**: `/gafas-graduadas/police`, `/sting`, `/lozza`, `/yalea`.

**La hipótesis de partida era simétrica y era incorrecta.** No es que cada cadena favorezca lo suyo:

```
Óptica 2000    →  De Rigo:      0 de 1.330   (0,0 %)
General Óptica →  Luxottica:  849 de 4.938  (17,2 %)
```

General Óptica dedica **más proporción de catálogo** a marcas propias de Luxottica (17,2 %) que la propia Óptica 2000 (16,6 %). Ray-Ban 328 referencias, Vogue 240, Persol 134, Oakley 126.

**Lectura:** De Rigo no puede sostener una cadena de ópticas en España sin Ray-Ban; EssilorLuxottica sí puede sostener una sin Police. Es poder de mercado medido como capacidad de excluir, no preferencia comercial.

Segunda capa: Óptica 2000 rellena el **18,9 %** de su catálogo con marca blanca de GrandVision (UNOFFICIAL 130, DbyD 78, SEEN 43). Integración vertical en fabricación y en distribución.

**Consecuencia para el proyecto:** el titular deja de ser "predigo el precio de una montura" y pasa a ser **"cómo la propiedad de las cadenas condiciona lo que un consumidor español puede comprar y a qué precio"**. La regresión sigue siendo el músculo técnico, pero es la evidencia de la segunda mitad de la pregunta, no el titular.

### H6bis · Con la tabla de grupos verificada, la asimetría es mucho mayor (1 ago 2026)

Las cifras de arriba contaban solo **marcas propias**. Al añadir las **licencias verificadas en fuente primaria**, el cuadro cambia de escala:

| | Óptica 2000 | General Óptica |
|---|---:|---:|
| EssilorLuxottica — marcas propias | 230 (17,3 %) | 849 (17,2 %) |
| EssilorLuxottica — licencias | 658 (49,5 %) | 824 (16,7 %) |
| De Rigo — marcas propias | **0 (0,0 %)** | 444 (9,0 %) |
| De Rigo — licencias | 6 (0,5 %) | 507 (10,3 %) |
| Marca blanca del minorista | 251 (18,9 %) | 0 |
| **TOTAL EssilorLuxottica** | **888 (66,8 %)** | **1.673 (33,9 %)** |
| **TOTAL De Rigo** | **6 (0,5 %)** | **951 (19,3 %)** |

**Dos tercios del catálogo de Óptica 2000 son de su propio dueño.** Sumando su marca blanca, el **85,7 %** de lo que vende es EssilorLuxottica o de la propia cadena. Del rival: 6 monturas, y son Tous — una *licencia* de De Rigo, no una marca propia. El cero de marcas propias se mantiene.

**General Óptica dedica a EssilorLuxottica casi el doble de catálogo (33,9 %) que a De Rigo, su propia dueña (19,3 %).** La cadena de De Rigo vende más del rival que de sí misma.

### Fuentes primarias de la tabla de grupos (verificadas 1 ago 2026)

**EssilorLuxottica** — `essilorluxottica.com/en/brands/eyewear/`:

> "…unparalleled portfolio of brands, **including** Ray-Ban, Oakley, Persol, Oliver Peoples, Vogue Eyewear, Arnette, Alain Mikli, Costa, Bliz, Native Eyewear and Bolon, along with leading reading glasses brand Foster Grant. We also boasts prestigious licensed brands, **including** Giorgio Armani, Brooks Brothers, Brunello Cucinelli, Burberry, Chanel, Coach, Diesel, Dolce&Gabbana, Ferrari, Jimmy Choo, Michael Kors, Moncler, Prada, Ralph Lauren, Swarovski, Tiffany & Co., Tory Burch and Versace."

⚠️ Dice **"including"**: la lista no es exhaustiva. La cuota real de EssilorLuxottica podría ser **mayor**, no menor. La dirección del hallazgo es segura.

**De Rigo** — marcas propias en `derigo.com/en/our-brands/`: Police, Sting, Lozza, Yalea.
**De Rigo** — 23 licencias en `derigo.com/en/brand-partner/`: Aramis, Blumarine, Chopard, Diff, Escada, Fila, Furla, Gap, John Varvatos, Jones NY, Just Cavalli, Lucky Brand, Mulberry, Nina Ricci, Philipp Plein, Porsche Design, Roberto Cavalli, Rodenstock, Tous, Tumi, Twinset, Victor Hugo, Zadig&Voltaire.

### Por qué había que verificar y no tirar de memoria

Cuatro asignaciones hechas de memoria estaban **mal**, y las corrigió la fuente primaria:

| Marca | Suposición | Realidad verificada |
|---|---|---|
| Swarovski | Marcolin | **Licencia de EssilorLuxottica** |
| Moncler | Marcolin | **Licencia de EssilorLuxottica** |
| Rodenstock | Independiente | **Socio de marca de De Rigo** |
| Carolina Herrera, Liu Jo | De Rigo | **No están en su listado** |

Con la clasificación de memoria, la cuota de Óptica 2000 habría salido mal y la conclusión habría sido más débil de lo que realmente es.

### H6ter · Con los cinco grupos verificados: no excluye a De Rigo, excluye a TODOS

Completada la tabla con las cinco grandes (1 ago 2026):

| Grupo | Óptica 2000 | General Óptica |
|---|---:|---:|
| **EssilorLuxottica** | **888 (66,8 %)** | 1.673 (33,9 %) |
| **GrandVision — marca blanca propia** | **251 (18,9 %)** | 0 |
| De Rigo | 6 (0,5 %) | **951 (19,3 %)** |
| Safilo | 6 (0,5 %) | 343 (6,9 %) |
| Kering Eyewear | 43 (3,2 %) | 169 (3,4 %) |
| Marcolin | 29 (2,2 %) | 168 (3,4 %) |
| **Marchon** | **0 (0,0 %)** | 117 (2,4 %) |
| Independientes | 43 (3,2 %) | 424 (8,6 %) |
| Sin clasificar | 58 (4,4 %) | 1.093 (22,1 %) |

**Suma de fabricantes rivales en Óptica 2000: 6,4 %.** (De Rigo 0,5 + Safilo 0,5 + Marchon 0,0 + Marcolin 2,2 + Kering 3,2). El otro **85,7 %** es su propio grupo o marca blanca de su propia cadena.

**Marchon en cero absoluto** es el dato más llamativo: ahí están Nike, Lacoste, Calvin Klein, Salvatore Ferragamo, Longchamp. Marcas masivas que cualquier óptica tiene. Ni una.

**General Óptica sí es multimarca de verdad:** EssilorLuxottica 33,9 %, De Rigo 19,3 %, Safilo 6,9 %, Kering 3,4 %, Marcolin 3,4 %, Marchon 2,4 %.

**Titular corregido.** No es "cada cadena barre para casa" (simétrico, y falso). Es: **Óptica 2000 es prácticamente un escaparate monomarca de su fabricante; General Óptica es una óptica multimarca normal que resulta tener un fabricante como dueño.** Eso explica además por qué su catálogo tiene 113 marcas frente a las 233 de General Óptica.

**Lección de proceso:** se estuvo a punto de pasar al scraper con el 17,7 % sin clasificar. Con esos datos el hallazgo era "excluye a De Rigo". Con la tabla completa es "excluye a toda la competencia" — una afirmación bastante más fuerte. **Completar la tabla antes de scrapear no fue burocracia: cambió la conclusión.**

### Fuentes de la tabla de grupos (todas verificadas 1 ago 2026)

| Grupo | Fuente primaria | Marcas |
|---|---|---:|
| EssilorLuxottica | `essilorluxottica.com/en/brands/eyewear/` | 37 |
| De Rigo | `derigo.com/en/our-brands/` + `/en/brand-partner/` | 27 |
| Safilo | `safilogroup.com/it/prodotto/marchi` | 31 |
| Marcolin | `marcolin.com/it/brand/` | 27 |
| Kering Eyewear | `keringeyewear.com/en/our-brands` | 16 |
| Marchon | `marchon.com/brands` | 22 |

**Nota sobre Safilo:** la versión inglesa (`/en/brands`) devuelve `Application error: a client-side exception has occurred`. **La italiana funciona.** No dar por caída una web porque falle una URL.

### Deuda pendiente

- ⬜ **General Óptica: 22,1 % sin clasificar.** Son el 4,4 % de marcas identificadas sin grupo (Bvlgari, Trussardi, Hackett, Mr. Wonderful, Agatha Ruiz de la Prada) más el 17,7 % de cola larga: 178 marcas con menos de 19 productos cada una. Rendimiento decreciente, pero es un quinto del catálogo.
- ⬜ **Óptica 2000: 4,4 % sin clasificar.** Está al 95,6 %, que es donde está el resultado fuerte.
- ⬜ Los recuentos por marca salen de parsear slugs con normalización heurística; pueden bailar un pequeño porcentaje. Los ceros no: están comprobados aparte.
- ⬜ La lista de EssilorLuxottica dice **"including"**: no es exhaustiva. Solo se contó lo demostrable, así que su cuota real puede ser **mayor**. El error solo va en una dirección.

**Entregable:** `marcas_grupo.csv` — 174 marcas, 163 verificadas con fuente y fecha, 11 inferidas o pendientes. Filtrar por la columna `estado` antes de usarla en el modelo.

**Entregable:** `marcas_grupo.csv` — 94 marcas, 67 verificadas con fuente y fecha, 27 en estado `sin_verificar`. Filtrar por la columna `estado` antes de usarla en el modelo.

Comparativa verificada el 1 ago 2026:

| | Lentiamo (actual) | General Óptica | Óptica 2000 |
|---|---:|---:|---:|
| Fichas graduadas | 2.875 | **1.770** | 1.058 |
| Fichas de sol | — | 30.589 (sitemap) | 1.351 |
| `Crawl-delay` en robots.txt | ninguno | **30 s** | ninguno |
| Renderizado | servidor | JavaScript | **servidor** |
| Precio de montura sola | sí | sí (explícito) | sí (explícito) |
| Precio anterior en el DOM | sí | sí (`old-price`) | sí (`antes:`) |
| EAN / GTIN | no | **sí** | **sí** |
| Material · color · género | sí | sí | sí |
| Forma de montura | sí | **no** | sí |
| Tipo de montura | sí | **no** | sí |
| Ancho lente · puente | sí | sí (calibre) | sí |
| Longitud de varilla | sí | **no** | sí |
| Ancho de montura | no | no | **sí** |
| Peso | **sí** | no | no |

**Recomendación:** Óptica 2000 como fuente base (atributos completos, sin crawl-delay), y General Óptica como segunda fuente **solo para precios**, cruzando por EAN.

**Comprobación previa barata:** contar cuántos EAN comparten los dos sitemaps. Se hace sin visitar una sola ficha. Si el solape es de cientos, el análisis entre cadenas se sostiene; si son veinte, se descarta.

#### Corrección de cifra (1 ago 2026)

Primero se dijo que General Óptica tenía **4.938** fichas de graduadas, contadas en su sitemap. **La cifra correcta es 1.770**, que es lo que declara la categoría navegable (`/es/gafa-graduada.html` → "1.770 artículos"). Las 3.168 URLs restantes del sitemap (64 %) no aparecen en el catálogo: casi con seguridad son productos descatalogados o sin stock. **El universo válido es el listado de categoría, no el sitemap.**

#### ¿Fusionar las dos tiendas o solo cruzar por EAN? — evidencia

Medido el 1 ago 2026 por submuestreo del dataset actual, comparando el set de atributos que publica cada tienda:

| Escenario | n | MAE |
|---|---:|---:|
| A · Óptica 2000 sola, atributos completos | ~1.058 | 22,55 € |
| D · Óptica 2000 recortada a los atributos de General Óptica | ~1.058 | 22,64 € |
| B · General Óptica sola, atributos pobres | ~2.868 | 21,14 € |
| C · Fusión, usando la intersección de atributos | ~3.900 | 21,14 € |

**Perder forma de montura, tipo de montura, longitud de varilla y talla cuesta 0,09 €.** Está en el ruido. Los atributos pobres de General Óptica **no son un impedimento**, al contrario de lo que se supuso al principio. La fusión gana 1,41 € frente a Óptica 2000 sola.

Conclusión: si se usa General Óptica, se meten **todas** sus fichas como filas, no solo las que crucen por EAN. El cruce por EAN sirve para el análisis de dispersión entre cadenas, que es otra cosa.

**Tres advertencias sobre esa medición:**

1. **No captura el efecto tienda.** El experimento remuestrea una sola fuente, así que no hay dos precios para el mismo producto. Al fusionar de verdad sí los habrá. Mitigación: incluir `tienda` como variable, para que el modelo aprenda la prima de cada cadena en vez de promediarla. Consecuencia: se predice "precio en la cadena X", y hay que declararlo.
2. **El tope simulado son 2.295 filas**, no las reales. Con la curva ya aplanándose, la ganancia real será algo mayor pero no mucho.
3. `peso` sí valía **1,30 €**. General Óptica publica `mpn` (p. ej. `0RX6448`) y la geometría es propiedad del modelo, no del vendedor: se puede recuperar el peso desde el dataset de Lentiamo cruzando por código de modelo. Procedencia verificable.

---

## P2 · Diseño del scraper

### Coste real de scrapeo (calculado 1 ago 2026)

| | Peticiones | Tiempo |
|---|---:|---:|
| General Óptica — fichas del catálogo real, a 30 s | 1.770 | **14,8 h** |
| General Óptica — sitemap completo, a 30 s | 4.938 | 41,1 h |
| Óptica 2000 — fichas, a 1 req/s | 1.058 | 0,3 h |

**Total realista del proyecto: ~15-16 horas.**

### Lo que trae la parrilla de categoría y lo que no

Comprobado el 1 ago 2026 en General Óptica. La parrilla sí da nombre, marca, enlace, precio actual, precio anterior y porcentaje de descuento:

```
Ray Ban JACK 0RX6465 · El precio solo incluye la montura · 25%DTO · 125,25 € · 167,00 €
```

**No da material, ni color, ni calibre.** Esos solo están en la ficha. Y `?product_list_limit=96` se ignora: la parrilla se queda fija en 24 productos por página. **Conclusión: hay que entrar en las fichas; el atajo por listados no basta.**

### Scraper reanudable — **DECIDIDO (1 ago 2026)**

Estado en **SQLite** (`sqlite3`, librería estándar, sin instalar nada). No sustituye al CSV: el dataset final sale igual en `data/raw/`. SQLite es la cola de trabajo.

```sql
CREATE TABLE productos (
  url TEXT PRIMARY KEY,
  estado TEXT,        -- pendiente | hecho | error
  ean TEXT,
  json TEXT,
  ts TEXT,            -- timestamp de captura, por fila
  intentos INTEGER,
  error TEXT
);
```

Reglas de diseño:

- **Escribir el dato primero, marcar como hecho después.** Un fallo repite una ficha, que es inofensivo, en vez de saltársela.
- La lista de URLs se enumera una vez desde la categoría y se guarda como pendientes. Reanudar es `SELECT url FROM productos WHERE estado='pendiente'`.
- **Script suelto (`.py`), no notebook.** Lanzado con el Programador de tareas de Windows o `nohup` en WSL. Un notebook abierto en VS Code muere al cerrar el portátil.
- Reintentos con espera creciente. No marcar como hecho si falla.
- **`ts` por fila es obligatorio**, para detectar si a mitad del scrapeo cambia una campaña promocional.

---

## Nota sobre el repositorio

`C:\Users\juan_\Desktop\ML-gafas` **no es la carpeta original del repo**: es la copia de trabajo. Los archivos se copian a la original antes de subirlos.

**Push bloqueado en esta copia (1 ago 2026).** Este directorio tenía el remoto real configurado, así que un `push` habría ido al repo público. Se ha desactivado solo el push, conservando el fetch para poder comparar con el repo real:

```
git remote set-url --push origin SIN-PUSH-DESDE-ESTA-COPIA
```

```
fetch → https://github.com/JuanAntoniomm/ProyectoML_gafas-graduadas.git
push  → SIN-PUSH-DESDE-ESTA-COPIA   ✗ fatal: does not appear to be a git repository
```

Verificado con `git push --dry-run`. **La única carpeta desde la que se sube es la original.** Reversible con `git remote set-url --push origin <url>`.

**No borrar `.gitattributes`.** Es la configuración de Git LFS (`models/*.pkl filter=lfs …`). Sin él, el modelo de 60 MB entraría en el repo como binario normal: GitHub avisa por encima de 50 MB y rechaza el push por encima de 100 MB. No tiene nada que ver con el remoto.

**Archivos que nunca deben subirse:** `busquedatrabajo.md` (expectativas salariales, nombres de recruiters, estrategia de candidaturas) y `curriculum.md` (autoevaluación honesta de habilidades, con la sección "En el CV pero sin ninguna base real"). Ninguno de los dos está cubierto por el `.gitignore` actual.

### Cómo commitear — **DECIDIDO (1 ago 2026)**

**No borrar lo que hay en un commit.** Motivos:

1. Git conserva el historial: borrar en un commit no elimina nada del repo, solo lo saca del árbol actual. Los notebooks de andamiaje y las métricas incorrectas seguirían siendo recuperables.
2. El repo está enlazado desde el CV y desde LinkedIn, y se está aplicando a ofertas ahora mismo. Un repo vacío con "borrado de archivos" como último commit es peor que el repo imperfecto actual, y la reconstrucción durará semanas.
3. El código y los datos de Lentiamo hacen falta como referencia — en particular `peso`, que es lo que se quiere recuperar cruzando por `mpn`.

**En su lugar:** `git checkout -b v2-reconstruccion`. `main` se queda presentable. Cuando la v2 esté terminada y sea mejor, se convierte en principal.

Beneficio secundario: el defecto nº 7 es "un solo commit". Una rama con commits reales y descriptivos lo arregla como efecto colateral de hacer el trabajo.

---

## 3. Descartadas

| Opción | Motivo | Verificado |
|---|---|---|
| **Mister Spex** | Ha cerrado operaciones en España. Su web redirige a un aviso de cierre. | 1 ago 2026 |
| **Alain Afflelou** | Catálogo renderizado por JS; la categoría devuelve "No hemos encontrado productos" sin JavaScript. Su `sitemap_es.xml` tiene 427 URLs y ninguna es ficha de producto. Negocio basado en packs y marca propia MAGIC. | 1 ago 2026 |
| **Ulloa Óptico** | Su `robots.txt` incluye `Disallow: */gafas/gafas-graduadas/*`. | 1 ago 2026 |
| **Varias tiendas como punto de partida** | El mismo producto en dos tiendas son dos targets distintos para features casi idénticas. Pospuesto a v2, con el EAN como clave de cruce. | — |

---

## 4. Hallazgos que cambian el planteamiento

### H1 · El bug de los 45 € está diagnosticado

En `data/raw/_debug.html`:

```html
onclick="trackEvent('Glasses crossell', 'click', '1_13802')"
> Lentiamo Anna Deep Black </a>
<span class="vc-offer-badge">Top ventas</span>
<p class="vc-price vc-price-category">
  <strong class="vc-price-value"><span class="vc-number">45,00 €</span></strong>
```

45,00 € era un **módulo de venta cruzada** presente en todas las fichas. El selector de la v2 cogía el precio del bloque de cross-sell en lugar del del producto. No era un problema difícil: era un selector sin acotar al contenedor del producto.

Lección para el scraper nuevo: **acotar siempre al contenedor del producto principal, y preferir JSON-LD a clases CSS.** Lentiamo, General Óptica y Óptica 2000 sirven datos estructurados.

### H2 · General Óptica aplica un 25 % a catálogo completo

Verificado el 1 ago 2026 sobre seis productos:

```
125,25/167,00 = 0,7500      141,74/188,99 = 0,7500
133,12/177,50 = 0,7500      113,24/150,99 = 0,7500
122,25/163,00 = 0,7500      105,37/140,49 = 0,7500
```

No es descuento por producto: es una promoción de catálogo. **Argumento fuerte a favor de usar PVP como target**: capturar el precio actual sería capturar la campaña de esa semana, no una propiedad del producto, y `en_oferta` saldría prácticamente constante.

### H3 · Los PVP coinciden entre cadenas; lo que cambia es la promoción

EAN `8056597124508` (Ray-Ban 0RX6448 / RB6448), verificado el 1 ago 2026:

```
General Óptica:  PVP 167,00 €  →  precio hoy 125,25 €
Óptica 2000:         163,00 €  →  sin oferta
```

Diferencia de PVP: **2,45 %**. Diferencia de precio pagado: **-23,16 %**.

Esto abre una pregunta más interesante que la regresión de precio: por qué el mismo producto cuesta 125 € en una cadena y 163 € en otra el mismo día. Es dispersión de precios en retail, se responde con datos y el EAN da la clave de cruce.

### H4 · Conflicto de interés a documentar

Óptica 2000 es Grandvisión Spain, del grupo EssilorLuxottica, que a su vez fabrica o licencia Ray-Ban, Oakley, Vogue, Persol y Arnette. El minorista y el fabricante son el mismo grupo. Con la variable "grupo licenciante" (D3) eso es un confusor evidente y hay que declararlo. No invalida nada: hace más interesante el contraste con un minorista independiente.

### H5 · La conclusión de fondo del proyecto se sostiene

Ablaciones verificadas el 1 ago 2026:

| Solo con… | MAE | R² |
|---|---:|---:|
| geometría + peso | 33,40 € | 0,464 |
| marca | 23,38 € | 0,801 |

"El precio es la marca, no la geometría de la montura" es cierto y **no depende de la tabla dudosa**. La conclusión de cabecera del proyecto sobrevive a la limpieza.

---

## 5. Métricas de referencia

### Las cifras reales del modelo actual

Reproducidas el 1 ago 2026 reentrenando desde `data/train/train.csv`, sin usar `models/final_model.pkl`:

| | Reproducido | Notebook celda 37 | README (incorrecto) |
|---|---:|---:|---:|
| RF — MAE | 17,18 € | 17,18 € | ~~17,78 €~~ |
| RF — RMSE | 25,84 € | 25,85 € | ~~27,78 €~~ |
| RF — R² | 0,869 | 0,87 | ~~0,84~~ |
| RF — MAPE | 15,11 % | 15,11 % | ~~14,75 %~~ |
| Ridge — MAE | 20,59 € | 20,59 € | ~~21,02 €~~ |
| Ridge — R² | 0,84 | 0,84 | ~~0,81~~ |

**El notebook tiene razón; el README está mal en las seis cifras.** El R² real es 0,87, no 0,84.

### Curva de aprendizaje — cuántos datos hacen falta

Submuestreo del train actual, 3 semillas, test fijo (1 ago 2026):

| n train | catálogo equivalente | MAE | R² | marcas |
|---:|---:|---:|---:|---:|
| 200 | ~250 | 26,64 € | 0,723 | 48 |
| 400 | ~500 | 23,30 € | 0,775 | 56 |
| 600 | ~750 | 21,41 € | 0,808 | 61 |
| 850 | ~1.062 | 19,92 € | 0,835 | 65 |
| 1.200 | ~1.500 | 18,98 € | 0,850 | 68 |
| 1.600 | ~2.000 | 18,15 € | 0,856 | 69 |
| 2.295 | ~2.868 | 17,10 € | 0,869 | 72 |

### Escenario decidido, sin enriquecimiento IA y sin `peso`

| Escenario | MAE |
|---|---:|
| 2.875 productos, con peso | 18,35 € |
| ~1.058 productos, sin peso | 22,51 € |

Degradación total esperada al cambiar a Óptica 2000: **+4,16 € de MAE (+23 %)**.

Contrapeso no cuantificado: los 18,35 € se miden contra un target contaminado por promociones. Con PVP limpio, parte de ese error desaparece.

---

## 6. Defectos del repo actual, para corregir al reconstruir

| # | Defecto | Estado |
|---|---|---|
| 1 | Las seis métricas del README no coinciden con el notebook | pendiente |
| 2 | El README apunta a `models/final_model_randomforest.pkl`; el archivo es `final_model.pkl` | pendiente |
| 3 | `data/` está en `.gitignore`: nadie que clone puede ejecutar nada | pendiente |
| 4 | El pickle exige scikit-learn 1.8.0 y Python ≥3.11; `requirements.txt` no fija versiones | pendiente |
| 5 | `src/training.py` no puede reproducir el modelo final: su grid no contiene la combinación ganadora (`max_depth=20`, `max_features=0.7`) | pendiente |
| 6 | El modelo final se selecciona mirando el test (`tabla_test['MAE_€'].idxmin()`) | pendiente |
| 7 | Un solo commit, "Initial commit - Proyecto ML" | pendiente |
| 8 | `prueba.ipynb`, `patch_precio.ipynb` y `patch_precio_v2.ipynb` publicados (~4.900 líneas de andamiaje) | pendiente |
| 9 | Rutas locales de Windows visibles en los outputs de tres notebooks | pendiente |
| 10 | El README ofrece como "próximos pasos" cosas ya hechas (scripts en `src`, app Streamlit, boosting) | pendiente |
| 11 | El README no menciona el web scraping, que es el argumento más diferencial del proyecto | pendiente |
| 12 | Sin licencia, sin quickstart, sin tests | pendiente |
| 13 | 5 filas del raw eran líquidos y sprays, no gafas; se cayeron por tener `marca` nula, no por un filtro explícito | pendiente |

**Nota:** `git status` marca `models/final_model.pkl` como modificado, pero es un artefacto de que el entorno de análisis no tiene `git-lfs`. No es un problema real del repo.

---

## 7. Cumplimiento y buenas prácticas de scrapeo

- **Lentiamo:** las 2.875 URLs del dataset actual son fichas de producto de un solo segmento. **Cero** coinciden con `Disallow: /gafas-graduadas/*/*` ni con `/all-glasses/*`. Verificado 1 ago 2026. Ojo: las páginas de listado por categoría **sí** están prohibidas — la lista de URLs debe salir del `sitemap.xml`.
- **Óptica 2000:** para `User-agent: *` solo prohíbe `/cancela-tu-cita` y `/reprograma-tu-cita`. Categorías y fichas permitidas. Publica sitemap.
- **General Óptica:** `Crawl-delay: 30` para todos. Las fichas de producto no están prohibidas (solo la ruta interna `/catalog/product/view/`). 4.938 fichas a 30 s son **41 horas**.
- En todos los casos: enumerar URLs desde el sitemap, no desde listados de categoría, y declarar en el README el ritmo de peticiones y el respeto a `robots.txt`.
