# Testing and verification

## Verified clean source package

The reorganized source package was tested on **Python 3.13.15** with system Chromium and the pinned runtime dependencies:

| Check | Result |
| --- | --- |
| Unit, API, engine, regression, and asset suites | **159 tests passed** in 115.562 seconds |
| Hub design matrix | Both locales, all five themes, five widths, settings/registration + axe; passed |
| Hokm browser flow | Complete match to 7 points; passed |
| Pasur/backgammon browser regression flow | Passed |
| Accessibility audits | axe-core WCAG A/AA checks passed for the audited screens/states |
| Responsive layouts | Persian/English at 320, 390, 768, 1024, and 1440 pixels (hub); gameplay at 320, 390, 768 and 1440 passed |
| Browser errors/assets | No JavaScript exceptions or failed asset requests observed |
| Offline shell | Public shell, private-API cache exclusion, and recovery passed |

Recorded logs are in [validation/](validation/). These checks ran against the cleaned `` layout. No live user database was used. Run times depend on hardware and concurrent load.

## Unit/API tests

Install runtime dependencies, then run from the project root:

```sh
python run_tests.py
```

The runner writes `test_output.txt`. All original tests remain, plus regressions and Hokm coverage. Tests create temporary databases.

To run individual suites:

```sh
python -m unittest test_backgammon_engine test_pasur_engine test_hokm_engine -v
python -m unittest test_app test_regressions test_hokm_api -v
```

The pure engine suites do not require Flask. API suites require the runtime dependencies.

Coverage includes legal moves, card conservation, complete AI games, follow-suit enforcement, trump selection, Kot scoring, Hakem rotation, hidden-card privacy and AI information boundaries. API coverage includes ownership/CSRF boundaries, fees/refills, idempotency, competing requests, saved states, results/achievements, password/session behavior, migration, backup, and static-asset serving.

## Browser checks

```sh
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
python browser_test.py
python browser_hokm_test.py
python browser_ui_test.py
```

Use `--browser /usr/bin/chromium` if Chromium is installed there. Each script starts and stops two Gunicorn workers and uses disposable data. Pass `--screenshots /tmp/club-screenshots` to keep captures; otherwise captures are temporary.

The general browser flow checks signup, Pasur/backgammon moves, legal controls, resume/resignation, history/rankings/settings, themes, language persistence, mobile navigation, offline recovery, and cache contents. The Hokm flow plays an entire match via the UI, then checks history, rankings, rules, and resignation. Its isolated test-server config seeds the initial draw to exercise human Hakem trump selection. That seed is not part of live runtime configuration.

### Optional accessibility audit

Install axe-core in a separate tooling directory, then pass the resulting script path:

```sh
npm install --prefix /tmp/club-qa --no-audit --no-fund axe-core
python browser_test.py --browser /usr/bin/chromium --axe /tmp/club-qa/node_modules/axe-core/axe.min.js
python browser_hokm_test.py --browser /usr/bin/chromium --axe /tmp/club-qa/node_modules/axe-core/axe.min.js
```

The recorded clean-package runs used axe-core 4.10.3. Omitting `--axe` skips those audits and reports that explicitly. npm is only needed for this optional developer tool; the app has no npm build/runtime dependency.

## Production-mode HTTP checks

```sh
python smoke_test.py
```

This separate tool starts two temporary production-mode Gunicorn workers, completes a hard backgammon game with the cube enabled, and checks duplicate charges, competing creates, overspending, duplicate refills, and shared rate limits. It uses isolated storage. It is provided for future verification; the clean-package validation logs record the unit and browser runs listed above.

## Manual checks still needed

Physical iPhone/Android touch and installation tests, other browser engines, manual screen-reader checks, realistic hosting/load tests, and measured AI-strength comparisons remain outstanding. Automated accessibility audits do not establish universal assistive-technology support.


## Groups

`python -m unittest test_party -v` covers membership, chat sanitising/rate limits, seating (partners/rivals), privacy of hands, stale versions, complete 2-human and 4-human games, leaving/kicking mid-game, and rotated views. `python browser_party_test.py --browser /path/to/chromium` drives two real browsers (chat draft survives polling, HTML in chat is inert, shared table, phone layout has no horizontal overflow). Both pass in the delivered package (full suite: see below).

### Group Pasur and backgammon tables

`python -m unittest test_party_games -v` covers: the owner choosing the game and seats following it; seat-relative views that never leak the other hand or the deck; a complete two-person Pasur game and a complete two-person backgammon game with the doubling cube, driven only through the HTTP API with random legal moves; mirrored backgammon boards and moves for seat 1; out-of-turn, illegal and stale-version rejections; AI filling an empty seat 0 or 1 (including cube decisions); leaving mid-game; spectators receiving only a summary; and the schema-2 default for existing rooms. `test_regressions` also checks the in-place upgrade of a schema-1 database. `python browser_party_games_test.py --browser /path/to/chromium` drives two real browsers through a Pasur table and a backgammon table with the cube (names instead of "AI opponent", waiting messages, the opponent's last card, seat-1 board orientation) and checks the phone layout. Full suite: 186 tests, all passing.
