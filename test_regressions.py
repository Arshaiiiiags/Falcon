"""Regression tests for input validation, accounting, sessions and concurrent AI requests."""
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from test_app import Client, appmod, reset_rate_limits


def clone(c):
    other = Client()
    other.c.set_cookie("session", c.c.get_cookie("session").value)
    other.csrf = c.csrf
    return other


class Regressions(unittest.TestCase):
    def setUp(self):
        reset_rate_limits()
        self.c = Client()
        self.name, code, _ = self.c.register()
        self.assertEqual(code, 200)

    def active(self, game="backgammon", start=True, payload=None):
        mid = self.c.new_match(game)[1]["match"]["id"]
        self.assertEqual(self.c.req("POST", f"/api/matches/{mid}/activate")[0], 200)
        path = "bg" if game == "backgammon" else "pasur"
        state = None
        if start:
            code, state = self.c.req("POST", f"/api/matches/{mid}/{path}/start", payload or {"level": "easy"})
            self.assertEqual(code, 201)
        return mid, state

    def deplete(self, balance=0):
        with appmod.db.session_scope() as s:
            s.execute("UPDATE users SET coins=? WHERE username=?", (balance, self.name))

    def test_game_field_rejects_non_strings_without_server_error(self):
        for value in ([], {}, None, 4, True):
            code, body = self.c.req("POST", "/api/matches", {"game": value, "idem_key": "bad-game-type"})
            self.assertEqual((code, body["error"]), (400, "invalid_input"))
        self.assertEqual(self.c.req("GET", "/api/me")[1]["user"]["coins"], 100)

    def test_non_ascii_csrf_header_returns_forbidden(self):
        result = self.c.c.post("/api/coins/refill", headers={"X-CSRF-Token": "é"})
        self.assertEqual((result.status_code, result.json["error"]), (403, "csrf_failed"))

    def test_idempotency_key_cannot_be_reused_for_another_game(self):
        data = {"game": "pasur", "idem_key": "shared-request-key"}
        self.assertEqual(self.c.req("POST", "/api/matches", data)[0], 201)
        code, body = self.c.req("POST", "/api/matches", dict(data, game="backgammon"))
        self.assertEqual((code, body["error"]), (409, "idempotency_conflict"))
        self.assertEqual(self.c.req("GET", "/api/me")[1]["user"]["coins"], 95)

    def test_resignation_ends_both_engine_states_and_preserves_pasur_scores(self):
        for game, path in (("backgammon", "bg"), ("pasur", "pasur")):
            mid, before = self.active(game)
            if game == "pasur":
                with appmod.db.session_scope() as s:
                    st = json.loads(s.scalar("SELECT state_json FROM game_states WHERE match_id=?", (mid,)))
                    st["scores"] = [12, 7]
                    s.execute("UPDATE game_states SET state_json=? WHERE match_id=?", (json.dumps(st), mid))
            self.assertEqual(self.c.req("POST", f"/api/matches/{mid}/{path}/resign")[0], 200)
            _, result = self.c.req("GET", f"/api/matches/{mid}/{path}")
            self.assertEqual(result["match_status"], "completed")
            self.assertEqual(result["version"], before["version"] + 1)
            self.assertEqual(result["state"]["winner"], 1)
            self.assertEqual(result["state"]["legal_moves" if path == "bg" else "legal_actions"], [])
            if game == "pasur":
                self.assertTrue(result["state"]["finished"])
                self.assertIsNone(result["state"]["turn"])
                history = self.c.req("GET", "/api/matches")[1]["matches"]
                self.assertEqual(next(m for m in history if m["id"] == mid)["score"], "12-7")

    def test_daily_refill_is_server_controlled_and_once_per_day(self):
        self.assertEqual(self.c.req("POST", "/api/coins/refill")[1]["error"], "refill_not_needed")
        self.deplete(3)
        code, body = self.c.req("POST", "/api/coins/refill", {"amount": 999999})
        self.assertEqual((code, body["coins"], body["granted"]), (200, 100, 97))
        self.deplete()
        self.assertEqual(self.c.req("POST", "/api/coins/refill")[1]["error"], "refill_already_claimed")
        with patch.object(appmod.db, "now", return_value="2099-01-02 12:00:00"):
            self.assertEqual(self.c.req("POST", "/api/coins/refill")[0], 200)

    def test_concurrent_refills_credit_once(self):
        self.deplete()
        clients = [clone(self.c) for _ in range(8)]
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda c: c.req("POST", "/api/coins/refill")[0], clients))
        self.assertEqual(results.count(200), 1)
        self.assertEqual(results.count(409), 7)
        self.assertEqual(self.c.req("GET", "/api/me")[1]["user"]["coins"], 100)
        with appmod.db.session_scope(write=False) as s:
            rows = s.all("SELECT amount,balance_after FROM coin_transactions WHERE kind='daily_refill' "
                         "AND user_id=(SELECT id FROM users WHERE username=?)", (self.name,))
        self.assertEqual([(r[0], r[1]) for r in rows], [(100, 100)])

    def test_refill_requires_authentication_and_csrf(self):
        self.assertEqual(Client().req("POST", "/api/coins/refill")[0], 401)
        self.assertEqual(self.c.req("POST", "/api/coins/refill", csrf=False)[0], 403)

    def test_password_change_revokes_other_sessions_and_rotates_csrf(self):
        other = clone(self.c)
        old_token = self.c.csrf
        code, body = self.c.req("POST", "/api/password", {"current": "password123", "new": "new-password-123"})
        self.assertEqual(code, 200)
        self.assertNotEqual(body["csrf"], old_token)
        self.assertIsNone(other.req("GET", "/api/me")[1]["user"])
        self.assertEqual(other.new_match()[0], 401)
        self.assertEqual(self.c.req("GET", "/api/me")[1]["user"]["username"], self.name)
        fresh = Client()
        self.assertEqual(fresh.req("POST", "/api/login", {"username": self.name, "password": "password123"})[0], 401)
        self.assertEqual(fresh.req("POST", "/api/login", {"username": self.name, "password": "new-password-123"})[0], 200)

    def test_inflight_old_password_login_cannot_acquire_new_session_version(self):
        fresh = Client()
        entered, release = threading.Event(), threading.Event()
        original = appmod.hasher.verify

        def pause_login(*args):
            result = original(*args)
            if threading.current_thread().name.startswith("login-race"):
                entered.set()
                if not release.wait(5): raise RuntimeError("Login test timed out")
            return result

        with patch.object(appmod.hasher, "verify", side_effect=pause_login):
            with ThreadPoolExecutor(max_workers=1, thread_name_prefix="login-race") as pool:
                login = pool.submit(fresh.req, "POST", "/api/login", {"username": self.name, "password": "password123"})
                try:
                    self.assertTrue(entered.wait(3))
                    self.assertEqual(self.c.req("POST", "/api/password", {"current": "password123", "new": "changed-password123"})[0], 200)
                finally:
                    release.set()
                self.assertEqual(login.result(timeout=3)[0], 401)
        self.assertIsNone(fresh.req("GET", "/api/me")[1]["user"])

    def test_history_pagination_and_invalid_filters(self):
        mids = [self.c.new_match()[1]["match"]["id"] for _ in range(3)]
        first = self.c.req("GET", "/api/matches?limit=2")[1]
        second = self.c.req("GET", "/api/matches?limit=2&offset=2")[1]
        self.assertEqual([m["id"] for m in first["matches"] + second["matches"]], list(reversed(mids)))
        self.assertTrue(first["pagination"]["has_more"])
        self.assertFalse(second["pagination"]["has_more"])
        for query in ("limit=0", "limit=101", "offset=-1", "limit=no", "game=chess", "result=no", "status=no"):
            self.assertEqual(self.c.req("GET", "/api/matches?" + query)[0], 400, query)

    def test_leaderboard_separates_games_levels_and_custom_rules(self):
        for game, level, rules in (("pasur", "easy", None), ("pasur", "hard", None),
                                   ("pasur", "easy", {"target_score": 1}), ("backgammon", "easy", None)):
            payload = {"level": level}
            if rules: payload["rules"] = rules
            mid, _ = self.active(game, payload=payload)
            self.c.req("POST", f"/api/matches/{mid}/{'bg' if game == 'backgammon' else 'pasur'}/resign")
        for game, level in (("pasur", "easy"), ("pasur", "hard"), ("backgammon", "easy")):
            response = self.c.req("GET", f"/api/leaderboard?game={game}&level={level}")[1]
            mine = next(r for r in response["leaderboard"] if r["username"] == self.name)
            self.assertEqual((mine["played"], mine["won"]), (1, 0))
            self.assertTrue(response["standard_rules"])
        self.assertEqual(self.c.req("GET", "/api/leaderboard?game=chess")[0], 400)

    def test_ai_does_not_lock_unrelated_writes_or_resurrect_resigned_game(self):
        for game, path in (("backgammon", "bg"), ("pasur", "pasur")):
            mid, state = self.active(game)
            payload = state["state"]["legal_moves" if path == "bg" else "legal_actions"][0]
            payload = dict(payload, version=state["version"])
            mover = clone(self.c)
            independent = Client(); independent.register()
            entered, release = threading.Event(), threading.Event()
            engine = appmod.bg if path == "bg" else appmod.ps
            original = engine.play_ai_turns

            def slow(st):
                entered.set()
                if not release.wait(5): raise RuntimeError("AI test timed out")
                return original(st)

            with patch.object(engine, "play_ai_turns", side_effect=slow):
                with ThreadPoolExecutor(max_workers=2) as pool:
                    move = pool.submit(mover.req, "POST", f"/api/matches/{mid}/{path}/move", payload)
                    try:
                        self.assertTrue(entered.wait(3))
                        unrelated = pool.submit(independent.new_match)
                        self.assertEqual(unrelated.result(timeout=3)[0], 201)
                        resign = pool.submit(self.c.req, "POST", f"/api/matches/{mid}/{path}/resign")
                        self.assertEqual(resign.result(timeout=3)[0], 200)
                    finally:
                        release.set()
                    self.assertEqual(move.result(timeout=3)[0], 409)
            result = self.c.req("GET", f"/api/matches/{mid}/{path}")[1]
            self.assertEqual((result["match_status"], result["state"]["winner"]), ("completed", 1))

    def test_competing_moves_commit_only_one_version(self):
        mid, state = self.active()
        payload = dict(state["state"]["legal_moves"][0], version=state["version"])
        clients = [clone(self.c), clone(self.c)]
        barrier = threading.Barrier(2)
        original = appmod.bg.play_ai_turns

        def simultaneous(st):
            barrier.wait(timeout=5)
            return original(st)

        with patch.object(appmod.bg, "play_ai_turns", side_effect=simultaneous):
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda c: c.req("POST", f"/api/matches/{mid}/bg/move", payload), clients))
        self.assertEqual(sorted(code for code, _ in results), [200, 409])
        result = self.c.req("GET", f"/api/matches/{mid}/bg")[1]
        self.assertEqual(result["version"], state["version"] + 1)

    def test_concurrent_starts_return_the_same_committed_state(self):
        mid, _ = self.active(start=False)
        clients = [clone(self.c), clone(self.c)]
        barrier = threading.Barrier(2)
        original = appmod.bg.new_game

        def simultaneous(*a, **kw):
            barrier.wait(timeout=5)
            return original(*a, **kw)

        with patch.object(appmod.bg, "new_game", side_effect=simultaneous):
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda c: c.req("POST", f"/api/matches/{mid}/bg/start", {"level": "easy"}), clients))
        self.assertEqual(sorted(code for code, _ in results), [200, 201])
        self.assertEqual(results[0][1], results[1][1])

    def test_rate_limits_are_shared_between_processes(self):
        for _ in range(9):  # registration already consumed one auth attempt
            self.c.req("POST", "/api/login", {"username": "absent", "password": "invalid"})
        program = "import app; c=app.app.test_client(); t=c.get('/api/csrf').json['token']; " \
                  "r=c.post('/api/login',json={'username':'absent','password':'invalid'},headers={'X-CSRF-Token':t}); print(r.status_code)"
        result = subprocess.run([sys.executable, "-c", program], cwd=Path(__file__).parent,
                                env=os.environ.copy(), capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "429")


