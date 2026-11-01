"""Server-authoritative backgammon engine (pure Python, no third-party dependencies).

Seats: 0 = human player, 1 = AI.  Dice are rolled ONLY here (random.SystemRandom),
never supplied by the client.  Rules implemented: bar entry, hitting, blocked points,
bearing off (exact / higher die only if no checker farther back), doubles = 4 moves,
must-use-max-dice rule (and the larger die if only one can be played), automatic pass,
win types (normal=1, gammon=2, backgammon=3 points).  Doubling cube: OPTIONAL (new_game(cube=True)), see the
'doubling cube' section; with the cube off the engine behaves exactly as before.

Board: 24 points, index 0..23.  points[i] > 0 = seat-0 checkers, < 0 = seat-1 checkers.
Seat 0 moves from high index to low (home = 0..5, bears off past index 0).
Seat 1 moves from low index to high (home = 18..23, bears off past index 23).
Move format: src = 0..23 | "bar" ; dst = 0..23 | "off".
State is a plain JSON-serialisable dict; every public function returns a NEW state.
"""
import copy
import random

HUMAN, AI = 0, 1
LEVELS = ("easy", "medium", "hard")
SR = random.SystemRandom()
DIR = {0: -1, 1: 1}


class IllegalMove(Exception):
    pass


# ----------------------------- position helpers -----------------------------
def initial_points():
    p = [0] * 24
    p[23], p[12], p[7], p[5] = 2, 5, 3, 5
    p[0], p[11], p[16], p[18] = -2, -5, -3, -5
    return p


def _own(pts, p, i):
    return pts[i] if p == 0 else -pts[i]


def _entry_idx(p, die):
    return 24 - die if p == 0 else die - 1


def _dist_off(p, i):
    return i + 1 if p == 0 else 24 - i


def _in_home(p, i):
    return i <= 5 if p == 0 else i >= 18


def _pos(state):
    return {"points": state["points"], "bar": state["bar"], "off": state["off"]}


def _key(pos):
    return tuple(pos["points"]) + tuple(pos["bar"]) + tuple(pos["off"])


def _all_home(pos, p):
    if pos["bar"][p] > 0:
        return False
    pts = pos["points"]
    return all(_own(pts, p, i) <= 0 or _in_home(p, i) for i in range(24))


def single_moves(pos, p, die):
    """All (src, dst) single-checker moves for one die value (ignores the max-dice rule)."""
    pts, res = pos["points"], []
    if pos["bar"][p] > 0:
        d = _entry_idx(p, die)
        if _own(pts, p, d) >= -1:
            res.append(("bar", d))
        return res
    can_off = _all_home(pos, p)
    for i in range(24):
        if _own(pts, p, i) <= 0:
            continue
        j = i + DIR[p] * die
        if 0 <= j <= 23:
            if _own(pts, p, j) >= -1:
                res.append((i, j))
        elif can_off:
            need = _dist_off(p, i)
            if die == need:
                res.append((i, "off"))
            elif die > need and not any(_own(pts, p, k) > 0 and _dist_off(p, k) > need for k in range(24)):
                res.append((i, "off"))
    return res


def apply_single(pos, p, src, dst):
    """Returns (new_pos, hit). Does not validate."""
    np_ = {"points": list(pos["points"]), "bar": list(pos["bar"]), "off": list(pos["off"])}
    pts, sgn, hit = np_["points"], (1 if p == 0 else -1), False
    if src == "bar":
        np_["bar"][p] -= 1
    else:
        pts[src] -= sgn
    if dst == "off":
        np_["off"][p] += 1
    else:
        if _own(pts, p, dst) == -1:
            pts[dst] = 0
            np_["bar"][1 - p] += 1
            hit = True
        pts[dst] += sgn
    return np_, hit


def _max_depth(pos, p, rem, memo):
    k = (_key(pos), tuple(sorted(rem)))
    if k in memo:
        return memo[k]
    best = 0
    for die in set(rem):
        r2 = list(rem)
        r2.remove(die)
        for s, d in single_moves(pos, p, die):
            v = 1 + _max_depth(apply_single(pos, p, s, d)[0], p, r2, memo)
            if v > best:
                best = v
        if best == len(rem):
            break
    memo[k] = best
    return best


