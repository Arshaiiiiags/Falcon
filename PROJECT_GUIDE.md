# Project guide

Source handoff: **2026-10-29**. Read `README.md` first for installation. Commands below run from the project root.

## 1. What is implemented

- Pasur and backgammon against AI, plus four-player partnership Hokm with one human and three AI players.
- Persian/RTL by default, English/LTR switch, and five saved appearance themes.
- Registration, login/logout, password changes, and server sessions.
- Match setup, legal-move controls, saved-game resume, resignation, history, filters, and pagination.
- Per-game statistics, difficulty-specific leaderboards, and server-awarded achievements.
- Transactional play-coin accounting and a daily refill for depleted accounts.
- Bundled raster cards, checker sprites, wood/cloth materials, artwork, and a local Persian/Latin font.
- **Groups:** create a group, share its 6-character code or invite link (`/?join=CODE`), text chat, and one shared table. The owner picks the game: Hokm (4 seats, partners 0+2 / 1+3 or rivals), Pasur (2 seats) or backgammon (2 seats, optional doubling cube). Empty seats are AI. Free: no coins, not in rankings.
- Installable PWA metadata and a cached public shell. Gameplay requires a server connection.

The frontend was redesigned with Impeccable guidance around the requested clean hub direction: immediate game selection, compact navigation, real game artwork and consistent controls. Product context is recorded in PRODUCT.md; implemented tokens and responsive rules are in DESIGN.md. See REDESIGN.md for the changes and verification.

## 2. Architecture and folder layout

This is a buildless Flask/SQLite app. HTML, CSS, and ES modules run directly in the browser. There is no frontend build process and no Node.js dependency for normal use.

| File/location | Responsibility |
| --- | --- |
| `app.py` | HTTP routes, authentication, CSRF, rate limits, coins, match ownership, state versions, results, rankings, and static-file allowlist |
| `database.py` | SQLite connections, schema, seed records, transactional access, migration, and online backup |
| `backgammon_engine.py` | Backgammon legality, dice, optional doubling cube, AI, and browser-safe views |
| `pasur_engine.py` | Pasur legality, scoring, configurable rules, AI, and browser-safe views |
| `party.py` | Groups API: membership, chat, lobby seats, human-vs-human Hokm / Pasur / backgammon room (blueprint, registered from `app.py`) |
| `party.js` | Groups screens: list/join, members, lobby, chat log, shared table |
| `hokm_engine.py` | Partnership Hokm, Hakem/dealing, trick play, scoring, AI, and browser-safe views |
| `index.html` | Browser entry document |
| `app.js` | Application state, screens, API requests, authentication/setup dialogs, and actions |
| `games.js` | Shared raster-card rendering plus backgammon/Pasur boards |
| `hokm.js` | Four-seat Hokm table, hand, trump controls, and hand results |
| `i18n.js` | Persian and English interface messages |
| `icons.js` | Small interface symbols |
| `style.css` | Themes, layout, responsive rules, and board presentation |
| `sw.js` | Public-shell caching and offline recovery |
| `manifest.json` | Installable-app metadata |
| `` image/font files | Required locally hosted game artwork and typography |
| `test_*.py` | Rules, API, accounting, concurrency, privacy, migration, and asset tests |
| `browser_*.py`, `smoke_test.py` | Real-browser and real-HTTP verification |
| `` | This guide, testing, asset provenance/licenses, and recorded validation |

Backend modules and tests stay at the root so their imports and execution remain straightforward. `` is a filesystem organization change; public URLs are unchanged. Source files and databases are never exposed by a general directory server.

## 3. State, requests, and persistence

The browser sends an action and the last state version it received. The server validates ownership, turn, phase, and legality. Random shuffles/dice, scores, results, and coin amounts are server-owned.

AI work runs against a snapshot outside the SQLite writer lock. The server then checks the match status and exact version again before committing. A competing move returns `409 state_conflict`; fetch the latest state rather than blindly replaying the old action. Starting an already-started engine returns its existing state.

The browser receives a public view, including its own hand and legal actions; hidden opponent hands and undealt cards remain server-side. A match is saved after every successful state-changing action. Refresh returns to the lounge; choose **Resume** in history to reopen the saved game.

