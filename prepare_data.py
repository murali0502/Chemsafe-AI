"""Download and validate the pinned SafeChem CSV splits."""

import csv
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from urllib.request import urlopen

from safechem_data import REVISION

DATA = Path(__file__).resolve().parent / "data"
SOURCE = f"https://huggingface.co/datasets/Anonymous-07/SafeChem/resolve/{REVISION}"
SPLITS = {"train": "split_train.csv", "validation": "split_val.csv", "test": "split_test.csv"}
REQUIRED_COLUMNS = {
    "primary_name",
    "cas_number",
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
    "flammable_liquids",
    "flammable_solids",
}


def validate_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.reader(source, strict=True)
        header = next(reader, [])
        missing = REQUIRED_COLUMNS.difference(header)
        if missing:
            raise ValueError(f"{path.name}: missing columns: {', '.join(sorted(missing))}")
        if len(header) != len(set(header)):
            raise ValueError(f"{path.name}: duplicate column names")

        count = 0
        for row in reader:
            if not row:
                continue
            if len(row) != len(header):
                raise ValueError(f"{path.name}: unexpected field count at line {reader.line_num}")
            count += 1

        if count == 0:
            raise ValueError(f"{path.name}: no data rows")
        return count


def main():
    DATA.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix=".safechem-", dir=DATA) as temporary:
        staged = {}
        for split, filename in SPLITS.items():
            path = Path(temporary) / f"safechem_{split}.csv"
            with urlopen(f"{SOURCE}/{filename}", timeout=60) as response, path.open("wb") as output:
                shutil.copyfileobj(response, output)
            staged[path] = validate_csv(path)

        for path, count in staged.items():
            path.replace(DATA / path.name)
            print(f"data/{path.name}: {count:,} rows")


if __name__ == "__main__":
    main()
