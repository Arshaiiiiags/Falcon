"""Backend API tests.  Needs: pip install -r requirements.txt
Run: python -m unittest test_app -v
Uses a throw-away SQLite file; never touches club.db.
Run alongside the engine tests before shipping. All tests use isolated temporary storage."""
import os
import tempfile
import threading
import unittest
import uuid

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_PATH"] = os.path.join(_tmp, "test.db")
os.environ["APP_ENV"] = "development"

import app as appmod  # noqa: E402


def reset_rate_limits():
    """app.py rate-limits register/login to 10 per minute per IP, and every test client shares 127.0.0.1.
    The whole suite registers >20 users within a minute, so without this reset later tests would get 429.
    (Found by reading the code; not by running it.)"""
    with appmod.db.session_scope() as s:
        s.execute("DELETE FROM rate_limit_hits")


class Client:
    def __init__(self):
        self.c = appmod.app.test_client()
        self.csrf = self.c.get("/api/csrf").get_json()["token"]

    def req(self, method, url, data=None, csrf=True):
        h = {"X-CSRF-Token": self.csrf} if csrf else {}
        r = self.c.open(url, method=method, json=data, headers=h)
        j = r.get_json(silent=True) or {}
        if isinstance(j, dict) and j.get("csrf"):
            self.csrf = j["csrf"]
        return r.status_code, j

    def register(self, name=None, pw="password123"):
        name = name or "u" + uuid.uuid4().hex[:8]
        code, j = self.req("POST", "/api/register", {"username": name, "password": pw, "confirm": pw})
        return name, code, j

    def new_match(self, game="backgammon"):
        return self.req("POST", "/api/matches", {"game": game, "idem_key": uuid.uuid4().hex})


