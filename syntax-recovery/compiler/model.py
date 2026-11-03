"""Isolation Forest model for ranking grammar-valid recovery candidates."""
import os

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn import __version__ as SKLEARN_VERSION

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(HERE, "..", "data", "isolation_forest.joblib")
BEFORE = 2
AFTER = 2
BOS, EOS, UNKNOWN = "<BOS>", "<EOS>", "<UNKNOWN>"
EXTRA_VOCAB = ["[", "]", ","]
N_ESTIMATORS = 100
RANDOM_STATE = 23


def abstract(token):
    """Convert lexer tokens to stable token classes for model features."""
    token_type = token if isinstance(token, str) else token.type
    return {"id": "ID", "num": "NUM", "$": EOS}.get(token_type, token_type)


class IsolationForestModel:
    def __init__(self, estimator, vocab, meta=None):
        self.estimator = estimator
        self.vocab = tuple(sorted(set(vocab) | {BOS, EOS, UNKNOWN}))
        self.vocab_indices = {token: index for index, token in enumerate(self.vocab)}
        self.meta = meta or {}

    @classmethod
    def train(cls, sequences, vocab, meta=None):
        """Fit on fixed-width token windows sampled only from valid programs."""
        vocab = set(vocab) | {BOS, EOS, UNKNOWN}
        vocab_indices = {token: index for index, token in enumerate(sorted(vocab))}
        features = []
        for sequence in sequences:
            tokens = [abstract(token) for token in sequence]
            padded = [BOS] * BEFORE + tokens + [EOS] * AFTER
            for center in range(BEFORE, BEFORE + len(tokens)):
                features.append(_feature_vector(padded, center, vocab_indices))
        if not features:
            raise ValueError("Cannot train the recovery model without token windows.")

        matrix = np.asarray(features, dtype=np.float32)
        estimator = IsolationForest(
            n_estimators=N_ESTIMATORS,
            max_samples=min(256, len(matrix)),
            contamination="auto",
            random_state=RANDOM_STATE,
            n_jobs=-1,
        )
        estimator.fit(matrix)
        model_meta = dict(meta or {})
        model_meta.update(
            programs=model_meta.get("train_programs", len(sequences)),
            training_windows=len(matrix),
            n_estimators=N_ESTIMATORS,
            feature_width=BEFORE + AFTER + 1,
            sklearn_version=SKLEARN_VERSION,
        )
        return cls(estimator, vocab, model_meta)

    def anomaly_score(self, tokens, index):
        """Return a higher-is-more-anomalous Isolation Forest score."""
        values = [BOS] * BEFORE + [abstract(token) for token in tokens] + [EOS] * AFTER
        center = max(BEFORE, min(index + BEFORE, len(values) - AFTER - 1))
        features = _feature_vector(values, center, self.vocab_indices)
        normality = float(self.estimator.decision_function([features])[0])
        return -normality

    def summary(self):
        return {
            "algorithm": "Isolation Forest",
            "programs": self.meta.get("programs", 0),
            "training_windows": self.meta.get("training_windows", 0),
            "feature_width": self.meta.get("feature_width", BEFORE + AFTER + 1),
            "features": len(self.vocab) * (BEFORE + AFTER + 1),
            "n_estimators": self.meta.get("n_estimators", N_ESTIMATORS),
            "random_state": RANDOM_STATE,
            "scikit_learn": self.meta.get("sklearn_version", "unknown"),
            "meta": self.meta,
        }


def _feature_vector(tokens, center, vocab_indices):
    width = BEFORE + AFTER + 1
    vector = [0.0] * (len(vocab_indices) * width)
    for slot, offset in enumerate(range(-BEFORE, AFTER + 1)):
        token = tokens[center + offset]
        token_index = vocab_indices.get(token, vocab_indices[UNKNOWN])
        vector[slot * len(vocab_indices) + token_index] = 1.0
    return vector


def save_model(model, path=MODEL_PATH):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    joblib.dump(model, path)


def load_model(path=MODEL_PATH):
    model = joblib.load(path)
    if not isinstance(model, IsolationForestModel):
        raise TypeError(f"Expected an IsolationForestModel in {path}.")
    trained_with = model.meta.get("sklearn_version")
    if trained_with != SKLEARN_VERSION:
        raise RuntimeError(
            f"The model was trained with scikit-learn {trained_with}; "
            f"the installed version is {SKLEARN_VERSION}. Retrain with python -m compiler.train."
        )
    return model
