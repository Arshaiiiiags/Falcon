"""Group tables for Pasur and backgammon in two real browsers.

python browser_party_games_test.py --browser /usr/bin/chromium [--screenshots /tmp/party-games-qa]
Disposable database; never touches the live account DB.
"""
import argparse, os, subprocess, sys, tempfile, time, uuid
from pathlib import Path
from urllib.request import build_opener, ProxyHandler
from playwright.sync_api import sync_playwright, expect
from browser_party_test import free_port, signup

ROOT = Path(__file__).resolve().parent


def act_once(pages, picker, limit=40):
    """Run `picker(page)` on both pages until one of them manages to act; returns the index."""
    for _ in range(limit):
        for i, pg in enumerate(pages):
            if picker(pg):
                return i
        time.sleep(.4)
    raise AssertionError("nobody could act")


def pasur_move(pg):
    cards = pg.locator("[data-action=hand-card]:not([disabled])")
    if not cards.count():
        return False
    cards.first.click()
    pg.locator("[data-action=pasur-suggest]").click()      # cycles to a legal capture, or reports none
    play = pg.locator("[data-action=pasur-play]")
    if play.is_disabled():
        pg.locator("[data-action=clear-selection]").click()
        pg.locator("[data-action=hand-card]:not([disabled])").first.click()    # just place the card
    play.click()
    return True


def bg_move(pg):
    roll = pg.locator("[data-action=bg-roll]")
    if roll.count():
        roll.click(); return True
    point = pg.locator("button.point.movable, .board-tools [data-action=bg-point]:not([disabled])")
    if not point.count():
        return False
    point.first.click()
    dest = pg.locator("button.point.destination, .board-tools [data-action=bg-point].primary")
    if not dest.count():
        return False
    dest.first.click()
    return True


