import argparse
import json
import re
from datetime import date
from pathlib import Path

import jsonschema

TOLERANCE = 0.01
GERMAN_VAT_ID = re.compile(r"^DE\d{9}$")


def close_enough(actual, expected, tolerance=TOLERANCE):
    return actual is not None and expected is not None and abs(actual - expected) <= tolerance


def add_check(report, rule, passed, message, severity="error"):
    report["checks"].append({
        "rule": rule,
        "status": "PASS" if passed else ("WARN" if severity == "warning" else "FAIL"),
        "message": message,
    })
    if not passed:
        report["summary"]["warnings" if severity == "warning" else "failures"] += 1


def validate_invoice(data, schema=None):
    report = {"document_number": data.get("document_number"), "checks": [],
              "summary": {"passed": 0, "failures": 0, "warnings": 0}}
    if schema is not None:
        try:
            jsonschema.validate(data, schema, format_checker=jsonschema.FormatChecker())
            add_check(report, "SCHEMA", True, "Output conforms to the supplied JSON schema.")
        except jsonschema.ValidationError as exc:
            add_check(report, "SCHEMA", False, f"Schema validation failed: {exc.message}")
    else:
        add_check(report, "SCHEMA", True, "Schema validation skipped (no schema file supplied).", "warning")

    items = data.get("line_items", [])
    is_credit = data.get("document_type") == "credit_note"

    # V1: quantity × unit price / price unit, applying any line discount.
    math_errors = []
    for item in items:
        quantity, unit_price = item.get("quantity"), item.get("unit_price")
        price_unit = item.get("price_unit") or 1
        discount, printed = item.get("discount_percent"), item.get("line_total")
        if None in (quantity, unit_price, price_unit, printed) or price_unit == 0:
            math_errors.append(f"position {item.get('position')}: missing numeric input or zero price unit")
            continue
        calculated = quantity * unit_price / price_unit
        if discount is not None:
            calculated *= (1 - discount / 100)
        calculated = round(calculated, 2)
        # Credit notes carry negative totals; compare arithmetic magnitudes.
        if not close_enough(abs(calculated) if is_credit else calculated,
                            abs(printed) if is_credit else printed):
            math_errors.append(f"position {item.get('position')}: calculated {calculated:.2f}, printed {printed:.2f}")
    add_check(report, "V1", not math_errors,
              "All line calculations agree within €0.01." if not math_errors else "; ".join(math_errors),
              severity="warning" if math_errors else "error")

    # V2: sum of item totals by VAT rate must match net subtotals.
    sums = {}
    for item in items:
        key = str(item.get("vat_rate"))
        sums[key] = round(sums.get(key, 0) + item.get("line_total", 0), 2)
    expected_nets = data.get("totals", {}).get("net_by_vat_rate", {})
    errors = []
    for rate in sorted(set(sums) | set(expected_nets)):
        if not close_enough(sums.get(rate), expected_nets.get(rate)):
            errors.append(f"{rate}%: line sum {sums.get(rate)} vs subtotal {expected_nets.get(rate)}")
    add_check(report, "V2", not errors,
              "Line totals reconcile to net subtotals by VAT rate." if not errors else "; ".join(errors))

    # V3: net subtotal × VAT rate = VAT amount.
    errors = []
    nets, vats = data.get("totals", {}).get("net_by_vat_rate", {}), data.get("totals", {}).get("vat_by_vat_rate", {})
    for rate in set(nets) | set(vats):
        try:
            calculated_vat = round(nets[rate] * int(rate) / 100, 2)
        except (ValueError, TypeError):
            errors.append(f"invalid VAT rate key {rate!r}")
            continue
        if not close_enough(calculated_vat, vats.get(rate)):
            errors.append(f"{rate}%: calculated VAT {calculated_vat:.2f} vs printed {vats.get(rate)}")
    add_check(report, "V3", not errors,
              "VAT amounts agree with net subtotals and rates." if not errors else "; ".join(errors))

    # V4: net + VAT = gross.
    totals = data.get("totals", {})
    net_total, vat_total, gross_total = totals.get("net_total"), totals.get("vat_total"), totals.get("gross_total")
    ok = None not in (net_total, vat_total, gross_total) and close_enough(round(net_total + vat_total, 2), gross_total)
    add_check(report, "V4", bool(ok),
              "Net total + VAT total equals gross total." if ok else
              f"Totals do not reconcile: net {net_total} + VAT {vat_total} vs gross {gross_total}.")

    # V5: German VAT ID format.
    vat_id = data.get("supplier", {}).get("vat_id")
    ok = bool(vat_id and GERMAN_VAT_ID.fullmatch(vat_id))
    add_check(report, "V5", ok, "Supplier VAT ID matches DE followed by 9 digits." if ok else f"Invalid German VAT ID: {vat_id!r}.")

    # V6: ISO dates are valid and due date cannot precede document date.
    errors, parsed = [], {}
    for field in ("document_date", "service_date", "due_date"):
        value = data.get(field)
        if value is None and field != "document_date":
            continue
        try:
            parsed[field] = date.fromisoformat(value)
        except (TypeError, ValueError):
            errors.append(f"{field} is not a valid ISO date: {value!r}")
    if "document_date" in parsed and "due_date" in parsed and parsed["due_date"] < parsed["document_date"]:
        errors.append("due_date is before document_date")
    add_check(report, "V6", not errors,
              "Dates are valid ISO dates and due date is not before document date." if not errors else "; ".join(errors))

    # V7: invoices are positive; credit notes are negative.
    errors = []
    expected_credit = data.get("document_type") == "credit_note"
    for item in items:
        amount = item.get("line_total")
        if amount is not None and ((amount > 0) if expected_credit else (amount < 0)):
            errors.append(f"position {item.get('position')} has unexpected line_total sign {amount}")
    for field in ("net_total", "vat_total", "gross_total"):
        amount = totals.get(field)
        if amount is not None and ((amount > 0) if expected_credit else (amount < 0)):
            errors.append(f"{field} has unexpected sign {amount}")
    add_check(report, "V7", not errors,
              "Invoice amounts are positive; credit-note amounts are negative." if not errors else "; ".join(errors))

    report["summary"]["passed"] = sum(c["status"] == "PASS" for c in report["checks"])
    return report


def main():
    parser = argparse.ArgumentParser(description="Validate extracted invoice JSON (V1–V7)")
    parser.add_argument("json_path", help="Path to extracted invoice JSON")
    parser.add_argument("--schema", default="output_schema.json", help="Path to assignment JSON schema")
    parser.add_argument("--report", help="Optional path to write validation report JSON")
    args = parser.parse_args()

    data = json.loads(Path(args.json_path).read_text(encoding="utf-8"))
    schema_path = Path(args.schema)
    schema = json.loads(schema_path.read_text(encoding="utf-8")) if schema_path.exists() else None
    report = validate_invoice(data, schema)

    for check in report["checks"]:
        print(f"[{check['status']}] {check['rule']}: {check['message']}")
    summary = report["summary"]
    print(f"\nSummary: {summary['passed']} passed, {summary['failures']} failed, {summary['warnings']} warning(s)")
    if args.report:
        output = Path(args.report)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Report written to: {output}")
    raise SystemExit(1 if summary["failures"] else 0)


if __name__ == "__main__":
    main()
