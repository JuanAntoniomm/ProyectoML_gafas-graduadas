"""
app_streamlit/app.py
====================

App Streamlit del proyecto: predice el precio de mercado de una montura de
gafas graduadas a partir de sus atributos (marca, género, material, medidas,
etc.) y muestra los productos más parecidos del catálogo de Lentiamo.

Modelo: RandomForestRegressor entrenado en `notebooks/03_Modelado.ipynb` y
guardado en `models/final_model.pkl`. El split train/test se hace al inicio
del pipeline para evitar fuga de datos. Métricas en test: MAE 17.18 € · R² 0.87.

Uso local:
    streamlit run app_streamlit/app.py

Despliegue:
    Conectar este repo a Streamlit Community Cloud y apuntar a este fichero
    como entrypoint.
"""

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# Rutas (relativas al fichero, funcionan local y en Streamlit Cloud)
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
MODEL_PATH = ROOT / 'models' / 'final_model.pkl'
MARCAS_TIER = ROOT / 'data' / 'raw' / 'marcas_tier.csv'
MATERIALES_TIER = ROOT / 'data' / 'raw' / 'materiales_tier.csv'
CATALOGO = ROOT / 'data' / 'processed' / 'lentiamo_graduadas_clean.csv'

MAE_TEST = 17.18  # MAE del RandomForest en el conjunto de test (referencia)


# ---------------------------------------------------------------------------
# Carga cacheada
# ---------------------------------------------------------------------------
@st.cache_resource
def cargar_modelo():
    return joblib.load(MODEL_PATH)


@st.cache_data
def cargar_marcas() -> pd.DataFrame:
    return pd.read_csv(MARCAS_TIER, sep=';')


@st.cache_data
def cargar_materiales() -> pd.DataFrame | None:
    if not MATERIALES_TIER.exists():
        return None
    # OJO: materiales_tier.csv usa coma como separador (no ';' como marcas)
    return pd.read_csv(MATERIALES_TIER)


@st.cache_data
def cargar_catalogo() -> pd.DataFrame:
    return pd.read_csv(CATALOGO)


# ---------------------------------------------------------------------------
# Enriquecimiento experto (replica la lógica del notebook 02 + predict_example)
# ---------------------------------------------------------------------------
def enriquecer_marca(p: dict, marcas: pd.DataFrame) -> dict:
    """Añade gama_marca, segmento_comercial, pais_origen y precio_medio_marca."""
    fila = marcas[marcas['marca'] == p['marca']]
    if len(fila) == 0:
        p['gama_marca'] = 'gama_media'
        p['segmento_comercial'] = 'moda_casual'
        p['pais_origen'] = 'Desconocido'
        p['precio_medio_marca'] = 100.0
        return p

    m = fila.iloc[0]
    p['gama_marca'] = m['tier']
    p['segmento_comercial'] = m['segmento']
    p['pais_origen'] = m['pais_origen']
    pmin = float(m['precio_min']) if pd.notna(m['precio_min']) else 0.0
    pmax = float(m['precio_max']) if pd.notna(m['precio_max']) else 0.0
    p['precio_medio_marca'] = (pmin + pmax) / 2 if (pmin + pmax) > 0 else 100.0
    return p


def enriquecer_material(p: dict, mat_df: pd.DataFrame | None) -> dict:
    """Añade categoria_material, gama_material y peso_relativo (si están)."""
    if mat_df is None:
        return p
    fila = mat_df[mat_df['material_montura'] == p['material_montura']]
    if len(fila) == 0:
        p['categoria_material'] = 'otro'
        p['gama_material'] = 'gama_media'
        p['peso_relativo'] = 'medio'
        return p
    m = fila.iloc[0]
    p['categoria_material'] = m['categoria_material']
    p['gama_material'] = m['gama_material']
    p['peso_relativo'] = m['peso_relativo']
    return p


def features_del_modelo(model) -> list:
    """Recupera el orden exacto de columnas que espera el ColumnTransformer."""
    prep = model.named_steps['prep']
    cols: list = []
    for name, _, c in prep.transformers_:
        if name != 'remainder':
            cols.extend(c)
    return cols


