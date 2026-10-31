"""PERSIAN GAME CLUB - Flask backend core: auth, CSRF, rate limit, coins ledger, matches."""
import os, re, secrets, hmac, time, json, base64, hashlib
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, jsonify, session, send_from_directory
from dotenv import load_dotenv

# Explicit loading works for both python app.py and Gunicorn. Real environment wins.
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

import database as db
IntegrityError = db.IntegrityError
import backgammon_engine as bg
import pasur_engine as ps
import hokm_engine as hk

ENGINES = {"backgammon": bg, "pasur": ps, "hokm": hk}

ROOT = os.path.dirname(os.path.abspath(__file__))
PUBLIC_ROOT = ROOT  # flat layout: every file lives in this one folder; only STATIC_OK names are served
IS_PROD = os.environ.get("APP_ENV", "development").lower() == "production"
if IS_PROD and not os.environ.get("SECRET_KEY"):
    raise RuntimeError("SECRET_KEY must be set in production")

app = Flask(__name__, static_folder=None)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
    SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_SECURE=IS_PROD,
    PERMANENT_SESSION_LIFETIME=timedelta(days=int(os.environ.get("SESSION_DAYS", "7"))),
    MAX_CONTENT_LENGTH=64 * 1024)
if os.environ.get("TRUST_PROXY") == "1":
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

class VerifyMismatchError(Exception): pass
class InvalidHashError(Exception): pass


class PasswordHasher:
    """scrypt (memory-hard KDF from the Python standard library; replaces argon2-cffi which
    could not be installed). Format: scrypt$logN$r$p$salt_b64$hash_b64"""
    LOGN, R, P = 14, 8, 1

    def _kdf(self, pw, salt, logn, r, p):
        return hashlib.scrypt(pw.encode("utf-8"), salt=salt, n=1 << logn, r=r, p=p,
                              maxmem=128 * 1024 * 1024, dklen=32)

    def hash(self, pw):
        salt = secrets.token_bytes(16)
        h = self._kdf(pw, salt, self.LOGN, self.R, self.P)
        b = lambda x: base64.b64encode(x).decode()
        return f"scrypt${self.LOGN}${self.R}${self.P}${b(salt)}${b(h)}"

    def verify(self, stored, pw):
        try:
            tag, logn, r, p, salt, h = stored.split("$")
            if tag != "scrypt": raise ValueError
            logn, r, p = int(logn), int(r), int(p)
            salt, h = base64.b64decode(salt), base64.b64decode(h)
        except Exception:
            raise InvalidHashError()
        if not hmac.compare_digest(self._kdf(pw, salt, logn, r, p), h):
            raise VerifyMismatchError()
        return True


hasher = PasswordHasher()
_DUMMY = hasher.hash("dummy-password-for-timing")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_\u0600-\u06FF\u200c]{3,20}$")
STATIC_OK = {"index.html", "style.css", "app.js", "games.js", "hokm.js",
             "icons.js", "i18n.js", "manifest.json", "sw.js", "icon.svg", "icon-192.png", "icon-512.png",
             "club-art.png", "club-font.ttf"}

STATIC_OK.update(f"card-{suit}{rank}.webp" for suit in "CDHS"
                 for rank in ("A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"))
STATIC_OK.update({"card-back-raster.webp", "table-cloth.webp", "board-wood.webp",
                  "checker-ivory.webp", "checker-ebony.webp"})


def err(code, status):
    return jsonify(error=code), status  # frontend translates the code via its i18n dictionary


def body():
    d = request.get_json(silent=True)
    return d if isinstance(d, dict) else {}


# ---- shared sliding-window limiter (SQLite, common to all local workers) ----
def rate_limited(bucket, limit, window):
    t = time.time()
    address = request.remote_addr or "unknown"
    with db.session_scope() as s:
        s.execute("DELETE FROM rate_limit_hits WHERE created_at <= ?", (t - 3600,))
        n = s.scalar("SELECT COUNT(*) FROM rate_limit_hits WHERE bucket=? AND address=? AND created_at>?",
                     (bucket, address, t - window))
        if n >= limit:
            return True
        s.execute("INSERT INTO rate_limit_hits(bucket,address,created_at) VALUES(?,?,?)", (bucket, address, t))
    return False


def authenticated_uid():
    uid = session.get("uid")
    if uid:
        with db.session_scope(write=False) as s:
            version = s.scalar("SELECT auth_version FROM users WHERE id=?", (uid,))
        if version is not None and version == session.get("auth_version"):
            return uid
        session.clear()
    return None


def login_required(f):
    @wraps(f)
    def w(*a, **k):
        if not authenticated_uid():
            return err("auth_required", 401)
        return f(*a, **k)
    return w