def legal_moves_pos(pos, p, rem):
    """Legal first moves honouring: use as many dice as possible; if only one die can be
    played, it must be the larger one (when both could be played alone)."""
    memo = {}
    maxlen = _max_depth(pos, p, rem, memo)
    if maxlen == 0:
        return []
    out = []
    for die in sorted(set(rem)):
        r2 = list(rem)
        r2.remove(die)
        for s, d in single_moves(pos, p, die):
            if 1 + _max_depth(apply_single(pos, p, s, d)[0], p, r2, memo) == maxlen:
                out.append({"src": s, "dst": d, "die": die})
    if maxlen == 1 and len(set(rem)) == 2:
        dies = {m["die"] for m in out}
        if len(dies) == 2:
            big = max(dies)
            out = [m for m in out if m["die"] == big]
    return out


def legal_moves(state):
    if state["winner"] is not None or not state["dice"]:
        return []
    return legal_moves_pos(_pos(state), state["turn"], list(state["dice"]))


def _expand_turn(pos, p, dice):
    """All distinct final positions reachable using the maximum number of dice.
    Returns list of (moves[(src,dst,die)...], final_pos)."""
    frontier = {(_key(pos), tuple(sorted(dice))): (pos, list(dice), [])}
    finals = []
    while frontier:
        nxt = {}
        for ps, rem, moves in frontier.values():
            moved = False
            for die in set(rem):
                r2 = list(rem)
                r2.remove(die)
                for s, d in single_moves(ps, p, die):
                    moved = True
                    np_, _ = apply_single(ps, p, s, d)
                    kk = (_key(np_), tuple(sorted(r2)))
                    if kk not in nxt:
                        nxt[kk] = (np_, r2, moves + [(s, d, die)])
            if not moved:
                finals.append((moves, ps))
        frontier = nxt
    maxlen = max(len(m) for m, _ in finals)
    finals = [f for f in finals if len(f[0]) == maxlen]
    if maxlen == 1 and len(set(dice)) == 2:
        dies = {f[0][0][2] for f in finals}
        if len(dies) == 2:
            finals = [f for f in finals if f[0][0][2] == max(dies)]
    seen, uniq = set(), []
    for m, ps in finals:
        k = _key(ps)
        if k not in seen:
            seen.add(k)
            uniq.append((m, ps))
    return uniq


# ----------------------------- game flow -----------------------------
def _roll(rng):
    a, b = rng.randint(1, 6), rng.randint(1, 6)
    return [a, b], ([a] * 4 if a == b else [a, b])


def win_type(pos, winner):
    """1 = normal, 2 = gammon, 3 = backgammon."""
    q = 1 - winner
    if pos["off"][q] > 0:
        return 1
    if pos["bar"][q] > 0 or any(_own(pos["points"], q, i) > 0 and _in_home(winner, i) for i in range(24)):
        return 3
    return 2


def _settle(state, rng):
    """End the turn automatically when no dice are left or none can be played (pass)."""
    for _ in range(200):
        if state["winner"] is not None:
            return
        if state["dice"] and legal_moves(state):
            return
        if state["dice"]:
            state["events"].append({"type": "pass", "player": state["turn"], "roll": state["roll"]})
            state["events"] = state["events"][-20:]
        state["turn"] = 1 - state["turn"]
        if _cube_on(state):  # cube games: the new player decides to roll or double first
            state["roll"], state["dice"], state["phase"] = [], [], "pre_roll"
            return
        state["roll"], state["dice"] = _roll(rng)


def new_game(level="medium", rng=None, cube=False):
    rng = rng or SR
    if level not in LEVELS:
        raise ValueError("bad_level")
    while True:  # opening roll: one die each, higher plays first using both dice
        a, b = rng.randint(1, 6), rng.randint(1, 6)
        if a != b:
            break
    state = {"points": initial_points(), "bar": [0, 0], "off": [0, 0],
             "turn": 0 if a > b else 1, "roll": [a, b], "dice": [a, b],
             "winner": None, "win_type": None, "points_won": 0,
             "level": level, "moves_count": 0, "events": [], "ai_turns": [],
             "phase": "move",
             "cube": {"enabled": bool(cube), "value": 1, "owner": None, "pending": None}}
    _settle(state, rng)
    return state


def _norm_point(x, word):
    if x == word:
        return word
    if type(x) is int and 0 <= x <= 23:
        return x
    raise IllegalMove("illegal_move")


