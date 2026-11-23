"""Build a static Chemsafe release from the prepared dataset and trained models."""

import json
from pathlib import Path
from shutil import copytree

import joblib
import pandas as pd

from prepare_data import REQUIRED_COLUMNS, SPLITS
from safechem_data import REVISION, dataset_revision

ROOT = Path(__file__).resolve().parent
PUBLISH = ROOT / "netlify-dist"
FIELDS = [
    "primary_name", "cas_number", "iupac_name", "molecular_formula", "molecular_weight",
    "flammable_liquids", "flammable_solids", "flash_point", "boiling_point", "cid",
    "canonical_smiles", "inchi_key", "xlogp", "tpsa", "dataset_split",
    "liquid_prediction", "liquid_score",
]


def main():
    frames = []
    for split in SPLITS:
        path = ROOT / "data" / f"safechem_{split}.csv"
        if dataset_revision(split, path.read_bytes()) != REVISION:
            raise ValueError(f"{path.name} does not match the pinned SafeChem revision")
        frame = pd.read_csv(path, low_memory=False, dtype={"cas_number": str})
        missing = REQUIRED_COLUMNS - set(frame)
        if missing:
            raise ValueError(f"{path.name} is missing {sorted(missing)}")
        frame["dataset_split"] = split
        frames.append(frame)

    records = pd.concat(frames, ignore_index=True)
    models = ROOT / "models"
    model = joblib.load(models / "flammable_liquids.joblib")
    features = records[list(model.feature_names_in_)].apply(pd.to_numeric, errors="coerce")
    classes = list(model.named_steps["classifier"].classes_)
    probabilities = model.predict_proba(features)
    records["liquid_prediction"] = model.predict(features)
    records["liquid_score"] = probabilities[:, classes.index(1)].round(6)

    copytree(ROOT / "site", PUBLISH, dirs_exist_ok=True)
    data = {
        "revision": REVISION,
        "fields": FIELDS,
        "rows": json.loads(records.reindex(columns=FIELDS).to_json(orient="values")),
        "metrics": json.loads((models / "metrics.json").read_text(encoding="utf-8")),
    }
    (PUBLISH / "catalog.json").write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False),
        encoding="utf-8",
    )
    print(f"Published {len(records):,} SafeChem records to {PUBLISH.name}/")


if __name__ == "__main__":
    main()
