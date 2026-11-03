import argparse
import json
import re
from datetime import datetime
from pathlib import Path
import pymupdf

NUM = r"(?:\d{1,3}(?:\.\d{3})*|\d+)(?:,\d+)?"

def german_number(value):
    value=value.strip()
    negative=value.endswith('-') or value.startswith('-')
    value=value.strip('-').replace('.', '').replace(',', '.')
    number=float(value)
    return -number if negative else number

def german_date(value):
    value = value.strip()
    for fmt in ('%d.%m.%Y', '%d. %B %Y'):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    # German month names for new invoice layout
    months = {'Januar':'01','Februar':'02','März':'03','April':'04','Mai':'05','Juni':'06','Juli':'07','August':'08','September':'09','Oktober':'10','November':'11','Dezember':'12'}
    m = re.fullmatch(r'(\d{1,2})\.\s*([A-Za-zÄÖÜäöü]+)\s+(\d{4})', value)
    if m and m.group(2) in months:
        return f"{m.group(3)}-{months[m.group(2)]}-{int(m.group(1)):02d}"
    raise ValueError(f'Unrecognized date: {value}')

def pdf_pages(path):
    doc = pymupdf.open(path)
    try:
        return [page.get_text() for page in doc], [[b[4].strip() for b in page.get_text('blocks')] for page in doc]
    finally:
        doc.close()

def clean_lines(text):
    return [s.strip() for s in text.splitlines() if s.strip()]

def after_label(lines, label):
    for i, line in enumerate(lines):
        if line == label and i + 1 < len(lines):
            return lines[i+1]
    return None

def extract_old_items(blocks):
    items=[]
    row_re = re.compile(rf'^(\d+)\s*\|\s*([A-Z]{{2}}-\d{{5}})\s*\|\s*(.*?)\s*\|\s*({NUM})\s*\|\s*(\S+)\s*\|\s*({NUM}(?:\s+{NUM})?)\s*\|\s*(.*?)\s*\|\s*({NUM})\s*\|\s*(\d{{1,2}})\s*$')
    for block in blocks:
        # Multi-line item blocks are kept; only first line is the item row.
        row = block.splitlines()[0].strip()
        m=row_re.match(row)
        if not m: continue
        pos, sku, desc, qty, unit, price_pe, rab, total, vat = m.groups()
        price_parts=price_pe.split()
        unit_price=german_number(price_parts[0]); price_unit=german_number(price_parts[1]) if len(price_parts)>1 else 1.0
        discount=None
        # Rabat column may be blank, one value, or row's visual blank collapsed.
        rab_tokens=[x for x in rab.split() if re.fullmatch(NUM,x)]
        if rab_tokens: discount=german_number(rab_tokens[0])
        items.append(dict(position=int(pos),article_number=sku,description=desc,quantity=german_number(qty),unit=unit,unit_price=unit_price,price_unit=price_unit,discount_percent=discount,line_total=german_number(total),vat_rate=int(vat)))
    return items

def extract_old_items_by_fields(blocks):
    """Parse legacy invoice rows where PyMuPDF exposes each table cell as a line."""
    items=[]
    for block in blocks:
        row_lines=[line.strip() for line in block.splitlines() if line.strip()]
        if len(row_lines)<8 or not re.fullmatch(r'\d+',row_lines[0]) or not re.fullmatch(r'[A-Z]{2}-\d{5}',row_lines[1]):
            continue
        pos,sku=int(row_lines[0]),row_lines[1]
        # Table row cells: position, SKU, description, quantity, unit, price, PE,
        # optional discount, line total, VAT. Description continuation is a separate block.
        desc=row_lines[2]; qty=row_lines[3]; unit=row_lines[4]
        price_parts=row_lines[5].split()
        price=german_number(price_parts[0])
        if len(price_parts)>1:
            price_unit=german_number(price_parts[1]); remaining=row_lines[6:]
        else:
            price_unit=german_number(row_lines[6]); remaining=row_lines[7:]
        if len(remaining)==2:
            discount=None; total,vat=remaining
        elif len(remaining)==3:
            discount=german_number(remaining[0]); total,vat=remaining[1:]
        else:
            continue
        items.append(dict(position=pos,article_number=sku,description=desc,quantity=german_number(qty),unit=unit,unit_price=price,price_unit=price_unit,discount_percent=discount,line_total=german_number(total),vat_rate=int(vat)))
    return items

