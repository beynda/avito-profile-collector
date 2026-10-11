# Avito Profile Collector

Python browser automation for public Avito seller profiles, with SQLite deduplication and CSV/XLSX exports. Collects visible names, links, locations, descriptions and email addresses when present. Does not collect phone numbers.

Avito targets the Russian market. This project is site-specific, not a US directory scraper. Website markup can change and access restrictions can prevent collection. CLI diagnostics and exported spreadsheet headings use English. Russian selectors and page detection remain necessary for Avito.

## Setup

Tested runtime: Python 3.13, Windows. From this folder in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
Copy-Item config.example.yaml config.yaml
```

Edit config.yaml: replace the placeholder keyword, city and service-category path. Paths are resolved relative to the configuration file. max_pages_per_query is one by default; zero means unlimited pages. Keep browser profiles and collected data private.

## Configure your task

Edit these fields in config.yaml:

| Field | Purpose |
| --- | --- |
| keywords | Search phrases for the services or products you need. You can add multiple phrases. |
| regions[].slug | City and category path copied from an Avito search URL, without the domain or query string. |
| regions[].name | City label written to the export. You can add multiple regions. |
| max_pages_per_query | Page limit for each phrase and region. Start with 1; 0 means no page limit. |
| browser.user_data_dir | Private local browser profile used to keep your session between runs. |
| output.excel_path / output.csv_path | Where to save the spreadsheets. |

For example, a search URL starting with https://www.avito.ru/rostov-na-donu/predlozheniya_uslug uses rostov-na-donu/predlozheniya_uslug as the region slug. Replace it with the path for your own city and category, and change keywords to your task. Parameters change the Avito search, not the target website.

The main output is seller profiles and listing links, not telephone contacts. Email is included only if found in visible text. Missing fields stay empty.

## Run

```powershell
.\.venv\Scripts\python.exe run.py --collect --prepare-session --config config.yaml
.\.venv\Scripts\python.exe run.py --export-only --config config.yaml
```

Running without --collect or --export-only displays help without accessing the website. Ctrl+C preserves committed database records and exports saved records before closing the browser. Incomplete queries restart from page one; successfully processed listings are skipped. A page limit does not mark a query complete. Empty databases produce no export.

The tool detects certain access restriction pages and does not save them as profiles. In visible-browser mode with an interactive terminal, collection pauses while you complete verification manually. Keep the tab open, wait for the normal page to load, then press Enter in the terminal. If access remains restricted, it waits again; type q to stop that attempt. Headless and noninteractive runs do not prompt. Browser access is not guaranteed. Only use collection where permitted by site rules and applicable requirements. This project is not a restriction bypass service.

## Browser preparation before collection

The collection browser uses a separate local profile. Your regular Chrome login is not automatically available there.

Login is optional. To pause for manual sign-in before collection, add --prepare-session. Complete verification in the opened browser, confirm that listings load, then press Enter in the terminal. Type q to cancel. Login does not guarantee access.

The browser profile, including cookies and login state, stays in the configured local data folder. Never share it or commit it. The tool does not ask for account passwords in the terminal. Export-only does not open a browser.

Ctrl+C requests a graceful stop through a separate launcher process. The current browser operation can take time to finish before export and shutdown. Avoid forcibly closing the terminal during export.

## Tests

```powershell
.\.venv\Scripts\python.exe tests/test_core.py
.\.venv\Scripts\python.exe tests/test_browser.py
.\.venv\Scripts\python.exe tests/test_shutdown.py
.\.venv\Scripts\python.exe tests/test_config.py
```

Core tests check SQLite deduplication, CSV/XLSX export and formula protection. Browser tests require installed Google Chrome and use local synthetic HTTP fixtures, never Avito. They check extraction, restricted pages, incomplete-query recovery and completed-query restart. Test data uses example.com.

Missing fields stay empty when they are not found in the visible page. A listing without a seller link is reported and left unfinished for a later retry. The tool does not guarantee complete contact details or successful extraction from every listing.

## License

MIT. Copyright (c) 2026 Beynda.
