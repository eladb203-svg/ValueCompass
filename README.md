# ValueCompass

Managing an investment portfolio and analyzing stocks according to value investing theory (Buffett and Graham scorecards, with sector-specific adaptations).
Financial data is stored in Supabase; the data collection layer is being redesigned as code-based source providers.

## Project structure

```
src/
  config.py          environment variables (Supabase, Tavily, Gemini)
  db.py              Supabase client
  clients/           external API clients (Tavily)
  models/            data normalization (company, listing, financials)
  repositories/      database access (company, listing, financial, update log)
  services/          business logic
    company_service.py             resolve / create companies and listings
    financial_year_service.py      normalize, validate and save a financial year
    financial_coverage_service.py  existing years and missing fields per company
    financial_validation_service.py
    web_access_service.py
supabase/migrations/ database migrations
docs/                scoring, sector methodology and reference documents
```

## Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create a `.env` file in the project root (never commit it):

```
SUPABASE_URL=
SUPABASE_SECRET_KEY=
TAVILY_API_KEY=
GEMINI_API_KEY=
GEMINI_MODEL=
```

## Documentation

See [docs/README.md](docs/README.md). The English documents are the source of truth; the Hebrew ones are translations.
