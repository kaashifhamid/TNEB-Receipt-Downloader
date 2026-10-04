import os
import re
import csv
import sys
import time
from datetime import datetime
from playwright.sync_api import sync_playwright

def normalize_date_for_portal(date_str):
    if not date_str:
        return ""
    date_str = date_str.strip()

    # Pattern: DD-MM-YYYY or DD/MM/YYYY or DD.MM.YYYY
    m = re.match(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})$", date_str)
    if m:
        day, month, year = m.groups()
        return f"{int(day):02d}/{int(month):02d}/{year}"

    # Pattern: YYYY-MM-DD or YYYY/MM/DD
    m = re.match(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$", date_str)
    if m:
        year, month, day = m.groups()
        return f"{int(day):02d}/{int(month):02d}/{year}"

    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d.%m.%Y", "%d %b %Y", "%d-%b-%Y"):
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%d/%m/%Y")
        except ValueError:
            pass

    return date_str.replace("-", "/").replace(".", "/")


def format_filename(date_str, consumer_no, receipt_no):
    norm = normalize_date_for_portal(date_str)
    try:
        dt = datetime.strptime(norm, "%d/%m/%Y")
        date_formatted = dt.strftime("%Y-%m-%d")
    except Exception:
        date_formatted = date_str.replace('/', '-').replace(':', '-')
        
    safe_consumer = re.sub(r'[\\/*?:"<>|]', '_', consumer_no.strip())
    safe_receipt = re.sub(r'[\\/*?:"<>|]', '_', receipt_no.strip())
    return f"{date_formatted} ; {safe_consumer} ; {safe_receipt}.pdf"


def process_csv(csv_path):
    if not os.path.exists(csv_path):
        print(f"[-] Error: CSV file '{csv_path}' does not exist.")
        sys.exit(1)
        
    records = []
    with open(csv_path, mode='r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        header = next(reader, None)
        print("CSV Header detected:", header)

        # Default indices:
        # Col 0: Consumer Number
        # Col 1: Collection Date (Col 22)
        # Col 2: Receipt No (Col 21)
        c_idx, d_idx, r_idx = 0, 1, 2
        
        # If header exists, auto-map columns intelligently
        if header:
            lower = [h.strip().lower() for h in header]
            for i, h in enumerate(lower):
                if "consumer" in h:
                    c_idx = i
                elif "receipt" in h:
                    r_idx = i
                elif "collection" in h or "col 22" in h or ("date" in h and "due" not in h and "bill" not in h and "entry" not in h):
                    d_idx = i
            print(f"Mapped columns -> Consumer: Col {c_idx}, Date: Col {d_idx}, Receipt: Col {r_idx}")

        for row_idx, row in enumerate(reader, start=2):
            if not row or not any(row):
                continue
            row = [cell.strip() for cell in row]
            
            # Extract based on mapped indices
            consumer_val = row[c_idx] if len(row) > c_idx else ""
            date_val = row[d_idx] if len(row) > d_idx else ""
            receipt_val = row[r_idx] if len(row) > r_idx else ""

            # Intelligent fallback: If date_val doesn't look like a date, find the date cell in the row
            if not re.search(r'\d{1,2}[-/.]\d{1,2}[-/.]\d{4}', date_val):
                for cell in row:
                    if re.match(r'^\d{1,2}[-/.]\d{1,2}[-/.]\d{4}$', cell):
                        date_val = cell
                        break

            # If receipt_val doesn't look like a receipt, find receipt-like pattern
            if not re.match(r'^[A-Z0-9]{8,}$', receipt_val):
                for cell in row:
                    if re.match(r'^[A-Z]{2,}[A-Z0-9]{6,}$', cell):
                        receipt_val = cell
                        break

            if consumer_val and receipt_val and date_val:
                records.append({
                    "consumer_no": consumer_val,
                    "date": date_val,
                    "receipt_no": receipt_val,
                    "row_idx": row_idx
                })

    return records


def download_receipts(records, output_dir="receipts"):
    os.makedirs(output_dir, exist_ok=True)
    success_count = 0
    failure_count = 0
    skipped_count = 0
    
    with sync_playwright() as p:
        print("\n[*] Launching browser for receipt downloads...")
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        
        total = len(records)
        for idx, rec in enumerate(records, start=1):
            c_no = rec['consumer_no']
            r_no = rec['receipt_no']
            raw_dt = rec['date']
            portal_date = normalize_date_for_portal(raw_dt)
            filename = format_filename(raw_dt, c_no, r_no)
            output_path = os.path.join(output_dir, filename)

            print(f"\n[{idx}/{total}] Consumer: {c_no} | Receipt: {r_no} | Date: {portal_date}")

            if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
                print(f"  -> ALREADY DOWNLOADED: '{filename}' (skipping)")
                skipped_count += 1
                success_count += 1
                continue

            downloaded = False
            for attempt in range(1, 3):
                try:
                    page.goto("https://www.tnebnet.org/awp/ereceipt?execution=e1s1", timeout=30000)
                    page.wait_for_load_state("networkidle")
                    
                    page.locator("id=ereceipt:consumer").fill(c_no)
                    page.locator("id=ereceipt:receipt").fill(r_no)
                    
                    date_input = page.locator("id=ereceipt:transaction_input")
                    date_input.fill("")
                    date_input.fill(portal_date)
                    
                    # Close datepicker
                    page.locator("text=E-Receipt Download").click()
                    page.wait_for_timeout(300)
                    
                    with page.expect_download(timeout=12000) as download_info:
                        page.locator("id=ereceipt:tt2").click()
                        
                    download = download_info.value
                    download.save_as(output_path)
                    
                    if os.path.exists(output_path) and os.path.getsize(output_path) > 500:
                        print(f"  -> SUCCESS: Saved '{filename}' ({os.path.getsize(output_path):,} bytes)")
                        success_count += 1
                        downloaded = True
                        break
                    else:
                        raise Exception("Downloaded file is empty or missing")

                except Exception as e:
                    err_box = page.locator(".ui-messages-error, .ui-message-error, .ui-messages-info, :has-text('could not be understood')")
                    if err_box.count() > 0:
                        err_text = " | ".join([t.strip() for t in err_box.all_text_contents() if t.strip()])
                        print(f"  -> PORTAL ERROR: {err_text}")
                        if "No Data Found" in err_text:
                            break
                    elif page.locator("text=No Data Found.").is_visible():
                        print(f"  -> PORTAL ERROR: No Data Found on website.")
                        break
                    else:
                        if attempt == 1:
                            print(f"  [Attempt 1/2 failed ({e}) - retrying in 2s...]", flush=True)
                            time.sleep(2)
                            continue
                        else:
                            print(f"  -> FAILED: {e}")

            if not downloaded:
                failure_count += 1

            time.sleep(1)

        browser.close()
        
    print("\n" + "=" * 60)
    print("Execution Summary:")
    print(f"  Total records : {len(records)}")
    print(f"  Successful    : {success_count} (including {skipped_count} pre-existing)")
    print(f"  Failed        : {failure_count}")
    print(f"  Receipts saved in: {os.path.abspath(output_dir)}")
    print("=" * 60)


if __name__ == "__main__":
    csv_file = None
    
    # 1. Argument
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        csv_file = sys.argv[1]
    else:
        # Candidate locations
        candidates = [
            "tneb_receipt_details.csv",
            "receipts_to_download.csv",
            r"..\02 TNEB Receipt Details\tneb_receipt_details.csv",
            os.path.join(os.path.expanduser("~"), "Desktop", "tneb_receipt_details.csv")
        ]
        for c in candidates:
            if os.path.exists(c):
                csv_file = c
                break

    if not csv_file:
        print("[-] Error: No CSV file found. Please provide path: python download_tneb_receipts.py <file.csv>")
        sys.exit(1)

    print(f"[*] Processing CSV file: {os.path.abspath(csv_file)}")
    records = process_csv(csv_file)
    print(f"[*] Valid records found: {len(records)}")
    
    download_receipts(records, output_dir="receipts")