# ---------------------------------------------------------------------------
# Productos similares (distancia euclídea en features numéricas estandarizadas)
# ---------------------------------------------------------------------------
def productos_similares(enriched: dict, catalogo: pd.DataFrame, n: int = 3) -> pd.DataFrame:
    num_cols = ['ancho_lente', 'ancho_puente', 'largo_varilla', 'peso', 'precio_medio_marca']
    user_num = np.array([enriched[c] for c in num_cols], dtype=float)
    cat_num = catalogo[num_cols].values.astype(float)
    means = np.nanmean(cat_num, axis=0)
    stds = np.nanstd(cat_num, axis=0) + 1e-9
    u_s = (user_num - means) / stds
    c_s = np.nan_to_num((cat_num - means) / stds, nan=0.0)
    dists = np.linalg.norm(c_s - u_s, axis=1)
    idx = np.argsort(dists)[:n]
    return catalogo.iloc[idx][['marca', 'modelo', 'forma', 'material_montura', 'color', 'precio']].copy()


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title='Pricing gafas graduadas',
    page_icon=None,
    layout='wide',
)

st.title('Predicción del precio de gafas graduadas')
st.caption(
    'Modelo: RandomForest entrenado sobre 2.295 productos del catálogo de Lentiamo · '
    f'MAE en test = {MAE_TEST:.2f} € · R² = 0.87'
)

# Carga de recursos
try:
    model = cargar_modelo()
    marcas = cargar_marcas()
    materiales = cargar_materiales()
    catalogo = cargar_catalogo()
except Exception as e:
    st.error(f'No se pudieron cargar los recursos del modelo:\n\n{e}')
    st.stop()

# Opciones del formulario (derivadas de los datos para que estén siempre alineadas)
marcas_opt = sorted(marcas['marca'].dropna().unique().tolist())
generos_opt = sorted(catalogo['genero'].dropna().unique().tolist())
materiales_opt = sorted(catalogo['material_montura'].dropna().unique().tolist())
formas_opt = sorted(catalogo['forma'].dropna().unique().tolist())
tipos_opt = sorted(catalogo['tipo_montura'].dropna().unique().tolist())
colores_opt = sorted(catalogo['color'].dropna().unique().tolist())
tallas_opt = sorted(catalogo['talla'].dropna().unique().tolist())


def _default_idx(options, preferred):
    return options.index(preferred) if preferred in options else 0


with st.form('form_gafas'):
    st.subheader('Características de la gafa')

    c1, c2, c3 = st.columns(3)
    with c1:
        marca = st.selectbox('Marca', marcas_opt,
                             index=_default_idx(marcas_opt, 'Ray-Ban'))
        genero = st.selectbox('Género', generos_opt,
                              index=_default_idx(generos_opt, 'Unisex'))
        material_montura = st.selectbox('Material de la montura', materiales_opt,
                                        index=_default_idx(materiales_opt, 'Acetato'))
    with c2:
        forma = st.selectbox('Forma', formas_opt,
                             index=_default_idx(formas_opt, 'Rectangulares'))
        tipo_montura = st.selectbox('Tipo de montura', tipos_opt,
                                    index=_default_idx(tipos_opt, 'Montura completa'))
        color = st.selectbox('Color', colores_opt,
                             index=_default_idx(colores_opt, 'negro'))
    with c3:
        talla = st.selectbox('Talla', tallas_opt,
                             index=_default_idx(tallas_opt, 'M'))
        ancho_lente = st.slider('Ancho de lente (mm)', 40.0, 65.0, 54.0, 0.5)
        ancho_puente = st.slider('Ancho de puente (mm)', 12.0, 25.0, 17.0, 0.5)

    c4, c5 = st.columns(2)
    with c4:
        largo_varilla = st.slider('Largo de varilla (mm)', 120.0, 155.0, 140.0, 0.5)
    with c5:
        peso = st.slider('Peso (g)', 10.0, 60.0, 25.0, 0.5)

    submitted = st.form_submit_button('Predecir precio', type='primary')

