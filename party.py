"""Groups ("parties"): shared text chat plus one human-vs-human table per group.

Players join a group with a short code, chat, and sit at the group's table. The owner picks the game:
four-seat Hokm (people on the same team, seats 0+2 or 1+3, are partners), or two-seat Pasur or
backgammon. Empty seats are played by the AI. The server stays authoritative: hands, dice, turns,
legality and scores never come from the browser. Clients poll /api/parties/<id> (no websockets, so it works behind the
existing Gunicorn/SQLite deployment).

Group games are free: no coins are charged and they do not appear in AI rankings.
"""
import json, re, secrets, time
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, session

import database as db
import hokm_engine as hk
import pasur_engine as ps
import backgammon_engine as bg

bp = Blueprint("party", __name__)

MAX_MEMBERS = 8
MAX_GROUPS_PER_USER = 10
MAX_MESSAGE = 500
MAX_NAME = 30
ONLINE_WINDOW = 15            # seconds since last poll = "online"
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # no 0/O/1/I
KEEP_MESSAGES = 300
GAMES = {"hokm": 4, "pasur": 2, "backgammon": 2}        # game -> number of seats
ILLEGAL = (hk.IllegalMove, ps.IllegalMove, bg.IllegalMove)
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f\u200e\u200f\u202a-\u202e\u2066-\u2069]")

# Injected by app.register_party() so this module never imports app (avoids a circular import).
_dep = {}


def err(code, status):
    return jsonify(error=code), status


def _clean(text, limit):
    if not isinstance(text, str):
        return ""
    return re.sub(r"\s+", " ", _CONTROL.sub("", text)).strip()[:limit]


def _ago(seconds):
    t = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=seconds)
    return t.isoformat(sep=" ")


def _clock():
    return time.time()


def _uid():
    return session["uid"]


def _username(s, uid):
    return s.scalar("SELECT username FROM users WHERE id=?", (uid,)) or ""


def _is_member(s, pid, uid):
    return s.one("SELECT 1 FROM party_members WHERE party_id=? AND user_id=?", (pid, uid)) is not None


def _say(s, pid, body, uid=None, username="", kind="system"):
    s.execute("INSERT INTO party_messages(party_id,user_id,username,kind,body,created_at) VALUES(?,?,?,?,?,?)",
              (pid, uid, username, kind, body, db.now()))
    s.execute("DELETE FROM party_messages WHERE party_id=? AND id <= "
              "(SELECT id FROM party_messages WHERE party_id=? ORDER BY id DESC LIMIT 1 OFFSET ?)",
              (pid, pid, KEEP_MESSAGES))


def _room(s, pid):
    return s.one("SELECT * FROM party_rooms WHERE party_id=?", (pid,))


def _seats(room):
    return json.loads(room["seats_json"])


def _game(room):
    return room["game"]


def _options(room):
    return json.loads(room["options_json"] or "{}")


def _finished(game, st):
    return bool(st["winner"] is not None or st.get("draw")) if game == "backgammon" else bool(st["finished"])


def _advance(game, st):
    """Let the AI play every empty seat until a person has to act."""
    ai = [i for i in range(GAMES[game]) if i not in st["humans"]]
    if game == "hokm":
        return hk.play_ai_turns(st)
    return (ps if game == "pasur" else bg).play_ai_for(st, ai)


def _new_state(game, level, humans, options):
    if game == "hokm":
        st = hk.new_party_game(level, humans)
    elif game == "pasur":
        st = ps.new_party_game(level, humans)
    else:
        st = bg.new_party_game(level, humans, cube=bool(options.get("cube")))
    return _advance(game, st)


def _save_room(s, pid, seats=None, status=None, state=None, clear_state=False, bump=True):
    sets, args = ["updated_at=?"], [db.now()]
    if seats is not None:
        sets.append("seats_json=?"); args.append(json.dumps(seats))
    if status is not None:
        sets.append("status=?"); args.append(status)
    if state is not None:
        sets.append("state_json=?"); args.append(json.dumps(state))
    if clear_state:
        sets.append("state_json=NULL")
    if bump:
        sets.append("version=version+1")
    s.execute(f"UPDATE party_rooms SET {', '.join(sets)} WHERE party_id=?", (*args, pid))


def _my_seat(seats, uid):
    return next((i for i, x in enumerate(seats) if x and x["uid"] == uid), None)


def _guard(s, pid):
    """(party_row, None) for a member, else (None, error response)."""
    party = s.one("SELECT * FROM parties WHERE id=?", (pid,))
    if not party or not _is_member(s, pid, _uid()):
        return None, err("party_not_found", 404)
    return party, None