@app.before_request
def csrf_protect():
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.path.startswith("/api/"):
        tok = session.get("csrf") or ""
        if not tok or not hmac.compare_digest(tok.encode("utf-8"),
                                             request.headers.get("X-CSRF-Token", "").encode("utf-8")):
            return err("csrf_failed", 403)


@app.after_request
def headers(r):
    r.headers["X-Content-Type-Options"] = "nosniff"
    r.headers["X-Frame-Options"] = "DENY"
    r.headers["Referrer-Policy"] = "same-origin"
    if request.path.startswith("/api/"):
        r.headers["Cache-Control"] = "no-store"
    if IS_PROD:
        r.headers["Strict-Transport-Security"] = "max-age=31536000"
    return r


@app.errorhandler(404)
def nf(_): return err("not_found", 404)
@app.errorhandler(413)
def big(_): return err("too_large", 413)
@app.errorhandler(Exception)
def boom(e):
    if hasattr(e, "code") and isinstance(e.code, int):
        return err("http_error", e.code)
    app.logger.exception("unhandled")  # never log passwords/bodies
    return err("server_error", 500)


# ---------------------------- auth ----------------------------
@app.get("/api/csrf")
def csrf():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return jsonify(token=session["csrf"])


def start_session(uid, version):
    session.clear(); session.permanent = True
    session["uid"] = uid; session["auth_version"] = version
    session["csrf"] = secrets.token_urlsafe(32)


@app.post("/api/register")
def register():
    if rate_limited("auth", 10, 60):
        return err("rate_limited", 429)
    d = body()
    username, pw, confirm = d.get("username"), d.get("password"), d.get("confirm")
    if not all(isinstance(x, str) for x in (username, pw, confirm)):
        return err("invalid_input", 400)
    username = username.strip()
    if not USERNAME_RE.match(username):
        return err("username_invalid", 400)
    if not 8 <= len(pw) <= 128:
        return err("password_weak", 400)
    if pw != confirm:
        return err("password_mismatch", 400)
    try:
        ph = hasher.hash(pw)  # slow KDF: computed before taking the DB write lock
        with db.session_scope() as s:
            uid = s.execute("INSERT INTO users(username, username_lower, password_hash, coins, created_at) "
                            "VALUES(?,?,?,?,?)", (username, username.lower(), ph, db.INITIAL_COINS, db.now())).lastrowid
            s.execute("INSERT INTO user_settings(user_id) VALUES(?)", (uid,))
            s.execute("INSERT INTO coin_transactions(user_id, match_id, amount, balance_after, kind, unique_key, created_at) "
                      "VALUES(?,NULL,?,?,?,?,?)", (uid, db.INITIAL_COINS, db.INITIAL_COINS, "initial_grant",
                                                    f"initial:{uid}", db.now()))
    except IntegrityError:
        return err("username_taken", 409)
    start_session(uid, 0)
    return me()


@app.post("/api/login")
def login():
    if rate_limited("auth", 10, 60):
        return err("rate_limited", 429)
    d = body()
    username, pw = d.get("username"), d.get("password")
    if not isinstance(username, str) or not isinstance(pw, str):
        return err("invalid_credentials", 401)
    with db.session_scope(write=False) as s:
        u = s.one("SELECT id, password_hash, auth_version FROM users WHERE username_lower=?", (username.strip().lower(),))
    h = u["password_hash"] if u else _DUMMY
    try:
        hasher.verify(h, pw); ok = u is not None
    except (VerifyMismatchError, InvalidHashError):
        ok = False
    if not ok:
        return err("invalid_credentials", 401)  # generic: no user enumeration
    uid = u["id"]
    start_session(uid, u["auth_version"])
    if not authenticated_uid():
        return err("invalid_credentials", 401)
    return me()


@app.post("/api/logout")
def logout():
    session.clear()
    session["csrf"] = secrets.token_urlsafe(32)
    return jsonify(ok=True, csrf=session["csrf"])


@app.post("/api/password")
@login_required
def change_password():
    if rate_limited("pw", 5, 60):
        return err("rate_limited", 429)
    d = body(); cur, new = d.get("current"), d.get("new")
    if not isinstance(cur, str) or not isinstance(new, str) or not 8 <= len(new) <= 128:
        return err("password_weak", 400)
    with db.session_scope(write=False) as s:
        old = s.scalar("SELECT password_hash FROM users WHERE id=?", (session["uid"],))
    try:
        hasher.verify(old, cur)
    except (VerifyMismatchError, InvalidHashError):
        return err("invalid_credentials", 401)
    updated = hasher.hash(new)
    with db.session_scope() as s:
        r = s.execute("UPDATE users SET password_hash=?, auth_version=auth_version+1 WHERE id=? AND password_hash=?",
                      (updated, session["uid"], old))
        if r.rowcount != 1:
            return err("state_conflict", 409)
        version = s.scalar("SELECT auth_version FROM users WHERE id=?", (session["uid"],))
    start_session(session["uid"], version)
    return jsonify(ok=True, csrf=session["csrf"])