def extract_new_items(blocks):
    items=[]
    for block in blocks:
        cells=[p.strip() for p in block.splitlines() if p.strip()]
        if len(cells)<7 or not re.fullmatch(r'\d{3}',cells[0]) or not re.fullmatch(r'[A-Z]{2}-\d{5}',cells[2]): continue
        pos=int(cells[0]); qm=re.fullmatch(rf'({NUM})\s+(\S+)',cells[1])
        if not qm: continue
        qty,unit=qm.groups(); sku=cells[2]; desc=cells[3]
        unit_price=german_number(re.search(NUM,cells[4]).group())
        vat=int(re.search(r'(\d+)%',cells[5]).group(1))
        # The printed amount is followed by an optional separate rebate note and amount.
        line_total=german_number(re.search(NUM,cells[6]).group())
        discount=None
        if len(cells)>=9:
            dm=re.search(r'(\d+(?:,\d+)?)\s*%',cells[7])
            rebate_amount=german_number(re.search(NUM,cells[8]).group())
            if dm:
                discount=german_number(dm.group(1))
                line_total=round(line_total-abs(rebate_amount),2)
        items.append(dict(position=pos,article_number=sku,description=desc,quantity=german_number(qty),unit=unit,unit_price=unit_price,price_unit=1.0,discount_percent=discount,line_total=line_total,vat_rate=vat))
    return items