def _drop_seat(s, pid, uid):
    """Free the seat `uid` holds. In a running game an AI takes over; with no people left the table closes."""
    room = _room(s, pid)
    seats = _seats(room)
    idx = _my_seat(seats, uid)
    if idx is None:
        return
    seats[idx] = None
    if room["status"] != "active":
        _save_room(s, pid, seats=seats)
        return
    st = json.loads(room["state_json"])
    st["humans"] = [h for h in st["humans"] if h != idx]
    if not st["humans"]:
        _save_room(s, pid, seats=[None] * GAMES[_game(room)], status="lobby", clear_state=True)
        return
    st = _advance(_game(room), st)
    _save_room(s, pid, seats=seats, status="finished" if _finished(_game(room), st) else "active", state=st)


# ------------------------------- payloads -------------------------------
def _room_out(room, uid):
    seats = _seats(room)
    game = _game(room)
    out = dict(status=room["status"], level=room["level"], version=room["version"], game=game,
               options=_options(room), seats=seats, my_seat=_my_seat(seats, uid))
    if room["state_json"]:
        st = json.loads(room["state_json"])
        if game == "backgammon":
            out.update(off=st["off"], winner=st["winner"])
        else:
            target = st["target_score"] if game == "hokm" else st["rules"]["target_score"]
            out.update(scores=st["scores"], round=st["round"], target=target, winner=st["winner"])
    return out


def _snapshot(s, pid, uid, after):
    party = s.one("SELECT * FROM parties WHERE id=?", (pid,))
    now = _clock()
    members = [dict(user_id=m["user_id"], username=m["username"], owner=m["user_id"] == party["owner_id"],
                    online=now - m["last_seen"] <= ONLINE_WINDOW)
               for m in s.all("SELECT m.user_id, u.username, m.last_seen FROM party_members m "
                              "JOIN users u ON u.id=m.user_id WHERE m.party_id=? ORDER BY m.joined_at, m.user_id", (pid,))]
    if after > 0:
        rows = s.all("SELECT id,user_id,username,kind,body,created_at FROM party_messages "
                     "WHERE party_id=? AND id>? ORDER BY id LIMIT 100", (pid, after))
    else:
        rows = list(reversed(s.all("SELECT id,user_id,username,kind,body,created_at FROM party_messages "
                                   "WHERE party_id=? ORDER BY id DESC LIMIT 60", (pid,))))
    return dict(party=dict(id=pid, name=party["name"], code=party["code"], owner_id=party["owner_id"],
                           is_owner=party["owner_id"] == uid, max_members=MAX_MEMBERS),
                me=uid, members=members, room=_room_out(_room(s, pid), uid),
                messages=[dict(r) for r in rows])


# ------------------------------- groups -------------------------------
def _list():
    uid = _uid()
    with db.session_scope(write=False) as s:
        rows = s.all(
            "SELECT p.id, p.name, p.code, p.owner_id, r.status, "
            "(SELECT COUNT(*) FROM party_members x WHERE x.party_id=p.id) AS members "
            "FROM parties p JOIN party_members m ON m.party_id=p.id AND m.user_id=? "
            "JOIN party_rooms r ON r.party_id=p.id ORDER BY m.joined_at DESC", (uid,))
        return jsonify(parties=[dict(id=r["id"], name=r["name"], code=r["code"], members=r["members"],
                                     is_owner=r["owner_id"] == uid, room=r["status"]) for r in rows])


def _create():
    uid = _uid()
    name = _clean(_dep["body"]().get("name"), MAX_NAME)
    if not name:
        return err("invalid_input", 400)
    if _dep["rate_limited"]("party_create", 12, 3600):
        return err("rate_limited", 429)
    for _ in range(8):
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
        try:
            with db.session_scope() as s:
                if s.scalar("SELECT COUNT(*) FROM party_members WHERE user_id=?", (uid,)) >= MAX_GROUPS_PER_USER:
                    return err("party_limit", 409)
                cur = s.execute("INSERT INTO parties(code,name,owner_id,created_at) VALUES(?,?,?,?)",
                                (code, name, uid, db.now()))
                pid = cur.lastrowid
                s.execute("INSERT INTO party_members(party_id,user_id,joined_at,last_seen) VALUES(?,?,?,?)",
                          (pid, uid, db.now(), _clock()))
                s.execute("INSERT INTO party_rooms(party_id,seats_json,updated_at) VALUES(?,?,?)",
                          (pid, json.dumps([None] * 4), db.now()))
            return jsonify(party=dict(id=pid, name=name, code=code)), 201
        except db.IntegrityError:
            continue
    return err("server_error", 500)