# ------------------------- profile / stats -------------------------
@app.get("/api/me")
def me():
    uid = authenticated_uid()
    if not uid:
        return jsonify(user=None, csrf=session.setdefault("csrf", secrets.token_urlsafe(32)))
    with db.session_scope(write=False) as s:
        u = s.one("SELECT username, coins FROM users WHERE id=?", (uid,))
        if not u:
            session.clear(); return jsonify(user=None)
        st = s.one("SELECT language, theme FROM user_settings WHERE user_id=?", (uid,))
        rows = s.all("SELECT m.game_key, r.result, COUNT(*) FROM matches m JOIN match_results r ON r.match_id=m.id "
                     "WHERE m.user_id=? GROUP BY m.game_key, r.result", (uid,))
    stats = {g: {"played": 0, "won": 0, "lost": 0, "win_rate": 0} for g in db.GAMES}
    for g, res, n in rows:
        stats[g]["played"] += n
        if res == "win": stats[g]["won"] += n
        if res == "loss": stats[g]["lost"] += n
    tot = {"played": 0, "won": 0, "lost": 0}
    for v in stats.values():
        v["win_rate"] = round(100 * v["won"] / v["played"], 1) if v["played"] else 0
        for k in tot: tot[k] += v[k]
    tot["win_rate"] = round(100 * tot["won"] / tot["played"], 1) if tot["played"] else 0
    return jsonify(user={"username": u["username"], "coins": u["coins"],
                         "language": st["language"], "theme": st["theme"],
                         "stats": stats, "total": tot},
                   csrf=session.get("csrf"))


@app.put("/api/settings")
@login_required
def settings():
    d = body(); lang, theme = d.get("language"), d.get("theme")
    if lang is not None and lang not in db.LANGS: return err("invalid_input", 400)
    if theme is not None and theme not in db.THEMES: return err("invalid_input", 400)
    with db.session_scope() as s:
        if lang: s.execute("UPDATE user_settings SET language=? WHERE user_id=?", (lang, session["uid"]))
        if theme: s.execute("UPDATE user_settings SET theme=? WHERE user_id=?", (theme, session["uid"]))
    return jsonify(ok=True)


# ------------------------- matches & coins -------------------------
MATCH_COLS = ("m.id, m.user_id, m.game_key, m.opponent_type, m.status, m.entry_fee, "
              "m.created_at, m.started_at, m.ended_at")


def match_dict(m, res=None):
    iso = lambda x: x.replace(" ", "T") + "Z" if x else None
    return {"id": m["id"], "game": m["game_key"], "opponent": m["opponent_type"], "status": m["status"],
            "entry_fee": m["entry_fee"], "created_at": iso(m["created_at"]), "started_at": iso(m["started_at"]),
            "ended_at": iso(m["ended_at"]), "result": res["result"] if res else None,
            "score": res["score"] if res else None}


class Insufficient(Exception):
    pass


def _credit(s, uid, delta, kind, key, match_id):
    s.execute("UPDATE users SET coins = coins + ? WHERE id = ?", (delta, uid))
    bal = s.scalar("SELECT coins FROM users WHERE id = ?", (uid,))
    s.execute("INSERT INTO coin_transactions(user_id, match_id, amount, balance_after, kind, unique_key, created_at) "
              "VALUES(?,?,?,?,?,?,?)", (uid, match_id, delta, bal, kind, key, db.now()))
    return bal


@app.post("/api/coins/refill")
@login_required
def refill_coins():
    """Free daily rescue grant for depleted balances; no client-supplied amounts."""
    uid = session["uid"]
    day = db.now()[:10]  # UTC calendar day, shared across workers
    key = f"daily_refill:{uid}:{day}"
    with db.session_scope() as s:
        balance = s.scalar("SELECT coins FROM users WHERE id=?", (uid,))
        if s.one("SELECT id FROM coin_transactions WHERE unique_key=?", (key,)):
            return err("refill_already_claimed", 409)
        if balance >= db.MATCH_FEE:
            return err("refill_not_needed", 409)
        amount = db.INITIAL_COINS - balance
        balance = _credit(s, uid, amount, "daily_refill", key, None)
    return jsonify(coins=balance, granted=amount, day=day)


def _get_match(s, mid):
    return s.one(f"SELECT {MATCH_COLS} FROM matches m WHERE m.id=?", (mid,))