def extract_invoice(pdf_path):
    page_texts, page_blocks = pdf_pages(pdf_path)
    full_text='\n'.join(page_texts); lines=clean_lines(full_text)
    is_new='Rechnung Nr.' in full_text and 'Preis/Einh.' in full_text
    if is_new:
        number=after_label(lines,'Rechnung Nr.'); date_text=after_label(lines,'Rechnungsdatum'); service_text=after_label(lines,'Lieferdatum')
        cust=after_label(lines,'Kundennummer'); order=after_label(lines,'Bestellnummer'); delivery=after_label(lines,'Lieferschein')
        buyer_block=next((b for b in page_blocks[0] if b.startswith('Rheinwerk Anlagenbau AG')), '')
        buyer_lines=buyer_block.splitlines(); street=buyer_lines[2] if len(buyer_lines)>2 else None
        postal_city=buyer_lines[3] if len(buyer_lines)>3 else ''
        pm=re.match(r'(\d{5})\s+(.+)',postal_city)
        buyer={'name':'Rheinwerk Anlagenbau AG','street':street,'postal_code':pm.group(1) if pm else None,'city':pm.group(2) if pm else None,'customer_number':cust}
        items=extract_new_items(page_blocks[0])
        due_match=re.search(r'bis (\d{1,2}\.\s*[A-Za-zÄÖÜäöü]+\s+\d{4})',full_text); due=german_date(due_match.group(1)) if due_match else None
        # New-layout summary is a single PDF text block; capture tax amounts from it.
        summary=next((b for b in page_blocks[0] if b.startswith('Summe netto')), '')
        summary_lines=[line.strip() for line in summary.splitlines() if line.strip()]
        def summary_value(label):
            for i,line in enumerate(summary_lines):
                if line==label and i+1<len(summary_lines): return german_number(re.search(NUM,summary_lines[i+1]).group())
            return None
        net_total=summary_value('Summe netto'); vat19=summary_value('MwSt 19%'); vat7=summary_value('MwSt 7%')
        grossm=re.search(r'Gesamtbetrag\s*('+NUM+r')',full_text); gross=german_number(grossm.group(1)) if grossm else None
        nets={}
        for item in items: nets[str(item['vat_rate'])]=round(nets.get(str(item['vat_rate']),0)+item['line_total'],2)
        vatsby={k:v for k,v in [('19',vat19),('7',vat7)] if v is not None}
        vat_total=round(sum(vatsby.values()),2)
        cash=None
    else:
        # Standard Kessler template: header values often form a separate text block.
        number=after_label(lines,'Gutschrift-Nr.') if 'Gutschrift-Nr.' in lines else after_label(lines,'Rechnungs-Nr.')
        date_text=after_label(lines,'Datum'); service_text=after_label(lines,'Leistungsdatum')
        cust=after_label(lines,'Kunden-Nr.'); order_line=after_label(lines,'Ihre Bestellung')
        order=re.match(r'(\S+)',order_line).group(1) if order_line else None
        delivery=after_label(lines,'Lieferschein-Nr.')
        buyer_block=next((b for b in page_blocks[0] if b.startswith('Rheinwerk Anlagenbau AG')), '')
        buyer_lines=buyer_block.splitlines(); street=buyer_lines[2] if len(buyer_lines)>2 else None
        postal_city=next((line for line in lines if re.match(r'\d{5}\s+.*Duisburg',line)),None)
        pm=re.match(r'(\d{5})\s+(.+)',postal_city or '')
        buyer={'name':'Rheinwerk Anlagenbau AG','street':street,'postal_code':pm.group(1) if pm else None,'city':pm.group(2) if pm else None,'customer_number':cust}
        items=extract_old_items_by_fields([b for page in page_blocks for b in page])
        due_line=next((line for line in lines if line.startswith('Zahlbar bis ')),None)
        due_match=re.search(r'(\d{2}\.\d{2}\.\d{4})',due_line or ''); due=german_date(due_match.group(1)) if due_match else None
        nets={}; vatsby={}
        for i,line in enumerate(lines):
            m=re.match(r'Nettobetrag\s+(\d+)\s*%\s+USt$',line)
            if m and i+1<len(lines): nets[m.group(1)]=german_number(lines[i+1])
            m=re.match(r'zzgl\.\s+(\d+)\s*%\s+USt auf',line)
            if m and i+1<len(lines): vatsby[m.group(1)]=german_number(lines[i+1])
        net_total=round(sum(nets.values()),2); vat_total=round(sum(vatsby.values()),2)
        gross_match=re.search(r'(?:Rechnungsbetrag|Gutschriftsbetrag)\s+('+NUM+r'-?)\s+EUR',full_text)
        gross=german_number(gross_match.group(1)) if gross_match else None
        sk=re.search(r'Bei Zahlung bis (\d{2}\.\d{2}\.\d{4}) abzüglich (\d+(?:,\d+)?) % Skonto \(= ('+NUM+r') EUR\)',full_text)
        cash={'percent':german_number(sk.group(2)),'until':german_date(sk.group(1)),'amount':german_number(sk.group(3))} if sk else None
        service_date=german_date(service_text) if service_text else None
    vat_id_match=re.search(r'\bDE\d{9}\b',full_text)
    doc_type='credit_note' if ('GUTSCHRIFT' in full_text or 'Gutschrift-Nr.' in full_text) else 'invoice'
    # credit-note amounts in this supplied Kessler format are printed with trailing minus signs.
    if doc_type=='credit_note':
        for item in items:
            item['line_total']=-abs(item['line_total'])
        nets={k:-abs(v) for k,v in nets.items()}; vatsby={k:-abs(v) for k,v in vatsby.items()}
        net_total=-abs(net_total) if net_total is not None else None
        vat_total=-abs(vat_total) if vat_total is not None else None
        gross=-abs(gross) if gross is not None else None
    return {'document_type':doc_type,'document_number':number,'document_date':german_date(date_text),'service_date':german_date(service_text) if service_text else None,'due_date':due,'currency':'EUR','supplier':{'name':'Kessler Industrietechnik GmbH','vat_id':vat_id_match.group(0) if vat_id_match else None},'buyer':buyer,'order_reference':order,'delivery_note_number':delivery,'referenced_invoice':after_label(lines,'Bezug Rechnung') if doc_type=='credit_note' else None,'line_items':items,'totals':{'net_by_vat_rate':nets,'vat_by_vat_rate':vatsby,'net_total':net_total,'vat_total':vat_total,'gross_total':gross},'cash_discount':cash}

def main():
    parser=argparse.ArgumentParser(description='Extract Kessler invoice data from PDF')
    parser.add_argument('pdf_path'); parser.add_argument('--output')
    args=parser.parse_args(); data=extract_invoice(args.pdf_path)
    output=Path(args.output) if args.output else Path('outputs')/(Path(args.pdf_path).name+'.json')
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Extracted invoice data to: {output}')
if __name__=='__main__': main()
