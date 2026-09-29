# Sullivan CRE Underwriting

Local-first commercial real estate underwriting with a standalone Python engine/CLI, a React input workspace, SQLite deal storage, and a configurable HTML-to-PDF offering memorandum.

## Local setup

On Windows, see [WINDOWS_SETUP.md](WINDOWS_SETUP.md) for one-click setup.

On macOS, install the native libraries used by WeasyPrint once:

```sh
brew install pango
```

Set up Python and run the tests:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest
```

Run the API and frontend in separate terminals:

```sh
.venv/bin/uvicorn cre_model.api:app --app-dir backend --reload --port 8000
```

```sh
cd frontend
npm install
npm run dev
```

The Vite development server prints the local URL. Deal assumptions are stored in `data/deals.sqlite3` by default; set `CRE_DATABASE_PATH` to use another location.

Report images can be uploaded from section 08 of the underwriting workspace. Uploads are stored beside the configured SQLite database in a `deals-images` directory, persist with the saved deal, and can be assigned to the cover, sponsor, market, location, property, or track-record sections. JPEG, PNG, and WebP files up to 10 MB are supported. Empty slots continue to use the illustrative report assets. Uploaded images and captions still require review before external distribution.

## Commercial rent-roll import

For retail, office, and industrial deals, upload a UTF-8 CSV, XLSX, or text-extractable PDF (up to 10 MB; PDFs up to 50 pages) in the rent-roll import area. CSV/XLSX should have a header with `tenant`, `suite`, `area_sf`, `lease_start`, `lease_end`, and one of `annual_rent`, `monthly_rent`, or `rent_per_sf`. Optional columns include `lease_structure`, `market_rent_per_sf`, `vacant`, and `lease_up_date`. Dates can use `YYYY-MM-DD` or `MM/DD/YYYY`. Vacant rows need a suite and area; market rent and lease-up can be entered during review.

Review parsed rows, warnings, area totals, rent basis, rent steps, and extensions before replacing the draft's rent roll. Set a market rent for every suite and reconcile suite SF to property rentable SF. Preview and Cancel never change a deal. Apply replaces only the current in-memory rent roll; Recalculate and Save are separate actions. Upload files are not stored. Text PDFs with other layouts may not parse; scanned PDFs require OCR or a spreadsheet export. The supplied sample PDF has duplicate suite identifiers and a current-rent total that differs from its stated total, so confirm both against the source.

Commercial vacancy uses actual vacant-suite market rent below 95% occupancy. At 95% or higher, the entered vacancy assumption acts as a floor on physical vacancy loss, not an additional deduction. TI and leasing commissions are modeled below NOI at lease events; rent-step and lease-up assumptions must be verified before external use.

## Standalone underwriting and PDF

```sh
.venv/bin/python -m cre_model.run --deal sample_deal.json --output palmer.pdf
```

The calculation engine can also be imported directly from `cre_model.engine`. Input and output schemas are in `cre_model.inputs`; report configuration lives under `config/`.

## Current implementation boundary

The current slice includes monthly and annual project cash flows, multifamily unit mix, commercial lease structures, recoveries and reviewed rent-roll imports, up to three debt tranches, dated XIRR, exit-cap and hold-period sensitivities, an LP/GP waterfall, SQLite CRUD, and a 16-page placeholder-aware PDF structure. Market comparables, maps, photos, sponsor history, deal-specific legal approval, day-count variants, construction loan draw/refinance mechanics, and more complex lease options and OCR still require follow-up implementation or verified firm inputs. The sample deal is synthetic and all report/legal content must be reviewed before external distribution.