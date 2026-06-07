"""
training.py
===========

Entrena el modelo final (RandomForest) sobre el conjunto de entrenamiento ya
procesado y lo guarda en `models/final_model.pkl`.

IMPORTANTE — sobre el split:
    El train/test split YA está hecho por `src/data_processing.py` (o por el
    notebook 02), sobre los datos CRUDOS y antes de cualquier imputación, para
    evitar fuga de datos. Por eso aquí NO se vuelve a partir el dataset: solo
    se carga `data/train/train.csv` y se entrena. La evaluación contra
    `data/test/test.csv` la hace `src/evaluation.py`.

Replica la lógica de `notebooks/03_Modelado.ipynb` con las decisiones tomadas
tras el análisis de ablaciones y VIF:

- Familia ganadora: árboles (RandomForestRegressor).
- Target: precio en € (los árboles no necesitan log).
- Features finales (5 numéricas + 10-13 categóricas según disponibilidad):
    Numéricas: ancho_lente, ancho_puente, largo_varilla, peso, precio_medio_marca.
    Categóricas: marca, genero, material_montura, forma, tipo_montura, color, talla,
                 gama_marca, segmento_comercial, pais_origen,
                 (+ categoria_material, gama_material, peso_relativo si existen).
- Hiperparámetros optimizados con GridSearchCV (5-fold).
- Métrica de selección: MAE (interpretable en € para negocio).

Uso:
    python src/training.py

Inputs:
    data/train/train.csv      (generado por src/data_processing.py)

Outputs:
    models/final_model.pkl
"""

from pathlib import Path

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.model_selection import GridSearchCV, KFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
TRAIN = ROOT / 'data' / 'train'
MODELS_DIR = ROOT / 'models'

CSV_TRAIN = TRAIN / 'train.csv'
MODEL_OUTPUT = MODELS_DIR / 'final_model.pkl'

RANDOM_STATE = 42
CV_SPLITS = 5

# Features finales (justificación en notebook 03 sec. 7-9)
NUM_FINAL = [
    'ancho_lente',
    'ancho_puente',
    'largo_varilla',
    'peso',
    'precio_medio_marca',
]
CAT_FINAL = [
    'marca', 'genero', 'material_montura', 'forma', 'tipo_montura',
    'color', 'talla',
    'gama_marca', 'segmento_comercial', 'pais_origen',
    'categoria_material', 'gama_material', 'peso_relativo',  # opcionales
]

PARAM_GRID = {
    'm__n_estimators':     [200, 400],
    'm__max_depth':        [None, 15, 25],
    'm__min_samples_leaf': [1, 3],
    'm__max_features':     ['sqrt', 0.5],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def existing(cols, df):
    """Devuelve solo las columnas que existen realmente en df."""
    return [c for c in cols if c in df.columns]


def build_preprocessor(num_cols, cat_cols):
    """ColumnTransformer para árboles: imputación + OneHot (sin escalar numéricas)."""
    num_pipe = Pipeline([('imputer', SimpleImputer(strategy='median'))])
    cat_pipe = Pipeline([
        ('imputer', SimpleImputer(strategy='most_frequent')),
        ('onehot',  OneHotEncoder(handle_unknown='ignore', sparse_output=False)),
    ])
    return ColumnTransformer(
        [('num', num_pipe, num_cols), ('cat', cat_pipe, cat_cols)],
        remainder='drop',
        verbose_feature_names_out=False,
    )


def cargar_train(path: Path) -> pd.DataFrame:
    """Carga train.csv (ya procesado) con renombre defensivo por compatibilidad."""
    df = pd.read_csv(path)
    rename_map = {'tier': 'gama_marca', 'segmento': 'segmento_comercial'}
    df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns}, inplace=True)
    print(f'Cargado: {path.name} -> {df.shape}')
    return df


def entrenar_con_gridsearch(X_train: pd.DataFrame, y_train: pd.Series,
                            num_cols: list, cat_cols: list) -> GridSearchCV:
    pipe = Pipeline([
        ('prep', build_preprocessor(num_cols, cat_cols)),
        ('m',    RandomForestRegressor(random_state=RANDOM_STATE, n_jobs=-1)),
    ])
    cv = KFold(n_splits=CV_SPLITS, shuffle=True, random_state=RANDOM_STATE)
    gs = GridSearchCV(
        pipe,
        param_grid=PARAM_GRID,
        cv=cv,
        scoring='neg_mean_absolute_error',
        n_jobs=-1,
        verbose=1,
    )
    print('\nLanzando GridSearchCV (RandomForest)...')
    gs.fit(X_train, y_train)
    print('\nMejores hiperparámetros:')
    for k, v in gs.best_params_.items():
        print(f'  - {k}: {v}')
    print(f'MAE en CV (mejor): {-gs.best_score_:.2f} €')
    return gs


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    if not CSV_TRAIN.exists():
        raise FileNotFoundError(
            f'Falta {CSV_TRAIN}. Ejecuta antes `python src/data_processing.py`.')

    train_df = cargar_train(CSV_TRAIN)

    num_cols = existing(NUM_FINAL, train_df)
    cat_cols = existing(CAT_FINAL, train_df)
    print(f'\nFeatures usadas:')
    print(f'  num ({len(num_cols)}): {num_cols}')
    print(f'  cat ({len(cat_cols)}): {cat_cols}')

    X_train = train_df[num_cols + cat_cols]
    y_train = train_df['precio']

    gs = entrenar_con_gridsearch(X_train, y_train, num_cols, cat_cols)

    joblib.dump(gs.best_estimator_, MODEL_OUTPUT)
    print(f'\nModelo guardado: {MODEL_OUTPUT}')


if __name__ == '__main__':
    main()
