# Persian Game Club

A browser game club with **Pasur, Backgammon, and four-player Hokm**, computer opponents, **groups with text chat and human-vs-human Hokm tables (partners or rivals)**, Persian/English interfaces, saved matches, history, and rankings.

**Start here:** this README explains how to run the project. [The project guide](PROJECT_GUIDE.md) explains the architecture, game behavior, APIs, deployment, and remaining work. [Testing](TESTING.md) contains verification commands and results. [Asset credits](ASSETS.md) contains sources, licenses, and artwork prompts.

## Run locally

Python **3.10 or newer** is required. The source package was validated on Python 3.13.15. Run these commands inside this folder:

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock
cp .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"
```

Copy the generated value into `SECRET_KEY` in `.env`, replacing the placeholder. Keep `APP_ENV=development` for a local HTTP preview. Then start:

```sh
python app.py
```

Open **http://localhost:8000** and create an account. Each account starts with 100 play coins. Each complete match costs 5 coins. No existing accounts or game saves are included in this source package.

SQLite tables are created automatically. The default data file is `club.db` in this folder; use `DATABASE_PATH` in `.env` to choose another persistent location. The frontend needs no Node.js, npm, bundler, or build step.

## Files

```text
app.py                    Flask application, auth, routes, match lifecycle
party.py / party.js       Groups: chat, lobby seats, human-vs-human Hokm
database.py              SQLite schema, transactions, migration, backup
*_engine.py               Independent rules and AI for each game
index.html, app.js, ... *.webp  Browser code, styles, cards, textures, font, PWA (same folder)
test_*.py                Unit/API/regression test suites
run_tests.py              Runs all suites and writes test_output.txt
browser_test.py           Pasur/backgammon browser verification
browser_hokm_test.py      Complete Hokm browser-match verification
browser_ui_test.py         Hub responsiveness, locales, themes and accessibility
browser_party_test.py     Two real browsers: group, chat, seats, shared Hokm table
PRODUCT.md / DESIGN.md     Product context and implemented design system
smoke_test.py             Production-mode HTTP/concurrency checks
measure_*_ai.py           Optional AI evaluation scripts
PROJECT_GUIDE.md      Architecture, API, behavior, deployment, backlog
TESTING.md            Reproducible checks and validation results
ASSETS.md             Artwork provenance and usage
*-LICENSE.txt             Third-party asset license texts
requirements*.txt/.lock   Runtime and optional development dependencies
.env.example              Configuration template; contains no real secrets
Procfile                  Example Gunicorn command for compatible hosts
```

All Python commands run from the project root. Public files are stored under ``, while their browser URLs remain `/app.js`, `/style.css`, `/card-SA.webp`, etc. Flask only serves an explicit allowlist; source, configuration, documentation, and databases are private.

## Deploy (GitHub + Railway)

See [DEPLOY_RAILWAY.md](DEPLOY_RAILWAY.md). Required Railway variables: `APP_ENV=production`, `SECRET_KEY`, `TRUST_PROXY=1`, `DATABASE_PATH=/data/club.db` (plus a Volume mounted at `/data`). Template: `.env.railway.example`.

## Verify

```sh
python run_tests.py
```

For browser checks, install the optional development dependencies and Chromium:

```sh
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
python browser_test.py
python browser_hokm_test.py
python browser_ui_test.py
```

For an already installed browser, pass `--browser /usr/bin/chromium`. See [TESTING.md](TESTING.md) for optional accessibility audits and screenshots.

## About this clean package

The package includes complete source, required runtime assets, tests, documentation, and asset licenses. Local secrets, user databases, Git history, virtual environments, caches, generated screenshots, unused artwork originals, retired SVG game illustrations, and old handoff notes are excluded. The original working project and its live preview were preserved separately.

The frontend was redesigned using the Impeccable design skill: immediate game selection, simplified navigation, larger game artwork, consistent controls, and readable Persian/English layouts. See [the redesign notes](REDESIGN.md) and [design system](DESIGN.md).