class AuthAndCoins(unittest.TestCase):
    def setUp(self):
        reset_rate_limits()

    def test_auth_rate_limit_returns_429(self):
        c = Client()
        codes = [c.req("POST", "/api/login", {"username": "nobody_x", "password": "wrongpass1"})[0]
                 for _ in range(11)]
        self.assertEqual(codes[:10], [401] * 10)
        self.assertEqual(codes[10], 429)

    def test_register_gives_100_coins_once(self):
        c = Client()
        _, code, j = c.register()
        self.assertEqual(code, 200)
        self.assertEqual(j["user"]["coins"], 100)
        self.assertEqual(c.req("GET", "/api/me")[1]["user"]["coins"], 100)

    def test_username_unique_case_insensitive(self):
        a, b = Client(), Client()
        name, code, _ = a.register()
        self.assertEqual(code, 200)
        _, code2, j2 = b.register(name.upper())
        self.assertEqual((code2, j2["error"]), (409, "username_taken"))

    def test_password_rules(self):
        c = Client()
        code, j = c.req("POST", "/api/register", {"username": "abcdef", "password": "short", "confirm": "short"})
        self.assertEqual((code, j["error"]), (400, "password_weak"))
        code, j = c.req("POST", "/api/register", {"username": "abcdef", "password": "password123", "confirm": "different123"})
        self.assertEqual((code, j["error"]), (400, "password_mismatch"))

    def test_login_logout_and_generic_error(self):
        c = Client()
        name, _, _ = c.register()
        c.req("POST", "/api/logout")
        self.assertIsNone(c.req("GET", "/api/me")[1]["user"])
        self.assertEqual(c.req("POST", "/api/login", {"username": name, "password": "wrongpass1"})[0], 401)
        self.assertEqual(c.req("POST", "/api/login", {"username": "nobody_x", "password": "wrongpass1"})[0], 401)
        self.assertEqual(c.req("POST", "/api/login", {"username": name, "password": "password123"})[0], 200)

    def test_csrf_required(self):
        c = Client()
        code, j = c.req("POST", "/api/register", {"username": "csrfuser", "password": "password123",
                                                   "confirm": "password123"}, csrf=False)
        self.assertEqual((code, j["error"]), (403, "csrf_failed"))

    def test_match_fee_idempotency_and_cancel_refund_once(self):
        c = Client(); c.register()
        key = uuid.uuid4().hex
        code, j = c.req("POST", "/api/matches", {"game": "pasur", "idem_key": key})
        self.assertEqual((code, j["coins"]), (201, 95))
        code, j2 = c.req("POST", "/api/matches", {"game": "pasur", "idem_key": key})  # retry: no second charge
        self.assertEqual((code, j2["charged"]), (200, False))
        self.assertEqual(c.req("GET", "/api/me")[1]["user"]["coins"], 95)
        mid = j["match"]["id"]
        self.assertEqual(c.req("POST", f"/api/matches/{mid}/cancel")[1]["coins"], 100)
        self.assertEqual(c.req("POST", f"/api/matches/{mid}/cancel")[0], 409)  # no double refund
        self.assertEqual(c.req("GET", "/api/me")[1]["user"]["coins"], 100)

    def test_no_refund_after_activate(self):
        c = Client(); c.register()
        mid = c.new_match()[1]["match"]["id"]
        self.assertEqual(c.req("POST", f"/api/matches/{mid}/activate")[0], 200)
        self.assertEqual(c.req("POST", f"/api/matches/{mid}/cancel")[0], 409)
        self.assertEqual(c.req("GET", "/api/me")[1]["user"]["coins"], 95)

    def test_insufficient_coins_and_never_negative(self):
        c = Client(); c.register()
        for _ in range(20):
            self.assertEqual(c.new_match()[0], 201)
        code, j = c.new_match()
        self.assertEqual((code, j["error"]), (402, "insufficient_coins"))
        self.assertEqual(c.req("GET", "/api/me")[1]["user"]["coins"], 0)

    def test_concurrent_creates_cannot_overspend(self):
        c = Client(); c.register()
        results = []
        def worker():
            cl = appmod.app.test_client()
            cl.set_cookie("session", c.c.get_cookie("session").value) if c.c.get_cookie("session") else None
            r = cl.post("/api/matches", json={"game": "pasur", "idem_key": uuid.uuid4().hex},
                        headers={"X-CSRF-Token": c.csrf})
            results.append(r.status_code)
        ts = [threading.Thread(target=worker) for _ in range(30)]
        [t.start() for t in ts]; [t.join() for t in ts]
        ok = results.count(201)
        coins = c.req("GET", "/api/me")[1]["user"]["coins"]
        self.assertLessEqual(ok, 20)
        self.assertEqual(coins, 100 - 5 * ok)
        self.assertGreaterEqual(coins, 0)

    def test_other_users_matches_are_private(self):
        a, b = Client(), Client(); a.register(); b.register()
        mid = a.new_match()[1]["match"]["id"]
        self.assertEqual(b.req("POST", f"/api/matches/{mid}/cancel")[0], 404)
        self.assertEqual(b.req("GET", f"/api/matches/{mid}/bg")[0], 404)

    def test_history_filters(self):
        c = Client(); c.register(); c.new_match("pasur"); c.new_match("backgammon")
        self.assertEqual(len(c.req("GET", "/api/matches?game=pasur")[1]["matches"]), 1)
        self.assertEqual(c.req("GET", "/api/matches?from=bad-date")[0], 400)
        self.assertEqual(len(c.req("GET", "/api/matches?from=2000-01-01&to=2999-01-01")[1]["matches"]), 2)