@app.post("/api/matches")
@login_required
def create_match():
    d = body(); game, idem = d.get("game"), d.get("idem_key")
    if not isinstance(game, str) or game not in db.GAMES or not isinstance(idem, str) or not 8 <= len(idem) <= 64:
        return err("invalid_input", 400)
    uid = session["uid"]

    def existing():
        with db.session_scope(write=False) as s:
            m = s.one(f"SELECT {MATCH_COLS} FROM matches m WHERE m.user_id=? AND m.idem_key=?", (uid, idem))
            return match_dict(m) if m else None

    if (m := existing()):  # retry of same request: never charge twice
        if m["game"] != game:
            return err("idempotency_conflict", 409)
        return jsonify(match=m, charged=False)
    try:
        with db.session_scope() as s:
            mid = s.execute("INSERT INTO matches(user_id, game_key, opponent_type, idem_key, entry_fee, status, created_at) "
                            "VALUES(?,?,?,?,?,?,?)", (uid, game, "ai", idem, db.MATCH_FEE, "pending", db.now())).lastrowid
            # atomic conditional debit: concurrency-safe, can never go negative
            r = s.execute("UPDATE users SET coins = coins - ? WHERE id = ? AND coins >= ?", (db.MATCH_FEE, uid, db.MATCH_FEE))
            if r.rowcount != 1:
                raise Insufficient()
            bal = s.scalar("SELECT coins FROM users WHERE id = ?", (uid,))
            s.execute("INSERT INTO coin_transactions(user_id, match_id, amount, balance_after, kind, unique_key, created_at) "
                      "VALUES(?,?,?,?,?,?,?)", (uid, mid, -db.MATCH_FEE, bal, "match_fee", f"fee:{mid}", db.now()))
            s.execute("INSERT INTO match_players(match_id, user_id, seat) VALUES(?,?,0)", (mid, uid))
            for seat in range(1, 4 if game == "hokm" else 2):
                s.execute("INSERT INTO match_players(match_id, user_id, seat) VALUES(?,NULL,?)", (mid, seat))
            out = match_dict(_get_match(s, mid))
    except Insufficient:
        return err("insufficient_coins", 402)
    except IntegrityError:  # concurrent duplicate with same idem_key
        m = existing()
        if not m or m["game"] != game:
            return err("idempotency_conflict", 409)
        return jsonify(match=m, charged=False)
    return jsonify(match=out, coins=bal, charged=True), 201


def _transition(match_id, frm, to, refund=False):
    uid = session["uid"]
    with db.session_scope() as s:
        col = "started_at" if to == "active" else "ended_at"
        r = s.execute(f"UPDATE matches SET status=?, {col}=? WHERE id=? AND user_id=? AND status=?",
                      (to, db.now(), match_id, uid, frm))
        if r.rowcount != 1:
            m = _get_match(s, match_id)
            if not m or m["user_id"] != uid:
                return err("not_found", 404)
            return err("invalid_state", 409)
        bal = None
        if refund:
            bal = _credit(s, uid, db.MATCH_FEE, "match_refund", f"refund:{match_id}", match_id)
        return jsonify(ok=True, coins=bal)


@app.post("/api/matches/<int:mid>/activate")
@login_required
def activate(mid):  # fee is consumed once the match is active (no refund after this point)
    return _transition(mid, "pending", "active")


@app.post("/api/matches/<int:mid>/cancel")
@login_required
def cancel(mid):  # only before active -> fee restored exactly once
    return _transition(mid, "pending", "cancelled", refund=True)


@app.get("/api/matches")
@login_required
def history():
    q = request.args; uid = session["uid"]
    where, args = ["m.user_id = ?"], [uid]
    for key, choices, column in (("game", db.GAMES, "m.game_key"),
                                 ("status", db.MATCH_STATUSES, "m.status"),
                                 ("result", ("win", "loss", "draw"), "r.result")):
        if key in q:
            if q[key] not in choices: return err("invalid_input", 400)
            where.append(f"{column} = ?"); args.append(q[key])
    try:
        limit, offset = int(q.get("limit", "100")), int(q.get("offset", "0"))
        if not 1 <= limit <= 100 or offset < 0: raise ValueError
    except ValueError:
        return err("invalid_input", 400)
    try:  # dates are validated, then compared as sortable ISO text
        if q.get("from"):
            where.append("m.created_at >= ?"); args.append(datetime.strptime(q["from"], "%Y-%m-%d").isoformat(sep=" "))
        if q.get("to"):
            where.append("m.created_at < ?")
            args.append((datetime.strptime(q["to"], "%Y-%m-%d") + timedelta(days=1)).isoformat(sep=" "))
    except ValueError:
        return err("invalid_input", 400)
    with db.session_scope() as s:
        expire_stale_matches(s, uid)
    with db.session_scope(write=False) as s:
        rows = s.all(f"SELECT {MATCH_COLS}, r.result AS result, r.score AS score FROM matches m "
                     "LEFT JOIN match_results r ON r.match_id = m.id WHERE " + " AND ".join(where) +
                     " ORDER BY m.created_at DESC, m.id DESC LIMIT ? OFFSET ?", args + [limit + 1, offset])
    return jsonify(matches=[match_dict(m, m if m["result"] else None) for m in rows[:limit]],
                   pagination={"limit": limit, "offset": offset, "has_more": len(rows) > limit})


