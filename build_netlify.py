"""Build a static Chemsafe release from the prepared dataset and trained models."""

from datetime import date
import json
import re
from pathlib import Path
from shutil import copyfile, copytree
from urllib.parse import urlsplit

import joblib
import pandas as pd

from prepare_data import REQUIRED_COLUMNS, SPLITS
from safechem_data import REVISION, dataset_revision, normalize_cas

ROOT = Path(__file__).resolve().parent
PUBLISH = ROOT / "netlify-dist"
FIELDS = [
    "primary_name", "cas_number", "iupac_name", "molecular_formula", "molecular_weight",
    "flammable_liquids", "flammable_solids", "flash_point", "boiling_point", "cid",
    "canonical_smiles", "inchi_key", "xlogp", "tpsa", "dataset_split",
    "liquid_prediction", "liquid_score",
]


def load_sds_catalog():
    path = ROOT / "sds_catalog.json"
    entries = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(entries, list):
        raise ValueError("sds_catalog.json must contain an array of product entries")

    required = ("cas_number", "manufacturer", "product_name", "revision_date", "sds_url")
    catalog = {}
    for index, item in enumerate(entries, start=1):
        entry = f"SDS catalog entry {index}"
        if not isinstance(item, dict) or any(
            not isinstance(item.get(key), str) or not item[key].strip() for key in required
        ):
            raise ValueError(f"{entry} requires nonempty string fields: {', '.join(required)}")
        product_code = item.get("product_code", "")
        if not isinstance(product_code, str):
            raise ValueError(f"{entry} product_code must be a string")

        cas = normalize_cas(item["cas_number"])
        match = re.fullmatch(r"([0-9]{2,7})-([0-9]{2})-([0-9])", cas)
        if not match or int(match[1]) == 0:
            raise ValueError(f"{entry} has an invalid CAS number")
        digits = match[1] + match[2]
        checksum = sum(int(digit) * weight for weight, digit in enumerate(reversed(digits), 1))
        if checksum % 10 != int(match[3]):
            raise ValueError(f"{entry} has an invalid CAS check digit")

        revision = item["revision_date"].strip()
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", revision):
            raise ValueError(f"{entry} revision_date must use YYYY-MM-DD")
        if date.fromisoformat(revision) > date.today():
            raise ValueError(f"{entry} revision_date cannot be in the future")
        url = urlsplit(item["sds_url"].strip())
        if url.scheme != "https" or not url.hostname or url.username or url.password:
            raise ValueError(f"{entry} sds_url must be an HTTPS link without credentials")

        row = {key: item[key].strip() for key in required if key != "cas_number"}
        row["product_code"] = product_code.strip()
        products = catalog.setdefault(cas, [])
        if row not in products:
            products.append(row)

    for products in catalog.values():
        products.sort(key=lambda item: item["revision_date"], reverse=True)
    return catalog


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

    sds_catalog = load_sds_catalog()
    copytree(ROOT / "site", PUBLISH, dirs_exist_ok=True)
    vendor = PUBLISH / "vendor"
    vendor.mkdir(exist_ok=True)
    package = ROOT / "node_modules" / "jspdf"
    copyfile(package / "dist" / "jspdf.umd.min.js", vendor / "jspdf.umd.min.js")
    copyfile(package / "LICENSE", vendor / "LICENSE-jspdf.txt")
    data = {
        "sds_catalog": sds_catalog,
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
