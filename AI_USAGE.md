# AI Usage

## Tools used

- ChatGPT (GPT-6): assisted with implementation iterations, debugging hypotheses, test planning, and documentation drafting.
- Python: executed extractor/validator tests and compared JSON structures.
- PyMuPDF (`pymupdf`): extracted selectable PDF text and layout blocks; no OCR was used.
- `jsonschema` with `FormatChecker`: checked extracted JSON against the supplied schema.
- VS Code / terminal: intended local development and execution environment.

AI assistance was used to draft and iteratively debug the PDF extraction implementation and project documentation. The developer should review the generated output and own final validation.

Concrete AI mistakes caught during testing:

1. **Assumed table rows would always be pipe-separated.** INV-02's extracted PDF blocks exposed each cell as a separate line; the initial parser returned zero rows. This was caught by checking item counts against the PDF's 26 positions and fixed with line-cell parsing.
2. **Assumed net/VAT labels and values were on the same text line.** INV-02 totals came out empty despite the printed totals being present. Inspection of the extracted page text showed label/value pairs on adjacent lines; parser updated and tested.

Additional edge cases verified: trailing-minus credit-note amounts, discount values, mixed VAT, new date format and separate discount note in INV-05. Output JSON was schema-validated for all five PDFs. INV-01 dictionary equality was checked against the provided expected JSON.

3. **Validation must separate arithmetic correctness from document sign convention.** A naive V1 check would flag every credit-note line as incorrect because printed totals are negative. Compared absolute magnitudes for arithmetic and separately verified negative signs in V7, then ran against INV-03.
