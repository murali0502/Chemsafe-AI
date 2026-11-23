from io import BytesIO
from pathlib import Path
import json

import joblib
import pandas as pd
import streamlit as st

from safechem_data import REVISION, dataset_revision, normalize_cas

st.set_page_config(
    page_title="Chemsafe AI",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded",
)

DATA = Path("data")
MODELS = Path("models")

FEATURES = [
    "molecular_weight", "exact_mass", "xlogp", "tpsa",
    "complexity", "charge", "h_bond_donor_count",
    "h_bond_acceptor_count", "rotatable_bond_count",
    "heavy_atom_count",
]

TARGETS = {
    "flammable_liquids": "Flammable liquids",
    "flammable_solids": "Flammable solids",
}


SAFETY_NOTICE = (
    "Research prototype only. Dataset labels and ML predictions are not "
    "certified safety determinations. Verify the exact substance or product "
    "against its current Safety Data Sheet (SDS)."
)
ZERO_LABEL_NOTICE = "A zero label is not proof of universal nonflammability."
SCORE_NOTICE = "Model output is not a calibrated probability of real-world flammability."
CONFLICT_NOTICE = (
    "SafeChem records with this name and CAS identifier disagree on the recorded hazard labels."
)
ZERO_RECALL_NOTICE = "This model detected zero positive labels in its test evaluation."
SOLIDS_NOTICE = (
    "The solids prediction is withheld because the model missed all positive test labels. "
    "See Model performance for the evaluation."
)


@st.cache_data
def load_data(file_versions):
    frames = []
    for split, path, _mtime in file_versions:
        contents = path.read_bytes()
        part = pd.read_csv(BytesIO(contents), low_memory=False, dtype={"cas_number": str})
        part["dataset_split"] = split
        part["dataset_revision"] = dataset_revision(split, contents)
        frames.append(part)

    if not frames:
        raise FileNotFoundError("No SafeChem CSV files found in data/")

    result = pd.concat(frames, ignore_index=True)
    result["primary_name"] = result["primary_name"].fillna("").astype(str)
    result["cas_number"] = result["cas_number"].fillna("").astype(str)
    result["_name"] = result["primary_name"].str.strip().str.casefold()
    if "iupac_name" in result:
        result["_iupac"] = result["iupac_name"].fillna("").astype(str).str.strip().str.casefold()
    else:
        result["_iupac"] = ""
    result["_cas"] = result["cas_number"].map(normalize_cas)
    return result


@st.cache_resource
def load_liquids_model(path, modified_ns):
    return joblib.load(path)


@st.cache_data
def load_metrics(path, modified_ns):
    with path.open() as file:
        return json.load(file)


def available(value):
    return pd.notna(value) and str(value).strip().casefold() not in {
        "", "nan", "none", "null"
    }


def recorded_label(value):
    if not available(value):
        return "Unknown — missing label"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "Unknown — unrecognized label"
    if number == 1:
        return "Positive hazard label recorded"
    if number == 0:
        return "No positive label recorded for this category"
    return "Unknown — unrecognized label"


def predict_liquids(record, model):
    features = pd.DataFrame(
        [[pd.to_numeric(record.get(feature), errors="coerce") for feature in FEATURES]],
        columns=FEATURES,
    )
    prediction = int(model.predict(features)[0])
    scores = model.predict_proba(features)[0]
    classes = list(model.named_steps["classifier"].classes_)
    positive_score = float(scores[classes.index(1)]) if 1 in classes else None
    return prediction, positive_score


st.title("🧪 Chemsafe AI")
st.caption("Chemical Flammability Intelligence Platform")

st.warning(SAFETY_NOTICE)

try:
    file_versions = []
    for split in ("train", "validation", "test"):
        path = DATA / f"safechem_{split}.csv"
        if path.exists():
            file_versions.append((split, path, path.stat().st_mtime_ns))
    df = load_data(file_versions)
except Exception as exc:
    st.error(f"Dataset loading failed: {exc}")
    st.stop()

liquids_path = (MODELS / "flammable_liquids.joblib").resolve()
liquids_model = (
    load_liquids_model(liquids_path, liquids_path.stat().st_mtime_ns)
    if liquids_path.is_file()
    else None
)
metrics_path = (MODELS / "metrics.json").resolve()
metrics = (
    load_metrics(metrics_path, metrics_path.stat().st_mtime_ns)
    if metrics_path.is_file()
    else {}
)

with st.sidebar:
    st.header("Project overview")
    st.metric("Loaded records", f"{len(df):,}")
    st.metric("Unique CAS identifiers", f"{df.loc[df['_cas'] != '', '_cas'].nunique():,}")
    st.caption("Dataset: Anonymous-07/SafeChem")

    page = st.radio(
        "Navigation",
        ["Chemical assessment", "Model performance", "Dataset explorer"],
    )

