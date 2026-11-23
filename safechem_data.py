"""Shared SafeChem identifiers and dataset provenance."""

import hashlib
import re

REVISION = "43fa095c6020ad0a34f2c34301e83b29aa11ce05"
SPLIT_SHA256 = {
    "train": "8ae696947780ac44f4e421e9adc28bc21289666a496400d7532531cf2dc9a589",
    "validation": "47fc1794801dfad138ab7d285b6e0475b2589b666079fad2ac2bc003ee7964f1",
    "test": "abfc2f14503e7c91182d38032e67031a314a64b55d5a9fabfdacc33ccc88c190",
}
CAS_PATTERN = re.compile(r"([0-9]{2,})\s*-\s*([0-9]{2})\s*-\s*([0-9])")


def normalize_cas(value):
    value = value.strip()
    match = CAS_PATTERN.fullmatch(value)
    if match is None:
        return value.casefold()
    first, middle, check = match.groups()
    first = first.lstrip("0").zfill(2)
    return f"{first}-{middle}-{check}"


def dataset_revision(split, contents):
    if hashlib.sha256(contents).hexdigest() == SPLIT_SHA256[split]:
        return REVISION
    return "Unverified"