def _join():
    uid = _uid()
    code = _clean(_dep["body"]().get("code"), 12).upper().replace(" ", "")
    if not re.fullmatch(r"[A-Z0-9]{4,12}", code):
        return err("invalid_input", 400)
    if _dep["rate_limited"]("party_join", 20, 60):
        return err("rate_limited", 429)
    with db.session_scope() as s:
        party = s.one("SELECT * FROM parties WHERE code=?", (code,))
        if not party:
            return err("party_not_found", 404)
        pid = party["id"]
        if not _is_member(s, pid, uid):
            if s.scalar("SELECT COUNT(*) FROM party_members WHERE party_id=?", (pid,)) >= MAX_MEMBERS:
                return err("party_full", 409)
            if s.scalar("SELECT COUNT(*) FROM party_members WHERE user_id=?", (uid,)) >= MAX_GROUPS_PER_USER:
                return err("party_limit", 409)
            s.execute("INSERT INTO party_members(party_id,user_id,joined_at,last_seen) VALUES(?,?,?,?)",
                      (pid, uid, db.now(), _clock()))
            _say(s, pid, "joined", uid, _username(s, uid))
        return jsonify(party=dict(id=pid, name=party["name"], code=party["code"]))


def _poll(pid):
    uid = _uid()
    try:
        after = max(0, int(_dep["request"].args.get("after", "0")))
    except ValueError:
        after = 0
    with db.session_scope(write=False) as s:
        party, e = _guard(s, pid)
        if e: return e
        seen = s.scalar("SELECT last_seen FROM party_members WHERE party_id=? AND user_id=?", (pid, uid))
        out = _snapshot(s, pid, uid, after)
    if _clock() - seen > 5:        # presence is written at most every few seconds per member
        with db.session_scope() as s:
            s.execute("UPDATE party_members SET last_seen=? WHERE party_id=? AND user_id=?", (_clock(), pid, uid))
    return jsonify(out)


def _send(pid):
    uid = _uid()
    text = _clean(_dep["body"]().get("text"), MAX_MESSAGE)
    if not text:
        return err("invalid_input", 400)
    with db.session_scope() as s:
        party, e = _guard(s, pid)
        if e: return e
        if s.scalar("SELECT COUNT(*) FROM party_messages WHERE user_id=? AND kind='text' AND created_at>?",
                    (uid, _ago(10))) >= 6:
            return err("rate_limited", 429)
        _say(s, pid, text, uid, _username(s, uid), kind="text")
        mid = s.scalar("SELECT MAX(id) FROM party_messages WHERE party_id=?", (pid,))
    return jsonify(id=mid), 201


def _remove_member(s, party, uid, body_code):
    pid = party["id"]
    name = _username(s, uid)
    _drop_seat(s, pid, uid)
    s.execute("DELETE FROM party_members WHERE party_id=? AND user_id=?", (pid, uid))
    heir = s.one("SELECT user_id FROM party_members WHERE party_id=? ORDER BY joined_at, user_id LIMIT 1", (pid,))
    if not heir:
        s.execute("DELETE FROM parties WHERE id=?", (pid,))   # cascades to members, messages, room
        return
    if party["owner_id"] == uid:
        s.execute("UPDATE parties SET owner_id=? WHERE id=?", (heir["user_id"], pid))
    _say(s, pid, body_code, uid, name)


def _leave(pid):
    with db.session_scope() as s:
        party, e = _guard(s, pid)
        if e: return e
        _remove_member(s, party, _uid(), "left")
    return jsonify(ok=True)


def _kick(pid):
    target = _dep["body"]().get("user_id")
    if type(target) is not int:
        return err("invalid_input", 400)
    with db.session_scope() as s:
        party, e = _guard(s, pid)
        if e: return e
        if party["owner_id"] != _uid():
            return err("forbidden", 403)
        if target == _uid() or not _is_member(s, pid, target):
            return err("invalid_input", 400)
        _remove_member(s, party, target, "kicked")
    return jsonify(ok=True)