# ------------------------- abandoned matches (timeout) -------------------------
# An ACTIVE match with no activity for ABANDON_AFTER_SECONDS becomes 'abandoned'. Decided here, on the
# server, lazily (no background job): when the owner lists history or touches a game endpoint.
# An abandoned match records NO result (not counted as a win/loss/played game) and the fee is NOT refunded.
ABANDON_AFTER_SECONDS = int(os.environ.get("ABANDON_AFTER_SECONDS", str(24 * 3600)))


def expire_stale_matches(s, uid):
    """Marks this user's stale active matches as abandoned. Last activity = the game state's last update
    (a move), else the activation time. Returns how many matches were changed."""
    now = db.now()
    cutoff = (datetime.fromisoformat(now) - timedelta(seconds=ABANDON_AFTER_SECONDS)).isoformat(sep=" ")
    r = s.execute("UPDATE matches SET status='abandoned', ended_at=? "
                  "WHERE user_id=? AND status='active' AND "
                  "COALESCE((SELECT g.updated_at FROM game_states g WHERE g.match_id = matches.id), "
                  "started_at, created_at) < ?", (now, uid, cutoff))
    return r.rowcount


# ------------------------- finishing a match (server only) -------------------------
def finish_match(s, match_id, uid, result, score, stats):
    """The ONLY way a match becomes 'completed'. Called solely from server-side engines,
    never with browser-supplied data. Idempotent: returns False if already finished."""
    r = s.execute("UPDATE matches SET status='completed', ended_at=? "
                  "WHERE id=? AND user_id=? AND status='active'", (db.now(), match_id, uid))
    if r.rowcount != 1:
        return False
    s.execute("INSERT INTO match_results(match_id, result, score, stats_json) VALUES(?,?,?,?)",
              (match_id, result, score, json.dumps(stats)))
    _award(s, match_id, uid, result, stats)
    return True


def _award(s, match_id, uid, result, stats):
    """Achievements are computed on the server from stored results (never from the client)."""
    played = s.scalar("SELECT COUNT(*) FROM matches m JOIN match_results r ON r.match_id=m.id WHERE m.user_id=?", (uid,))
    wins = s.scalar("SELECT COUNT(*) FROM matches m JOIN match_results r ON r.match_id=m.id "
                    "WHERE m.user_id=? AND r.result='win'", (uid,))
    game = s.scalar("SELECT game_key FROM matches WHERE id=?", (match_id,))
    got = []
    if result == "win":
        got += ["first_win"] if wins == 1 else []
        got += ["ten_wins"] if wins >= 10 else []
        got.append(f"{game}_win")
        if game == "backgammon" and stats.get("win_type") in ("gammon", "backgammon"):
            got.append("gammon_win")
    if played >= 10:
        got.append("played_10")
    for k in got:
        s.execute("INSERT OR IGNORE INTO user_achievements(user_id, achievement_key, earned_at) VALUES(?,?,?)",
                  (uid, k, db.now()))


@app.get("/api/achievements")
@login_required
def achievements():
    with db.session_scope(write=False) as s:
        rows = s.all("SELECT a.key, a.name_fa, a.name_en, u.earned_at FROM achievements a "
                     "LEFT JOIN user_achievements u ON u.achievement_key=a.key AND u.user_id=? ORDER BY a.rowid",
                     (session["uid"],))
    return jsonify(achievements=[{"key": r["key"], "name_fa": r["name_fa"], "name_en": r["name_en"],
                                  "earned": r["earned_at"] is not None,
                                  "earned_at": r["earned_at"].replace(" ", "T") + "Z" if r["earned_at"] else None}
                                 for r in rows])