if page == "Chemical assessment":
    st.header("Search a chemical")

    query = st.text_input(
        "Chemical name, IUPAC name, or CAS number",
        placeholder="e.g. ethanol or 64-17-5",
    )

    if query.strip():
        term = query.strip().casefold()
        cas_term = normalize_cas(term)
        exact = df["_name"].eq(term) | df["_iupac"].eq(term) | df["_cas"].eq(cas_term)
        if exact.any():
            # Include companion rows even when only one carries the matched IUPAC name.
            matching_keys = pd.MultiIndex.from_frame(df.loc[exact, ["_name", "_cas"]])
            records = pd.MultiIndex.from_frame(df[["_name", "_cas"]])
            results = df[records.isin(matching_keys)]
        else:
            results = df[
                df["_name"].str.contains(term, regex=False, na=False)
                | df["_iupac"].str.contains(term, regex=False, na=False)
                | df["_cas"].str.contains(cas_term, regex=False, na=False)
                | df["cas_number"].str.contains(term, case=False, regex=False, na=False)
            ]

        if results.empty:
            st.error("No matching record found in SafeChem.")
            st.info(
                "No match does not mean nonflammable. Check spelling, CAS "
                "number, or the product's SDS."
            )
        else:
            groups = results.groupby(["_name", "_cas"], sort=False).indices
            selection = st.selectbox(
                "Select the intended record",
                list(groups),
                format_func=lambda key: (
                    f"{results.iloc[groups[key][0]]['primary_name']} | "
                    f"CAS: {results.iloc[groups[key][0]]['cas_number']}"
                ),
            )
            matches = results.iloc[groups[selection]]
            label_summaries = matches.reindex(columns=list(TARGETS)).apply(
                lambda column: column.map(recorded_label)
            )
            conflicting_labels = len(label_summaries.drop_duplicates()) > 1
            record = matches.iloc[0]
            if conflicting_labels:
                st.warning(CONFLICT_NOTICE)
                choices = {
                    index: f"Record {number} ({matches.loc[index, 'dataset_split']}) | "
                    + " | ".join(
                        f"{name}: {label_summaries.loc[index, target]}"
                        for target, name in TARGETS.items()
                    )
                    for number, index in enumerate(matches.index, start=1)
                }
                index = st.selectbox("Choose a source record", list(choices), format_func=choices.get)
                record = matches.loc[index]

            st.subheader(record["primary_name"])
            c1, c2, c3 = st.columns(3)
            c1.metric("CAS number", record["cas_number"] or "Unavailable")
            c2.metric(
                "Formula",
                str(record.get("molecular_formula"))
                if available(record.get("molecular_formula"))
                else "Unavailable",
            )
            c3.metric(
                "Molecular weight",
                str(record.get("molecular_weight"))
                if available(record.get("molecular_weight"))
                else "Unavailable",
            )

            if available(record.get("iupac_name")):
                st.write(f"**IUPAC name** · {record['iupac_name']}")
            if not st.checkbox(
                "I confirm this is the intended substance record",
                key=f"confirm_{term}_{record.name}_{file_versions}",
            ):
                st.stop()

            st.subheader("Recorded SafeChem labels")
            split = record["dataset_split"]
            if record["dataset_revision"] == REVISION:
                source_url = f"https://huggingface.co/datasets/Anonymous-07/SafeChem/tree/{REVISION}"
                st.caption(f"Source · [SafeChem]({source_url}) · {split} split")
            else:
                st.caption(f"Source · Local {split} CSV · Dataset revision unverified")
            for target, label in TARGETS.items():
                value = record.get(target)
                status = recorded_label(value)
                st.write(f"**{label}:** {status}")

            st.caption(ZERO_LABEL_NOTICE)

            st.subheader("Machine-learning predictions")
            st.info(SOLIDS_NOTICE)
            if liquids_model is None:
                st.info("Run `python train_model.py` to enable the liquids prediction.")
            else:
                prediction, positive_score = predict_liquids(record, liquids_model)
                st.markdown("**Flammable liquids**")
                if prediction == 1:
                    st.error("Model predicts positive label")
                else:
                    st.info("Model predicts negative label")
                if positive_score is not None:
                    st.write(f"Model positive-class score · {positive_score:.1%}")
                st.caption(SCORE_NOTICE)
                if metrics.get("flammable_liquids", {}).get("positive_recall") == 0:
                    st.warning(ZERO_RECALL_NOTICE)

            st.subheader("Available properties")
            properties = [
                ("flash_point", "Flash point (source text)"),
                ("boiling_point", "Boiling point (source text)"),
                ("canonical_smiles", "Canonical SMILES"),
                ("inchi_key", "InChI Key"),
                ("xlogp", "XLogP"),
                ("tpsa", "TPSA"),
            ]

            for key, label in properties:
                value = record.get(key)
                if available(value):
                    st.write(f"**{label}:** {value}")

            if available(record.get("cid")):
                try:
                    cid = int(float(record["cid"]))
                    st.link_button(
                        "Open PubChem",
                        f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}",
                    )
                except (ValueError, TypeError, OverflowError):
                    pass

            report = {
                "chemical_name": record["primary_name"],
                "cas_number": record["cas_number"],
                "molecular_formula": record.get("molecular_formula"),
                "flash_point": record.get("flash_point"),
                "boiling_point": record.get("boiling_point"),
                "dataset_split": record.get("dataset_split"),
                "dataset_revision": record.get("dataset_revision"),
                "safety_notice": SAFETY_NOTICE,
                "zero_label_notice": ZERO_LABEL_NOTICE,
                "record_conflict_notice": CONFLICT_NOTICE if conflicting_labels else "",
            }

            for target in TARGETS:
                report[f"recorded_{target}"] = record.get(target)
                report[f"recorded_{target}_meaning"] = recorded_label(record.get(target))

            report["model_evaluation_notice_flammable_solids"] = SOLIDS_NOTICE
            if liquids_model is not None:
                report["model_score_notice"] = SCORE_NOTICE
                report["model_prediction_flammable_liquids"] = prediction
                report["model_positive_score_flammable_liquids"] = positive_score
                if metrics.get("flammable_liquids", {}).get("positive_recall") == 0:
                    report["model_evaluation_notice_flammable_liquids"] = ZERO_RECALL_NOTICE

            st.download_button(
                "Download assessment as CSV",
                pd.DataFrame([report]).to_csv(index=False).encode("utf-8"),
                file_name="chemsafe_assessment.csv",
                mime="text/csv",
            )

    else:
        st.write(
            "Enter a chemical name or CAS number to inspect its recorded "
            "hazard labels and available ML predictions."
        )
        st.subheader("What this app provides")
        c1, c2, c3 = st.columns(3)
        c1.metric("Chemical records", f"{len(df):,}")
        c2.metric("Hazard targets", len(TARGETS))
        c3.metric("AI API required", "No")

