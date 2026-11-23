import { downloadAssessmentPdf } from "./report.js";

const get = (id) => document.getElementById(id);
const fmt = new Intl.NumberFormat("en");
const percent = (value) => `${(100 * value).toFixed(1)}%`;
const targets = { flammable_liquids: "Flammable liquids", flammable_solids: "Flammable solids" };
const safety = "Research prototype. Verify the exact product against its current Safety Data Sheet (SDS).";
const zeroLabel = "A zero label is not proof of nonflammability.";
const scoreNotice = "The model score is not a calibrated probability of real-world flammability.";
const conflictNotice = "SafeChem records for this identifier disagree on substance details or hazard labels.";
const solidsNotice = "The solids prediction is withheld from assessments. See Model results for the evaluation.";
const source = "https://huggingface.co/datasets/Anonymous-07/SafeChem";
const pageSize = 50;
let catalog;
let rows = [];
let filtered = [];
let page = 0;
const grouped = new Map();

function node(tag, content, className) {
  const element = document.createElement(tag);
  if (content !== undefined && content !== null) element.textContent = content;
  if (className) element.className = className;
  return element;
}

function nameKey(value) {
  return String(value ?? "").trim().toLowerCase();
}

function casKey(value) {
  const term = nameKey(value).replace(/[‐‑–—]/g, "-").replace(/\s+/g, "");
  const match = term.match(/^([0-9]{2,})-([0-9]{2})-([0-9])$/)
    ?? term.match(/^([0-9]{2,})([0-9]{2})([0-9])$/);
  if (!match) return "";
  const first = match[1].replace(/^0+(?=\d)/, "").padStart(2, "0");
  if (first.length > 7 || Number(first) === 0) return "";
  const check = [...(first + match[2])].reverse()
    .reduce((sum, digit, index) => sum + Number(digit) * (index + 1), 0);
  return check % 10 === Number(match[3]) ? `${first}-${match[2]}-${match[3]}` : "";
}

function labelMeaning(value) {
  if (value === 1) return "Positive hazard label recorded";
  if (value === 0) return "No positive label recorded";
  return "Recorded label unavailable";
}