@app.get("/api/leaderboard")
@login_required
def leaderboard():
    """Compare a single game/difficulty under standard rules; custom Pasur is unranked."""
    game = request.args.get("game", "backgammon")
    level = request.args.get("level", "medium")
    if game not in db.GAMES or level not in bg.LEVELS:
        return err("invalid_input", 400)
    where = ["m.game_key=?", "json_extract(r.stats_json, '$.level')=?"]
    args = [game, level]
    if game == "pasur":
        for key, value in ps.DEFAULT_RULES.items():
            where.append("json_extract(r.stats_json, ?) = ?")
            args.extend([f"$.rules.{key}", value])
    with db.session_scope(write=False) as s:
        rows = s.all("SELECT u.username AS username, COUNT(*) AS played, "
                     "SUM(CASE WHEN r.result='win' THEN 1 ELSE 0 END) AS won FROM users u "
                     "JOIN matches m ON m.user_id=u.id JOIN match_results r ON r.match_id=m.id WHERE " +
                     " AND ".join(where) + " GROUP BY u.id ORDER BY won DESC, played ASC, u.id ASC LIMIT 20", args)
    return jsonify(game=game, level=level, standard_rules=True,
                   leaderboard=[{"rank": i + 1, "username": r["username"], "played": r["played"], "won": r["won"],
                                 "win_rate": round(100 * r["won"] / r["played"], 1)} for i, r in enumerate(rows)])


# ------------------------- backgammon (server-authoritative) -------------------------
def _bg_match(s, mid, allow_done=False):
    return _game_match(s, mid, "backgammon", allow_done)


def _bg_out(state, version, mid, status):
    return jsonify(match_id=mid, version=version, match_status=status, state=bg.public_view(state))


@app.post("/api/matches/<int:mid>/bg/start")
@login_required
def bg_start(mid):
    """Creates the game state once (idempotent). The server rolls the opening dice."""
    b = body()
    level, cube = b.get("level", "medium"), b.get("cube", False)
    if level not in bg.LEVELS or type(cube) is not bool:
        return err("invalid_input", 400)
    return _start_game(mid, "backgammon", lambda: bg.play_ai_turns(bg.new_game(level, cube=cube)))


@app.get("/api/matches/<int:mid>/bg")
@login_required
def bg_get(mid):
    with db.session_scope() as s:
        m, e = _bg_match(s, mid, allow_done=True)
        if e: return e
        row = s.one("SELECT state_json, version FROM game_states WHERE match_id=?", (mid,))
        if not row: return err("not_found", 404)
        return _bg_out(json.loads(row["state_json"]), row["version"], mid, m["status"])


@app.post("/api/matches/<int:mid>/bg/move")
@login_required
def bg_move(mid):
    """One checker move. The client sends only src/dst(/die) + the version it last saw.
    Legality, dice, AI reply, winner, score are all decided here."""
    d = body()
    if type(d.get("version")) is not int:
        return err("invalid_input", 400)
    def move(st):
        if st["winner"] is not None or st["turn"] != bg.HUMAN:
            raise _NotYourTurn()
        return bg.apply_move(st, d.get("src"), d.get("dst"), d.get("die"))
    return _mutate_game(mid, "backgammon", d["version"], move)


# ---- doubling cube (only for games started with {"cube": true}); every decision is made on the server ----
class _NotYourTurn(Exception):
    pass


def _bg_cube_action(mid, fn):
    d = body()
    if type(d.get("version")) is not int:
        return err("invalid_input", 400)
    def action(st):
        if not (st.get("cube") or {}).get("enabled"):
            raise _InvalidState()
        if st["winner"] is not None:
            raise _NotYourTurn()
        return fn(st, d)
    return _mutate_game(mid, "backgammon", d["version"], action)


def _need_human_turn(st):
    if st["turn"] != bg.HUMAN or (st.get("cube") or {}).get("pending"):
        raise _NotYourTurn()


def _do_roll(st, d):
    _need_human_turn(st)
    return bg.roll_dice(st)


def _do_double(st, d):
    _need_human_turn(st)
    return bg.human_double(st)  # the AI answers immediately (take or drop)


def _do_respond(st, d):
    pend = (st.get("cube") or {}).get("pending")
    if not pend or pend["by"] != bg.AI:
        raise _NotYourTurn()
    if type(d.get("accept")) is not bool:
        raise ValueError("accept")
    return bg.respond_double(st, d["accept"])


@app.post("/api/matches/<int:mid>/bg/roll")
@login_required
def bg_roll(mid): return _bg_cube_action(mid, _do_roll)


@app.post("/api/matches/<int:mid>/bg/double")
@login_required
def bg_double(mid): return _bg_cube_action(mid, _do_double)


@app.post("/api/matches/<int:mid>/bg/respond")
@login_required
def bg_respond(mid): return _bg_cube_action(mid, _do_respond)


# ------------------------- pasur (server-authoritative) -------------------------
def _game_match(s, mid, game, allow_done=False):
    """Same checks as _bg_match, for any game key: owner only, right game, active (or completed to view)."""
    expire_stale_matches(s, session["uid"])
    m = _get_match(s, mid)
    if not m or m["user_id"] != session["uid"] or m["game_key"] != game:
        return None, err("not_found", 404)
    if m["status"] != "active" and not (allow_done and m["status"] in ("completed", "abandoned")):
        return None, err("invalid_state", 409)
    return m, None


