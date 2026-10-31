# UI redesign · October 29, 2026

## What changed

The user requested installing and applying [pbakaus/impeccable](https://github.com/pbakaus/impeccable) after rejecting generic marketing/dashboard styling. The existing request for a clean game hub, with Papergames/Poki/Lichess as reference directions, supplied the brief.

- Removed the oversized marketing hero and decorative club slogans.
- Replaced wood wallpaper and gold decoration with a neutral shell, quiet sidebar, one primary action color and clear active navigation.
- Moved Hokm, backgammon and Pasur into immediate view on desktop. Game tiles use actual bundled raster cards and board artwork.
- Made play controls explicit, shortened English/Persian copy and increased readable interface type.
- Kept history, rankings, rules, authentication, setup, five themes and the mobile drawer working through existing handlers.
- Applied shared tokens to dialogs, settings, tables and game controls; retained physical board geometry, card faces, cloth, wood and checker materials.
- Updated the public-shell cache version. API requests remain excluded from offline caching.
- Added browser_ui_test.py and durable product/design documentation.

No backend rules, AI, schema, account records, balances or saved matches were changed by the redesign.

## Impeccable installation and usage

Installed globally at `~/.codex/skills/impeccable` using the Codex skill-installer GitHub helper, from `.agents/skills/impeccable` in the repository. Source inspected at commit `e67a3be565fbad97b967f1c736dc246da0896f42`, skill version 4.8.0. The skill is available to subsequent Codex turns. The verified engine is cached at `~/.impeccable/bin/0.1.18/impeccable`.

Applied the skill's Operate, new-work and craft-floor guidance. The engine's initial context download stalled, and the documented fallback (read project context and the written references directly) was used. The work follows the user's established familiar-hub direction and was built directly in code. No image comp or concept-selection round was used or claimed.

The engine was subsequently downloaded successfully and SHA256-verified against its pinned manifest. Source and rendered desktop/mobile scans completed. The initial scan reported two desktop readability findings (small sidebar text) and four source findings in superseded synthetic-card/material CSS. These were addressed in one final batch: larger sidebar text, removed unused face styles/background, neutral shadow. Paragraph wrapping was improved for two advisory Persian widows. Source palette/type advisories include retained gameplay styling; no claim of a zero-finding source scan is made. Pre-fix detector JSON is retained in TESTING.md.

A fresh independent finish reviewer visually inspected six captures: desktop hub, Persian mobile hub, dark desktop hub, Hokm, backgammon and mobile Pasur. Its disposition was `ship` for that visual scope. The registered skill-specific reviewer type was unavailable, so an equivalent fresh reviewer was used. A separate documenter checked the implementation and wrote token-bearing DESIGN.md and `.impeccable/design.json`. The final targeted review scored every readability/cleanup fix resolved, with no visible regression in the six recaptures. See TESTING.mdvisual-review.md.

## Verification

- 159 unit/API/engine/regression tests passed in 115.562 seconds.
- Classic browser flow passed: signup, moves, saved-match resume, resignation, filters, themes, locales, rules, mobile menu/Escape, offline shell and recovery.
- Hokm browser flow passed: first-five/trump/deal, complete match to seven, legal moves, trick/hand acknowledgment, refresh/resume, history, rankings and resignation.
- New hub matrix passed in English and Persian, all five themes, at 320/390/768/1024/1440px. Checks include no horizontal page overflow, all tile imagery loaded, registration and keyboard dismissal, no JS errors or failed asset requests.
- axe-core 4.10.3 WCAG A/AA checks passed on the audited hub/settings/modal/game/account screens and states.

Logs: `TESTING.md`. Automated browser checks use isolated temporary databases and two Gunicorn workers. These are Chromium checks, not a claim of physical iOS/Android or manual screen-reader verification. AI strength is unchanged and not newly benchmarked.

## Running and editing

See README.md for startup. The frontend requires no build step. Edit `app.js`, `i18n.js` and `style.css`; keep the physical table seating rules intact. Change the service-worker cache name when replacing the shell. Consult DESIGN.md for the actual implemented system and ASSETS.md for provenance.