class BackgammonApi(unittest.TestCase):
    def setUp(self):
        reset_rate_limits()

    def start(self, level="easy"):
        c = Client(); c.register()
        mid = c.new_match("backgammon")[1]["match"]["id"]
        self.assertEqual(c.req("POST", f"/api/matches/{mid}/bg/start", {"level": level})[0], 409)  # not active yet
        c.req("POST", f"/api/matches/{mid}/activate")
        code, j = c.req("POST", f"/api/matches/{mid}/bg/start", {"level": level})
        self.assertEqual(code, 201)
        return c, mid, j

    def test_start_is_idempotent_and_never_rerolls(self):
        c, mid, j = self.start()
        code, j2 = c.req("POST", f"/api/matches/{mid}/bg/start", {"level": "hard"})
        self.assertEqual(code, 200)
        self.assertEqual(j["state"]["roll"], j2["state"]["roll"])
        self.assertEqual(j2["state"]["level"], "easy")

    def test_wrong_game_endpoint_rejected(self):
        c = Client(); c.register()
        mid = c.new_match("pasur")[1]["match"]["id"]
        c.req("POST", f"/api/matches/{mid}/activate")
        self.assertEqual(c.req("POST", f"/api/matches/{mid}/bg/start", {"level": "easy"})[0], 404)

    def test_illegal_move_and_stale_version(self):
        c, mid, j = self.start()
        v = j["version"]
        self.assertEqual(c.req("POST", f"/api/matches/{mid}/bg/move", {"src": 0, "dst": 0, "version": v})[1]["error"], "illegal_move")
        m = j["state"]["legal_moves"][0]
        self.assertEqual(c.req("POST", f"/api/matches/{mid}/bg/move", {"src": m["src"], "dst": m["dst"], "version": v + 5})[1]["error"], "state_conflict")

    def test_client_cannot_inject_result_or_dice(self):
        c, mid, j = self.start()
        m = j["state"]["legal_moves"][0]
        code, j2 = c.req("POST", f"/api/matches/{mid}/bg/move",
                         {"src": m["src"], "dst": m["dst"], "version": j["version"],
                          "result": "win", "winner": 0, "dice": [6, 6], "coins": 999})
        self.assertEqual(code, 200)
        self.assertIsNone(j2["state"]["winner"])
        self.assertEqual(c.req("GET", "/api/me")[1]["user"]["coins"], 95)

    def test_full_game_ends_on_server_and_is_recorded(self):
        c, mid, j = self.start("easy")
        for _ in range(3000):
            st = j["state"]
            if st["winner"] is not None:
                break
            m = st["legal_moves"][0]
            code, j = c.req("POST", f"/api/matches/{mid}/bg/move",
                            {"src": m["src"], "dst": m["dst"], "die": m["die"], "version": j["version"]})
            self.assertEqual(code, 200, j)
        self.assertIsNotNone(j["state"]["winner"])
        self.assertEqual(j["match_status"], "completed")
        me = c.req("GET", "/api/me")[1]["user"]
        self.assertEqual(me["stats"]["backgammon"]["played"], 1)
        self.assertEqual(me["coins"], 95)  # no invented rewards
        hist = c.req("GET", "/api/matches?status=completed")[1]["matches"]
        self.assertEqual(hist[0]["result"], "win" if j["state"]["winner"] == 0 else "loss")
        self.assertEqual(c.req("POST", f"/api/matches/{mid}/bg/move", {"src": 0, "dst": 1, "version": j["version"]})[0], 409)


