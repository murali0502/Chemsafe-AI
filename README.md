# Chemsafe AI

Chemical Flammability Intelligence Platform built with Streamlit,
pandas, and scikit-learn.

## Features

- Chemical search by recorded name, IUPAC name, or CAS number with record confirmation
- SafeChem dataset explorer with split and recorded-hazard filters, pagination, and CSV export
- Recorded flammable-liquid and flammable-solid hazard labels
- Baseline machine-learning models
- Model evaluation dashboard with test metrics, baseline comparison, and split audit
- Downloadable assessment reports

## Technology

- Python
- Streamlit
- pandas
- scikit-learn
- SafeChem dataset from Hugging Face

## Setup

Install dependencies:

    pip install -r requirements.txt

From the repository root, download and validate the SafeChem splits:

    python prepare_data.py

The script downloads the original CSV files from a pinned
[SafeChem revision](https://huggingface.co/datasets/Anonymous-07/SafeChem/tree/43fa095c6020ad0a34f2c34301e83b29aa11ce05)
and writes `data/safechem_train.csv`, `data/safechem_validation.csv`, and
`data/safechem_test.csv`. It validates all three files before replacing
any existing CSVs with those names. The script uses the Python standard
library and requires an internet connection.

Train models:

    python train_model.py

Run the application:

    streamlit run app.py

## Model evaluation

The training command compares each random forest with a majority-class
baseline on the supplied test split. It reports class counts and checks
for shared CAS identifiers and InChI keys across the available splits.
The validation split is included in the audit. The default model
settings are fixed.

The flammable-solids model missed all 29 positive test labels in the
pinned dataset. The app shows its results on the Model performance page
and withholds its predictions from assessments and CSV exports. Recorded
SafeChem solids labels remain available after record confirmation.

## Limitations

This is a research prototype. Model predictions reproduce dataset labels
and are not certified chemical safety determinations. Verify the exact
substance or product against authoritative safety documentation.
