"""
evaluation.py
=============

Evalúa el modelo final entrenado contra el test set y reporta métricas en
unidades de negocio (€).

Replica la lógica de la sección de evaluación de `notebooks/03_Modelado.ipynb`:
- Carga `models/final_model.pkl`.
- Carga `data/test/test.csv`.
- Detecta automáticamente las features que usa el modelo (las inferimos del
  ColumnTransformer guardado dentro del Pipeline).
- Calcula MAE, RMSE, R² y MAPE en €.
- Lista los 10 productos donde el modelo más se equivoca (revisión cualitativa).

Uso:
    python src/evaluation.py

Inputs:
    data/test/test.csv
    models/final_model.pkl

Output:
    Métricas y top de errores por stdout.
"""

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
TEST = ROOT / 'data' / 'test'
MODELS_DIR = ROOT / 'models'

CSV_TEST = TEST / 'test.csv'
MODEL_PATH = MODELS_DIR / 'final_model.pkl'


# ---------------------------------------------------------------------------
# Métricas
# ---------------------------------------------------------------------------
def rmse(y_true, y_pred) -> float:
    return float(np.sqrt(mean_squared_error(y_true, y_pred)))


def mape(y_true, y_pred, eps: float = 1e-9) -> float:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    return float(np.mean(np.abs((y_true - y_pred) / np.maximum(np.abs(y_true), eps))) * 100)


def calcular_metricas(y_true, y_pred) -> dict:
    return {
        'MAE_€':  float(mean_absolute_error(y_true, y_pred)),
        'RMSE_€': rmse(y_true, y_pred),
        'R²':     float(r2_score(y_true, y_pred)),
        'MAPE_%': mape(y_true, y_pred),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def features_del_modelo(model) -> list:
    """Recupera las columnas esperadas a partir del ColumnTransformer guardado."""
    prep = model.named_steps['prep']
    cols = []
    for name, _, c in prep.transformers_:
        if name != 'remainder':
            cols.extend(c)
    return cols


def top_errores(test_df: pd.DataFrame, y_pred: np.ndarray, n: int = 10) -> pd.DataFrame:
    """Top n productos donde el modelo más se equivoca (revisión cualitativa)."""
    df = test_df.copy()
    df['pred']      = y_pred
    df['error']     = df['precio'] - df['pred']
    df['error_abs'] = df['error'].abs()
    cols_show = [c for c in ('marca', 'modelo', 'gama_marca', 'precio', 'pred', 'error')
                 if c in df.columns]
    return df.nlargest(n, 'error_abs')[cols_show].round(2)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f'Falta el modelo: {MODEL_PATH}. Ejecuta antes `python src/training.py`.')
    if not CSV_TEST.exists():
        raise FileNotFoundError(f'Falta el test: {CSV_TEST}. Ejecuta antes `python src/training.py`.')

    test_df = pd.read_csv(CSV_TEST)
    print(f'test: {test_df.shape}')

    model = joblib.load(MODEL_PATH)
    estimador = model.named_steps['m']
    print(f'Modelo: {type(estimador).__name__}')

    features = features_del_modelo(model)
    X_test = test_df[features]
    y_test = test_df['precio']
    y_pred = model.predict(X_test)

    metricas = calcular_metricas(y_test, y_pred)
    print('\n=== Métricas en test (€) ===')
    print(f'  MAE   : {metricas["MAE_€"]:>7.2f} €')
    print(f'  RMSE  : {metricas["RMSE_€"]:>7.2f} €')
    print(f'  R²    : {metricas["R²"]:>7.3f}')
    print(f'  MAPE  : {metricas["MAPE_%"]:>7.2f} %')

    print('\n=== Top 10 errores absolutos (revisión cualitativa) ===')
    print(top_errores(test_df, y_pred, n=10).to_string(index=False))

    # Devolver dict por si se usa programáticamente
    return metricas


if __name__ == '__main__':
    main()