# ------------------------------- the table -------------------------------
def _room_seat(pid):
    uid = _uid()
    d = _dep["body"]()
    want = d.get("seat")
    with db.session_scope() as s:
        party, e = _guard(s, pid)
        if e: return e
        room = _room(s, pid)
        seats = _seats(room)
        if want is not None and (type(want) is not int or want not in range(GAMES[_game(room)])):
            return err("invalid_input", 400)
        if want is None:                       # stand up (an AI covers the seat in a running game)
            _drop_seat(s, pid, uid)
            return jsonify(ok=True)
        if room["status"] != "lobby":
            return err("invalid_state", 409)
        if seats[want] and seats[want]["uid"] != uid:
            return err("seat_taken", 409)
        mine = _my_seat(seats, uid)
        if mine is not None:
            seats[mine] = None
        seats[want] = dict(uid=uid, name=_username(s, uid))
        _save_room(s, pid, seats=seats)
    return jsonify(ok=True)


def _room_settings(pid):
    """Owner, lobby only: AI level, which game the table plays, and the backgammon doubling cube."""
    d = _dep["body"]()
    level, game, cube = d.get("level"), d.get("game"), d.get("cube")
    if level is None and game is None and cube is None:
        return err("invalid_input", 400)
    if (level is not None and level not in hk.LEVELS) or (game is not None and game not in GAMES) \
            or (cube is not None and type(cube) is not bool):
        return err("invalid_input", 400)
    with db.session_scope() as s:
        party, e = _guard(s, pid)
        if e: return e
        if party["owner_id"] != _uid():
            return err("forbidden", 403)
        room = _room(s, pid)
        if room["status"] != "lobby":
            return err("invalid_state", 409)
        seats, options = _seats(room), _options(room)
        if game is not None and game != _game(room):
            n = GAMES[game]                      # people keep their place when the new table has room for them
            seats = (seats + [None] * n)[:n]
        if cube is not None:
            options["cube"] = cube
        s.execute("UPDATE party_rooms SET level=?, game=?, seats_json=?, options_json=?, version=version+1, "
                  "updated_at=? WHERE party_id=?",
                  (level or room["level"], game or _game(room), json.dumps(seats), json.dumps(options),
                   db.now(), pid))
    return jsonify(ok=True)


def _room_start(pid):
    with db.session_scope() as s:
        party, e = _guard(s, pid)
        if e: return e
        if party["owner_id"] != _uid():
            return err("forbidden", 403)
        room = _room(s, pid)
        if room["status"] != "lobby":
            return err("invalid_state", 409)
        humans = [i for i, x in enumerate(_seats(room)) if x]
        if not humans:
            return err("no_players", 409)
        level, game, options, version = room["level"], _game(room), _options(room), room["version"]
    st = _new_state(game, level, humans, options)       # AI search runs outside the writer lock
    with db.session_scope() as s:
        party, e = _guard(s, pid)
        if e: return e
        room = _room(s, pid)
        if (room["status"] != "lobby" or room["version"] != version
                or [i for i, x in enumerate(_seats(room)) if x] != humans):
            return err("state_conflict", 409)
        _save_room(s, pid, status="finished" if _finished(game, st) else "active", state=st)
        _say(s, pid, "game_start" if game == "hokm" else f"game_start_{game}", _uid(), _username(s, _uid()))
    return jsonify(ok=True), 201


def _room_reset(pid):
    """Owner returns the table to the lobby (after a game, or to end one that is stuck). Seats are kept."""
    with db.session_scope() as s:
        party, e = _guard(s, pid)
        if e: return e
        if party["owner_id"] != _uid():
            return err("forbidden", 403)
        room = _room(s, pid)
        if room["status"] == "lobby":
            return err("invalid_state", 409)
        _save_room(s, pid, status="lobby", clear_state=True)
    return jsonify(ok=True)


def _view(room, seat):
    seats = _seats(room)
    game = _game(room)
    st = json.loads(room["state_json"])
    names = [x["name"] if x else None for x in seats]
    if game == "hokm":
        view = hk.public_view_for(st, seat, names)
    else:
        view = (ps if game == "pasur" else bg).public_view_for(st, seat, names)
    return dict(version=room["version"], match_status="active" if room["status"] == "active" else "completed",
                my_seat=seat, game=game, state=view)


def _game_get(pid):
    with db.session_scope(write=False) as s:
        party, e = _guard(s, pid)
        if e: return e
        room = _room(s, pid)
        seat = _my_seat(_seats(room), _uid())
        if room["status"] == "lobby" or seat is None or not room["state_json"]:
            return err("invalid_state", 409)
        return jsonify(_view(room, seat))


KINDS = {"hokm": ("trump", "move", "continue"), "pasur": ("move",),
         "backgammon": ("move", "roll", "double", "respond")}


