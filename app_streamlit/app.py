"""Demostrador del modelo de precio de catálogo (PVP) de monturas graduadas.

    streamlit run app_streamlit/app.py

No es una herramienta de pricing: el precio de unas gafas graduadas lo dominan la
lente, el laboratorio, el local y el tiempo del optometrista, no la montura.

Lo que enseña es el hallazgo del proyecto, que la marca explica el 81 % de la
varianza del precio y la geometría el 16 %. Por eso la sección principal no es
cuánto vale una montura sino cuánto cambia su precio según el nombre que lleve.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import pandas as pd
import streamlit as st

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src" / "modelado"))
sys.path.insert(0, str(RAIZ / "src" / "scraping"))
from datos import CAT, FEATURES, NUM, cargar  # noqa: E402
from marcas import normalizar  # noqa: E402

MODELO = RAIZ / "models" / "modelo_pvp.pkl"
METRICAS = RAIZ / "models" / "metricas.json"

st.set_page_config(page_title="Precio de monturas graduadas",
                   page_icon="👓", layout="wide")


# ---------------------------------------------------------------------------
# Carga (en caché: el modelo son 9,4 MB y el dataset 6.121 filas)
# ---------------------------------------------------------------------------
@st.cache_resource
def cargar_modelo():
    if not MODELO.exists():
        st.error(f"No encuentro `{MODELO.relative_to(RAIZ)}`. "
                 "Ejecuta antes: `python src/modelado/entrenar.py`")
        st.stop()
    return joblib.load(MODELO)


@st.cache_data
def cargar_metricas() -> dict:
    return json.loads(METRICAS.read_text(encoding="utf-8")) if METRICAS.exists() else {}


@st.cache_data
def cargar_datos() -> pd.DataFrame:
    return cargar()


modelo = cargar_modelo()
info = cargar_metricas()
d = cargar_datos()

MAE = info.get("test", {}).get("MAE_eur", 18.9)
R2 = info.get("test", {}).get("R2", 0.85)

# Opciones sacadas del dataset real, para que no haya combinaciones que el
# modelo nunca ha visto.
#
# Las dos tiendas escriben algunas marcas distinto ("Ray Ban" / "Ray-Ban"). El
# modelo las trata como categorías separadas a propósito: normalizarlas empeora
# el MAE de 18,90 a 19,01 €, porque la grafía funciona como identificador
# encubierto de la tienda. En el desplegable se muestra solo la más frecuente.
_frec = d.dropna(subset=["marca"]).groupby("marca").size()
_canon = {}
for m, n in _frec.items():
    k = normalizar(m)
    if k not in _canon or n > _frec[_canon[k]]:
        _canon[k] = m
marcas = sorted(_canon.values())
marca_a_grupo = d.dropna(subset=["marca"]).groupby("marca")["grupo"].first().to_dict()
tiendas = sorted(d["tienda"].unique())
materiales = sorted(d["material_montura"].dropna().unique())
colores = sorted(d["color"].dropna().unique())
generos = sorted(d["genero"].dropna().unique())

# ---------------------------------------------------------------------------
# Cabecera
# ---------------------------------------------------------------------------
st.title("👓 ¿Qué determina el precio de una montura?")
st.markdown(
    "Modelo entrenado con 6.121 monturas graduadas de Óptica 2000 y General "
    "Óptica, capturadas en agosto de 2026. Predice el precio de catálogo (PVP), "
    "no el precio promocional del día."
)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Error medio", f"{MAE:.2f} €")
c2.metric("R² en test", f"{R2:.3f}")
c3.metric("Productos", f"{len(d):,}".replace(",", "."))
c4.metric("Marcas", d["marca"].nunique())

st.divider()

# ---------------------------------------------------------------------------
# Formulario
# ---------------------------------------------------------------------------
izq, der = st.columns([1, 1.4])

with izq:
    st.subheader("Configura la montura")
    # Por defecto, la marca con más referencias en el dataset.
    _defecto = max(marcas, key=lambda m: int(_frec.get(m, 0)))
    marca = st.selectbox("Marca", marcas, index=marcas.index(_defecto))
    grupo = marca_a_grupo.get(marca, "desconocido")
    st.caption(f"Grupo propietario: **{grupo}**")

    tienda = st.selectbox("Tienda", tiendas)
    material = st.selectbox("Material de la montura", materiales)
    color = st.selectbox("Color", colores)
    genero = st.selectbox("Género", generos)
    ancho_lente = st.slider("Ancho de lente (mm)", 35, 65, 52)
    ancho_puente = st.slider("Ancho del puente (mm)", 12, 30, 18)

ficha = pd.DataFrame([{
    "marca": marca, "grupo": grupo, "tienda": tienda,
    "material_montura": material, "color": color, "genero": genero,
    "ancho_lente": float(ancho_lente), "ancho_puente": float(ancho_puente),
}])[FEATURES]

pred = float(modelo.predict(ficha)[0])

with der:
    st.subheader("Precio de catálogo estimado")
    st.markdown(f"# {pred:,.2f} €".replace(",", "."))
    st.caption(
        f"El modelo se equivoca de media en {MAE:.2f} €, así que el rango "
        f"razonable es {max(pred - MAE, 0):,.0f} a {pred + MAE:,.0f} €. "
        "No es un precio de venta: es lo que costaría una montura con estas "
        "características en el catálogo de estas dos cadenas."
    )

    # Precios de la marca en todo el dataset, no solo en la tienda elegida:
    # filtrar por marca y tienda dejaba el recuadro vacío casi la mitad de las
    # veces, porque solo el 12 % de las marcas está en las dos cadenas.
    reales = d[d["marca"] == marca]["pvp"]
    if len(reales) >= 3:
        st.info(
            f"{marca} en el dataset: {len(reales)} monturas reales, "
            f"de {reales.min():,.0f} € a {reales.max():,.0f} €, "
            f"mediana {reales.median():,.0f} €."
        )
    else:
        st.warning(
            f"Solo hay {len(reales)} montura(s) de {marca} en todo el dataset. "
            "La predicción para esta marca es poco fiable."
        )

    # Que una marca falte en una cadena no es un hueco de datos, es el hallazgo:
    # el 69 % está solo en General Óptica, el 20 % solo en Óptica 2000.
    en_tiendas = sorted(d.loc[d["marca"] == marca, "tienda"].unique())
    if len(en_tiendas) == 2:
        st.caption("Esta marca se vende en las dos cadenas. Solo el 12 % lo hace.")
    elif en_tiendas and tienda not in en_tiendas:
        otra = en_tiendas[0]
        st.caption(
            f"{marca} no se vende en {tienda}, solo en {otra}. La predicción es "
            "una extrapolación: el modelo estima qué costaría si la vendiera. Que "
            "falte no es un vacío del dataset, es el reparto de marcas entre cadenas."
        )
    elif en_tiendas:
        st.caption(f"Esta marca solo se vende en {en_tiendas[0]}.")

st.divider()

# ---------------------------------------------------------------------------
# La sección que demuestra el hallazgo del proyecto
# ---------------------------------------------------------------------------
st.subheader("La misma montura, distinta marca")
st.markdown(
    "Se mantienen los mismos atributos físicos (material, color, género y "
    "calibre) y solo se cambia la marca. Todo lo que se mueva en el gráfico es "
    "precio que no viene del producto."
)

n_marcas = st.slider("Cuántas marcas comparar", 5, 30, 15)
frecuentes = d["marca"].value_counts().head(n_marcas).index.tolist()
if marca not in frecuentes:
    frecuentes = [marca] + frecuentes[:-1]

comparacion = pd.DataFrame([{
    "marca": m, "grupo": marca_a_grupo.get(m, "desconocido"), "tienda": tienda,
    "material_montura": material, "color": color, "genero": genero,
    "ancho_lente": float(ancho_lente), "ancho_puente": float(ancho_puente),
} for m in frecuentes])

comparacion["PVP estimado (€)"] = modelo.predict(comparacion[FEATURES]).round(2)
comparacion = comparacion.sort_values("PVP estimado (€)", ascending=False)

g1, g2 = st.columns([1.5, 1])
with g1:
    st.bar_chart(comparacion.set_index("marca")["PVP estimado (€)"], height=380)
with g2:
    st.dataframe(
        comparacion[["marca", "grupo", "PVP estimado (€)"]].reset_index(drop=True),
        hide_index=True, height=380,
    )

mn, mx = comparacion["PVP estimado (€)"].min(), comparacion["PVP estimado (€)"].max()
st.success(
    f"Con los mismos atributos físicos, el precio va de {mn:,.0f} € a "
    f"{mx:,.0f} €: {mx - mn:,.0f} € de diferencia, {mx / mn:.1f} veces. "
    "El material, el color y el calibre no han cambiado. Solo el nombre."
)

st.divider()

# ---------------------------------------------------------------------------
# Honestidad sobre el modelo
# ---------------------------------------------------------------------------
with st.expander("Qué explica el precio, y qué no puede hacer este modelo"):
    st.markdown(f"""