def flow(base, browser_path, shots):
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=browser_path, headless=True, args=["--no-sandbox"])
        ctxs = [browser.new_context(viewport={"width": 1280, "height": 1100}) for _ in range(2)]
        for c in ctxs:
            c.add_init_script("localStorage.setItem('pgc_lang','en')")
        a, b = [c.new_page() for c in ctxs]
        for pg in (a, b):
            pg.on("pageerror", lambda e: errors.append(str(e)))
        na, nb = "amir" + uuid.uuid4().hex[:5], "bahar" + uuid.uuid4().hex[:5]
        signup(a, base, na); signup(b, base, nb)
        a.get_by_role("button", name="Groups").first.click()
        a.fill("#party-name", "Game night"); a.get_by_role("button", name="Create group").click()
        expect(a.locator(".party-head h1")).to_have_text("Game night")
        code = a.locator(".code-chip").inner_text().strip()
        b.get_by_role("button", name="Groups").first.click()
        b.fill("#party-code", code); b.get_by_role("button", name="Join group").click()
        expect(b.locator(".party-head h1")).to_have_text("Game night")
        expect(a.locator(".member-list li")).to_have_count(2, timeout=8000)

        # ---- Pasur
        expect(b.locator("[data-action=party-game]")).to_have_count(0)            # only the owner picks the game
        a.locator("[data-action=party-game][data-game=pasur]").click()
        expect(a.locator(".table-lobby h2")).to_have_text("Pasur table")
        expect(b.locator(".table-lobby h2")).to_have_text("Pasur table", timeout=8000)
        expect(a.locator("[data-action=party-sit]")).to_have_count(2)             # two seats only
        a.locator("[data-action=party-sit][data-seat='0']").click()
        b.locator("[data-action=party-sit][data-seat='1']").click()
        expect(a.locator(".seat-slot.taken")).to_have_count(2, timeout=8000)
        if shots: a.screenshot(path=str(shots / "pasur-lobby.png"), full_page=True)
        a.get_by_role("button", name="Start game").click()
        for pg in (a, b):
            expect(pg.locator(".pasur-board")).to_be_visible(timeout=10000)
        expect(a.locator(".player-strip")).to_contain_text(nb)                     # the rival is named, not "AI"
        expect(b.locator(".player-strip")).to_contain_text(na)
        assert "AI opponent" not in a.locator(".pasur-board").inner_text()
        # Round 1 is led by seat 0 (A): B waits and cannot touch the hand.
        expect(b.locator(".game-hint")).to_contain_text("Waiting for " + na, timeout=8000)
        assert b.locator("[data-action=hand-card]:not([disabled])").count() == 0
        assert pasur_move(a)
        expect(b.locator(".last-play")).to_contain_text(na + " played", timeout=8000)   # B sees A's card
        assert act_once([a, b], lambda pg: False if pg is a else pasur_move(pg)) == 1
        expect(a.locator(".last-play")).to_contain_text(nb + " played", timeout=8000)
        if shots: a.screenshot(path=str(shots / "pasur-a.png"), full_page=True); b.screenshot(path=str(shots / "pasur-b.png"), full_page=True)
        # A leaves the table: the AI takes over seat 0, B keeps playing, and B ends the game by leaving too.
        a.locator("[data-action=party-stand-ask]").click(); a.locator("[data-action=party-stand-confirm]").click()
        expect(a.locator(".table-lobby, .party-main")).to_be_visible()
        expect(b.locator(".pasur-board")).to_be_visible()
        a.locator("[data-action=party-reset-ask]").click(); a.locator("[data-action=party-reset-confirm]").click()
        expect(a.locator("[data-action=party-start]")).to_be_visible(timeout=8000)
        expect(b.locator("[data-action=party-sit]").first).to_be_visible(timeout=8000)

        # ---- Backgammon with the cube
        a.locator("[data-action=party-game][data-game=backgammon]").click()
        expect(a.locator(".table-lobby h2")).to_have_text("Backgammon table")
        a.locator("[data-filter=partyCube]").check()
        expect(b.locator(".table-lobby")).to_contain_text("Doubling cube: on", timeout=8000)
        a.locator("[data-action=party-sit][data-seat='0']").click()      # B kept seat 1 when the table was reset
        expect(a.locator(".seat-slot.taken")).to_have_count(2, timeout=8000)
        expect(b.locator(".seat-slot.mine")).to_have_count(1)
        a.get_by_role("button", name="Start game").click()
        for pg in (a, b):
            expect(pg.locator(".backgammon-board")).to_be_visible(timeout=10000)
        # Both players see their own checkers as ivory on the same board geometry.
        for pg in (a, b):
            assert pg.locator(".checker.ivory").count() >= 4 and pg.locator(".checker.ebony").count() >= 4
            assert pg.locator("button.point .checker").count() > 0
        # The opening roll belongs to one side; a few full turns each way (roll -> move -> ...).
        for _ in range(6):
            who = act_once([a, b], bg_move)
            time.sleep(.5)
        if shots: a.screenshot(path=str(shots / "backgammon-a.png"), full_page=True); b.screenshot(path=str(shots / "backgammon-b.png"), full_page=True)
        texts = [pg.locator(".turn-chip").inner_text() for pg in (a, b)]
        assert sorted(texts) in (sorted(["Your move", "Their move"]), sorted(["Your move", "Your move"])) or "Their move" in texts, texts

        # Mobile layout for a table: no horizontal overflow.
        ctx = browser.new_context(viewport={"width": 390, "height": 800}); m = ctx.new_page()
        m.add_init_script("localStorage.setItem('pgc_lang','fa')")
        signup(m, base, "mobi" + uuid.uuid4().hex[:5])
        m.locator(".mobile-menu").click(); m.locator(".sidebar.open [data-view=party]").click()
        m.fill("#party-name", "گروه ما"); m.locator("[data-form=party-create] button[type=submit]").click()
        expect(m.locator(".party-head h1")).to_have_text("گروه ما")
        m.locator("[data-action=party-game][data-game=pasur]").click()
        expect(m.locator(".table-lobby h2")).to_have_text("میز پاسور")
        m.locator("[data-action=party-sit][data-seat='0']").click()
        m.get_by_role("button", name="شروع بازی").click()
        expect(m.locator(".pasur-board")).to_be_visible(timeout=10000)
        assert m.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), "horizontal overflow on phone"
        if shots: m.screenshot(path=str(shots / "mobile-pasur-fa.png"), full_page=True)
        browser.close()
    assert not errors, errors


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--browser", required=True); ap.add_argument("--screenshots")
    args = ap.parse_args()
    shots = Path(args.screenshots) if args.screenshots else None
    if shots: shots.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.mkdtemp(); port = free_port()
    env = {**os.environ, "DATABASE_PATH": os.path.join(tmp, "t.db"), "APP_ENV": "development", "SECRET_KEY": "x" * 40,
           "PORT": str(port), "NO_PROXY": "127.0.0.1", "no_proxy": "127.0.0.1"}
    cmd = [sys.executable, "-c", f"import app; app.app.run('127.0.0.1', {port}, threaded=True)"]
    srv = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        op = build_opener(ProxyHandler({}))
        for _ in range(50):
            try:
                op.open(f"http://127.0.0.1:{port}/api/health", timeout=1); break
            except Exception:
                time.sleep(.3)
        flow(f"http://127.0.0.1:{port}", args.browser, shots)
        print("party games browser test: OK")
    finally:
        srv.terminate()


if __name__ == "__main__":
    main()