class PasurApi(unittest.TestCase):
    def setUp(self):
        reset_rate_limits()

    def start(self, level="easy", rules=None):
        c = Client(); c.register()
        mid = c.new_match("pasur")[1]["match"]["id"]
        payload = {"level": level}
        if rules is not None:
            payload["rules"] = rules
        self.assertEqual(c.req("POST", f"/api/matches/{mid}/pasur/start", payload)[0], 409)  # not active yet
        c.req("POST", f"/api/matches/{mid}/activate")
        code, j = c.req("POST", f"/api/matches/{mid}/pasur/start", payload)
        self.assertEqual(code, 201, j)
        return c, mid, j

    def test_start_is_idempotent_and_never_redeals(self):
        c, mid, j = self.start(rules={"target_score": 30})
        code, j2 = c.req("POST", f"/api/matches/{mid}/pasur/start", {"level": "hard", "rules": {"target_score": 99}})
        self.assertEqual(code, 200)
        self.assertEqual(j["state"]["table"], j2["state"]["table"])
        self.assertEqual(j["state"]["hand"], j2["state"]["hand"])
        self.assertEqual((j2["state"]["level"], j2["state"]["rules"]["target_score"]), ("easy", 30))
        self.assertEqual(c.req("GET", f"/api/matches/{mid}/pasur")[1]["state"]["hand"], j["state"]["hand"])

    def test_bad_level_rules_and_wrong_game(self):
        c = Client(); c.register()
        mid = c.new_match("pasur")[1]["match"]["id"]
        c.req("POST", f"/api/matches/{mid}/activate")
        self.assertEqual(c.req("POST", f"/api/matches/{mid}/pasur/start", {"level": "godlike"})[0], 400)
        self.assertEqual(c.req("POST", f"/api/matches/{mid}/pasur/start", {"rules": {"nope": 1}})[0], 400)
        self.assertEqual(c.req("POST", f"/api/matches/{mid}/pasur/start", {"rules": {"target_score": "9"}})[0], 400)
        self.assertEqual(c.req("GET", f"/api/matches/{mid}/pasur")[0], 404)  # valid match, no game yet
        bgmid = c.new_match("backgammon")[1]["match"]["id"]
        c.req("POST", f"/api/matches/{bgmid}/activate")
        self.assertEqual(c.req("POST", f"/api/matches/{bgmid}/pasur/start", {"level": "easy"})[0], 404)

    def test_other_user_cannot_see_or_move(self):
        c, mid, j = self.start()
        other = Client(); other.register()
        self.assertEqual(other.req("GET", f"/api/matches/{mid}/pasur")[0], 404)
        self.assertEqual(other.req("POST", f"/api/matches/{mid}/pasur/move",
                                   {"card": j["state"]["hand"][0], "capture": [], "version": 0})[0], 404)

    def test_view_never_leaks_deck_or_ai_hand(self):
        c, mid, j = self.start()
        st = j["state"]
        self.assertNotIn("deck", st); self.assertNotIn("hands", st)
        self.assertEqual((st["deck_count"], st["opponent_hand_count"], len(st["hand"])), (40, 4, 4))

    def test_illegal_move_and_stale_version(self):
        c, mid, j = self.start()
        v = j["version"]
        for bad in ({"card": "ZZ", "capture": [], "version": v}, {"card": None, "capture": [], "version": v},
                    {"card": j["state"]["hand"][0], "capture": ["NOPE"], "version": v}):
            code, r = c.req("POST", f"/api/matches/{mid}/pasur/move", bad)
            self.assertEqual((code, r["error"]), (400, "illegal_move"), bad)
        a = j["state"]["legal_actions"][0]
        code, r = c.req("POST", f"/api/matches/{mid}/pasur/move", {**a, "version": v + 5})
        self.assertEqual((code, r["error"]), (409, "state_conflict"))
        self.assertEqual(c.req("POST", f"/api/matches/{mid}/pasur/move", {**a})[1]["error"], "invalid_input")

    def test_client_cannot_inject_result_score_or_coins(self):
        c, mid, j = self.start()
        a = j["state"]["legal_actions"][0]
        code, r = c.req("POST", f"/api/matches/{mid}/pasur/move",
                        {**a, "version": j["version"], "result": "win", "winner": 0, "scores": [999, 0],
                         "coins": 999, "deck": [], "finished": True})
        self.assertEqual(code, 200)
        self.assertFalse(r["state"]["finished"])
        self.assertEqual(r["state"]["scores"], [0, 0])
        self.assertEqual(c.req("GET", "/api/me")[1]["user"]["coins"], 95)

    def test_full_game_ends_on_server_and_is_recorded(self):
        c, mid, j = self.start("easy", rules={"target_score": 1})  # first scored round ends the game
        for _ in range(500):
            st = j["state"]
            if st["finished"]:
                break
            a = st["legal_actions"][0]
            code, j = c.req("POST", f"/api/matches/{mid}/pasur/move", {**a, "version": j["version"]})
            self.assertEqual(code, 200, j)
        st = j["state"]
        self.assertTrue(st["finished"])
        self.assertEqual(j["match_status"], "completed")
        me = c.req("GET", "/api/me")[1]["user"]
        self.assertEqual(me["stats"]["pasur"]["played"], 1)
        self.assertEqual(me["coins"], 95)  # no invented rewards
        hist = c.req("GET", "/api/matches?status=completed&game=pasur")[1]["matches"]
        expect = "draw" if st["winner"] is None else ("win" if st["winner"] == 0 else "loss")
        self.assertEqual(hist[0]["result"], expect)
        self.assertEqual(hist[0]["score"], f"{st['scores'][0]}-{st['scores'][1]}")
        self.assertEqual(c.req("GET", f"/api/matches/{mid}/pasur")[1]["state"]["finished"], True)  # viewable after
        code, r = c.req("POST", f"/api/matches/{mid}/pasur/move", {"card": "C2", "capture": [], "version": j["version"]})
        self.assertEqual(code, 409)  # match is completed -> invalid_state