Cuánto explica cada bloque de variables por sí solo (R² en test, notebook 02):

| Con solo… | R² |
|---|---:|
| la marca | 0,81 |
| el grupo propietario | 0,24 |
| la geometría (calibre y puente) | 0,16 |
| la tienda | 0,00 |

Que la tienda dé 0,00 no es un fallo, es un resultado: el precio de catálogo de
una montura es el mismo la venda quien la venda. Se comprobó primero sobre los
110 productos idénticos presentes en las dos cadenas, donde el PVP coincide
dentro de ±5 % en el 99 % de los casos, y luego el modelo lo confirmó por su
cuenta.

Limitaciones:

- Son precios de catálogo online de dos cadenas concretas. En España la venta
  online ronda el 10 % del mercado de gafas graduadas.
- Es una foto de agosto de 2026.
- El modelo infraestima las monturas caras: por encima de 300 € hay pocos datos
  y muy heterogéneos.
- No sirve para fijar precios en una óptica. Su margen de error es de {MAE:.0f} €
  sobre una mediana de 158 €, y no conoce ni tus costes ni tus proveedores ni tu
  clientela.
- Mide asociación, no causalidad: que la marca prediga el precio no demuestra
  que lo cause.
""")

st.caption(
    "Juan Antonio Muñoz Moreno · [github.com/JuanAntoniomm]"
    "(https://github.com/JuanAntoniomm) · Datos capturados respetando el "
    "robots.txt de ambas webs. El código de los scrapers y los notebooks están "
    "en el repositorio."
)
