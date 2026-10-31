# SKINSHIFT
Two separate sign-in pages on one FastAPI service: `/app` (participants) and `/research` (researchers). Both show the data-use notice first and require acknowledgement; each login records the notice version.

## Run
    pip install -r requirements.txt
    DEV=1 RESEARCHER_EMAIL=r@lab.org RESEARCHER_PASSWORD='change-me-please' uvicorn app.main:app
    pytest

Docker: `SECRET_KEY=$(openssl rand -hex 32) RESEARCHER_EMAIL=... RESEARCHER_PASSWORD=... docker compose up --build`

## What it does
Participant: register/login, daily check-in with Open-Meteo UV/PM2.5/humidity (source recorded, "unavailable" if the call fails), personal twin (per-person ridge regression, shown after 8 days), research-consent toggle, JSON export, account deletion.
Researcher: admin-issued accounts, aggregates from opted-in users only, groups under 5 suppressed, every query audit-logged.
Security: scrypt hashes, HttpOnly SameSite=Strict role-specific cookies, login throttling, CSP and no inline scripts, SECRET_KEY required outside DEV.

## Before real users (not done here)
Run behind HTTPS; move to PostgreSQL and a shared rate-limit store; email verification, password reset and MFA (especially researchers); encryption at rest and backups; legal review under India’s DPDP Act; ethics approval; photo features; instrument (TEWL/hydration) imports; mixed-effects/XGBoost models.

## Data pipeline (real data)
    pip install -r requirements.txt
    python -m pipeline.ingest --start 2024-01-01 --end 2025-12-31      # Open-Meteo + NASA POWER (+ OpenAQ if OPENAQ_API_KEY is set)
    EXPORT_SALT=<secret> python -m pipeline.export                       # opted-in, de-identified check-ins
    python -m pipeline.train                                             # writes reports/metrics.json
CPCB: download station CSVs from the CPCB portal and load them with `pipeline.ingest.load_csv`. Ingestion was written against the public API docs and unit-tested with mocked responses; run it once with network access and check the output before trusting it. Training refuses to run below 20 participants / 500 next-day rows.

## Consumer app (four tabs)
Home (one recommendation or “no change needed”, with why, confidence and evidence; alerts respect quiet mode), My Skin (profile, check-in, twin, consent, export/delete), My Products (routine, ingredient functions, avoid-list flags, duplicate and active-combination cautions), Ask SKINSHIFT (rule-based answers and escalation to a doctor for concerning symptoms; not an LLM).

## Researcher tools
`/research` after sign-in: cohorts, data-quality monitoring (completeness, dropout, city imbalance, warnings), hypotheses derived from cohort effects, the latest model report, and a city-day aggregate download (cells under 5 people are never released). All queries are audit-logged. Create accounts with `python -m app.admin create-researcher EMAIL PASSWORD`.

## AI assistant and alerts
Set `NVIDIA_API_KEY` (from build.nvidia.com) and optionally `NVIDIA_MODEL` (default `nvidia/nemotron-3.5-super-vl-120b-a12b`). Verify with `python -m app.check_llm` before relying on it. Deterministic rules answer purchase, combination and ingredient questions first and escalate worrying symptoms to a doctor before any model is called; the model answers only open questions, from `app/knowledge.json` (an unreviewed draft: have an expert review it), and answers containing banned claims are replaced by the rule-based reply. Product lists are sent only if the user opts in. If the key is missing or the call fails, the rule-based helper is used.
Alerts: run `python -m app.alerts` daily (cron). They appear in the Home tab as an in-app inbox; push and email delivery are not built.

## Scanning, photo check, alert delivery
- **Barcode:** camera scan (Chrome/Android `BarcodeDetector`) or typed number, looked up in Open Beauty Facts (community data, many Indian products missing). Results prefill the form; the user confirms before adding.
- **Label scan:** photo sent to the NVIDIA VL model only after explicit consent; nothing stored; result is a draft the user checks.
- **Photo check:** server-side quality checks (light, sharpness, size) and a relative redness reading computed with Pillow/numpy. Photos are discarded; only numbers are stored. Thresholds are unvalidated guesses, and the reading has not been validated across Indian skin tones. This is not a diagnosis or skin score.
- **Delivery:** email (set `SMTP_*`) and web push (`python -m app.gen_vapid`, set `VAPID_*`; push needs HTTPS). Messages are generic by design. Both are opt-in.

## Photo history (Routine > Progress)
An optional visual timeline of how your skin *looks* over time. Photos are kept only in the user's browser (IndexedDB) and are **never uploaded**, so the server holds no face photos.
- **Add:** Camera or Gallery, with a date (today by default, or an earlier date). Saved photos are re-encoded in the browser, which also strips EXIF/GPS data.
- **View:** Gallery grid with dates ("See all" for older photos), a Timeline view with gaps between photos, a full-size viewer, and a gentle two-week reminder line.
- **Compare:** tick any two photos for a Before/After slider or side-by-side view (earlier photo is always "Before").
- **Delete:** single photos or all photos; deleting the account also clears this browser's copies.
- **Optional quality check:** a separate per-photo checkbox sends that one photo to the server for light/sharpness/redness numbers, then discards it. Saving to history never needs it.
- **Does not claim:** barrier integrity, TEWL/hydration, cellular aging, oxidative stress or biological skin age. The UI says so and notes that lighting, camera, angle and make-up change how photos look.

Trade-off: photos are lost if browser data is cleared or the phone changes (the app asks the browser for persistent storage, which helps but is not a guarantee). Server-side encrypted storage should only be added after a DPDP review. Not covered by automated browser tests in `tests/`; I exercised it in headless Chromium and it should still be tried on a real phone.

UI: `static/consumer.html` + `consumer.css` use a phone-first layout with bottom navigation (Home, Routine, Care, Ask). Routine has Schedule (products) and Progress (photo history) tabs; Care holds check-in, Skin Twin, profile and data controls.

## Training data
Only one model needs training: the next-day comfort forecaster (`pipeline/train.py`). It needs two tables: environment per city-day (`pipeline.ingest`, real public data) and daily comfort check-ins per participant (`pipeline.export`, collected from consenting users). No public dataset contains the second table. Until enough real check-ins exist (20+ participants, 500+ next-day rows), `python -m pipeline.synthetic` writes clearly labelled synthetic files to test the pipeline only; never report results from them. The per-user Skin Twin trains on each user's own check-ins and needs no dataset. The photo history trains nothing.