class _InvalidState(Exception):
    pass


def _game_out(game, st, version, mid, status):
    return jsonify(match_id=mid, version=version, match_status=status,
                   state=ENGINES[game].public_view(st))


def _state_row(s, mid):
    return s.one("SELECT state_json, version FROM game_states WHERE match_id=?", (mid,))


def _start_game(mid, game, create):
    # Snapshot and validate, then release the writer lock before any AI search.
    with db.session_scope() as s:
        m, e = _game_match(s, mid, game)
        if e: return e
        row = _state_row(s, mid)
        if row:
            return _game_out(game, json.loads(row["state_json"]), row["version"], mid, m["status"])
    st = create()
    with db.session_scope() as s:
        m, e = _game_match(s, mid, game)
        if e: return e
        row = _state_row(s, mid)
        if row:  # A concurrent start won. Return its state; never replace its deal/dice.
            return _game_out(game, json.loads(row["state_json"]), row["version"], mid, m["status"])
        s.execute("INSERT INTO game_states(match_id,state_json,version,updated_at) VALUES(?,?,0,?)",
                  (mid, json.dumps(st), db.now()))
        return _game_out(game, st, 0, mid, m["status"]), 201


def _mutate_game(mid, game, version, action):
    with db.session_scope() as s:
        m, e = _game_match(s, mid, game)
        if e: return e
        row = _state_row(s, mid)
        if not row: return err("not_found", 404)
        if version != row["version"]: return err("state_conflict", 409)
        st = json.loads(row["state_json"])
    try:
        st = action(st)
        st = ENGINES[game].play_ai_turns(st)
    except _NotYourTurn:
        return err("not_your_turn", 409)
    except _InvalidState:
        return err("invalid_state", 409)
    except (bg.IllegalMove, ps.IllegalMove, hk.IllegalMove):
        return err("illegal_move", 400)
    except ValueError:
        return err("invalid_input", 400)
    # A move, resignation, or timeout may have occurred during the search.
    # Recheck ownership/status and commit only against the exact snapshot version.
    with db.session_scope() as s:
        m, e = _game_match(s, mid, game)
        if e: return e
        r = s.execute("UPDATE game_states SET state_json=?, version=version+1, updated_at=? "
                      "WHERE match_id=? AND version=?", (json.dumps(st), db.now(), mid, version))
        if r.rowcount != 1: return err("state_conflict", 409)
        status = "active"
        if game == "backgammon" and st["winner"] is not None:
            pts, won = st["points_won"], st["winner"] == bg.HUMAN
            finish_match(s, mid, session["uid"], "win" if won else "loss",
                         f"{pts}-0" if won else f"0-{pts}",
                         {"win_type": st["win_type"], "level": st["level"],
                          "moves": st["moves_count"], "borne_off": st["off"],
                          "cube": bg.cube_value(st)})
            status = "completed"
        elif game in ("pasur", "hokm") and st["finished"]:
            result, score, stats = ENGINES[game].finish_info(st)
            finish_match(s, mid, session["uid"], result, score, stats)
            status = "completed"
        return _game_out(game, st, version + 1, mid, status)


def _pasur_out(state, version, mid, status):
    return jsonify(match_id=mid, version=version, match_status=status, state=ps.public_view(state))


@app.post("/api/matches/<int:mid>/pasur/start")
@login_required
def pasur_start(mid):
    """Creates the game once (idempotent). Server shuffles/deals. Optional `rules` (validated, see
    pasur_engine.DEFAULT_RULES) are fixed for the whole match at this point."""
    d = body()
    level = d.get("level", "medium")
    if level not in ps.LEVELS:
        return err("invalid_input", 400)
    try:
        rules = ps.validate_rules(d.get("rules"))
    except ps.RulesError:
        return err("invalid_input", 400)
    return _start_game(mid, "pasur", lambda: ps.play_ai_turns(ps.new_game(level, rules)))


@app.get("/api/matches/<int:mid>/pasur")
@login_required
def pasur_get(mid):
    with db.session_scope() as s:
        m, e = _game_match(s, mid, "pasur", allow_done=True)
        if e: return e
        row = s.one("SELECT state_json, version FROM game_states WHERE match_id=?", (mid,))
        if not row: return err("not_found", 404)
        return _pasur_out(json.loads(row["state_json"]), row["version"], mid, m["status"])


