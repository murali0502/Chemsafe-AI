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

Download the dataset using the Hugging Face datasets library and export
the train, validation, and test splits to the data/ directory.

Train models:

    python train_model.py

Run the application:

    streamlit run app.py

## Limitations

This is a research prototype. Model predictions reproduce dataset labels
and are not certified chemical safety determinations. Verify the exact
substance or product against authoritative safety documentation.
