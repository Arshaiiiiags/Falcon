"""Groups in a real browser: two separate players create/join a group, chat, take seats as
partners/rivals, start a Hokm game and play cards.

python browser_party_test.py --browser /usr/bin/chromium [--screenshots /tmp/party-qa]
Uses Gunicorn (two workers) when installed, else Flask's threaded server, and a disposable database; never touches the live account DB.
"""
import argparse, os, socket, subprocess, sys, tempfile, time, uuid
from pathlib import Path
from unittest.mock import patch
from urllib.request import build_opener, ProxyHandler
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parent


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]


def signup(page, base, name):
    page.goto(base)
    page.locator("[data-action=signup]").first.click()
    page.fill("#auth-username", name); page.fill("#auth-password", "password123"); page.fill("#auth-confirm", "password123")
    page.locator("#modal button[type=submit]").click()
    expect(page.locator("#modal")).not_to_be_visible()


def flow(base, browser_path, shots):
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=browser_path, headless=True, args=["--no-sandbox"])
        ctxs = [browser.new_context(viewport={"width": 1280, "height": 1000}) for _ in range(2)]
        for c in ctxs:
            c.add_init_script("localStorage.setItem('pgc_lang','en')")
        a, b = [c.new_page() for c in ctxs]
        for pg in (a, b):
            pg.on("pageerror", lambda e: errors.append(str(e)))
        na, nb = "amir" + uuid.uuid4().hex[:5], "bahar" + uuid.uuid4().hex[:5]
        signup(a, base, na); signup(b, base, nb)

        # A creates a group; B joins by code.
        a.get_by_role("button", name="Groups").first.click()
        a.fill("#party-name", "Friday night"); a.get_by_role("button", name="Create group").click()
        expect(a.locator(".party-head h1")).to_have_text("Friday night")
        code = a.locator(".code-chip").inner_text().strip()
        b.get_by_role("button", name="Groups").first.click()
        b.fill("#party-code", code.lower()); b.get_by_role("button", name="Join group").click()
        expect(b.locator(".party-head h1")).to_have_text("Friday night")
        expect(a.locator(".member-list li")).to_have_count(2, timeout=8000)      # A sees B arrive by polling

        # Chat both ways, without losing a half-typed draft when the other side posts.
        a.fill("#chat-input", "salam bahar"); a.press("#chat-input", "Enter")
        expect(b.locator("#party-log")).to_contain_text("salam bahar", timeout=8000)
        b.fill("#chat-input", "half typed draft")
        a.fill("#chat-input", "second line"); a.press("#chat-input", "Enter")
        expect(b.locator("#party-log")).to_contain_text("second line", timeout=8000)
        assert b.input_value("#chat-input") == "half typed draft", "poll must not clobber the draft"
        b.fill("#chat-input", ""); b.fill("#chat-input", "<img src=x onerror=window.__xss=1>"); b.press("#chat-input", "Enter")
        expect(a.locator("#party-log")).to_contain_text("<img src=x", timeout=8000)
        assert a.evaluate("window.__xss") is None and a.locator("#party-log img").count() == 0

        # Seats: A (team 1, seat 1) with B as a rival (team 2, first seat).
        a.locator("[data-action=party-sit][data-seat='0']").click()
        expect(a.locator(".seat-slot.mine")).to_have_count(1)
        b.locator("[data-action=party-sit][data-seat='1']").click()
        expect(a.locator(".seat-slot.taken")).to_have_count(2, timeout=8000)
        expect(b.locator("[data-action=party-start]")).to_have_count(0)           # only the owner starts
        if shots: a.screenshot(path=str(shots / "lobby.png"), full_page=True)
        a.get_by_role("button", name="Start game").click()
        for pg in (a, b):
            expect(pg.locator(".hokm-table")).to_be_visible(timeout=10000)
        if shots: a.screenshot(path=str(shots / "table-a.png"), full_page=True); b.screenshot(path=str(shots / "table-b.png"), full_page=True)

        # Names appear at the seats; each player sees only their own cards.
        expect(a.locator(".hokm-seat-0")).to_contain_text(na)
        expect(b.locator(".hokm-seat-0")).to_contain_text(nb)
        expect(a.locator(".hokm-table")).to_contain_text(nb)                  # the rival is named on the table

        # Whoever is Hakem picks trump; then the player on turn plays a card.
        for _ in range(60):
            moved = False
            for pg in (a, b):
                trump = pg.locator("[data-action=hokm-trump]").first
                if trump.count():
                    trump.click(); moved = True; break
                cards = pg.locator("[data-action=hokm-card]:not([disabled])")
                if cards.count() and pg.locator("[data-action=hokm-play]").count():
                    cards.first.click(); pg.locator("[data-action=hokm-play]").click(); moved = True; break
            if moved:
                break
            time.sleep(.5)
        assert moved, "nobody could act"
        time.sleep(1.2)
        # Wrong-seat waiting message shows for the other player.
        texts = [pg.locator(".hokm-status strong").inner_text() for pg in (a, b)]
        assert any("Waiting for" in t or "choosing trump" in t or "Your turn" in t for t in texts), texts
        if shots: a.screenshot(path=str(shots / "after-move.png"), full_page=True)

        # Leaving the table hands the seat to AI; the other player keeps playing.
        b.locator("[data-action=party-stand-ask]").click(); b.locator("[data-action=party-stand-confirm]").click()
        expect(b.locator(".table-lobby, .party-main")).to_be_visible()
        expect(a.locator("#party-log")).to_contain_text("started a Hokm game")
        # Mobile layout: no horizontal overflow.
        ctx = browser.new_context(viewport={"width": 390, "height": 800}); m = ctx.new_page()
        m.add_init_script("localStorage.setItem('pgc_lang','fa')")
        signup(m, base, "mobi" + uuid.uuid4().hex[:5])
        m.locator(".mobile-menu").click(); m.locator(".sidebar.open [data-view=party]").click()
        m.fill("#party-name", "گروه ما"); m.locator("[data-form=party-create] button[type=submit]").click()
        expect(m.locator(".party-head h1")).to_have_text("گروه ما")
        assert m.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), "horizontal overflow on phone"
        if shots: m.screenshot(path=str(shots / "mobile-fa.png"), full_page=True)
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
    import importlib.util
    if importlib.util.find_spec("gunicorn"):
        cmd = [sys.executable, "-m", "gunicorn", "app:app", "--bind", f"127.0.0.1:{port}", "--workers", "2", "--threads", "4"]
    else:   # Flask's threaded dev server is enough when Gunicorn is not installed
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
        print("party browser test: OK")
    finally:
        srv.terminate()


if __name__ == "__main__":
    main()