@app.post("/api/matches/<int:mid>/pasur/move")
@login_required
def pasur_move(mid):
    """One card play. The client sends only {card, capture:[ids]} + the version it last saw.
    Legality, shuffling, the AI reply, scoring and the winner are all decided here."""
    d = body()
    if type(d.get("version")) is not int:
        return err("invalid_input", 400)
    def move(st):
        if st["finished"] or st["turn"] != ps.HUMAN:
            raise _NotYourTurn()
        return ps.apply_move(st, d.get("card"), d.get("capture"))
    return _mutate_game(mid, "pasur", d["version"], move)


# ------------------------- resign (server decides; counts as a loss) -------------------------
@app.post("/api/matches/<int:mid>/hokm/start")
@login_required
def hokm_start(mid):
    level = body().get("level", "medium")
    if level not in hk.LEVELS:
        return err("invalid_input", 400)
    return _start_game(mid, "hokm", lambda: hk.play_ai_turns(hk.new_game(level)))


@app.get("/api/matches/<int:mid>/hokm")
@login_required
def hokm_get(mid):
    with db.session_scope() as s:
        m, e = _game_match(s, mid, "hokm", allow_done=True)
        if e: return e
        row = _state_row(s, mid)
        if not row: return err("not_found", 404)
        return _game_out("hokm", json.loads(row["state_json"]), row["version"], mid, m["status"])


def _hokm_action(mid, kind):
    d = body()
    if type(d.get("version")) is not int:
        return err("invalid_input", 400)
    def action(st):
        if kind == "trump":
            return hk.choose_trump(st, hk.HUMAN, d.get("suit"))
        if kind == "continue":
            return hk.continue_game(st)
        return hk.apply_move(st, d.get("card"))
    return _mutate_game(mid, "hokm", d["version"], action)


@app.post("/api/matches/<int:mid>/hokm/trump")
@login_required
def hokm_trump(mid): return _hokm_action(mid, "trump")


@app.post("/api/matches/<int:mid>/hokm/move")
@login_required
def hokm_move(mid): return _hokm_action(mid, "move")


@app.post("/api/matches/<int:mid>/hokm/continue")
@login_required
def hokm_continue(mid): return _hokm_action(mid, "continue")


def _resign(mid, game):
    """Giving up an ACTIVE match. The client sends nothing but the request itself; the server records a
    loss through finish_match. The entry fee is not refunded (the match was active)."""
    uid = session["uid"]
    with db.session_scope() as s:
        m, e = _game_match(s, mid, game)
        if e: return e
        row = s.one("SELECT state_json, version FROM game_states WHERE match_id=?", (mid,))
        st = json.loads(row["state_json"]) if row else None
        cube = ((st.get("cube") or {}).get("value", 1) if st and game == "backgammon" else 1)
        if game == "backgammon":
            score = f"0-{cube}"
            if st:
                st.update(winner=bg.AI, win_type="resigned", points_won=cube, dice=[], roll=[])
                st["cube"]["pending"] = None
        else:
            score = f"{st['scores'][0]}-{st['scores'][1]}" if st else "0-0"
            if st:
                st.update(finished=True, winner=ps.AI, draw=False, turn=None)
                if game == "hokm": st["phase"] = "finished"
        stats = {"resigned": True}
        if st:
            stats["level"] = st["level"]
            if game == "pasur": stats["rules"] = st["rules"]
        if not finish_match(s, mid, uid, "loss", score, stats):
            return err("invalid_state", 409)
        if st:
            st["resigned"] = True
            s.execute("UPDATE game_states SET state_json=?, version=version+1, updated_at=? WHERE match_id=?",
                      (json.dumps(st), db.now(), mid))
    return jsonify(ok=True, match_status="completed", result="loss")


@app.post("/api/matches/<int:mid>/bg/resign")
@login_required
def bg_resign(mid): return _resign(mid, "backgammon")


@app.post("/api/matches/<int:mid>/pasur/resign")
@login_required
def pasur_resign(mid): return _resign(mid, "pasur")


@app.post("/api/matches/<int:mid>/hokm/resign")
@login_required
def hokm_resign(mid): return _resign(mid, "hokm")


@app.get("/api/health")
def health():
    with db.session_scope(write=False) as s:
        s.scalar("SELECT 1")
    return jsonify(ok=True)


# ------------------------- static files -------------------------
@app.get("/")
def index():
    if os.path.exists(os.path.join(PUBLIC_ROOT, "index.html")):
        return send_from_directory(PUBLIC_ROOT, "index.html")
    return "Persian Game Club API is running. Frontend not built yet.", 200


@app.get("/<path:name>")
def static_files(name):
    if name in STATIC_OK and os.path.exists(os.path.join(PUBLIC_ROOT, name)):
        r = send_from_directory(PUBLIC_ROOT, name)
        if name == "sw.js": r.headers["Cache-Control"] = "no-cache"
        return r
    return err("not_found", 404)


db.init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), debug=not IS_PROD)