def apply_move(state, src, dst, die=None, rng=None):
    rng = rng or SR
    if state["winner"] is not None:
        raise IllegalMove("game_over")
    src, dst = _norm_point(src, "bar"), _norm_point(dst, "off")
    if src == "off" or dst == "bar":
        raise IllegalMove("illegal_move")
    if die is not None and (type(die) is not int or not 1 <= die <= 6):
        raise IllegalMove("illegal_move")
    p = state["turn"]
    cands = [m for m in legal_moves(state)
             if m["src"] == src and m["dst"] == dst and (die is None or m["die"] == die)]
    if not cands:
        raise IllegalMove("illegal_move")
    m = min(cands, key=lambda x: x["die"])  # bearing off: prefer the exact/smallest die
    new = copy.deepcopy(state)
    pos, _ = apply_single(_pos(new), p, m["src"], m["dst"])
    new["points"], new["bar"], new["off"] = pos["points"], pos["bar"], pos["off"]
    new["dice"].remove(m["die"])
    new["moves_count"] += 1
    if new["off"][p] == 15:
        new["winner"], new["dice"] = p, []
        wt = win_type(pos, p)
        new["win_type"] = ("normal", "gammon", "backgammon")[wt - 1]
        new["points_won"] = wt * cube_value(new)
    _settle(new, rng)
    return new


# ----------------------------- doubling cube -----------------------------
CUBE_MAX = 64


def _cube_on(state):
    return bool((state.get("cube") or {}).get("enabled"))


def cube_value(state):
    return (state.get("cube") or {}).get("value", 1)


def can_double(state, p):
    """True if seat p may offer a double now (cube on, own turn, before rolling, cube centred or
    owned by p, nothing pending, value < 64)."""
    c = state.get("cube") or {}
    return bool(c.get("enabled") and state["winner"] is None and state.get("phase") == "pre_roll"
                and state["turn"] == p and not c.get("pending") and c["value"] < CUBE_MAX
                and c["owner"] in (None, p))


def roll_dice(state, rng=None):
    """Roll the dice for the player on turn (cube games only; the server rolls, never the client)."""
    rng = rng or SR
    c = state.get("cube") or {}
    if state["winner"] is not None or state.get("phase") != "pre_roll" or c.get("pending"):
        raise IllegalMove("illegal_move")
    new = copy.deepcopy(state)
    new["roll"], new["dice"] = _roll(rng)
    new["phase"] = "move"
    _settle(new, rng)  # a roll with no legal move passes automatically
    return new


def offer_double(state, by):
    """Seat `by` offers to double. The other seat must answer with respond_double."""
    if not can_double(state, by):
        raise IllegalMove("illegal_move")
    new = copy.deepcopy(state)
    new["cube"]["pending"] = {"by": by, "value": new["cube"]["value"] * 2}
    new["events"].append({"type": "double_offer", "player": by, "value": new["cube"]["pending"]["value"]})
    new["events"] = new["events"][-20:]
    return new


def respond_double(state, accept):
    """The responder takes (cube value doubles, responder owns the cube) or drops (the doubler wins
    the cube value that stood BEFORE the double, as a normal win)."""
    c = state.get("cube") or {}
    pend = c.get("pending")
    if state["winner"] is not None or not pend:
        raise IllegalMove("illegal_move")
    by = pend["by"]
    new = copy.deepcopy(state)
    nc = new["cube"]
    nc["pending"] = None
    if accept:
        nc["value"], nc["owner"] = pend["value"], 1 - by
        new["events"].append({"type": "double_taken", "player": 1 - by, "value": nc["value"]})
    else:
        new["winner"], new["dice"], new["roll"] = by, [], []
        new["win_type"], new["points_won"] = "cube_drop", nc["value"]
        new["events"].append({"type": "double_dropped", "player": 1 - by, "value": nc["value"]})
    new["events"] = new["events"][-20:]
    return new


def ai_should_double_for(state, p):
    """Pip-count heuristic (NOT measured for strength): seat p doubles when clearly ahead in the race
    and nothing of its own is on the bar. easy never doubles; medium needs a bigger lead than hard."""
    if not can_double(state, p) or state.get("level") == "easy":
        return False
    pos = _pos(state)
    if pos["bar"][p] > 0:
        return False
    pm, po = pip(pos, p), pip(pos, 1 - p)
    need = 0.12 if state.get("level") == "medium" else 0.08
    return po > 0 and (po - pm) >= max(10, need * po)