class ResignAchievementsLeaderboard(unittest.TestCase):
    """Added after the sqlite3/scrypt rewrite (resign endpoints, achievements, leaderboard)."""
    def setUp(self):
        reset_rate_limits()

    def _active(self, c, game):
        _, j = c.new_match(game)
        mid = j["match"]["id"]
        self.assertEqual(c.req("POST", f"/api/matches/{mid}/activate")[0], 200)
        return mid

    def test_resign_is_a_loss_once_and_no_refund(self):
        for game, path in (("pasur", "pasur"), ("backgammon", "bg")):
            c = Client(); c.register()
            mid = self._active(c, game)
            code, j = c.req("POST", f"/api/matches/{mid}/{path}/resign")
            self.assertEqual((code, j["result"]), (200, "loss"))
            self.assertEqual(c.req("POST", f"/api/matches/{mid}/{path}/resign")[0], 409)
            self.assertEqual(c.req("GET", "/api/me")[1]["user"]["coins"], 95)  # fee kept
            h = c.req("GET", "/api/matches?result=loss")[1]["matches"]
            self.assertEqual([(m["game"], m["status"]) for m in h], [(game, "completed")])

    def test_resign_needs_active_match_and_owner(self):
        a, b = Client(), Client(); a.register(); b.register()
        _, j = a.new_match("pasur"); mid = j["match"]["id"]  # still pending
        self.assertEqual(a.req("POST", f"/api/matches/{mid}/pasur/resign")[0], 409)
        a.req("POST", f"/api/matches/{mid}/activate")
        self.assertEqual(b.req("POST", f"/api/matches/{mid}/pasur/resign")[0], 404)
        self.assertEqual(a.req("POST", f"/api/matches/{mid}/bg/resign")[0], 404)  # wrong game

    def test_achievements_are_server_side_and_leaderboard_is_public_safe(self):
        c = Client(); name, _, _ = c.register()
        for _ in range(12):  # AI is "easy": a win comes quickly; each match costs 5 coins
            mid = self._active(c, "pasur")
            _, p = c.req("POST", f"/api/matches/{mid}/pasur/start", {"level": "easy"})
            while p["match_status"] == "active":
                a = p["state"]["legal_actions"][0]
                _, p = c.req("POST", f"/api/matches/{mid}/pasur/move",
                             {"card": a["card"], "capture": a["capture"], "version": p["version"]})
            if p["state"]["winner"] == 0:
                break
        else:
            self.fail("no win in 12 easy games")
        ach = {x["key"]: x["earned"] for x in c.req("GET", "/api/achievements")[1]["achievements"]}
        self.assertTrue(ach["first_win"] and ach["pasur_win"])
        self.assertFalse(ach["backgammon_win"] or ach["ten_wins"])
        # client cannot grant achievements
        self.assertEqual(c.req("POST", "/api/achievements", {"key": "ten_wins"})[0], 405)
        rows = c.req("GET", "/api/leaderboard?game=pasur&level=easy")[1]["leaderboard"]
        mine = [r for r in rows if r["username"] == name][0]
        self.assertEqual(set(mine), {"rank", "username", "played", "won", "win_rate"})
        self.assertGreaterEqual(mine["won"], 1)

    def test_leaderboard_requires_login(self):
        self.assertEqual(Client().req("GET", "/api/leaderboard")[0], 401)

    def test_password_hash_is_scrypt_and_wrong_password_rejected(self):
        h = appmod.hasher.hash("password123")
        self.assertTrue(h.startswith("scrypt$"))
        self.assertTrue(appmod.hasher.verify(h, "password123"))
        with self.assertRaises(appmod.VerifyMismatchError):
            appmod.hasher.verify(h, "password124")
        with self.assertRaises(appmod.InvalidHashError):
            appmod.hasher.verify("garbage", "x")