def _apply(game, kind, st, seat, d):
    """One person's action. Raises ILLEGAL for rule violations and returns an error response for
    out-of-turn calls; otherwise returns the new state (before the AI replies)."""
    if game == "hokm":
        if kind == "trump":
            if st["phase"] != "choose_trump" or st["hakem"] != seat:
                return err("not_your_turn", 409)
            return hk.choose_trump(st, seat, d.get("suit"))
        if kind == "move":
            if st["phase"] != "play" or st["turn"] != seat:
                return err("not_your_turn", 409)
            return hk.apply_move(st, d.get("card"), seat)
        return hk.continue_game(st)
    if game == "pasur":
        if st["turn"] != seat or st["finished"]:
            return err("not_your_turn", 409)
        return ps.apply_party_move(st, seat, d.get("card"), d.get("capture"))
    # backgammon
    st = dict(st, events=[])
    pend = (st.get("cube") or {}).get("pending")
    if kind == "respond":
        if not pend or pend["by"] == seat:
            return err("not_your_turn", 409)
        if type(d.get("accept")) is not bool:
            return err("invalid_input", 400)
        return bg.respond_double(st, d["accept"])
    if st["turn"] != seat or st["winner"] is not None or pend:
        return err("not_your_turn", 409)
    if kind == "roll":
        return bg.roll_dice(st)
    if kind == "double":
        return bg.offer_double(st, seat)
    src, dst = bg.to_seat_move(seat, d.get("src"), d.get("dst"))       # seat 1 sees a mirrored board
    return bg.apply_move(st, src, dst, d.get("die"))


def _game_action(pid, kind):
    uid = _uid()
    d = _dep["body"]()
    if type(d.get("version")) is not int:
        return err("invalid_input", 400)
    with db.session_scope(write=False) as s:
        party, e = _guard(s, pid)
        if e: return e
        room = _room(s, pid)
        seat = _my_seat(_seats(room), uid)
        if room["status"] != "active" or seat is None or not room["state_json"]:
            return err("invalid_state", 409)
        if kind not in KINDS[_game(room)]:
            return err("invalid_input", 400)
        if room["version"] != d["version"]:
            return err("state_conflict", 409)
        game = _game(room)
        st = json.loads(room["state_json"])
    try:
        st = _apply(game, kind, st, seat, d)
        if not isinstance(st, dict):          # an error response from _apply
            return st
        st = _advance(game, st)
    except ILLEGAL:
        return err("illegal_move", 400)
    with db.session_scope() as s:
        party, e = _guard(s, pid)
        if e: return e
        done = _finished(game, st)
        r = s.execute("UPDATE party_rooms SET state_json=?, version=version+1, updated_at=?, status=? "
                      "WHERE party_id=? AND version=? AND status='active'",
                      (json.dumps(st), db.now(), "finished" if done else "active", pid, d["version"]))
        if r.rowcount != 1:
            return err("state_conflict", 409)
        if done:
            _say(s, pid, "game_over")
        return jsonify(_view(_room(s, pid), seat))


def register(app, *, login_required, body, rate_limited, request):
    """Wire the blueprint into the Flask app (dependencies are passed in, not imported)."""
    _dep.update(body=body, rate_limited=rate_limited, request=request)
    r = lambda rule, fn, methods: bp.add_url_rule(rule, fn.__name__.lstrip('_'), login_required(fn), methods=methods)
    r("/api/parties", _list, ["GET"])
    r("/api/parties", _create, ["POST"])
    r("/api/parties/join", _join, ["POST"])
    r("/api/parties/<int:pid>", _poll, ["GET"])
    r("/api/parties/<int:pid>/messages", _send, ["POST"])
    r("/api/parties/<int:pid>/leave", _leave, ["POST"])
    r("/api/parties/<int:pid>/kick", _kick, ["POST"])
    r("/api/parties/<int:pid>/room/seat", _room_seat, ["POST"])
    r("/api/parties/<int:pid>/room/settings", _room_settings, ["POST"])
    r("/api/parties/<int:pid>/room/start", _room_start, ["POST"])
    r("/api/parties/<int:pid>/room/reset", _room_reset, ["POST"])
    r("/api/parties/<int:pid>/game", _game_get, ["GET"])
    for kind in ("trump", "move", "continue", "roll", "double", "respond"):
        bp.add_url_rule(f"/api/parties/<int:pid>/game/{kind}", f"game_{kind}",
                        login_required(lambda pid, kind=kind: _game_action(pid, kind)), methods=["POST"])
    app.register_blueprint(bp)
