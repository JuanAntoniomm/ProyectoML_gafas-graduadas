"""Entrena el modelo final de PVP.

    python src/modelado/entrenar.py

Escribe models/modelo_pvp.pkl y models/metricas.json. Las features y el split se
importan de datos.py para que el script y los notebooks no puedan divergir.

El MAE en train (8,8 €) es la mitad que en test (18,9 €): un RandomForest sin
límite de profundidad memoriza el entrenamiento. Acotarlo empeora el test, está
medido abajo.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

sys.path.insert(0, str(Path(__file__).resolve().parent))
from datos import CAT, FEATURES, NUM, RAIZ, SEMILLA, TARGET, cargar, separar  # noqa: E402

SALIDA_MODELO = RAIZ / "models" / "modelo_pvp.pkl"
SALIDA_METRICAS = RAIZ / "models" / "metricas.json"

# Los del notebook 02. Medido sobre este dataset:
#     n=150, por defecto   MAE 18,90   R2 0,850    9,4 MB   <- el que se usa
#     min_samples_leaf=2   MAE 18,79   R2 0,858    6,2 MB
#     max_depth=20         MAE 28,83   R2 0,717    2,8 MB
#     n=300                MAE 18,92   R2 0,850   18,7 MB
# Acotar la profundidad para reducir el pickle sale caro: con 112 marcas en
# one-hot el árbol necesita profundidad para aislar combinaciones de marca.
# min_samples_leaf=2 daría algo mejor, pero no está evaluado en el notebook y
# aquí prioriza reproducirlo.
PARAMS = dict(
    n_estimators=150,
    random_state=SEMILLA,
    n_jobs=-1,
)


def construir_pipeline() -> Pipeline:
    """Preprocesado y modelo en un solo objeto, para que los estadísticos de
    imputación se aprendan solo con train y la app no pueda aplicar una
    transformación distinta a la del entrenamiento."""
    prep = ColumnTransformer([
        ("num", Pipeline([("imp", SimpleImputer(strategy="median"))]), NUM),
        ("cat", Pipeline([
            ("imp", SimpleImputer(strategy="most_frequent")),
            ("oh", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]), CAT),
    ], remainder="drop")
    return Pipeline([("prep", prep), ("modelo", RandomForestRegressor(**PARAMS))])


def metricas(y, pred) -> dict:
    return {
        "MAE_eur": round(float(mean_absolute_error(y, pred)), 2),
        "RMSE_eur": round(float(np.sqrt(mean_squared_error(y, pred))), 2),
        "R2": round(float(r2_score(y, pred)), 4),
        "MAPE_pct": round(float(np.mean(np.abs((y - pred) / y)) * 100), 2),
    }


def main() -> None:
    t0 = time.time()
    d = cargar()
    tr, te = separar(d)
    print(f"Dataset: {len(d)} productos · {d['marca'].nunique()} marcas")
    print(f"  train {len(tr)} · test {len(te)}  (split agrupado por EAN)")

    pipe = construir_pipeline()
    pipe.fit(tr[FEATURES], tr[TARGET])

    m_test = metricas(te[TARGET], pipe.predict(te[FEATURES]))
    m_train = metricas(tr[TARGET], pipe.predict(tr[FEATURES]))
    dummy = DummyRegressor(strategy="mean").fit(tr[FEATURES], tr[TARGET])
    m_dummy = metricas(te[TARGET], dummy.predict(te[FEATURES]))

    SALIDA_MODELO.parent.mkdir(parents=True, exist_ok=True)
    # compress=3 baja el pickle de 60 a 9,4 MB, así que va al repo sin Git LFS y
    # Streamlit Cloud puede desplegarlo.
    joblib.dump(pipe, SALIDA_MODELO, compress=3)
    mb = SALIDA_MODELO.stat().st_size / 1048576

    info = {
        "fecha_entrenamiento": pd.Timestamp.utcnow().isoformat(timespec="seconds"),
        "n_train": len(tr), "n_test": len(te), "n_marcas": int(d["marca"].nunique()),
        "target": TARGET, "features": FEATURES, "hiperparametros": PARAMS,
        "test": m_test, "train": m_train, "baseline_dummy_test": m_dummy,
        "modelo_mb": round(mb, 2),
    }
    SALIDA_METRICAS.write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n{'':22}{'MAE €':>9}{'RMSE €':>9}{'R²':>8}{'MAPE %':>9}")
    for nombre, m in [("test", m_test), ("train", m_train), ("baseline (media)", m_dummy)]:
        print(f"  {nombre:20}{m['MAE_eur']:>9}{m['RMSE_eur']:>9}{m['R2']:>8}{m['MAPE_pct']:>9}")
    print(f"\n  Reduce el error del baseline un "
          f"{100 * (1 - m_test['MAE_eur'] / m_dummy['MAE_eur']):.0f} %")
    print(f"\nGuardado: {SALIDA_MODELO.name} ({mb:.1f} MB) y {SALIDA_METRICAS.name}")
    print(f"Tiempo: {time.time() - t0:.0f}s")

    if m_train["MAE_eur"] * 2.5 < m_test["MAE_eur"]:
        print("\nAVISO: el error en train es mucho menor que en test. Posible "
              "sobreajuste; revisa max_depth y min_samples_leaf.")


if __name__ == "__main__":
    main()