class BackgammonCubeApi(unittest.TestCase):
    """Doubling cube over HTTP (new in stage 7). Controlled positions are written straight into
    game_states (test setup only); every outcome below is still decided by the server code."""
    def setUp(self):
        reset_rate_limits()

    def _start(self, cube=True, level="hard"):
        c = Client(); c.register()
        mid = c.new_match("backgammon")[1]["match"]["id"]
        c.req("POST", f"/api/matches/{mid}/activate")
        code, j = c.req("POST", f"/api/matches/{mid}/bg/start", {"level": level, "cube": cube})
        self.assertEqual(code, 201, j)
        return c, mid, j

    def _inject(self, mid, st):
        import json
        with appmod.db.session_scope() as s:
            s.execute("UPDATE game_states SET state_json=?, version=version+1 WHERE match_id=?", (json.dumps(st), mid))
            return s.scalar("SELECT version FROM game_states WHERE match_id=?", (mid,))

    def _pre_roll(self, points, turn=0, level="hard", value=1, owner=None, pending=None):
        import test_backgammon_engine as t
        return t.mkc(points, turn=turn, level=level, value=value, owner=owner, pending=pending)

    def test_start_validates_cube_and_is_off_by_default(self):
        c = Client(); c.register()
        mid = c.new_match("backgammon")[1]["match"]["id"]
        c.req("POST", f"/api/matches/{mid}/activate")
        self.assertEqual(c.req("POST", f"/api/matches/{mid}/bg/start", {"level": "easy", "cube": "yes"})[1]["error"], "invalid_input")
        code, j = c.req("POST", f"/api/matches/{mid}/bg/start", {"level": "easy"})
        self.assertEqual((code, j["state"]["cube"]["enabled"]), (201, False))
        # cube endpoints refuse a game that has no cube
        v = j["version"]
        for path, data in (("roll", {}), ("double", {}), ("respond", {"accept": True})):
            code, r = c.req("POST", f"/api/matches/{mid}/bg/{path}", dict(data, version=v))
            self.assertEqual((code, r["error"]), (409, "invalid_state"), path)

    def test_cube_game_start_view(self):
        c, mid, j = self._start(cube=True)
        st = j["state"]
        self.assertTrue(st["cube"]["enabled"])
        self.assertEqual((st["cube"]["value"], st["cube"]["owner"]), (1, None))
        self.assertNotIn("deck", st)
        again = c.req("POST", f"/api/matches/{mid}/bg/start", {"level": "easy", "cube": False})
        self.assertEqual((again[0], again[1]["state"]["cube"]["enabled"]), (200, True))  # idempotent

    def test_roll_and_double_need_the_right_moment_and_version(self):
        c, mid, j = self._start()
        v = self._inject(mid, self._pre_roll({23: 15, 22: -15}, level="easy"))
        base = f"/api/matches/{mid}/bg"
        self.assertEqual(c.req("POST", base + "/roll", {"version": v + 3})[1]["error"], "state_conflict")
        self.assertEqual(c.req("POST", base + "/roll", {"version": "1"})[1]["error"], "invalid_input")
        self.assertEqual(c.req("POST", base + "/respond", {"accept": True, "version": v})[1]["error"], "not_your_turn")  # nothing pending
        code, r = c.req("POST", base + "/roll", {"version": v, "dice": [6, 6]})  # injected dice are ignored
        self.assertEqual(code, 200)
        self.assertEqual(r["state"]["phase"] in ("move", "pre_roll"), True)
        self.assertEqual(c.req("POST", base + "/roll", {"version": r["version"]})[1]["error"] in ("not_your_turn", "illegal_move"), True)
        # cannot double after rolling (checkers must be moved first)
        if r["state"]["phase"] == "move":
            self.assertEqual(c.req("POST", base + "/double", {"version": r["version"]})[1]["error"], "illegal_move")

    def test_human_double_dropped_by_ai_is_a_server_recorded_win(self):
        c, mid, j = self._start()
        v = self._inject(mid, self._pre_roll({0: 15, 1: -15}, level="hard", value=2, owner=0))
        code, r = c.req("POST", f"/api/matches/{mid}/bg/double", {"version": v, "result": "win", "points": 999})
        self.assertEqual(code, 200, r)
        st = r["state"]
        self.assertEqual((st["winner"], st["win_type"], st["points_won"], r["match_status"]), (0, "cube_drop", 2, "completed"))
        h = c.req("GET", "/api/matches?status=completed")[1]["matches"][0]
        self.assertEqual((h["result"], h["score"]), ("win", "2-0"))
        self.assertEqual(c.req("GET", "/api/me")[1]["user"]["coins"], 95)  # no invented coins
        self.assertEqual(c.req("POST", f"/api/matches/{mid}/bg/double", {"version": r["version"]})[0], 409)  # finished

    def test_human_double_taken_by_ai_doubles_cube_and_ai_owns_it(self):
        c, mid, j = self._start()
        v = self._inject(mid, self._pre_roll({23: 15, 22: -15}, level="hard"))
        code, r = c.req("POST", f"/api/matches/{mid}/bg/double", {"version": v})
        st = r["state"]
        self.assertEqual((code, st["cube"]["value"], st["cube"]["owner"], st["winner"]), (200, 2, 1, None))
        self.assertTrue(st["can_roll"] and not st["can_double"])  # human rolls next; AI owns the cube

    def test_ai_double_human_takes_or_drops(self):
        pend = {"by": 1, "value": 2}
        for accept in (True, False):
            c, mid, j = self._start()
            st = self._pre_roll({23: 15, 22: -15}, turn=1, pending=pend)
            v = self._inject(mid, st)
            base = f"/api/matches/{mid}/bg"
            view = c.req("GET", base)[1]["state"]
            self.assertTrue(view["must_respond"] and view["cube"]["pending_by"] == 1)
            self.assertEqual(c.req("POST", base + "/roll", {"version": v})[1]["error"], "not_your_turn")
            self.assertEqual(c.req("POST", base + "/double", {"version": v})[1]["error"], "not_your_turn")
            self.assertEqual(c.req("POST", base + "/respond", {"accept": "yes", "version": v})[1]["error"], "invalid_input")
            code, r = c.req("POST", base + "/respond", {"accept": accept, "version": v})
            self.assertEqual(code, 200, r)
            if accept:
                self.assertEqual((r["state"]["cube"]["value"], r["state"]["cube"]["owner"]), (2, 0))
                self.assertIsNone(r["state"]["cube"]["pending_by"])
                self.assertEqual(r["match_status"], "active")
            else:
                self.assertEqual((r["state"]["winner"], r["state"]["points_won"], r["match_status"]), (1, 1, "completed"))
                h = c.req("GET", "/api/matches?status=completed")[1]["matches"][0]
                self.assertEqual((h["result"], h["score"]), ("loss", "0-1"))

    def test_resign_loses_the_current_cube_value(self):
        c, mid, j = self._start()
        self._inject(mid, self._pre_roll({23: 15, 22: -15}, value=4, owner=0))
        self.assertEqual(c.req("POST", f"/api/matches/{mid}/bg/resign")[0], 200)
        h = c.req("GET", "/api/matches?status=completed")[1]["matches"][0]
        self.assertEqual((h["result"], h["score"]), ("loss", "0-4"))

    def test_full_cube_game_over_http(self):
        import random
        rng = random.Random(7)
        c, mid, j = self._start(level="easy")
        for _ in range(4000):
            st = j["state"]
            if st["winner"] is not None:
                break
            v = j["version"]
            if st["must_respond"]:
                code, j = c.req("POST", f"/api/matches/{mid}/bg/respond", {"accept": rng.random() < 0.7, "version": v})
            elif st["can_roll"]:
                if st["can_double"] and rng.random() < 0.25:
                    code, j = c.req("POST", f"/api/matches/{mid}/bg/double", {"version": v})
                else:
                    code, j = c.req("POST", f"/api/matches/{mid}/bg/roll", {"version": v})
            else:
                m = rng.choice(st["legal_moves"])
                code, j = c.req("POST", f"/api/matches/{mid}/bg/move",
                                {"src": m["src"], "dst": m["dst"], "die": m["die"], "version": v})
            self.assertEqual(code, 200, j)
        st = j["state"]
        self.assertIsNotNone(st["winner"])
        self.assertEqual(j["match_status"], "completed")
        h = c.req("GET", "/api/matches?status=completed")[1]["matches"][0]
        pts = st["points_won"]
        self.assertEqual(h["score"], f"{pts}-0" if st["winner"] == 0 else f"0-{pts}")
        self.assertEqual(c.req("GET", "/api/me")[1]["user"]["coins"], 95)