elif page == "Model performance":
    st.header("Model evaluation")
    st.write(
        "These metrics measure agreement with SafeChem test labels, not "
        "independently verified real-world flammability."
    )

    if not metrics:
        st.info("Run `python train_model.py` to generate model metrics.")
    else:
        if "split_overlap" in metrics:
            st.subheader("Shared identifiers across dataset splits")
            st.dataframe([
                {
                    "Splits": " / ".join(pair["splits"]),
                    "Shared CAS identifiers": pair["cas_number"],
                    "Shared InChI keys": pair["inchi_key"],
                }
                for pair in metrics["split_overlap"]
            ], hide_index=True)

        for target, label in TARGETS.items():
            if target not in metrics:
                continue

            result = metrics[target]
            st.subheader(label)

            a, b, c, d = st.columns(4)
            a.metric("Accuracy", f"{result['test_accuracy']:.1%}")
            b.metric("Balanced accuracy", f"{result['test_balanced_accuracy']:.1%}")
            c.metric("Positive recall", f"{result['positive_recall']:.1%}")
            d.metric("Positive F1", f"{result['positive_f1']:.1%}")

            baseline = result.get("majority_baseline")
            if baseline:
                st.write(
                    f"Majority-class baseline · Balanced accuracy {baseline['test_balanced_accuracy']:.1%} · "
                    f"Positive recall {baseline['positive_recall']:.1%} · Positive F1 {baseline['positive_f1']:.1%}"
                )
            if "class_counts" in result:
                st.dataframe([
                    {"Split": split, **counts}
                    for split, counts in result["class_counts"].items()
                ], hide_index=True)
            if result["positive_recall"] == 0:
                st.warning(ZERO_RECALL_NOTICE)

            st.write("Confusion matrix: `[[TN, FP], [FN, TP]]`")
            st.write(result["confusion_matrix_labels_0_1"])

            st.json(result["classification_report"])

elif page == "Dataset explorer":
    st.header("Dataset explorer")
    st.write("Browse the records loaded from the three supplied CSV splits.")

    search = st.text_input("Filter by name or CAS")
    view = df

    if search.strip():
        term = search.strip().casefold()
        view = df[
            df["_name"].str.contains(term, regex=False, na=False)
            | df["_cas"].str.contains(normalize_cas(term), regex=False, na=False)
            | df["cas_number"].str.contains(term, case=False, regex=False, na=False)
        ]

    columns = [
        "primary_name", "cas_number", "molecular_formula",
        "molecular_weight", "flammable_liquids",
        "flammable_solids", "flash_point", "dataset_split",
    ]
    columns = [c for c in columns if c in view.columns]

    st.caption(f"{len(view):,} matching records")
    st.dataframe(view[columns].head(500), use_container_width=True)

    st.download_button(
        "Download filtered records",
        view[columns].to_csv(index=False).encode("utf-8"),
        file_name="chemsafe_filtered_records.csv",
        mime="text/csv",
    )

st.divider()
st.caption(
    "Chemsafe AI | SafeChem research prototype | "
    "Verify current product-specific SDS before safety-critical use."
)
