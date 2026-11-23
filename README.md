# Chemsafe AI

Chemsafe AI is a portfolio project for reviewing recorded chemical flammability evidence. Search 32,211 SafeChem records by name, IUPAC name, or CAS number, confirm the substance, and download an assessment that includes the source revision.

[Live app](https://chemsafe-ai.netlify.app/) · [Portfolio case study and 60-second walkthrough](https://chemsafe-ai.netlify.app/case-study.html)

## Try the demo

1. Search for `64-17-6` to see how the app catches a mistyped CAS check digit.
2. Search for `64-17-5` or `ethanol` and confirm the **ETHYL ALCOHOL** record.
3. Search product code `A409-4` to find Fisher Scientific’s ethanol SDS. Choose the product and confirm its SafeChem record, then download a PDF with the manufacturer link.
4. Open **Model results** to compare both models on the SafeChem test split.

## What the app does

- **Substance lookup.** CAS searches validate the check digit and require an exact match. When records for the same CAS disagree, the app asks which source record to use.
- **Evidence and reports.** The assessment shows the recorded labels and dataset revision. The PDF and CSV include the selected manufacturer Safety Data Sheet (SDS) when available.
- **Dataset explorer.** Browse records, filter by dataset split or recorded hazard label, and export the full filtered result set as CSV.
- **Model evaluation.** Compare two random forests with a majority-class baseline. The dashboard shows class counts, confusion matrices, and shared CAS identifiers and InChI keys across data splits.

## How it works

Python downloads and validates a pinned SafeChem revision, trains the scikit-learn models, then generates the static catalog and metrics. The Netlify app uses HTML, CSS, and JavaScript for search and reports. jsPDF creates PDFs in the browser. The live site runs without a Python server.

| Path | Purpose |
| --- | --- |
| `site/` | Browser app, PDF generator, and portfolio case study |
| `prepare_data.py` | Download and validate the pinned SafeChem splits |
| `train_model.py` | Train and evaluate the liquid and solid classifiers |
| `build_netlify.py` | Build the static site and catalog in `netlify-dist/` |
| `sds_catalog.json` | Public-approved manufacturer SDS entries |
| `netlify.toml` | Netlify build command and publish directory |

## Run locally

Use Python 3.11 and Node.js with npm. From the repository root, run:

```bash
npm ci
python -m pip install -r requirements.txt
python prepare_data.py
python train_model.py
python build_netlify.py
python -m http.server 8000 --directory netlify-dist
```

Open [localhost:8000](http://localhost:8000). For the Streamlit version, run `python -m streamlit run app.py` after preparing the data and training the models.

## Deploy to Netlify

Connect the repository's `main` branch to a Netlify project. Netlify reads the build and publish settings from `netlify.toml`, and `runtime.txt` selects Python 3.11. For a manual deploy, publish the generated `netlify-dist/` directory.

## Release checks

The Netlify build checks that public manufacturer links return PDFs. The Chromium smoke test covers CAS validation, source conflicts, product lookup, and PDF downloads. Run it against any preview with `CHEMSAFE_TEST_URL=http://localhost:8000/ node scripts/smoke.cjs` after installing Chromium with `npx playwright install chromium`.

## Add product SDS entries

The public starter catalog links to five official Fisher Scientific SDS documents. Add entries approved for public sharing to `sds_catalog.json` and rebuild. Each entry requires `cas_number`, `manufacturer`, `product_name`, `revision_date` in `YYYY-MM-DD` format, and an official HTTPS `sds_url`. The `product_code` field is optional.

Check that each sheet matches the exact manufacturer and product and is the current revision before publishing it. Catalog entries are public.

## Model results and limitations

| Model | Positive labels detected | Positive recall | Balanced accuracy |
| --- | ---: | ---: | ---: |
| Flammable liquids | 232 of 340 | 68.2% | 82.8% |
| Flammable solids | 0 of 29 | 0.0% | 50.0% |

These figures measure agreement with SafeChem test labels. The liquids prediction is experimental and opt-in. The solids model matched the majority-class baseline on balanced accuracy, so the app withholds its predictions from assessments. Recorded solids labels remain available.

Chemsafe AI is a research prototype. Check the exact product against its current SDS before making a safety decision.

## Data attribution

The app uses a pinned snapshot of SafeChem from Anonymous-07. The browser catalog selects source fields and adds model outputs. [Pinned dataset revision](https://huggingface.co/datasets/Anonymous-07/SafeChem/tree/43fa095c6020ad0a34f2c34301e83b29aa11ce05) · [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
