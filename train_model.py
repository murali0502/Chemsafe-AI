from itertools import combinations
from pathlib import Path
import json

import joblib
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.pipeline import Pipeline

from safechem_data import normalize_cas

DATA = Path("data")
OUT = Path("models")
OUT.mkdir(exist_ok=True)

FEATURES = [
    "molecular_weight",
    "exact_mass",
    "xlogp",
    "tpsa",
    "complexity",
    "charge",
    "h_bond_donor_count",
    "h_bond_acceptor_count",
    "rotatable_bond_count",
    "heavy_atom_count",
]

TARGETS = [
    "flammable_liquids",
    "flammable_solids",
]


def read_split(name):
    path = DATA / f"safechem_{name}.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing dataset: {path}")
    return pd.read_csv(path, low_memory=False, dtype={"cas_number": str})


def identifier_sets(frame):
    identifiers = {}
    for column in ("cas_number", "inchi_key"):
        if column in frame:
            values = frame[column].dropna().astype(str)
            normalize = normalize_cas if column == "cas_number" else lambda value: value.strip().casefold()
            identifiers[column] = set(values.map(normalize)) - {"", "na", "nan", "none", "null", "unknown"}
    return identifiers


def class_counts(frame, target):
    labels = pd.to_numeric(frame[target], errors="coerce")
    negative = int(labels.eq(0).sum())
    positive = int(labels.eq(1).sum())
    return {"negative": negative, "positive": positive, "excluded": len(frame) - negative - positive}


train = read_split("train")
test = read_split("test")
splits = {"train": train, "test": test}
if (DATA / "safechem_validation.csv").exists():
    splits["validation"] = read_split("validation")

for name, frame in splits.items():
    missing = set(FEATURES + TARGETS) - set(frame.columns)
    if missing:
        raise ValueError(f"{name}: missing required columns: {sorted(missing)}")

identifiers = {name: identifier_sets(frame) for name, frame in splits.items()}
overlap = []
for first, second in combinations(identifiers, 2):
    counts = {}
    for column in ("cas_number", "inchi_key"):
        counts[column] = (
            len(identifiers[first][column] & identifiers[second][column])
            if column in identifiers[first] and column in identifiers[second]
            else None
        )
    overlap.append({"splits": [first, second], **counts})
    print(f"Shared identifiers ({first}, {second}): {counts}")

results = {"split_overlap": overlap}


for target in TARGETS:
    print(f"\n{'=' * 60}\nTraining target: {target}")

    train_labels = pd.to_numeric(train[target], errors="coerce")
    test_labels = pd.to_numeric(test[target], errors="coerce")

    train_mask = train_labels.isin([0, 1])
    test_mask = test_labels.isin([0, 1])

    X_train = train.loc[train_mask, FEATURES].apply(
        pd.to_numeric, errors="coerce"
    )
    y_train = train_labels.loc[train_mask].astype(int)

    X_test = test.loc[test_mask, FEATURES].apply(
        pd.to_numeric, errors="coerce"
    )
    y_test = test_labels.loc[test_mask].astype(int)

    if y_train.nunique() != 2:
        raise ValueError(f"{target} must have both classes in training data.")
    if y_test.nunique() != 2:
        raise ValueError(f"{target} must have both classes in test data to report balanced accuracy.")

    model = Pipeline([
        ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
        ("classifier", RandomForestClassifier(
            n_estimators=160,
            min_samples_leaf=2,
            class_weight="balanced",
            random_state=42,
            n_jobs=-1,
        )),
    ])

    model.fit(X_train, y_train)
    predictions = model.predict(X_test)
    baseline = DummyClassifier(strategy="most_frequent")
    baseline.fit(X_train, y_train)
    baseline_predictions = baseline.predict(X_test)

    metrics = {
        "class_counts": {
            name: class_counts(frame, target) for name, frame in splits.items()
        },
        "majority_baseline": {
            "test_accuracy": float(accuracy_score(y_test, baseline_predictions)),
            "test_balanced_accuracy": float(balanced_accuracy_score(y_test, baseline_predictions)),
            "positive_recall": float(recall_score(y_test, baseline_predictions, zero_division=0)),
            "positive_f1": float(f1_score(y_test, baseline_predictions, zero_division=0)),
        },
        "train_rows": int(len(y_train)),
        "test_rows": int(len(y_test)),
        "test_accuracy": float(accuracy_score(y_test, predictions)),
        "test_balanced_accuracy": float(
            balanced_accuracy_score(y_test, predictions)
        ),
        "positive_precision": float(
            precision_score(y_test, predictions, zero_division=0)
        ),
        "positive_recall": float(
            recall_score(y_test, predictions, zero_division=0)
        ),
        "positive_f1": float(
            f1_score(y_test, predictions, zero_division=0)
        ),
        "confusion_matrix_labels_0_1": confusion_matrix(
            y_test, predictions, labels=[0, 1]
        ).tolist(),
        "classification_report": classification_report(
            y_test,
            predictions,
            labels=[0, 1],
            target_names=["label_0", "label_1"],
            zero_division=0,
            output_dict=True,
        ),
        "features": FEATURES,
        "target": target,
    }

    joblib.dump(model, OUT / f"{target}.joblib")
    results[target] = metrics

    print(f"Class counts: {metrics['class_counts']}")
    print(f"Majority baseline: {metrics['majority_baseline']}")
    print(f"Training records: {len(y_train):,}")
    print(f"Test records: {len(y_test):,}")
    print(f"Accuracy: {metrics['test_accuracy']:.3f}")
    print(f"Balanced accuracy: {metrics['test_balanced_accuracy']:.3f}")
    print(f"Positive precision: {metrics['positive_precision']:.3f}")
    print(f"Positive recall: {metrics['positive_recall']:.3f}")
    print(f"Positive F1: {metrics['positive_f1']:.3f}")
    print("Confusion matrix [[TN, FP], [FN, TP]]:")
    print(metrics["confusion_matrix_labels_0_1"])

with open(OUT / "metrics.json", "w") as file:
    json.dump(results, file, indent=2)

print("\nModels and evaluation metrics saved to models/")
