# Marking Notes

## Field location
- Document number/date and customer/order/delivery references: anchored by printed labels in header text.
- Service/delivery date and due date: label or payment sentence anchored.
- Supplier VAT ID: `DE` followed by nine digits in the footer.
- Buyer: buyer name/address block and five-digit postal/city line.
- Item rows: structured PyMuPDF text blocks; legacy layout reads cells in row sequence, new layout reads its reordered quantity/article/description/price/VAT/amount cells.
- Totals: printed VAT-category net/tax amounts and invoice gross; revised layout summary block.
- Credit note: document type and negative sign normalized from trailing-minus amounts.

## Robustness
- Reads every PDF page and processes rows from each page, not just page one.
- Skips repeated headers, carry-forward subtotal lines and footers because they do not match item row patterns.
- Parses German numeric formatting and German month-name dates.
- Supports blank discount cells, PE values, VAT categories 7% and 19%, credit-note negative amounts, and informational extra description blocks.
- INV-05 discount row is integrated into its item's line total; skonto is not populated when the PDF says there is no discount.

## Break risks
- Scanned/image-only PDF requires OCR and is not supported in this extractor.
- Layout changes that alter PDF text block cell ordering may break row parsing.
- Multi-line descriptions are presently not concatenated into item descriptions; they're retained as separate source blocks and ignored for output descriptions.
- Buyer address extraction assumes a recognizable Rheinwerk buyer block.
- INV-04 position 7 contains a printed quantity/unit-price/amount inconsistency. Values are preserved from source and should be caught by line math validation.
- Revised invoice layout supports the currently supplied invoice pattern, not arbitrary vendor templates.

## INV-05 layout change (under 200 words)
INV-05 changes the header labels and switches dates to German month names. Its item table also reorders columns: quantity and unit precede the article number and description, while unit price, VAT rate and amount appear in a compact row. Position 2 includes a separate special-discount note and negative amount. The extractor uses a distinct parser for this revised layout, converts dates such as “19. Oktober 2026” to ISO format, and integrates the discount into the position's line total. The net subtotal is allocated by VAT rate from the item rows, while VAT totals are read from the printed summary. Skonto remains null because the invoice explicitly states no skonto deduction.
