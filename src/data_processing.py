"""
data_processing.py
==================

Procesa el dataset crudo de Lentiamo (gafas graduadas) y genera los conjuntos
de entrenamiento y test listos para el modelado.

Replica EXACTAMENTE la lógica del notebook `notebooks/02_LimpiezaEDA.ipynb`:

- El train/test split se hace AL PRINCIPIO, sobre los datos crudos, antes de
  cualquier transformación. Es el momento correcto: los estadísticos de
  imputación (medianas por marca, modas) se aprenden SOLO de train y se aplican
  tal cual a test. Así se evita la fuga de datos (data leakage).
- Limpieza inicial: drop de columnas inútiles, duplicados y NaN críticos.
- Imputación: mediana por marca (fallback global) para numéricas, moda para
  categóricas. Estadísticos aprendidos en train.
- Reducción de multicolinealidad (drop calibre_total).
- Enriquecimiento experto de marcas (merge con marcas_tier.csv).
- Normalización categórica (color, material).
- Enriquecimiento opcional de materiales (materiales_tier.csv).
- Feature engineering (8 features derivadas).
- Renombre de columnas a nombres definitivos (tier -> gama_marca, etc.).

Uso:
    python src/data_processing.py

Inputs:
    data/raw/lentiamo_graduadas.csv      (obligatorio, precio actual de mercado)
    data/raw/marcas_tier.csv             (obligatorio, separador ';')
    data/raw/materiales_tier.csv         (opcional,    separador ',')

Outputs:
    data/train/train.csv
    data/test/test.csv
    data/processed/lentiamo_graduadas_clean.csv   (train+test, solo referencia)

Notas de diseño:
    - NO se winsoriza el target: los precios altos son productos premium reales,
      no outliers. Recortarlos haría que el modelo infraestimase el segmento
      de mayor margen para una óptica.
    - log_precio se crea como target alternativo (no destructivo) para modelos
      lineales que asumen distribución normal de errores.
"""

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / 'data' / 'raw'
PROC = ROOT / 'data' / 'processed'
TRAIN = ROOT / 'data' / 'train'
TEST = ROOT / 'data' / 'test'

CSV_INPUT = RAW / 'lentiamo_graduadas.csv'
CSV_MARCAS = RAW / 'marcas_tier.csv'
CSV_MATERIALES = RAW / 'materiales_tier.csv'  # opcional
CSV_OUTPUT = PROC / 'lentiamo_graduadas_clean.csv'

RANDOM_STATE = 42
TEST_SIZE = 0.2

NUM_COLS_BASE = ['ancho_lente', 'ancho_puente', 'largo_varilla', 'calibre_total', 'peso']
CAT_COLS_BASE = ['genero', 'material_montura', 'forma', 'tipo_montura', 'color', 'talla']

MAPEO_COLOR = {
    'negro':        ['negro', 'black'],
    'marron':       ['marrón', 'marron', 'havana', 'café', 'brown', 'caoba'],
    'gris':         ['gris', 'grafito', 'grey', 'antracita', 'plomo'],
    'transparente': ['transparente', 'cristal', 'crystal', 'translúcido', 'translucido'],
    'azul':         ['azul', 'navy', 'blue'],
    'dorado':       ['dorado', 'oro', 'gold'],
    'plateado':     ['plateado', 'plata', 'silver'],
    'rojo':         ['rojo', 'red', 'burdeos', 'borgoña'],
    'rosa':         ['rosa', 'rosado', 'pink'],
    'verde':        ['verde', 'green', 'oliva'],
    'morado':       ['morado', 'violeta', 'purple', 'lila'],
    'blanco':       ['blanco', 'white', 'beige', 'crema', 'marfil'],
    'tortoise':     ['tortoise'],
}

RENAME_FINAL = {
    'tier':     'gama_marca',
    'segmento': 'segmento_comercial',
}