def ai_takes_double_for(state, p):
    """Pip-count heuristic (NOT measured): seat p takes unless it trails by more than ~12 % of the
    doubler's pip count. easy always takes."""
    if state.get("level") == "easy":
        return True
    pos = _pos(state)
    pm, po = pip(pos, p), pip(pos, 1 - p)
    return (pm - po) <= 0.12 * max(po, 1)


def ai_should_double(state):
    return ai_should_double_for(state, AI)


def ai_takes_double(state):
    return ai_takes_double_for(state, AI)


def human_double(state):
    """The human offers a double and the AI answers at once. Returns the new state."""
    return respond_double(offer_double(state, HUMAN), ai_takes_double(state))


# ----------------------------- AI -----------------------------
def pip(pos, p):
    pts = pos["points"]
    return 25 * pos["bar"][p] + sum(_own(pts, p, i) * _dist_off(p, i) for i in range(24) if _own(pts, p, i) > 0)


def evaluate(pos, p):
    """Heuristic score of a position from seat p's point of view (higher = better)."""
    q, pts = 1 - p, pos["points"]
    if pos["off"][p] == 15:
        return 10000.0
    if pos["off"][q] == 15:
        return -10000.0
    s = float(pip(pos, q) - pip(pos, p))
    s += 100.0 * (pos["off"][p] - pos["off"][q])
    s += 10.0 * pos["bar"][q] - 12.0 * pos["bar"][p]
    opp = [k for k in range(24) if _own(pts, q, k) > 0]
    if q == 1:
        lo = min(opp) if opp else 99
        reach = lambda i: pos["bar"][1] > 0 or lo < i
    else:
        hi = max(opp) if opp else -1
        reach = lambda i: pos["bar"][0] > 0 or hi > i
    run = 0
    order = range(24) if p == 1 else range(23, -1, -1)  # walk along my travel direction
    for i in order:
        c = _own(pts, p, i)
        if c == 1 and reach(i):
            s -= 3.0 + 0.5 * (25 - _dist_off(p, i))
        if c >= 2:
            s += 3.0 + (2.0 if _in_home(p, i) else 0.0) - max(0, c - 3)
            run += 1
            if run >= 3:
                s += run
        else:
            run = 0
    return s


def _expected_after(fp, p):
    """1-ply lookahead: average over the 21 opponent rolls of my evaluation after
    the opponent's greedy best reply."""
    q, total = 1 - p, 0.0
    if fp["off"][p] == 15:
        return 10000.0
    for a in range(1, 7):
        for b in range(a, 7):
            dice = [a] * 4 if a == b else [a, b]
            fin = _expand_turn(fp, q, dice)
            reply = max(fin, key=lambda f: evaluate(f[1], q))[1]
            total += (1 if a == b else 2) * evaluate(reply, p)
    return total / 36.0


HARD_WIDTH = 5  # how many of the heuristic's best candidate turns 'hard' re-ranks with the lookahead


def ai_plan(state, rng=None):
    """Returns the list of (src, dst, die) the AI plays this turn (state['level'])."""
    rng = rng or SR
    p, pos = state["turn"], _pos(state)
    finals = _expand_turn(pos, p, list(state["dice"]))
    if not finals or not finals[0][0]:
        return []
    level = state.get("level", "medium")
    if level == "easy":
        return rng.choice(finals)[0]
    ranked = sorted(finals, key=lambda f: -evaluate(f[1], p))
    if level == "medium":
        return ranked[0][0]
    best, best_v = ranked[0], None
    for f in ranked[:HARD_WIDTH]:
        v = _expected_after(f[1], p)
        if best_v is None or v > best_v:
            best, best_v = f, v
    return best[0]


def play_ai_turns(state, rng=None):
    """Plays AI turns until it is the human's turn (or the game is over). Returns a new state."""
    rng = rng or SR
    st = copy.deepcopy(state)
    st["ai_turns"] = []
    for _ in range(100):
        if st["winner"] is not None or st["turn"] != AI:
            break
        if _cube_on(st) and st.get("phase") == "pre_roll":
            if st["cube"].get("pending"):
                break  # waiting for the human to take or drop
            if ai_should_double(st):
                st = offer_double(st, AI)
                break
            st = roll_dice(st, rng)
            continue
        roll, plan = list(st["roll"]), ai_plan(st, rng)
        if not plan:  # defensive: _settle should already have passed
            break
        for s, d, die in plan:
            st = apply_move(st, s, d, die, rng)
        st["ai_turns"].append({"roll": roll, "moves": [[s, d] for s, d, _ in plan]})
    return st


