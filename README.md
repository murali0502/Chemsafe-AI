# Chemsafe AI

Chemical Flammability Intelligence Platform built with Streamlit,
pandas, and scikit-learn.

## Features

- Chemical search by name or CAS number
- SafeChem dataset exploration
- Recorded flammable-liquid and flammable-solid hazard labels
- Baseline machine-learning models
- Model evaluation metrics
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

## Limitations

This is a research prototype. Model predictions reproduce dataset labels
and are not certified chemical safety determinations. Verify the exact
substance or product against authoritative safety documentation.