SQLite tables cover users/settings, games, matches/players, versioned game states, results, coin transactions, achievements, and shared rate-limit hits. Schema version is **2** (version 2 adds `party_rooms.game` and `options_json`; older databases are upgraded in place and existing rooms stay Hokm). Startup upgrades older supported databases and idempotently seeds all three game types and achievement definitions.

## 4. Games and AI

### Hokm

A full match uses two fixed partnerships: human seat 0 plus opposite AI seat 2, against AI seats 1 and 3. Seats advance to the right. The engine draws Hakem and their partner using aces, reseats the players, and reshuffles for the actual deal. Trump is chosen from Hakem's first five cards. The remainder is dealt in 5–4–4 packets, giving thirteen cards per player.

The server enforces following suit, determines trick winners, and applies the standard 1/2/3-point ordinary/Kot/Hakem-Kot scoring. A match ends at seven points. Each full trick remains visible until **Next trick** is pressed; each completed hand waits for **Deal next hand**. Hakem retention/rotation is handled by the engine.

Rule references: [Ali Jahanshiri](https://www.jahanshiri.ir/cardgames/en/hokm) and [Pagat](https://www.pagat.com/whist/hokm.html). Local house-rule variants are not enabled. Detailed bilingual rules are available inside the app.

All three AI seats use the chosen difficulty. Easy chooses a random legal card. Medium conserves cards and accounts for partnership play. Hard samples 32 possible hidden deals consistent with public void suits and looks ahead through the current trick. It uses its own cards and public information, not actual hidden hands. This is bounded lookahead, not an expert solver; no claim of measured playing strength is made.

Hokm phases are `choose_trump`, `play`, `trick_end`, `hand_end`, and `finished`. `winner` denotes team 0 or 1. Use `can_choose_trump`, `can_continue`, and `legal_cards` to drive the UI.

### Backgammon

The human plays ivory checkers from point 24 toward point 1. The engine enforces legal dice use, bar entry, hits, and bearing off. The optional doubling cube adds roll/double/take/drop decisions. Normal/gammon/backgammon wins and the cube affect results. See `backgammon_engine.py` for the exact rules and AI implementation.

### Pasur

The engine implements sum-to-eleven captures, face-card captures, Sur, and round scoring. Rules are validated and fixed when a match starts. `DEFAULT_RULES` and its validation ranges in `pasur_engine.py` are the source of truth. The original incomplete specification is unavailable; these defaults have not been reconciled with it. Custom rules are excluded from standard-rule leaderboards.

## 5. HTTP API

All `/api/` responses are JSON and use `Cache-Control: no-store`. Errors use `{"error":"code"}`. Sign in and retain the session cookie. Obtain a CSRF token from `/api/csrf` or a returned `csrf` field; send `X-CSRF-Token` on every non-GET API request. Replace the token when the server rotates it.

| Area | Endpoints |
| --- | --- |
| Health/token | `GET /api/health`, `GET /api/csrf` |
| Accounts | `POST /api/register`, `/api/login`, `/api/logout`, `/api/password`; `GET /api/me` |
| Preferences | `PUT /api/settings` |
| Coins | `POST /api/coins/refill` |
| Matches | `POST /api/matches`, `/api/matches/{id}/activate`, `/api/matches/{id}/cancel` |
| History | `GET /api/matches?game=&status=&result=&from=&to=&limit=&offset=` |
| Backgammon | `GET /api/matches/{id}/bg`; `POST` to `/bg/start`, `/bg/move`, `/bg/roll`, `/bg/double`, `/bg/respond`, `/bg/resign` |
| Pasur | `GET /api/matches/{id}/pasur`; `POST` to `/pasur/start`, `/pasur/move`, `/pasur/resign` |
| Hokm | `GET /api/matches/{id}/hokm`; `POST` to `/hokm/start`, `/hokm/trump`, `/hokm/move`, `/hokm/continue`, `/hokm/resign` |
| Progress | `GET /api/achievements`, `GET /api/leaderboard?game=&level=` |

Create payload: `{game: "hokm", idem_key: "a-unique-request-id"}`. Supported games are `hokm`, `pasur`, and `backgammon`. Reuse the same idempotency key only to retry the same create request; another game with that key is rejected without a second charge. Activate the pending match, then start its engine.

Start payloads accept `level: "easy" | "medium" | "hard"`. Backgammon also accepts `cube: true`; Pasur accepts a validated `rules` object. Game-action payloads are:

- Backgammon move: `{src, dst, die, version}`; roll/double: `{version}`; cube response: `{accept, version}`.
- Pasur move: `{card, capture: [card_ids], version}`.
- Hokm trump: `{suit: "S", version}`; move: `{card, version}`; continue: `{version}`. Suits are C/D/H/S.
- Resign: POST to that game's `/resign` endpoint. The server records the loss and terminates the saved state.

Engine responses include `match_id`, `version`, `match_status`, and `state`. Card IDs are suit plus rank, for example `SA`, `H10`, or `CQ`.

History dates use YYYY-MM-DD. Limit is 1–100 (default 100); offset defaults to 0. The response includes `pagination.has_more`. Results are ordered newest first. Offset pages can shift as new matches are added.

### Groups (human multiplayer)

Tables: `parties`, `party_members`, `party_messages`, `party_rooms` (one room per group: `game` = `hokm`/`pasur`/`backgammon`, seats, level, `options_json` such as `{"cube":true}`, state, version). Limits: 8 members per group, 10 groups per user, 500-character messages (control and bidi-override characters removed), 6 messages per 10 s per user.

| Endpoint | Purpose |
| --- | --- |
| `GET/POST /api/parties`, `POST /api/parties/join` | list mine, create `{name}`, join `{code}` |
| `GET /api/parties/{id}?after=<msg id>` | poll: members (online flag), room, new chat lines |
| `POST /api/parties/{id}/messages` / `leave` / `kick` | chat `{text}`, leave, owner removes `{user_id}` |
| `POST /api/parties/{id}/room/seat` | `{seat: 0-3}` (Hokm) or `{seat: 0-1}` (Pasur, backgammon) to sit in the lobby, or `{seat: null}` to stand up (AI takes over mid-game) |
| `POST /api/parties/{id}/room/settings` / `start` / `reset` | owner: `{level, game, cube}` (any subset, lobby only; changing `game` keeps people in the seats that still exist), start, back to lobby |
| `GET /api/parties/{id}/game` | the seated player's view (`game` names the game; spectators get only the summary in the poll) |
| `POST .../game/trump\|move\|continue` | Hokm actions (`version` required on every action) |
| `POST .../game/move` | Pasur `{card, capture:[ids]}`; backgammon `{src, dst, die}` in the viewer's own board orientation |
| `POST .../game/roll\|double\|respond` | backgammon with the cube: roll, offer a double, answer `{accept: bool}` |

Hokm: seats 0 and 2 are one team, 1 and 3 the other, so sitting opposite someone makes you partners. Pasur and backgammon: seats 0 and 1 face each other; every seated player sees themselves as seat 0. For backgammon, seat 1 receives a mirrored board (point `i` becomes `23-i`, colours swapped) and the server mirrors submitted moves back, so one board renderer serves both players. `public_view_for` exists in all three engines and never includes another player's hand, the deck or undealt cards. The AI fills empty seats with `play_ai_for` (Pasur, backgammon) or `play_ai_turns` (Hokm), including cube decisions in backgammon. `hokm_engine.public_view_for` re-indexes every view so the viewer is seat 0 (partner = seat 2, team 0 = your team) and never includes other hands; the existing table renderer works unchanged. Ownership passes to the oldest member when the owner leaves; an empty group is deleted.

## 6. Coins, rankings, and expiration

New accounts receive **100 play coins**. Each whole match costs **5 coins**, charged once when created. Cancel a pending match to refund the entry; activation consumes it. Wins award no extra coins. Active resignation is a loss with no refund.

When balance is below 5, the refill endpoint restores it to 100 once per UTC calendar day. The server controls the amount and prevents duplicate grants transactionally.

Rankings compare completed AI matches for one game/difficulty. Standard Pasur rules are required. History and personal stats include other supported matches. Achievements are awarded from committed results, including a separate Hokm win badge.

After 24 hours without a saved update, active matches expire lazily on the owner's next game/history request. They become `abandoned`, with no win/loss result and no refund. Pending games remain cancellable. Configure the timeout with `ABANDON_AFTER_SECONDS`.

## 7. Configuration

Copy `.env.example` to `.env` and set a random stable secret. Real environment variables override `.env` values. Never distribute `.env` or live database files with the source.

| Variable | Default / meaning |
| --- | --- |
| `APP_ENV` | `development`; set `production` behind HTTPS |
| `SECRET_KEY` | Stable random secret required in production; signs sessions |
| `DATABASE_PATH` | `club.db` next to `database.py`; persistent SQLite storage |
| `SESSION_DAYS` | 7; permanent-session lifetime |
| `TRUST_PROXY` | 0; set 1 only behind exactly one trusted reverse proxy |
| `ABANDON_AFTER_SECONDS` | 86400; inactivity timeout for active matches |
| `PORT` | 8000 for `python app.py` / the provided Procfile |

Passwords use scrypt. Password changes rotate CSRF/session state and invalidate other sessions. Auth-related rate limits are stored in SQLite so workers share them. Current responses include frame/content-type/referrer protections; production also enables secure cookies and HSTS.

## 8. Deployment and backup

The development command is `python app.py`. A production example is:

```sh
gunicorn app:app --bind 127.0.0.1:8000 --workers 2
```

Set `APP_ENV=production`, supply a strong shared secret and a persistent database path, and serve through an HTTPS reverse proxy. Secure production cookies will not maintain a session over ordinary HTTP. The Procfile binds the port supplied by a compatible hosting platform; HTTPS and persistent disk are still host configuration responsibilities.

This storage design is for one application host. Multiple workers must use the same SQLite file and secret. Horizontal deployment across multiple independent hosts requires different shared storage/session/rate-limit arrangements.

Create a consistent online backup, including committed WAL data:

```sh
python database.py --backup ../club-backup.db
```

The destination must not already exist. To restore, stop all workers, preserve the current database and its WAL/SHM files, then configure `DATABASE_PATH` to point at a verified backup before restarting. Never replace a database underneath running workers.

## 9. Editing and verification

Edit frontend files in ``; public URLs remain unchanged. When releasing changed frontend files, increment the cache name in `sw.js`. Cache version in this package is `persian-club-shell-v3-hokm`.

The service worker caches only an explicit public-shell list. It does not cache API responses or account/game state. Opening the shell offline is supported; starting/advancing matches offline is not.

Run `python run_tests.py` after rules/backend changes. Browser tests require optional development dependencies; commands and recorded results are in `TESTING.md`. Both browser scripts use disposable databases. The Hokm browser script supplies a seeded initial draw only inside its temporary test-server configuration, so human trump choice is guaranteed; live games use system randomness.

`measure_bg_ai.py` and `measure_pasur_ai.py` are optional evaluation tools, not verification that any difficulty has a particular strength.

## 10. Remaining work and limits

- User feedback on the redesigned frontend; real-device testing remains separate from automated Chromium checks.
- Confirm intended Pasur defaults against the missing original specification.
- Benchmark AI strength rather than assuming hard beats medium.
- Physical iPhone/Android touch and installation tests, broader browser coverage, and manual screen-reader checks.
- Password recovery, scheduled cleanup, and hosting-capacity measurements.
- Human-versus-human play exists in **groups** for Hokm, Pasur and backgammon. Group games are free and unranked; Pasur uses the default rules and backgammon only the optional cube as table options. Single-player matches still play against the AI only.
- Group tables have no turn timer: an idle player is replaced by AI when they stand up, leave, or the owner removes them.
- Groups use polling every 2.5 s (no websockets). Fine for friend groups on one host; very large traffic would call for push updates.

Asset origins, exact generation prompts, and third-party licenses are documented in `ASSETS.md` and `the *LICENSE.txt files`.

## 11. Packaging cleanup

The clean source package moves browser files into ``, consolidates handoff documentation into this guide, keeps all tests and runtime assets, and removes obsolete references to two unused SVG game images. Existing public URLs and game behavior are preserved.

Excluded: user accounts/saves, real secrets, Git history, virtual environments, Python/browser caches, screenshots, unused texture JPG originals, retired SVG game illustrations, old test-output duplicates, and historical AI handoff prompts. The previous working folder and its live preview were left intact. Verification results for this cleaned layout are included under `TESTING.md`.