def public_view(state):
    keys = ("points", "bar", "off", "turn", "roll", "dice", "winner", "win_type", "points_won",
            "level", "moves_count", "events", "ai_turns")
    v = {k: state[k] for k in keys}
    v["resigned"] = state.get("resigned", False)
    v["legal_moves"] = legal_moves(state) if state["turn"] == HUMAN and state["winner"] is None else []
    c = state.get("cube") or {"enabled": False, "value": 1, "owner": None, "pending": None}
    pend = c.get("pending")
    v["phase"] = state.get("phase", "move")
    v["cube"] = {"enabled": bool(c["enabled"]), "value": c["value"], "owner": c["owner"],
                 "pending_by": pend["by"] if pend else None, "pending_value": pend["value"] if pend else None}
    v["can_roll"] = bool(c["enabled"] and state["winner"] is None and v["phase"] == "pre_roll"
                         and state["turn"] == HUMAN and not pend)
    v["can_double"] = can_double(state, HUMAN)
    v["must_respond"] = bool(pend and pend["by"] == AI and state["winner"] is None)
    return v


# ----------------------------- human-vs-human tables (groups) -----------------------------
def new_party_game(level="medium", humans=(0,), cube=False, rng=None):
    """Two-seat table. `humans` are the seats controlled by people; the AI plays an empty seat."""
    humans = sorted({h for h in humans if type(h) is int and h in (0, 1)})
    if not humans:
        raise ValueError("no humans")
    st = new_game(level, rng, cube=cube)
    st["humans"], st["party"] = humans, True
    return st


def play_ai_for(state, ai_seats, rng=None):
    """Plays for every seat in `ai_seats` (including cube decisions) until a person has to act."""
    rng = rng or SR
    st = copy.deepcopy(state)
    st["ai_turns"] = []
    for _ in range(200):
        if st["winner"] is not None:
            break
        pend = (st.get("cube") or {}).get("pending")
        if pend:
            responder = 1 - pend["by"]
            if responder not in ai_seats:
                break
            st = respond_double(st, ai_takes_double_for(st, responder))
            continue
        p = st["turn"]
        if p not in ai_seats:
            break
        if _cube_on(st) and st.get("phase") == "pre_roll":
            if ai_should_double_for(st, p):
                st = offer_double(st, p)
                continue
            st = roll_dice(st, rng)
            continue
        plan = ai_plan(st, rng)
        if not plan:
            break
        for s_, d_, die in plan:
            st = apply_move(st, s_, d_, die, rng)
    return st


def _mp(i):
    """Mirror a point index (or "bar"/"off") between the two seats' views of the board."""
    return 23 - i if type(i) is int else i


def to_seat_move(seat, src, dst):
    """A move made by `seat`, written in that seat's own view, translated to real board coordinates."""
    if seat == 0:
        return src, dst
    return _mp(src), _mp(dst)


def public_view_for(state, seat, names=None):
    """What `seat` may see. Seat 1 sees the board mirrored (point i -> 23-i, colours swapped) so the
    viewer is always the ivory player moving from high to low, exactly like the single-player board."""
    if type(seat) is not int or seat not in (0, 1):
        raise ValueError("bad seat")
    if seat == 0:
        m = state
    else:
        m = dict(state)
        m["points"] = [-state["points"][23 - i] for i in range(24)]
        m["bar"], m["off"] = state["bar"][::-1], state["off"][::-1]
        m["turn"] = 1 - state["turn"]
        if state["winner"] is not None:
            m["winner"] = 1 - state["winner"]
        c = dict(state["cube"])
        if c.get("owner") is not None:
            c["owner"] = 1 - c["owner"]
        if c.get("pending"):
            c["pending"] = dict(c["pending"], by=1 - c["pending"]["by"])
        m["cube"] = c
        m["events"] = [dict(e, player=1 - e["player"]) if "player" in e else e for e in state["events"]]
    m = dict(m, ai_turns=[])
    v = public_view(m)
    names = names or [None, None]
    v["party"] = True
    v["names"] = [names[seat], names[1 - seat]]
    v["kinds"] = ["human" if i in state.get("humans", []) else "ai" for i in (seat, 1 - seat)]
    return v