# ---------------------------------------------------------------------------
# Resultado
# ---------------------------------------------------------------------------
if submitted:
    user_input = {
        'marca': marca, 'genero': genero, 'material_montura': material_montura,
        'forma': forma, 'tipo_montura': tipo_montura, 'color': color, 'talla': talla,
        'ancho_lente': ancho_lente, 'ancho_puente': ancho_puente,
        'largo_varilla': largo_varilla, 'peso': peso,
    }
    enriched = enriquecer_marca(dict(user_input), marcas)
    enriched = enriquecer_material(enriched, materiales)

    feats = features_del_modelo(model)
    row = {f: enriched.get(f, np.nan) for f in feats}
    X = pd.DataFrame([row])[feats]
    precio = float(model.predict(X)[0])

    st.divider()
    st.subheader('Resultado')

    col_a, col_b = st.columns([2, 3])
    with col_a:
        st.metric(
            label='Precio estimado',
            value=f'{precio:.2f} €',
            delta=f'± {MAE_TEST:.2f} € (MAE en test)',
            delta_color='off',
        )
        st.markdown(
            f"""
            **Tier de marca:** {enriched['gama_marca']}
            **Segmento comercial:** {enriched['segmento_comercial']}
            **País de origen:** {enriched['pais_origen']}
            **Precio medio de la marca:** {enriched['precio_medio_marca']:.0f} €
            **Categoría del material:** {enriched.get('categoria_material', '—')}
            """
        )
    with col_b:
        st.markdown('**Productos más parecidos del catálogo** (geometría y precio de marca similares):')
        sim = productos_similares(enriched, catalogo, n=3)
        sim_show = sim.rename(columns={
            'marca': 'Marca',
            'modelo': 'Modelo',
            'forma': 'Forma',
            'material_montura': 'Material',
            'color': 'Color',
            'precio': 'Precio (€)',
        })
        sim_show['Precio (€)'] = sim_show['Precio (€)'].map(lambda x: f'{x:.2f}')
        st.dataframe(sim_show, hide_index=True, use_container_width=True)

    with st.expander('¿Cómo funciona esta predicción?'):
        st.markdown(
            """
            La predicción combina los **atributos que introduces** con
            **conocimiento experto** de cada marca (tier, segmento comercial,
            país, precio medio histórico) y de cada material (categoría, gama,
            peso relativo). Esa información viene de un enriquecimiento manual
            del catálogo, no del scraping puro.

            El modelo es un **RandomForestRegressor** entrenado sobre 2.295
            productos del catálogo de Lentiamo. El conjunto de test
            (575 productos) se separó al inicio del pipeline, antes de cualquier
            imputación o feature engineering, para evitar **fuga de datos**.

            **Métricas en test:** MAE = 17.18 € · RMSE = 25.85 € · R² = 0.87
            · MAPE = 15.11 %. Sobre una mediana de mercado de 114 € eso
            equivale a un error medio de unos 15 puntos porcentuales, razonable
            para una herramienta de pricing asistido.
            """
        )
else:
    st.info('Rellena el formulario y pulsa **Predecir precio** para obtener una estimación.')


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header('Acerca de')
    st.markdown(
        """
        Proyecto final del módulo de **Machine Learning** del bootcamp de
        Data Science de **The Bridge**.

        Predice el precio de mercado de una montura de gafas graduadas a partir
        de marca, género, material, medidas físicas y otras características.
        Caso de uso: pricing asistido para una óptica.

        **Pipeline**
        - Scraping de Lentiamo (75 marcas, ~2.870 productos).
        - Enriquecimiento experto vía LLMs (Perplexity + NotebookLM) con tier
          de marca, segmento, país de origen y categoría de material.
        - Split train/test (80/20) al inicio del pipeline para evitar fuga.
        - Ablaciones de features + análisis VIF para llegar a 5 numéricas
          + 13 categóricas.
        - GridSearchCV sobre RandomForest.

        **Repo:** [github.com/aJk15lml/THE-BRIDGE](https://github.com/aJk15lml/THE-BRIDGE)
        """
    )
