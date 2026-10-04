# TNEB E-Receipt Bulk Downloader

A Python script that bulk-downloads electricity payment e-receipts (PDF) from the [TNEB e-receipt portal](https://www.tnebnet.org/awp/ereceipt?execution=e1s1) using a CSV list of consumer numbers, collection dates, and receipt numbers.

It automates the portal's manual form (consumer number → receipt number → transaction date → download) with [Playwright](https://playwright.dev/python/), so you can fetch dozens or hundreds of receipts unattended.

## Features

- Reads receipt details from a CSV file
- Auto-detects columns from the header (consumer, receipt, date), with fallback pattern matching if columns are misplaced
- Accepts many date formats (`DD-MM-YYYY`, `DD/MM/YYYY`, `DD.MM.YYYY`, `YYYY-MM-DD`, `DD Mon YYYY`, …) and converts them to the portal's `DD/MM/YYYY`
- Runs headless Chromium
- Retries once on transient failures
- Skips receipts already downloaded, so you can safely re-run after an interruption
- Detects portal errors such as "No Data Found" and moves on
- Prints a summary of successes, failures, and skipped files

## Requirements

- Python 3.8+
- [Playwright for Python](https://playwright.dev/python/)
- Internet access to `tnebnet.org`

## Installation

```bash
pip install playwright
playwright install chromium
```

## CSV Format

Create `tneb_receipt_details.csv` with a header row and these columns:

| Consumer Number | Collection Date (Col 22) | Receipt No (Col 21) |
|---|---|---|
| `XXXXXXXXXXXX` | `DD-MM-YYYY` | `PGIBPXXXXXXXXXX` |

Example:

```csv
Consumer Number,Collection Date (Col 22),Receipt No (Col 21)
123456789012,15-03-2025,PGIBP1234567890
123456789012,14-04-2025,PGIBP1234567891
```

Column detection is header-based:

- a header containing `consumer` → consumer number
- a header containing `receipt` → receipt number
- a header containing `collection`, or a generic `date` (excluding "due", "bill", "entry") → collection date

If no header matches, columns default to order: Consumer, Date, Receipt.

> **Privacy:** Real consumer numbers and receipt numbers are personal data. Do not commit your actual CSV or downloaded receipts to a public repository (see `.gitignore` below).

## Usage

Pass the CSV path as an argument:

```bash
python download_tneb_receipts.py tneb_receipt_details.csv
```

Or run with no arguments and the script looks for the CSV in these locations, in order:

1. `tneb_receipt_details.csv` (current folder)
2. `receipts_to_download.csv` (current folder)
3. `..\02 TNEB Receipt Details\tneb_receipt_details.csv`
4. `~/Desktop/tneb_receipt_details.csv`

## Output

PDFs are saved to a `receipts/` folder next to where you run the script, named:

```
YYYY-MM-DD ; <consumer_no> ; <receipt_no>.pdf
```

Example: `2025-03-15 ; 123456789012 ; PGIBP1234567890.pdf`

Files that already exist and are larger than 1000 bytes are skipped.

## How It Works

1. Parses the CSV and normalizes each record.
2. Opens the e-receipt page in headless Chromium.
3. Fills in consumer number, receipt number, and transaction date.
4. Clicks the download button and saves the PDF.
5. On failure, retries once after 2 seconds. If the portal reports "No Data Found", the record is marked failed without retrying.
6. Waits 1 second between records to be gentle on the server.

## Troubleshooting

| Problem | Likely cause / fix |
|---|---|
| `No CSV file found` | Pass the path explicitly as an argument |
| `No Data Found` | Consumer number, receipt number, and date don't match a receipt on the portal — check the row |
| Repeated timeouts | Portal may be slow or down; re-run later (completed files are skipped) |
| Playwright errors about missing browsers | Run `playwright install chromium` |
| Portal layout changed | Element IDs (`ereceipt:consumer`, `ereceipt:receipt`, `ereceipt:transaction_input`, `ereceipt:tt2`) in the script may need updating |

## Suggested `.gitignore`

```
receipts/
*.csv
__pycache__/
```

## Disclaimer

This is an unofficial tool, not affiliated with TNEB / TANGEDCO. It relies on the public portal's page structure, which may change without notice. Use it only for receipts you are entitled to access, keep request volume reasonable, and follow the portal's terms of use.

## License

Choose a license for your repository (e.g. MIT) and add a `LICENSE` file.
Vibe Coded and tested.
