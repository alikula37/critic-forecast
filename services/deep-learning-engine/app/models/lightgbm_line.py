import numpy as np
from lightgbm import LGBMClassifier, LGBMRegressor
from sklearn.multioutput import MultiOutputRegressor

from .. import config


def _quantile_model(alpha, n_estimators=160):
    return LGBMRegressor(
        objective="quantile",
        alpha=alpha,
        n_estimators=n_estimators,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_lambda=1.0,
        random_state=config.SEED,
        n_jobs=1,
        verbose=-1,
    )


def train_lightgbm_core(X_train, Y_train, n_estimators=160):
    models = {}
    for key, alpha in (("p10", 0.10), ("p50", 0.50), ("p90", 0.90)):
        models[key] = MultiOutputRegressor(_quantile_model(alpha, n_estimators), n_jobs=1)
        models[key].fit(X_train, Y_train)
    return models


def train_direction_classifier(X_train, Y_train_final):
    labels = np.where(np.asarray(Y_train_final) > 0, 1, 0)
    clf = LGBMClassifier(
        n_estimators=180,
        max_depth=5,
        learning_rate=0.06,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=config.SEED,
        n_jobs=-1,
        verbose=-1,
    )
    clf.fit(X_train, labels)
    return clf


def feature_importances(models):
    est = models["p50"].estimators_[0]
    from ..training.dataset import FEATURE_NAMES

    imp = est.feature_importances_
    idx = np.argsort(imp)[::-1][:8]
    return [{"feature": FEATURE_NAMES[i], "importance": float(imp[i])} for i in idx]