# ---------------------------------------------------------------------------
# Carga y split
# ---------------------------------------------------------------------------
def cargar(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    print(f'Cargado: {path.name} -> {df.shape}')
    return df


def split_train_test(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split SOBRE DATOS CRUDOS, antes de transformar nada (anti-fuga de datos)."""
    train_raw, test_raw = train_test_split(
        df, test_size=TEST_SIZE, random_state=RANDOM_STATE)
    print(f'Split crudo: train={len(train_raw)} | test={len(test_raw)}')
    return train_raw, test_raw


# ---------------------------------------------------------------------------
# Pasos del pipeline
# ---------------------------------------------------------------------------
def limpiar(df: pd.DataFrame) -> pd.DataFrame:
    """Drop columnas inútiles, duplicados y NaN en críticos."""
    df = df.copy()
    for col in ('url', 'tipo', 'polarizadas'):
        if col in df.columns:
            df = df.drop(columns=col)
    df = df.drop_duplicates(subset=['modelo'])
    df = df.dropna(subset=['precio', 'marca']).copy()
    return df


def aprender_imputacion(train: pd.DataFrame) -> dict:
    """Aprende los estadísticos de imputación SOLO de train.

    Devuelve un dict con la mediana por marca y la mediana global de cada
    numérica, y la moda de cada categórica. Estos valores se reaplican tal cual
    a test, de forma que test nunca influye en la preparación de train.
    """
    stats = {'mediana_marca': {}, 'mediana_global': {}, 'moda': {}}
    for c in NUM_COLS_BASE:
        if c in train.columns:
            stats['mediana_marca'][c] = train.groupby('marca')[c].median()
            stats['mediana_global'][c] = float(train[c].median())
    for c in CAT_COLS_BASE:
        if c in train.columns:
            moda = train[c].mode()
            stats['moda'][c] = moda.iloc[0] if len(moda) > 0 else 'Desconocido'
    return stats


def imputar(df: pd.DataFrame, stats: dict) -> pd.DataFrame:
    """Aplica los estadísticos de TRAIN (sirve para train y para test)."""
    df = df.copy()
    for c in NUM_COLS_BASE:
        if c in df.columns:
            df[c] = (df[c]
                     .fillna(df['marca'].map(stats['mediana_marca'][c]))
                     .fillna(stats['mediana_global'][c]))
    for c in CAT_COLS_BASE:
        if c in df.columns:
            df[c] = df[c].fillna(stats['moda'][c])
    return df


def reducir_multicolinealidad(df: pd.DataFrame) -> pd.DataFrame:
    """calibre_total es ~ 2*ancho_lente + ancho_puente -> redundante."""
    if 'calibre_total' in df.columns:
        df = df.drop(columns=['calibre_total'])
    return df


def enriquecer_marcas(df: pd.DataFrame) -> pd.DataFrame:
    """Merge con marcas_tier.csv: tier, segmento, pais_origen, precio_min/max."""
    if not CSV_MARCAS.exists():
        raise FileNotFoundError(f'Falta {CSV_MARCAS}. Genera con flujo Perplexity + NotebookLM.')

    marcas_tier = pd.read_csv(CSV_MARCAS, sep=';')
    df = df.merge(marcas_tier, on='marca', how='left')
    df['tier']        = df['tier'].fillna('gama_media')
    df['segmento']    = df['segmento'].fillna('moda_casual')
    df['pais_origen'] = df['pais_origen'].fillna('Desconocido')
    df['precio_min']  = df['precio_min'].fillna(0).astype(float)
    df['precio_max']  = df['precio_max'].fillna(0).astype(float)
    if 'notas' in df.columns:
        df = df.drop(columns=['notas'])
    return df


def normalizar_color(df: pd.DataFrame) -> pd.DataFrame:
    def _map(s):
        if pd.isna(s):
            return 'otro'
        s_low = str(s).lower()
        for canon, sinonimos in MAPEO_COLOR.items():
            if any(syn in s_low for syn in sinonimos):
                return canon
        return 'otro'
    df = df.copy()
    df['color'] = df['color'].apply(_map)
    return df


def normalizar_material(df: pd.DataFrame) -> pd.DataFrame:
    """Agrupa todas las variantes 'Eco-friendly - X' en una sola categoría."""
    df = df.copy()
    df['material_montura'] = df['material_montura'].apply(
        lambda x: 'Eco-friendly' if isinstance(x, str) and x.startswith('Eco-friendly') else x
    )
    return df


def enriquecer_materiales(df: pd.DataFrame) -> pd.DataFrame:
    """Merge opcional con materiales_tier.csv (categoría/gama/peso del material)."""
    if not CSV_MATERIALES.exists():
        print(f'  {CSV_MATERIALES.name} no encontrado, se omite enriquecimiento de materiales.')
        return df

    mat = pd.read_csv(CSV_MATERIALES, sep=',')
    cols = ['material_montura', 'categoria_material', 'gama_material', 'peso_relativo']
    df = df.merge(mat[cols], on='material_montura', how='left')
    df['categoria_material'] = df['categoria_material'].fillna('otro')
    df['gama_material']      = df['gama_material'].fillna('gama_media')
    df['peso_relativo']      = df['peso_relativo'].fillna('medio')
    return df


def crear_log_target(df: pd.DataFrame) -> pd.DataFrame:
    """Target alternativo. NO se winsoriza el precio (decisión justificada en nb 02)."""
    df = df.copy()
    df['log_precio'] = np.log1p(df['precio'])
    return df


def feature_engineering(df: pd.DataFrame, precio_mediano: float) -> pd.DataFrame:
    """Features derivadas con sentido de negocio.

    `precio_mediano` es la mediana de precio de TRAIN, usada como fallback de
    precio_medio_marca (no se usa la mediana del dataset completo: sería fuga).
    """
    df = df.copy()
    df['aspect_ratio']     = df['ancho_lente'] / df['largo_varilla']
    df['area_aprox']       = df['ancho_lente'] * df['ancho_puente']
    df['densidad']         = df['peso'] / df['area_aprox']
    df['ancho_total']      = 2 * df['ancho_lente'] + df['ancho_puente']
    df['montura_completa'] = (df['tipo_montura'].str.contains('completa', case=False, na=False)
                              .astype(int))
    df['es_unisex']        = df['genero'].str.lower().eq('unisex').astype(int)
    df['color_basico']     = df['color'].isin(['negro', 'marron']).astype(int)
    df['material_eco']     = (df['material_montura'] == 'Eco-friendly').astype(int)

    df['precio_medio_marca'] = (df['precio_min'] + df['precio_max']) / 2
    df['precio_medio_marca'] = (df['precio_medio_marca']
                                .replace(0, np.nan)
                                .fillna(precio_mediano))
    return df


def renombrar_final(df: pd.DataFrame) -> pd.DataFrame:
    """Renombre canónico para coherencia con el notebook 03 y el resto del pipeline."""
    return df.rename(columns={k: v for k, v in RENAME_FINAL.items() if k in df.columns})


def reordenar(df: pd.DataFrame) -> pd.DataFrame:
    """Identificadores -> features -> targets."""
    ids   = [c for c in ['modelo'] if c in df.columns]
    tgts  = [c for c in ('precio', 'log_precio') if c in df.columns]
    feats = [c for c in df.columns if c not in ids + tgts]
    return df[ids + feats + tgts]


def pipeline_resto(df: pd.DataFrame, precio_mediano: float) -> pd.DataFrame:
    """Transformaciones deterministas posteriores a la imputación (train y test)."""
    df = reducir_multicolinealidad(df)
    df = enriquecer_marcas(df)
    df = normalizar_color(df)
    df = normalizar_material(df)
    df = enriquecer_materiales(df)
    df = crear_log_target(df)
    df = feature_engineering(df, precio_mediano)
    df = renombrar_final(df)
    return df


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    for p in (PROC, TRAIN, TEST):
        p.mkdir(parents=True, exist_ok=True)

    df = cargar(CSV_INPUT)

    # 1. Split sobre datos crudos -> evita fuga de datos
    train_raw, test_raw = split_train_test(df)

    # 2. Limpieza inicial (determinista, en ambos conjuntos)
    train = limpiar(train_raw)
    test  = limpiar(test_raw)

    # 3. Imputación: estadísticos aprendidos SOLO de train, aplicados a ambos
    stats = aprender_imputacion(train)
    train = imputar(train, stats)
    test  = imputar(test, stats)

    # 4. Fallback de precio_medio_marca: mediana de precio de train
    precio_mediano = float(train['precio'].median())

    # 5. Resto del pipeline (determinista, en ambos conjuntos)
    train = pipeline_resto(train, precio_mediano)
    test  = pipeline_resto(test, precio_mediano)

    # 6. Reordenar columnas (idéntico orden en train y test)
    train = reordenar(train)
    test  = reordenar(test)[train.columns]

    assert list(train.columns) == list(test.columns), 'Columnas train/test no coinciden'

    # 7. Guardar
    train.to_csv(TRAIN / 'train.csv', index=False)
    test.to_csv(TEST / 'test.csv', index=False)
    pd.concat([train, test], ignore_index=True).to_csv(CSV_OUTPUT, index=False)

    print(f'\nOK train.csv: {train.shape[0]} filas, {train.shape[1]} columnas')
    print(f'OK test.csv:  {test.shape[0]} filas, {test.shape[1]} columnas')
    print(f'OK lentiamo_graduadas_clean.csv: {len(train) + len(test)} filas (referencia)')


if __name__ == '__main__':
    main()
