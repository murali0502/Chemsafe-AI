let pdfAssets;

function loadAssets() {
  if (!pdfAssets) {
    const library = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = "./vendor/jspdf.umd.min.js";
      script.onload = () => resolve(window.jspdf.jsPDF);
      script.onerror = () => { script.remove(); reject(new Error("Could not load the PDF library.")); };
      document.head.append(script);
    });
    const font = fetch("./fonts/DejaVuSans.ttf").then((response) => {
      if (!response.ok) throw new Error("Could not load the report font.");
      return response.blob();
    }).then((blob) => new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result.split(",")[1]);
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    }));
    pdfAssets = Promise.all([library, font]).catch((error) => {
      pdfAssets = undefined;
      throw error;
    });
  }
  return pdfAssets;
}

export async function downloadAssessmentPdf(report, product) {
  const [PDF, font] = await loadAssets();
  const pdf = new PDF({ unit: "mm", format: "a4", compress: true, putOnlyUsedFonts: true });
  pdf.addFileToVFS("DejaVuSans.ttf", font);
  pdf.addFont("DejaVuSans.ttf", "DejaVu", "normal");
  pdf.setFont("DejaVu");
  pdf.setProperties({ title: "Chemsafe AI assessment", subject: report.chemical_name, creator: "Chemsafe AI" });

  const margin = 19;
  const width = 172;
  const blue = "#18284d";
  const slate = "#3f5069";
  let y = 33;
  pdf.setFillColor(blue);
  pdf.rect(0, 0, 210, 11, "F");

  function paragraph(text, size = 10, color = slate, url) {
    pdf.setFontSize(size);
    pdf.setTextColor(color);
    const lineHeight = size * .48;
    for (const line of pdf.splitTextToSize(String(text), width)) {
      if (y > 269) { pdf.addPage(); y = 21; }
      if (url) pdf.textWithLink(line, margin, y, { url });
      else pdf.text(line, margin, y);
      y += lineHeight;
    }
  }

  function section(title) {
    y += 5;
    if (y > 255) { pdf.addPage(); y = 21; }
    paragraph(title, 13, blue);
  }

  paragraph("Chemsafe AI", 23, blue);
  paragraph("Chemical assessment", 14, blue);
  paragraph(report.safety_notice);

  section("Confirmed substance");
  paragraph(report.chemical_name || "Source name unavailable", 12, blue);
  paragraph("CAS number: " + (report.normalized_cas_number || report.cas_number || "Unavailable"));
  if (report.molecular_formula) paragraph("Formula: " + report.molecular_formula);
  if (report.record_conflict_notice) paragraph(report.record_conflict_notice, 10, "#854518");

  section("Recorded hazard labels");
  paragraph("Flammable liquids: " + report.recorded_flammable_liquids_meaning);
  paragraph("Flammable solids: " + report.recorded_flammable_solids_meaning);
  paragraph(report.zero_label_notice);

  section("Source and revision");
  paragraph("SafeChem dataset, " + report.dataset_split + " split");
  paragraph("Revision: " + report.dataset_revision);
  paragraph("Open the pinned SafeChem source", 10, "#225998",
    "https://huggingface.co/datasets/Anonymous-07/SafeChem/tree/" + report.dataset_revision);

  section("Product Safety Data Sheet");
  if (product) {
    paragraph(product.manufacturer + " / " + product.product_name);
    if (product.product_code) paragraph("Product code: " + product.product_code);
    paragraph("SDS revision date: " + product.revision_date);
    paragraph("Open manufacturer SDS", 10, "#225998", product.sds_url);
  } else {
    paragraph("No product SDS was selected for this assessment. Consult the current SDS for the exact product.");
  }

  for (let page = 1; page <= pdf.getNumberOfPages(); page++) {
    pdf.setPage(page);
    pdf.setDrawColor("#d4deea");
    pdf.line(margin, 278, margin + width, 278);
    pdf.setFontSize(9);
    pdf.setTextColor(slate);
    pdf.text("Chemsafe AI / Recorded SafeChem evidence", margin, 284);
    pdf.text(String(page), margin + width, 284, { align: "right" });
  }
  const id = report.normalized_cas_number || "assessment";
  pdf.save("chemsafe-" + id + "-report.pdf");
}
