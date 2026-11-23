const assert = require("node:assert/strict");
const { readFile } = require("node:fs/promises");
const { chromium } = require("playwright");

async function main() {
  const url = process.env.CHEMSAFE_TEST_URL || "http://127.0.0.1:8514/";
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH,
  });
  try {
    const page = await browser.newPage({ acceptDownloads: true, viewport: { width: 390, height: 844 } });
    await page.goto(url);
    const search = page.getByRole("searchbox", { name: "Chemical name, IUPAC name, or CAS number" });
    await search.fill("64-17-6");
    await page.getByRole("button", { name: "Search", exact: true }).click();
    await page.getByText(/Enter a complete, valid CAS number/).waitFor();

    await page.getByRole("searchbox", { name: "Manufacturer, product name, or product code" }).fill("Fisher A4094");
    await page.getByRole("button", { name: "Find SDS", exact: true }).click();
    await page.getByRole("button", { name: "Use product A409-4", exact: true }).click();
    await page.getByRole("button", { name: "Confirm substance", exact: true }).click();
    const source = page.getByRole("link", { name: "Open manufacturer SDS", exact: true });
    const link = new URL(await source.getAttribute("href"));
    assert.equal(link.hostname, "www.fishersci.com");
    assert.equal(link.searchParams.get("partNumber"), "A4094");
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));

    const downloadEvent = page.waitForEvent("download");
    await page.getByRole("button", { name: "Download assessment PDF", exact: true }).click();
    const download = await downloadEvent;
    const pdf = await readFile(await download.path());
    assert.equal(pdf.subarray(0, 5).toString(), "%PDF-");
    assert(pdf.includes(Buffer.from("partNumber=A4094")));

    const fixture = await page.evaluate(async () => {
      const response = await fetch("./catalog.json");
      if (!response.ok) throw new Error(`Catalog request returned ${response.status}`);
      return response.json();
    });
    const index = (field) => fixture.fields.indexOf(field);
    const evidence = fixture.rows.find((row) => row[index("cas_number")] === "000064-17-5");
    assert(evidence);
    const conflicting = evidence.slice();
    conflicting[index("primary_name")] = "Alternate source record";
    conflicting[index("flammable_liquids")] = 1 - evidence[index("flammable_liquids")];
    fixture.rows = [evidence, conflicting];
    const conflictPage = await browser.newPage();
    await conflictPage.route("**/catalog.json", (route) => route.fulfill({ json: fixture }));
    await conflictPage.goto(url);
    await conflictPage.getByRole("button", { name: "Ethanol", exact: true }).click();
    await conflictPage.getByText(/disagree on substance details or hazard labels/).waitFor();
    const confirm = conflictPage.getByRole("button", { name: "Confirm substance", exact: true });
    assert(await confirm.isDisabled());
    await conflictPage.getByRole("combobox", { name: "Source record", exact: true }).selectOption("1");
    await confirm.click();
    await conflictPage.getByRole("heading", { name: "Recorded hazard labels", exact: true }).waitFor();
    console.log("CAS validation, source conflicts, product lookup, and PDF export passed.");
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
