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
    initial_sidebar_state="collapsed",
)

ROOT = Path(__file__).resolve().parent
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
    "The solids prediction is withheld from assessments. "
    "See Model results for the evaluation."
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


st.html(ROOT / "dashboard.css")

with st.container(key="app_bar", horizontal=True, vertical_alignment="center"):
    st.html('<div class="cs-brand"><span class="cs-mark" aria-hidden="true">CS</span> Chemsafe AI</div>')
    navigation = {
        "Chemical assessment": "Assessment",
        "Model performance": "Model results",
        "Dataset explorer": "Explore data",
    }
    page = st.radio(
        "Navigation",
        list(navigation),
        format_func=navigation.__getitem__,
        horizontal=True,
        label_visibility="collapsed",
    )

try:
    file_versions = []
    for split in ("train", "validation", "test"):
        path = DATA / f"safechem_{split}.csv"
        if path.exists():
            file_versions.append((split, path, path.stat().st_mtime_ns))
    df = load_data(file_versions)
except (OSError, ValueError) as exc:
    st.title("Prepare the SafeChem dataset")
    st.error(f"Dataset loading failed: {exc}")
    st.code("python prepare_data.py", language="bash")
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

if page == "Chemical assessment":
    st.html(
        '<section class="cs-hero"><h1>Chemical assessments</h1>'
        '<p>Find a substance, confirm its identity, and review the flammability '
        'evidence recorded in SafeChem.</p></section>'
    )

    if "assessment_draft" not in st.session_state:
        st.session_state["assessment_draft"] = st.session_state.get("assessment_query", "")
    with st.container(key="search_panel"):
        st.subheader("Find a substance")
        with st.form("assessment_search", border=False):
            field, action = st.columns([5, 1], vertical_alignment="center")
            draft_query = field.text_input(
                "Chemical name, IUPAC name, or CAS number",
                placeholder="Search ethanol or 64-17-5",
                key="assessment_draft",
                label_visibility="collapsed",
            )
            if action.form_submit_button("Search", type="primary", width="stretch"):
                st.session_state["assessment_query"] = draft_query
        with st.container(key="search_examples", horizontal=True, vertical_alignment="center"):
            st.caption("Examples", width="content")
            for example in ("Ethanol", "67-56-1", "Acetone"):
                if st.button(example, on_click=st.session_state.__setitem__,
                             args=("assessment_draft", example)):
                    st.session_state["assessment_query"] = example
        query = st.session_state.get("assessment_query", "")

    st.warning(SAFETY_NOTICE)

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
            st.caption(
                f"{len(groups):,} {'exact' if exact.any() else 'partial'} "
                f"{'match' if len(groups) == 1 else 'matches'}"
            )
            selection = st.selectbox(
                "Matching substances",
                list(groups),
                index=0 if len(groups) == 1 else None,
                placeholder="Choose a substance to review",
                format_func=lambda key: (
                    f"{results.iloc[groups[key][0]]['primary_name']} | "
                    f"CAS: {results.iloc[groups[key][0]]['cas_number']}"
                ),
            )
            if selection is None:
                st.stop()
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

            with st.container(key="identity_panel"):
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
                confirmed = st.checkbox(
                    "I confirm this is the intended substance record",
                    key=f"confirm_{term}_{record.name}_{file_versions}",
                )
            if not confirmed:
                st.stop()

            with st.container(key="evidence_panel"):
                st.subheader("Recorded hazard labels")
                split = record["dataset_split"]
                if record["dataset_revision"] == REVISION:
                    source_url = f"https://huggingface.co/datasets/Anonymous-07/SafeChem/tree/{REVISION}"
                    st.caption(f"Source · [SafeChem]({source_url}) · {split} split · revision `{REVISION[:8]}`")
                else:
                    st.caption(f"Source · Local {split} CSV · Dataset revision unverified")
                for column, (target, label) in zip(st.columns(2), TARGETS.items()):
                    with column:
                        status = recorded_label(record.get(target))
                        st.markdown(f"**{label}**")
                        if status == "Positive hazard label recorded":
                            st.warning(status, icon=":material/warning:")
                        else:
                            st.info(status)
                st.caption(ZERO_LABEL_NOTICE)

            with st.container(key="prediction_panel"):
                st.subheader("Experimental model")
                st.caption(SOLIDS_NOTICE)
                if liquids_model is None:
                    st.info("Run `python train_model.py` to enable the liquids prediction.")
                else:
                    prediction, positive_score = predict_liquids(record, liquids_model)
                    st.markdown("**Flammable liquids**")
                    st.write("Predicted positive label" if prediction == 1 else "Predicted negative label")
                    if positive_score is not None:
                        st.progress(positive_score, text=f"Positive-class score · {positive_score:.1%}")
                    st.caption(SCORE_NOTICE)
                    if metrics.get("flammable_liquids", {}).get("positive_recall") == 0:
                        st.warning(ZERO_RECALL_NOTICE)

            with st.expander("Molecular properties and identifiers"):
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
                type="primary",
            )
    else:
        records, identifiers, splits = st.columns(3)
        records.metric("SafeChem records", f"{len(df):,}", border=True)
        identifiers.metric("CAS identifiers", f"{df.loc[df['_cas'] != '', '_cas'].nunique():,}", border=True)
        splits.metric("Dataset splits", df["dataset_split"].nunique(), border=True)