class ConfigurationAndMigration(unittest.TestCase):
    def test_backup_includes_committed_wal_data_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.db"
            target = Path(directory) / "backup.db"
            with patch.object(appmod.db, "PATH", str(source)):
                appmod.db.init_db()
                connection = sqlite3.connect(source)
                try:
                    connection.execute("INSERT INTO users(username,username_lower,password_hash,coins,created_at) "
                                       "VALUES('backup','backup','hash',73,'2026-01-01')")
                    connection.commit()
                    appmod.db.backup_database(target)
                    with closing(sqlite3.connect(target)) as restored:
                        self.assertEqual(restored.execute("SELECT coins FROM users").fetchone()[0], 73)
                        self.assertEqual(restored.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                    original = target.read_bytes()
                    with self.assertRaises(FileExistsError): appmod.db.backup_database(target)
                    self.assertEqual(target.read_bytes(), original)
                    with self.assertRaises(FileExistsError): appmod.db.backup_database(source)
                finally:
                    connection.close()

    def test_dotenv_and_existing_database_upgrade_are_repeatable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("app.py", "database.py", "pasur_engine.py", "backgammon_engine.py", "hokm_engine.py", "party.py"):
                shutil.copy(Path(__file__).parent / name, root / name)
            dbfile = root / "old.db"
            connection = sqlite3.connect(dbfile)
            # Original schema, before the auth_version and group-game migrations.
            old_schema = appmod.db.SCHEMA.replace(
                ",\n  game TEXT NOT NULL DEFAULT 'hokm', options_json TEXT NOT NULL DEFAULT '{}'", "")
            self.assertNotIn("options_json", old_schema)
            connection.executescript(old_schema)
            connection.execute("INSERT INTO users(username,username_lower,password_hash,coins,created_at) VALUES('old','old','hash',42,'2026-01-01')")
            connection.commit(); connection.close()
            (root / ".env").write_text(f"SECRET_KEY=dotenv-test-key\nDATABASE_PATH={dbfile}\nAPP_ENV=production\n")
            env = os.environ.copy()
            for key in ("SECRET_KEY", "DATABASE_PATH", "APP_ENV"): env.pop(key, None)
            program = "import app; app.db.init_db(); print(app.IS_PROD,app.app.secret_key); " \
                      "c=app.db._connect(); print(c.execute('PRAGMA user_version').fetchone()[0]); " \
                      "print(tuple(c.execute('SELECT coins,auth_version FROM users').fetchone())); " \
                      "print(tuple(c.execute('SELECT game,options_json FROM party_rooms').fetchall())); c.close()"
            result = subprocess.run([sys.executable, "-c", program], cwd=root, env=env,
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.splitlines(), ["True dotenv-test-key", "2", "(42, 0)", "()"])
            env["SECRET_KEY"] = "environment-wins"
            result = subprocess.run([sys.executable, "-c", "import app; print(app.app.secret_key)"],
                                    cwd=root, env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "environment-wins")


class FrontendAssets(unittest.TestCase):
    def test_lobby_and_all_required_assets_are_served(self):
        client = appmod.app.test_client()
        with client.get("/") as response:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.mimetype, "text/html")
            self.assertIn(b'type="module" src="/app.js"', response.data)
        assets = ["style.css", "app.js", "games.js", "icons.js", "i18n.js", "club-art.png",
                  "club-font.ttf", "icon.svg", "sw.js"]
        for asset in assets:
            with self.subTest(asset=asset):
                with client.get("/" + asset) as result:
                    self.assertEqual(result.status_code, 200)
                    self.assertGreater(len(result.data), 0)

    def test_complete_raster_deck_and_materials(self):
        client = appmod.app.test_client()
        names = [f"card-{s}{r}.webp" for s in "CDHS"
                 for r in ("A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K")]
        names += ["card-back-raster.webp", "table-cloth.webp", "board-wood.webp",
                  "checker-ivory.webp", "checker-ebony.webp"]
        for name in names:
            with self.subTest(asset=name), client.get("/" + name) as response:
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.mimetype, "image/webp")
                self.assertEqual(response.data[:4], b"RIFF")
                self.assertEqual(response.data[8:12], b"WEBP")
        for invalid in ("card-C1.webp", "card-H11.webp", "card-XK.webp"):
            self.assertEqual(client.get("/" + invalid).status_code, 404)

    def test_manifest_icons_and_private_file_boundary(self):
        client = appmod.app.test_client()
        with client.get("/manifest.json") as response:
            manifest = response.json
        self.assertEqual(manifest["start_url"], "/")
        for image in manifest["icons"]:
            with client.get(image["src"]) as result:
                self.assertEqual(result.status_code, 200)
                if image["type"] == "image/png":
                    self.assertEqual(result.data[:8], b"\x89PNG\r\n\x1a\n")
        for private in ("app.py", "database.py", ".env", "club.db", "test_output.txt", "README.md", "PROJECT_GUIDE.md", "requirements.txt", "Procfile"):
            self.assertEqual(client.get("/" + private).status_code, 404)
        with client.get("/sw.js") as response:
            self.assertEqual(response.headers["Cache-Control"], "no-cache")


if __name__ == "__main__":
    unittest.main()
