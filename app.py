from pathlib import Path
import json

import joblib
import pandas as pd
import streamlit as st

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


@st.cache_data
def load_data():
    frames = []
    for split in ["train", "validation", "test"]:
        path = DATA / f"safechem_{split}.csv"
        if path.exists():
            part = pd.read_csv(path, low_memory=False)
            part["dataset_split"] = split
            frames.append(part)

    if not frames:
        raise FileNotFoundError("No SafeChem CSV files found in data/")

    result = pd.concat(frames, ignore_index=True)
    result["primary_name"] = result["primary_name"].fillna("").astype(str)
    result["cas_number"] = result["cas_number"].fillna("").astype(str)
    result["_name"] = result["primary_name"].str.casefold()
    result["_cas"] = result["cas_number"].str.casefold()
    return result


@st.cache_resource
def load_models():
    loaded = {}
    for target in TARGETS:
        path = MODELS / f"{target}.joblib"
        if path.exists():
            loaded[target] = joblib.load(path)
    return loaded


@st.cache_data
def load_metrics():
    path = MODELS / "metrics.json"
    if path.exists():
        with open(path) as file:
            return json.load(file)
    return {}


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


def predict_record(record, models):
    features = pd.DataFrame(
        [[pd.to_numeric(record.get(f), errors="coerce") for f in FEATURES]],
        columns=FEATURES,
    )
    results = {}

    for target, label in TARGETS.items():
        if target not in models:
            results[target] = None
            continue

        model = models[target]
        prediction = int(model.predict(features)[0])
        scores = model.predict_proba(features)[0]
        classes = list(model.named_steps["classifier"].classes_)
        positive_score = (
            float(scores[classes.index(1)]) if 1 in classes else None
        )

        results[target] = {
            "label": label,
            "prediction": prediction,
            "positive_score": positive_score,
        }

    return results


st.title("🧪 Chemsafe AI")
st.caption("Chemical Flammability Intelligence Platform")

st.warning(
    "Research prototype only. Dataset labels and ML predictions are not "
    "certified safety determinations. Verify the exact substance or product "
    "against its current Safety Data Sheet (SDS)."
)

try:
    df = load_data()
except Exception as exc:
    st.error(f"Dataset loading failed: {exc}")
    st.stop()

models = load_models()
metrics = load_metrics()

with st.sidebar:
    st.header("Project overview")
    st.metric("Loaded records", f"{len(df):,}")
    st.metric("Unique CAS identifiers", f"{df.loc[df['_cas'] != '', '_cas'].nunique():,}")
    st.metric("Trained models available", f"{len(models)}/{len(TARGETS)}")
    st.caption("Dataset: Anonymous-07/SafeChem")

    page = st.radio(
        "Navigation",
        ["Chemical assessment", "Model performance", "Dataset explorer"],
    )

if page == "Chemical assessment":
    st.header("Search a chemical")

    query = st.text_input(
        "Chemical name or CAS number",
        placeholder="e.g. ethanol or 007790-91-2",
    )

    if query.strip():
        term = query.strip().casefold()
        exact = df[(df["_name"] == term) | (df["_cas"] == term)]
        results = exact

        if results.empty:
            contains = df[
                df["_name"].str.contains(term, regex=False, na=False)
                | df["_cas"].str.contains(term, regex=False, na=False)
            ]
            results = contains

        if results.empty:
            st.error("No matching record found in SafeChem.")
            st.info(
                "No match does not mean nonflammable. Check spelling, CAS "
                "number, or the product's SDS."
            )
        else:
            # Deduplicate displayed choices, not the underlying dataset.
            results = results.copy()
            results["_display"] = (
                results["primary_name"].str.strip()
                + " | CAS: "
                + results["cas_number"].str.strip()
            )
            options = results["_display"].drop_duplicates().tolist()
            selected = st.selectbox("Select the intended record", options)
            record = results[results["_display"] == selected].iloc[0]

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

            st.subheader("Recorded SafeChem labels")
            for target, label in TARGETS.items():
                value = record.get(target)
                status = recorded_label(value)
                st.write(f"**{label}:** {status}")

            st.caption(
                "A zero label is not proof of universal nonflammability."
            )

            st.subheader("Machine-learning predictions")
            if not models:
                st.info(
                    "Models are not trained yet. Run "
                    "`python train_model.py` in the terminal."
                )
            else:
                predictions = predict_record(record, models)
                cols = st.columns(2)

                for col, (target, label) in zip(cols, TARGETS.items()):
                    result = predictions[target]
                    with col:
                        st.markdown(f"**{label}**")
                        if result is None:
                            st.info("Model unavailable")
                        elif result["prediction"] == 1:
                            st.error("Model predicts positive label")
                        else:
                            st.info("Model predicts negative label")

                        score = result["positive_score"]
                        if score is not None:
                            st.write(
                                f"Model positive-class score: {score:.1%}"
                            )

                        st.caption(
                            "Model output is not a calibrated probability "
                            "of real-world flammability."
                        )

            st.subheader("Available properties")
            properties = [
                ("iupac_name", "IUPAC name"),
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
            }

            for target in TARGETS:
                report[f"recorded_{target}"] = record.get(target)

            if models:
                for target, result in predictions.items():
                    if result:
                        report[f"model_prediction_{target}"] = result["prediction"]
                        report[f"model_positive_score_{target}"] = result["positive_score"]

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
            | df["_cas"].str.contains(term, regex=False, na=False)
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