elif page == "Model performance":
    st.title("Model performance")
    st.write("Compare the random forests with the majority-class baseline on SafeChem test labels.")
    st.caption("These metrics measure agreement with dataset labels. Consult a current SDS for safety decisions.")

    if not metrics:
        st.info("Run `python train_model.py` to generate model metrics.")
    else:
        comparison = []
        for target, label in TARGETS.items():
            result = metrics.get(target, {})
            baseline = result.get("majority_baseline")
            if baseline:
                for series, scores in (("Random forest", result), ("Majority class", baseline)):
                    comparison.append({
                        "Hazard label": label,
                        "Model": series,
                        "Balanced accuracy (%)": 100 * scores["test_balanced_accuracy"],
                        "Positive recall (%)": 100 * scores["positive_recall"],
                    })
        if comparison:
            with st.container(key="performance_summary"):
                st.subheader("Test-set comparison")
                score = st.radio(
                    "Metric to compare",
                    ["Positive recall (%)", "Balanced accuracy (%)"],
                    horizontal=True,
                )
                st.bar_chart(
                    pd.DataFrame(comparison),
                    x="Hazard label", y=score, color="Model",
                    stack=False, height=260,
                )

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

            with st.expander(f"{label} · Confusion matrix and classification report"):
                st.dataframe(
                    pd.DataFrame(
                        result["confusion_matrix_labels_0_1"],
                        index=["Recorded negative", "Recorded positive"],
                        columns=["Predicted negative", "Predicted positive"],
                    )
                )
                st.json(result["classification_report"])

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

elif page == "Dataset explorer":
    st.title("Dataset explorer")
    st.write("Filter SafeChem records and export your selection.")

    with st.container(key="explorer_filters"):
        search = st.text_input("Chemical name, IUPAC name, or CAS", key="explorer_query")
        split_column, hazard_column = st.columns(2)
        splits = split_column.multiselect("Dataset splits", df["dataset_split"].unique().tolist())
        hazard = hazard_column.selectbox(
            "Recorded positive hazard label",
            ["Any", *TARGETS],
            format_func=lambda value: TARGETS.get(value, value),
        )

    view = df
    if search.strip():
        term = search.strip().casefold()
        view = view[
            view["_name"].str.contains(term, regex=False, na=False)
            | view["_iupac"].str.contains(term, regex=False, na=False)
            | view["_cas"].str.contains(normalize_cas(term), regex=False, na=False)
            | view["cas_number"].str.contains(term, case=False, regex=False, na=False)
        ]
    if splits:
        view = view[view["dataset_split"].isin(splits)]
    if hazard != "Any":
        if hazard in view:
            view = view[pd.to_numeric(view[hazard], errors="coerce").eq(1)]
        else:
            view = view.iloc[:0]

    if view.empty:
        st.info("No records match these filters.")
    else:
        columns = [
            "primary_name", "cas_number", "molecular_formula",
            "molecular_weight", "flammable_liquids", "flammable_solids",
            "flash_point", "dataset_split",
        ]
        columns = [column for column in columns if column in view]
        page_size = 100
        page_count = (len(view) + page_size - 1) // page_size
        current_page = 1
        if page_count > 1:
            current_page = st.number_input(
                "Page", min_value=1, max_value=page_count,
                key=f"explorer_page_{search}_{splits}_{hazard}",
            )
        offset = (current_page - 1) * page_size
        st.caption(
            f"Showing {offset + 1:,}–{min(offset + page_size, len(view)):,} of {len(view):,} matching records"
        )
        st.dataframe(
            view[columns].iloc[offset:offset + page_size],
            hide_index=True,
            column_config={
                "primary_name": "Substance",
                "cas_number": "CAS number",
                "molecular_formula": "Formula",
                "molecular_weight": "Molecular weight",
                "flammable_liquids": "Liquid label",
                "flammable_solids": "Solid label",
                "flash_point": "Flash point (source text)",
                "dataset_split": "Split",
            },
        )
        st.caption("Label 1 indicates a recorded positive. " + ZERO_LABEL_NOTICE)
        st.download_button(
            "Download filtered records",
            view[columns].to_csv(index=False).encode("utf-8"),
            file_name="chemsafe_filtered_records.csv",
            mime="text/csv",
        )

st.html('<footer class="cs-footer">Chemsafe AI · SafeChem research prototype</footer>')