class AbandonedMatches(unittest.TestCase):
    """Active matches with no activity for ABANDON_AFTER_SECONDS become 'abandoned' (new in stage 7)."""
    def setUp(self):
        reset_rate_limits()
        self._old = appmod.ABANDON_AFTER_SECONDS
        appmod.ABANDON_AFTER_SECONDS = 3600

    def tearDown(self):
        appmod.ABANDON_AFTER_SECONDS = self._old

    def _active(self, c, game="backgammon", start=True):
        mid = c.new_match(game)[1]["match"]["id"]
        c.req("POST", f"/api/matches/{mid}/activate")
        if start:
            self.assertIn(c.req("POST", f"/api/matches/{mid}/{'bg' if game == 'backgammon' else 'pasur'}/start",
                                {"level": "easy"})[0], (200, 201))
        return mid

    def _age(self, mid, hours):
        """Test setup only: pretend the last activity happened `hours` ago."""
        from datetime import datetime, timedelta, timezone
        old = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours)).isoformat(sep=" ")
        with appmod.db.session_scope() as s:
            s.execute("UPDATE matches SET started_at=?, created_at=? WHERE id=?", (old, old, mid))
            s.execute("UPDATE game_states SET updated_at=? WHERE match_id=?", (old, mid))

    def _status(self, mid):
        with appmod.db.session_scope(write=False) as s:
            return s.scalar("SELECT status FROM matches WHERE id=?", (mid,))

    def test_stale_active_match_is_abandoned_without_result_or_refund(self):
        for game in ("backgammon", "pasur"):
            c = Client(); c.register()
            mid = self._active(c, game)
            path = "bg" if game == "backgammon" else "pasur"
            self._age(mid, 2)
            hist = c.req("GET", "/api/matches")[1]["matches"]
            self.assertEqual([(m["id"], m["status"], m["result"]) for m in hist], [(mid, "abandoned", None)])
            self.assertIsNotNone(hist[0]["ended_at"])
            me = c.req("GET", "/api/me")[1]["user"]
            self.assertEqual(me["coins"], 95)                       # fee not refunded
            self.assertEqual(me["total"]["played"], 0)              # not counted as a played game
            for url, data in ((f"/api/matches/{mid}/{path}/move", {"version": 0, "src": 0, "dst": 1, "card": "C2", "capture": []}),
                              (f"/api/matches/{mid}/{path}/resign", None),
                              (f"/api/matches/{mid}/cancel", None)):
                self.assertEqual(c.req("POST", url, data)[0], 409, url)
            self.assertEqual(c.req("GET", f"/api/matches/{mid}/{path}")[1]["match_status"], "abandoned")  # still viewable
            self.assertEqual(c.req("GET", "/api/matches?status=abandoned")[1]["matches"][0]["id"], mid)

    def test_recent_or_other_states_are_not_touched(self):
        c = Client(); c.register()
        fresh = self._active(c)
        old_no_state = self._active(c, start=False)          # activated but never started
        pending = c.new_match("pasur")[1]["match"]["id"]     # never activated
        done = self._active(c)
        c.req("POST", f"/api/matches/{done}/bg/resign")
        self._age(old_no_state, 5); self._age(pending, 5); self._age(done, 5)
        statuses = {m["id"]: m["status"] for m in c.req("GET", "/api/matches")[1]["matches"]}
        self.assertEqual(statuses[fresh], "active")
        self.assertEqual(statuses[old_no_state], "abandoned")  # old activation time, no game state
        self.assertEqual(statuses[pending], "pending")         # waiting matches can still be cancelled
        self.assertEqual(statuses[done], "completed")
        self.assertEqual(c.req("POST", f"/api/matches/{pending}/cancel")[0], 200)

    def test_a_move_counts_as_activity_and_only_owner_is_affected(self):
        c = Client(); c.register(); other = Client(); other.register()
        mid = self._active(c)
        theirs = self._active(other)
        self._age(mid, 2); self._age(theirs, 2)
        # the owner's own touch of the stale match abandons it...
        self.assertEqual(c.req("POST", f"/api/matches/{mid}/bg/move", {"version": 0, "src": 0, "dst": 1})[0], 409)
        self.assertEqual(self._status(mid), "abandoned")
        # ...but nobody else's request changes it (other user's stale match is still 'active' in the DB)
        self.assertEqual(self._status(theirs), "active")
        # recent activity prevents abandonment
        fresh = self._active(c)
        self.assertEqual(c.req("GET", "/api/matches?status=active")[1]["matches"][0]["id"], fresh)


if __name__ == "__main__":
    unittest.main()