function route() {
  const requested = location.hash.slice(1);
  const section = ["assessment", "models", "explore"].includes(requested) ? requested : "assessment";
  document.querySelectorAll(".view").forEach((view) => { view.hidden = view.id !== section; });
  document.querySelectorAll("nav a").forEach((link) => {
    if (link.hash === `#${section}`) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  if (requested === section) window.scrollTo(0, 0);
}

function searchRows(query, strictCas = false) {
  const term = nameKey(query);
  const cas = casKey(term);
  if (strictCas && /^[0-9\s‐‑–—-]+$/.test(term)) {
    return {
      records: cas ? grouped.get(`CAS:${cas}`) ?? [] : [],
      exact: true,
      invalidCas: !cas,
    };
  }
  const exact = rows.filter((row) => row.name === term || row.alias === term || (cas && row.cas === cas));
  if (exact.length) return { records: exact, exact: true };
  const records = rows.filter((row) =>
    row.name.includes(term) || row.alias.includes(term) ||
    (cas && row.cas.includes(cas)) || nameKey(row.cas_number).includes(term));
  records.sort((a, b) => Number(b.name.startsWith(term)) - Number(a.name.startsWith(term)));
  return { records, exact: false };
}

function downloadCsv(filename, fields, data) {
  const quote = (value) => {
    let text = String(value ?? "");
    if (typeof value === "string" && /^[\s]*[=+\-@]/.test(text)) text = "'" + text;
    return '"' + text.replaceAll('"', '""') + '"';
  };
  const lines = [fields, ...data.map((entry) => fields.map((field) => entry[field]))];
  const url = URL.createObjectURL(new Blob([lines.map((line) => line.map(quote).join(",")).join("\r\n")], { type: "text/csv;charset=utf-8" }));
  const link = node("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function search(query) {
  if (!catalog || !query.trim()) return;
  const { records, exact, invalidCas } = searchRows(query, true);
  const matches = get("matches");
  const result = get("assessment-result");
  result.hidden = true;
  result.replaceChildren();
  matches.replaceChildren();
  matches.hidden = records.length === 0;
  const candidates = new Map();
  for (const row of records) {
    if (!candidates.has(row.group)) candidates.set(row.group, row);
  }
  const keys = [...candidates.keys()];
  get("search-status").textContent = invalidCas
    ? "Enter a complete, valid CAS number. Check the digits against the product’s current SDS."
    : keys.length
    ? `${fmt.format(keys.length)} ${exact ? "exact" : "partial"} ${keys.length === 1 ? "match" : "matches"}`
    : "No matching record. Check the spelling or CAS number and consult the product’s current SDS.";
  if (!keys.length) return;
  const panel = node("section", undefined, "panel rise");
  const title = node("h2", "Select a substance");
  const select = node("select");
  select.setAttribute("aria-label", "Matching substances");
  const placeholder = new Option("Choose a substance to review", "");
  placeholder.disabled = true;
  select.append(placeholder);
  keys.forEach((key, index) => {
    const row = candidates.get(key);
    select.add(new Option(`${row.primary_name || "Unnamed substance"} · ${row.cas_number || "CAS unavailable"}`, String(index)));
  });
  const identity = node("div");
  panel.append(title, select, identity);
  matches.append(panel);
  const update = () => {
    result.hidden = true;
    result.replaceChildren();
    identity.replaceChildren();
    if (select.value !== "") {
      const key = keys[Number(select.value)];
      renderIdentity(grouped.get(key), candidates.get(key), identity);
    }
  };
  select.addEventListener("change", update);
  select.value = keys.length === 1 ? "0" : "";
  update();
}

function renderIdentity(records, candidate, container) {
  const distinctLabels = new Set(records.map((row) => JSON.stringify(Object.keys(targets).map((key) => row[key]))));
  const identities = new Set(records.map((row) => nameKey(row.inchi_key)).filter(Boolean));
  const formulas = new Set(records.map((row) => nameKey(row.molecular_formula)).filter(Boolean));
  const disagreement = distinctLabels.size > 1 || identities.size > 1 || formulas.size > 1;
  const properties = node("dl", undefined, "identity");
  const confirm = node("button", "Confirm substance", "primary");
  confirm.type = "button";
  const choose = node("select");
  choose.setAttribute("aria-label", "Source record");
  if (disagreement) {
    container.append(node("p", conflictNotice + " Choose the source record to review.", "warning"));
    const placeholder = new Option("Choose a source record", "");
    placeholder.disabled = true;
    choose.add(placeholder);
    records.forEach((row, index) => choose.add(new Option(
      `${row.primary_name || "Unnamed substance"} · ${row.dataset_split} · ${row.molecular_formula || "formula unavailable"} · liquid ${row.flammable_liquids ?? "unknown"} · solid ${row.flammable_solids ?? "unknown"}`,
      String(index))));
    choose.value = "";
    container.append(choose);
  }
  container.append(properties, confirm);

  function selected() {
    return disagreement ? records[Number.parseInt(choose.value, 10)] : candidate;
  }

  function update() {
    const row = selected();
    confirm.disabled = !row;
    properties.replaceChildren();
    get("assessment-result").hidden = true;
    if (!row) return;
    const fields = [
      ["Source name", row.primary_name],
      ["CAS number", row.cas || row.cas_number],
      ["Formula", row.molecular_formula],
    ];
    if (row.iupac_name) fields.push(["IUPAC name", row.iupac_name]);
    for (const [label, value] of fields) {
      const item = node("div");
      item.append(node("dt", label), node("dd", value || "Unavailable"));
      properties.append(item);
    }
    if (row.cas_number && !row.cas) {
      const notice = node("div", undefined, "identity-note");
      notice.append(node("dt", "Identifier check"), node("dd", "The recorded CAS value failed the format or check-digit check."));
      properties.append(notice);
    }
  }
  choose.addEventListener("change", update);
  confirm.addEventListener("click", () => renderAssessment(selected(), disagreement));
  update();
}


function renderSds(cas) {
  const section = node("section", undefined, "panel sds-panel");
  const products = Object.hasOwn(catalog.sds_catalog, cas) ? catalog.sds_catalog[cas] : [];
  section.append(node("h2", "Product Safety Data Sheets"));
  if (!products.length) {
    section.append(node("p", "No product SDS is listed for this record. Obtain the current sheet from the manufacturer for the exact product.", "muted"));
    return { section, selected: () => null };
  }

  section.append(node("p", "Match the manufacturer and product code on your container before selecting a sheet.", "muted"));
  const select = node("select");
  select.setAttribute("aria-label", "Product Safety Data Sheet");
  select.add(new Option("Choose the exact product SDS", ""));
  products.forEach((product, index) => {
    const code = product.product_code ? ` · ${product.product_code}` : "";
    select.add(new Option(
      `${product.manufacturer} · ${product.product_name}${code} · ${product.revision_date}`,
      String(index),
    ));
  });
  const detail = node("div", undefined, "sds-detail");
  const selected = () => products[Number.parseInt(select.value, 10)] ?? null;
  select.addEventListener("change", () => {
    detail.replaceChildren();
    const product = selected();
    if (!product) return;
    const identity = node("dl", undefined, "identity");
    for (const [label, value] of [
      ["Manufacturer", product.manufacturer], ["Product", product.product_name],
      ["Product code", product.product_code || "Unavailable"], ["SDS revision", product.revision_date],
    ]) {
      const field = node("div");
      field.append(node("dt", label), node("dd", value));
      identity.append(field);
    }
    const link = node("a", "Open manufacturer SDS");
    link.href = product.sds_url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    detail.append(identity, link);
  });
  section.append(select, detail);
  return { section, selected };
}

function renderAssessment(row, conflict) {
  const result = get("assessment-result");
  const recorded = node("section", undefined, "panel rise");
  const title = node("h2", "Recorded hazard labels");
  title.tabIndex = -1;
  const provenance = node("p", undefined, "muted");
  const link = node("a", "SafeChem");
  link.href = `${source}/tree/${catalog.revision}`;
  provenance.append("Source · ", link, ` · ${row.dataset_split} split · revision ${catalog.revision.slice(0, 8)}`);
  const evidence = node("div", undefined, "evidence");
  const report = { chemical_name: row.primary_name, cas_number: row.cas_number, molecular_formula: row.molecular_formula,
    flash_point: row.flash_point, boiling_point: row.boiling_point, dataset_split: row.dataset_split,
    dataset_revision: catalog.revision, normalized_cas_number: row.cas || "",
    safety_notice: safety, zero_label_notice: zeroLabel,
    record_conflict_notice: conflict ? conflictNotice : "" };
  Object.entries(targets).forEach(([field, label]) => {
    const value = row[field];
    const meaning = labelMeaning(value);
    const card = node("div", undefined, value === 1 ? "evidence-item warning" : "evidence-item");
    card.append(node("h3", label), node("p", meaning));
    evidence.append(card);
    report[`recorded_${field}`] = value;
    report[`recorded_${field}_meaning`] = meaning;
  });
  recorded.append(title, provenance, evidence, node("p", zeroLabel, "muted"));

  const sds = renderSds(row.cas);
  const model = node("details", undefined, "panel");
  model.append(node("summary", "Show experimental liquids prediction"));
  const meter = node("progress");
  meter.max = 1;
  meter.value = row.liquid_score;
  meter.setAttribute("aria-label", "Positive-class score");
  if (conflict) {
    model.append(node("p", "The experimental prediction is withheld because the source records disagree.", "warning"));
  } else {
    model.append(node("p", `Predicted ${row.liquid_prediction === 1 ? "positive" : "negative"} label · ${percent(row.liquid_score)} positive-class score`),
      meter, node("p", scoreNotice, "muted"));
    const metrics = catalog.metrics.flammable_liquids;
    const [missed, detected] = metrics.confusion_matrix_labels_0_1[1];
    model.append(node("p",
      `On SafeChem’s test split, this model detected ${fmt.format(detected)} of ${fmt.format(detected + missed)} positive labels (${percent(metrics.positive_recall)} recall).`,
      "muted"));
    if (row.dataset_split === "train") {
      model.append(node("p", "This record belongs to the training split. Its score is an in-sample prediction.", "muted"));
    }
  }
  model.append(node("p", solidsNotice, "muted"));

  const details = node("details", undefined, "panel");
  details.append(node("summary", "Molecular properties and identifiers"));
  for (const [label, value] of [
    ["Molecular weight", row.molecular_weight], ["Flash point (source text)", row.flash_point],
    ["Boiling point (source text)", row.boiling_point], ["Canonical SMILES", row.canonical_smiles],
    ["InChI Key", row.inchi_key], ["XLogP", row.xlogp], ["TPSA", row.tpsa],
  ]) {
    if (value !== null) details.append(node("p", `${label} · ${value}`));
  }
  if (Number.isInteger(row.cid) && row.cid > 0) {
    const pubchem = node("a", "Open PubChem");
    pubchem.href = `https://pubchem.ncbi.nlm.nih.gov/compound/${row.cid}`;
    details.append(pubchem);
  }
  const actions = node("div", undefined, "actions");
  const pdfButton = node("button", "Download assessment PDF", "primary");
  const pdfStatus = node("p", undefined, "muted");
  pdfStatus.setAttribute("role", "status");
  pdfButton.addEventListener("click", async () => {
    pdfButton.disabled = true;
    pdfStatus.textContent = "Preparing your PDF…";
    try {
      await downloadAssessmentPdf(report, sds.selected());
      pdfStatus.textContent = "PDF downloaded.";
    } catch (error) {
      console.error(error);
      pdfStatus.textContent = "Could not create the PDF. Please try again.";
    } finally {
      pdfButton.disabled = false;
    }
  });
  const exportButton = node("button", "Download assessment CSV");
  exportButton.addEventListener("click", () => {
    const exportRecord = { ...report };
    const product = sds.selected();
    if (product) {
      exportRecord.sds_manufacturer = product.manufacturer;
      exportRecord.sds_product_name = product.product_name;
      exportRecord.sds_product_code = product.product_code;
      exportRecord.sds_revision_date = product.revision_date;
      exportRecord.sds_url = product.sds_url;
    }
    if (model.open && !conflict) {
      exportRecord.model_prediction_flammable_liquids = row.liquid_prediction;
      exportRecord.model_positive_score_flammable_liquids = row.liquid_score;
      exportRecord.model_score_notice = scoreNotice;
      exportRecord.model_evaluation_notice_flammable_solids = solidsNotice;
    }
    downloadCsv("chemsafe_assessment.csv", Object.keys(exportRecord), [exportRecord]);
  });
  actions.append(pdfButton, exportButton, pdfStatus);
  result.replaceChildren(recorded, sds.section, model, details, actions);
  result.hidden = false;
  title.focus();
}

function makeTable(headers, values) {
  const wrap = node("div", undefined, "table-wrap");
  const table = node("table");
  const header = table.createTHead().insertRow();
  headers.forEach((value) => header.append(node("th", value)));
  const body = table.createTBody();
  values.forEach((row) => {
    const tr = body.insertRow();
    row.forEach((value) => tr.append(node("td", value ?? "—")));
  });
  wrap.append(table);
  return wrap;
}

function renderModels() {
  const outputs = get("models-content");
  for (const [target, name] of Object.entries(targets)) {
    const metrics = catalog.metrics[target];
    const panel = node("section", undefined, "panel rise");
    panel.append(node("h2", name));
    if (metrics.positive_recall === 0) {
      panel.append(node("p", "This model detected zero positive labels in its test evaluation.", "warning"));
    }
    for (const [label, key] of [["Positive recall", "positive_recall"], ["Balanced accuracy", "test_balanced_accuracy"], ["Positive F1", "positive_f1"]]) {
      const comparison = node("div", undefined, "comparison");
      comparison.append(node("h3", label));
      for (const [series, values] of [["Random forest", metrics], ["Majority class", metrics.majority_baseline]]) {
        const meter = node("progress");
        meter.className = series === "Majority class" ? "baseline" : "";
        meter.max = 1;
        meter.value = values[key];
        meter.setAttribute("aria-label", `${series} ${label}`);
        comparison.append(node("span", `${series} · ${percent(values[key])}`, "muted"), meter);
      }
      panel.append(comparison);
    }
    const details = node("details");
    details.append(node("summary", "Class counts and confusion matrix"));
    details.append(makeTable(["Split", "Negative", "Positive", "Excluded"],
      Object.entries(metrics.class_counts).map(([split, counts]) => [split, counts.negative, counts.positive, counts.excluded])));
    details.append(makeTable(["Recorded label", "Predicted negative", "Predicted positive"],
      metrics.confusion_matrix_labels_0_1.map((pair, index) => [index === 0 ? "Negative" : "Positive", ...pair])));
    panel.append(details);
    outputs.append(panel);
  }
  const audit = node("section", undefined, "panel");
  audit.append(node("h2", "Dataset split audit"), makeTable(["Splits", "Shared CAS identifiers", "Shared InChI keys"],
    catalog.metrics.split_overlap.map((entry) => [entry.splits.join(" / "), entry.cas_number, entry.inchi_key])));
  outputs.append(audit);
}

function renderTable() {
  const offset = page * pageSize;
  const body = get("dataset-rows");
  const fragment = document.createDocumentFragment();
  filtered.slice(offset, offset + pageSize).forEach((row) => {
    const tr = node("tr");
    [row.primary_name, row.cas_number, row.molecular_formula, row.flammable_liquids, row.flammable_solids, row.dataset_split]
      .forEach((value) => tr.append(node("td", value ?? "—")));
    fragment.append(tr);
  });
  body.replaceChildren(fragment);
  get("filter-status").textContent = filtered.length
    ? `Showing ${fmt.format(offset + 1)}–${fmt.format(Math.min(offset + pageSize, filtered.length))} of ${fmt.format(filtered.length)} matching records`
    : "No records match these filters.";
  get("previous").disabled = page === 0;
  get("next").disabled = offset + pageSize >= filtered.length;
  get("export-records").disabled = filtered.length === 0;
}

function applyFilters() {
  const query = get("filter-query").value.trim();
  const split = get("filter-split").value;
  const hazard = get("filter-hazard").value;
  filtered = (query ? searchRows(query).records : rows)
    .filter((row) => (!split || row.dataset_split === split) && (!hazard || row[hazard] === 1));
  page = 0;
  renderTable();
}

async function load() {
  const response = await fetch("./catalog.json");
  if (!response.ok) throw new Error(`Catalog request returned ${response.status}`);
  catalog = await response.json();
  rows = catalog.rows.map((values) => {
    const row = Object.fromEntries(catalog.fields.map((field, index) => [field, values[index]]));
    row.name = nameKey(row.primary_name);
    row.alias = nameKey(row.iupac_name);
    row.cas = casKey(row.cas_number);
    row.group = row.cas ? `CAS:${row.cas}` : JSON.stringify([row.name, nameKey(row.cas_number)]);
    if (!grouped.has(row.group)) grouped.set(row.group, []);
    grouped.get(row.group).push(row);
    return row;
  });
  get("dataset-link").href = `${source}/tree/${catalog.revision}`;
  const stats = get("catalog-stats");
  for (const [label, value] of [["SafeChem records", rows.length], ["Valid-format CAS identifiers", new Set(rows.map((row) => row.cas).filter(Boolean)).size], ["Dataset splits", new Set(rows.map((row) => row.dataset_split)).size]]) {
    const item = node("div");
    item.append(node("dt", label), node("dd", fmt.format(value)));
    stats.append(item);
  }
  renderModels();
  applyFilters();
  get("catalog-status").hidden = true;
  document.querySelectorAll("#search-form button, [data-example]").forEach((button) => { button.disabled = false; });
}

get("query").addEventListener("input", () => {
  get("matches").hidden = true;
  get("assessment-result").hidden = true;
  get("search-status").textContent = "";
});
get("search-form").addEventListener("submit", (event) => {
  event.preventDefault();
  search(get("query").value);
});
document.querySelectorAll("[data-example]").forEach((button) => button.addEventListener("click", () => {
  get("query").value = button.dataset.example;
  search(button.dataset.example);
}));
get("filter-query").addEventListener("input", applyFilters);
for (const id of ["filter-split", "filter-hazard"]) get(id).addEventListener("change", applyFilters);
get("previous").addEventListener("click", () => { page--; renderTable(); });
get("next").addEventListener("click", () => { page++; renderTable(); });
get("export-records").addEventListener("click", () => downloadCsv("chemsafe_filtered_records.csv", [
  "primary_name", "cas_number", "molecular_formula", "molecular_weight", "flammable_liquids",
  "flammable_solids", "flash_point", "dataset_split",
], filtered));
window.addEventListener("hashchange", route);
route();
load().catch((error) => {
  console.error(error);
  get("catalog-status").textContent = "The SafeChem catalog could not load. Refresh the page to try again.";
});
