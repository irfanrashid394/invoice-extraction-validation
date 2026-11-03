# Failure Log

1. **INV-01 prototype only returned header fields.** The first version did not include line items, dates beyond the document date, or totals. Expanded it to schema-complete extraction and compared the parsed output to the expected JSON.
2. **PDF block grouping differed by layout.** Some Kessler PDFs emitted a table row as pipe-separated content in one extraction mode, but the new files expose each cell on its own line. The parser was updated to process line-based cells and tested on INV-02's 26 positions.
3. **Discount column is not consistently present.** INV-02 rows may omit a blank discount field or have a populated discount. Parser now distinguishes two/three tail values; item count and totals bucket sums were checked.
4. **Credit-note amounts use trailing minus.** Initial numeric conversion failed on values like `225,80-`. German number parsing now handles leading and trailing minus; INV-03 outputs negative line totals and negative net/VAT/gross totals.
5. **Revised INV-05 table does not match legacy column sequence.** Legacy parser found zero item rows. Added separate layout parsing for position, quantity/unit, SKU, description, price, VAT and amount, with special discount integrated into the line total.
6. **Summary labels and values are separate text lines.** A regex looking for label and amount on the same line returned empty VAT buckets for INV-02. Adjusted summary parsing to read the next extracted line after each label.
7. **INV-04 printed line arithmetic discrepancy.** Position 7 has qty 26 × unit price 48.02 but printed line amount 1,284.52 (arithmetic is 1,248.52). Extractor preserves PDF amount; discrepancy documented for validator review.

8. **Validator catches source inconsistency rather than treating it as a clean pass.** V1 flags INV-04 position 7 calculation (€1,248.52 vs printed €1,284.52), and V2 reports item net sum (€5,249.22) against printed 19% subtotal (€5,213.22). Kept this as a validation failure; source amount is not silently rewritten.
9. **Credit-note arithmetic uses negative presentation.** Validator initially needed to compare magnitudes for V1 while preserving negative signs for V7. Validation logic separates arithmetic magnitude from sign convention; INV-03 passes both.
