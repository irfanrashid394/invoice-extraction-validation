# Fingerprint Invoice Extraction Challenge

## Files

- `extract.py`: PDF extraction.
- `validate.py`: V1–V7 validation.
- `output_schema.json`: supplied output schema.
- `INV-01_expected_output.json`: supplied expected result for INV-01.
- `outputs/`: extracted JSON and validation reports for the five supplied PDFs.
- `MARKING_NOTES.md`, `FAILURE_LOG.md`, `AI_USAGE.md`: assignment documentation.

## Run

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Extract one invoice:

```bash
python extract.py documents/INV-02_RE-2026-10431.pdf
```

Output defaults to `outputs/<pdf-filename>.json`. To choose a path:

```bash
python extract.py path/to/invoice.pdf --output outputs/custom.json
```

## Supported sample layouts

- INV-01: baseline Kessler invoice, one page.
- INV-02: three-page Kessler invoice, repeated page headers, item rows across pages, two VAT rates, price units and discounts.
- INV-03: credit note; negative line amounts and totals.
- INV-04: two-page invoice with extended item list and mixed VAT.
- INV-05: revised single-page layout, month-name dates, discount note and revised item table.

The parser uses PyMuPDF's PDF text blocks. It does not OCR image-only/scanned invoices.

## Test results

During development, extractor outputs for all five supplied PDFs were generated and validated against `output_schema.json` with `jsonschema` and `FormatChecker`; all passed schema validation. INV-01 parsed JSON equals the provided expected output as a Python dictionary.

INV-04 has a source-level arithmetic mismatch in the printed data: position 7 shows quantity 26, unit price 48.02 and line amount 1,284.52, though quantity × unit price is 1,248.52. The extractor preserves the amount printed on the PDF; the validator should flag this discrepancy rather than silently alter the source.

## Validation

Run the assignment checks V1–V7 and JSON Schema validation:

```bash
python validate.py outputs/INV-02_RE-2026-10431.pdf.json
```

The command prints PASS/FAIL/WARN per check and exits with code 1 when a validation failure exists. To save a machine-readable report:

```bash
python validate.py outputs/INV-02_RE-2026-10431.pdf.json --report outputs/validation_INV-02.json
```

Checks:
- V1: line-item arithmetic (quantity × unit price ÷ price unit, applying line discount; tolerance €0.01)
- V2: line totals summed by VAT rate reconcile to net subtotals
- V3: net subtotal × VAT rate reconciles to VAT amount
- V4: net total + VAT total reconciles to gross total
- V5: German supplier VAT ID format (`DE` + 9 digits)
- V6: ISO dates are valid; due date does not precede document date
- V7: invoice values are positive and credit-note values are negative

INV-04 triggers V1 warning and V2 failure because position 7's printed line amount disagrees with its printed quantity/unit price, which causes the item sum to differ from the printed 19% net subtotal. This is intentionally surfaced; source values are not auto-corrected.
