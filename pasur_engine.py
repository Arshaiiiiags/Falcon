"""Server-authoritative Pasur (پاسور) engine - pure Python, no third-party dependencies.

Seats: 0 = human player, 1 = AI.  Shuffling happens ONLY here (random.SystemRandom),
never from client input.  State is a plain JSON-serialisable dict; every public function
returns a NEW state (the input is never mutated).

CARDS   52-card deck.  Card id = suit letter + rank, e.g. "C2", "D10", "SJ", "HA".
        Suits: C = clubs ♣ (گشنیز), D = diamonds ♦ (خشت), H = hearts ♥ (دل), S = spades ♠ (پیک).
        Ranks: A(=1), 2..10, J (سرباز), Q (بی‌بی), K (شاه).

FLOW    One game = several rounds ("دست") until the target score is reached.
        A round: 4 cards face-up on the table, then the deck is dealt 4 cards to each player,
        6 times (52 - 4 = 48 cards).  Players alternate; the leader of round 1 is the human,
        then the leader alternates every round.  On your turn you play ONE card from your hand.

CAPTURE (the played card always goes to your pile together with what it captures)
        * Number cards A,2..10 (A = 1): capture any set of table number cards that can be split into
          groups, each group adding up to 11 together with the played card
          (e.g. played 4 -> a 7, or a 3+4, or both).  Face cards on the table are never part of a sum.
          If rule `multi_group_capture` is False only ONE group may be taken.
        * Jack (J): captures ALL table cards except Kings and Queens (if there are none, it is just placed).
        * Queen (Q): captures one Queen from the table.   King (K): captures one King.
        * If nothing is captured the played card is placed on the table.
          Capturing is optional unless rule `capture_mandatory` is True
          (then a card that CAN capture may not simply be placed).
        * Sur (سور): capturing every card on the table (table empty afterwards) scores `sur_points`,
          except: a capture made with a Jack does not count (`jack_sur_counts`), and a capture made by the
          very last play of the round does not count (`last_sur_counts`).
        * When the last card of the round is played, the cards still on the table go to the player who
          captured last (`last_capturer_takes_table`; if False they are discarded).

SCORING (per round, added to the running totals; all values are configurable rules)
        most cards captured          3   (tie: nobody)         `most_cards_points`
        most clubs ♣                 7   (tie: nobody)         `most_clubs_points`
        10 of diamonds (ده خشت)      3                         `ten_diamonds_points`
        2 of clubs (دوی گشنیز)       2                         `two_clubs_points`
        each Ace                     1                         `ace_points`
        each Jack                    1                         `jack_points`
        each Sur                     5                         `sur_points`
GAME END after a round: if someone has >= `target_score` and the scores differ -> higher score wins;
        if tied, one more round is played.  After `max_rounds` rounds the higher score wins (tie = draw).

IMPORTANT: the default values above are the commonly used Iranian rules as understood by the author;
they are NOT taken from the project's original specification (that text was cut off / not available).
Compare with the spec and change DEFAULT_RULES if they differ.

AI levels: easy = random legal action; medium = greedy point-value heuristic;
hard = medium + estimates the opponent's best reply from the cards not yet seen.
The AI only uses information a real player has (its own hand, the table, all captured cards);
it never looks at the human's hand or the deck.
"""
import copy
import math
import random

HUMAN, AI = 0, 1
LEVELS = ("easy", "medium", "hard")
SR = random.SystemRandom()

SUITS = ("C", "D", "H", "S")
RANKS = ("A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K")
NUM = {"A": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9, "10": 10}
ALL_CARDS = tuple(s + r for s in SUITS for r in RANKS)

DEFAULT_RULES = {
    "target_score": 62,
    "max_rounds": 30,
    "capture_mandatory": False,
    "multi_group_capture": True,
    "no_jack_on_initial_table": True,
    "last_capturer_takes_table": True,
    "sur_points": 5,
    "jack_sur_counts": False,
    "last_sur_counts": False,
    "most_cards_points": 3,
    "most_clubs_points": 7,
    "ten_diamonds_points": 3,
    "two_clubs_points": 2,
    "ace_points": 1,
    "jack_points": 1,
}
_BOOL_RULES = {"capture_mandatory", "multi_group_capture", "no_jack_on_initial_table",
               "last_capturer_takes_table", "jack_sur_counts", "last_sur_counts"}
_INT_RANGES = {"target_score": (1, 1000), "max_rounds": (1, 100), "sur_points": (0, 50),
               "most_cards_points": (0, 50), "most_clubs_points": (0, 50), "ten_diamonds_points": (0, 50),
               "two_clubs_points": (0, 50), "ace_points": (0, 50), "jack_points": (0, 50)}


class IllegalMove(Exception):
    pass


class RulesError(ValueError):
    pass


def validate_rules(rules=None):
    """Merge user rules over DEFAULT_RULES. Unknown keys / wrong types / out-of-range -> RulesError."""
    out = dict(DEFAULT_RULES)
    if rules is None:
        return out
    if not isinstance(rules, dict):
        raise RulesError("rules must be an object")
    for k, v in rules.items():
        if k in _BOOL_RULES:
            if type(v) is not bool:
                raise RulesError(f"{k} must be true/false")
        elif k in _INT_RANGES:
            lo, hi = _INT_RANGES[k]
            if type(v) is not int or not lo <= v <= hi:
                raise RulesError(f"{k} must be an integer in {lo}..{hi}")
        else:
            raise RulesError(f"unknown rule: {k}")
        out[k] = v
    return out


# ----------------------------- card helpers -----------------------------
def rank(c):
    return c[1:]


def suit(c):
    return c[0]


def _is_num(c):
    return rank(c) in NUM


def capture_options(table, card, rules):
    """All legal non-empty capture sets (frozensets of table card ids) for playing `card`."""
    r = rank(card)
    if r == "J":
        elig = [c for c in table if rank(c) not in ("K", "Q")]
        return [frozenset(elig)] if elig else []
    if r in ("Q", "K"):
        return [frozenset([c]) for c in table if rank(c) == r]
    need = 11 - NUM[r]
    nums = sorted((c for c in table if _is_num(c)), key=lambda c: (NUM[rank(c)], c))
    groups = []

    def dfs(i, cur, total):
        if total == need:
            groups.append(frozenset(cur))
            return
        for j in range(i, len(nums)):
            v = NUM[rank(nums[j])]
            if total + v <= need:
                cur.append(nums[j])
                dfs(j + 1, cur, total + v)
                cur.pop()

    dfs(0, [], 0)
    if not groups:
        return []
    if not rules["multi_group_capture"]:
        return groups
    found = set()

    def unite(start, used):
        for k in range(start, len(groups)):
            g = groups[k]
            if used.isdisjoint(g):
                nu = used | g
                found.add(nu)
                unite(k + 1, nu)

    unite(0, frozenset())
    return list(found)


def _sorted_options(opts):
    return sorted((sorted(o) for o in opts), key=lambda l: (len(l), l))


def legal_actions(state, seat=None):
    """List of {"card": id, "capture": [ids]} the seat may play (capture [] = just place the card)."""
    p = state["turn"] if seat is None else seat
    if state["finished"] or p is None:
        return []
    rules, table = state["rules"], state["table"]
    acts = []
    for card in sorted(state["hands"][p]):
        opts = capture_options(table, card, rules)
        for cap in _sorted_options(opts):
            acts.append({"card": card, "capture": cap})
        if not (opts and rules["capture_mandatory"]):
            acts.append({"card": card, "capture": []})
    return acts


# ----------------------------- scoring -----------------------------
def score_round(captured, sur, rules):
    """Return (points[2], breakdown[2]) for one round. Pure function."""
    cnt = [len(c) for c in captured]
    clubs = [sum(1 for x in c if suit(x) == "C") for c in captured]
    pts, br = [0, 0], []
    for i in (0, 1):
        b = {"cards": cnt[i], "clubs": clubs[i], "most_cards": 0, "most_clubs": 0, "ten_diamonds": 0,
             "two_clubs": 0, "aces": 0, "jacks": 0, "sur": 0}
        if cnt[i] > cnt[1 - i]:
            b["most_cards"] = rules["most_cards_points"]
        if clubs[i] > clubs[1 - i]:
            b["most_clubs"] = rules["most_clubs_points"]
        if "D10" in captured[i]:
            b["ten_diamonds"] = rules["ten_diamonds_points"]
        if "C2" in captured[i]:
            b["two_clubs"] = rules["two_clubs_points"]
        b["aces"] = rules["ace_points"] * sum(1 for x in captured[i] if rank(x) == "A")
        b["jacks"] = rules["jack_points"] * sum(1 for x in captured[i] if rank(x) == "J")
        b["sur"] = rules["sur_points"] * sur[i]
        b["total"] = (b["most_cards"] + b["most_clubs"] + b["ten_diamonds"] + b["two_clubs"]
                      + b["aces"] + b["jacks"] + b["sur"])
        pts[i] = b["total"]
        br.append(b)
    return pts, br


# ----------------------------- game flow -----------------------------
def _new_deck(rules, rng):
    deck = list(ALL_CARDS)
    rng.shuffle(deck)
    if rules["no_jack_on_initial_table"]:  # the 4 table cards are deck.pop() x4 = the LAST 4 entries
        n = len(deck)
        for i in range(n - 4, n):
            if rank(deck[i]) == "J":
                j = next(k for k in range(n - 4) if rank(deck[k]) != "J")
                deck[i], deck[j] = deck[j], deck[i]
    return deck


def _deal(st):
    for s in (0, 1):
        st["hands"][s] = [st["deck"].pop() for _ in range(4)]


def _start_round(st, rng):
    st["round"] += 1
    st["leader"] = HUMAN if st["round"] % 2 == 1 else AI
    st["turn"] = st["leader"]
    deck = _new_deck(st["rules"], rng)
    st["table"] = [deck.pop() for _ in range(4)]
    st["deck"] = deck
    st["captured"] = [[], []]
    st["sur"] = [0, 0]
    st["last_capturer"] = None
    st["hands"] = [[], []]
    _deal(st)


def new_game(level="medium", rules=None, rng=None):
    if level not in LEVELS:
        raise ValueError("bad level")
    rng = rng or SR
    st = {"level": level, "rules": validate_rules(rules), "round": 0, "scores": [0, 0], "sur_total": [0, 0],
          "round_log": [], "finished": False, "winner": None, "draw": False, "moves_count": 0, "events": [],
          "deck": [], "table": [], "hands": [[], []], "captured": [[], []], "sur": [0, 0],
          "last_capturer": None, "turn": HUMAN, "leader": HUMAN}
    _start_round(st, rng)
    return st


def _end_round(st, rng):
    rules = st["rules"]
    lc = st["last_capturer"]
    if st["table"]:
        if rules["last_capturer_takes_table"] and lc is not None:
            st["captured"][lc] += st["table"]
        st["table"] = []
    pts, br = score_round(st["captured"], st["sur"], rules)
    for i in (0, 1):
        st["scores"][i] += pts[i]
    st["round_log"].append({"round": st["round"], "points": pts, "breakdown": br, "scores": list(st["scores"])})
    st["events"].append({"type": "round_end", "round": st["round"], "points": pts})
    s0, s1 = st["scores"]
    if (max(s0, s1) >= rules["target_score"] and s0 != s1) or st["round"] >= rules["max_rounds"]:
        st["finished"] = True
        st["winner"] = HUMAN if s0 > s1 else (AI if s1 > s0 else None)
        st["draw"] = st["winner"] is None
        st["turn"] = None
        st["hands"] = [[], []]
        return
    _start_round(st, rng)


def _advance(st, rng):
    if st["hands"][0] or st["hands"][1]:
        return
    if st["deck"]:
        _deal(st)
        st["events"].append({"type": "deal"})
        return
    _end_round(st, rng)


def _play(st, p, card, capture, rng):
    """Mutating core. Raises IllegalMove for anything invalid (never TypeError/KeyError)."""
    if st["finished"]:
        raise IllegalMove("game_finished")
    if st["turn"] != p:
        raise IllegalMove("not_your_turn")
    if not isinstance(card, str) or card not in st["hands"][p]:
        raise IllegalMove("card_not_in_hand")
    if capture is None:
        capture = []
    if (not isinstance(capture, (list, tuple)) or len(capture) > len(st["table"])
            or not all(isinstance(x, str) for x in capture)):
        raise IllegalMove("invalid_capture")
    cap = frozenset(capture)
    if len(cap) != len(capture):
        raise IllegalMove("invalid_capture")
    rules = st["rules"]
    opts = capture_options(st["table"], card, rules)
    if cap:
        if cap not in set(opts):
            raise IllegalMove("invalid_capture")
    elif opts and rules["capture_mandatory"]:
        raise IllegalMove("capture_mandatory")
    st["hands"][p].remove(card)
    sur = False
    if cap:
        st["table"] = [c for c in st["table"] if c not in cap]
        st["captured"][p] += [card] + sorted(cap)
        st["last_capturer"] = p
        last_play = not st["deck"] and not st["hands"][0] and not st["hands"][1]
        if (not st["table"] and (rank(card) != "J" or rules["jack_sur_counts"])
                and (not last_play or rules["last_sur_counts"])):
            st["sur"][p] += 1
            st["sur_total"][p] += 1
            sur = True
    else:
        st["table"].append(card)
    st["events"].append({"type": "play", "seat": p, "card": card, "capture": sorted(cap), "sur": sur})
    st["moves_count"] += 1
    st["turn"] = 1 - p
    _advance(st, rng)


def play_card(state, seat, card, capture=None, rng=None):
    """Play one card for `seat` (any seat; used for self-play and tests). Returns a NEW state."""
    st = copy.deepcopy(state)
    _play(st, seat, card, capture, rng or SR)
    return st


def apply_move(state, card, capture=None, rng=None):
    """The human's move. Clears the event log first (events = what happened since this move)."""
    st = copy.deepcopy(state)
    st["events"] = []
    _play(st, HUMAN, card, capture, rng or SR)
    return st


# ----------------------------- AI -----------------------------
def _card_value(c, rules):
    v = rules["most_cards_points"] / 26.0
    if suit(c) == "C":
        v += rules["most_clubs_points"] / 13.0
    if c == "D10":
        v += rules["ten_diamonds_points"]
    if c == "C2":
        v += rules["two_clubs_points"]
    if rank(c) == "A":
        v += rules["ace_points"]
    if rank(c) == "J":
        v += rules["jack_points"]
    return v


def _gain(table, card, cap, rules, sur_ok):
    g = _card_value(card, rules) + sum(_card_value(c, rules) for c in cap)
    if sur_ok and len(cap) == len(table) and (rank(card) != "J" or rules["jack_sur_counts"]):
        g += rules["sur_points"]
    return g


def _expected_max(vals, k):
    """E[max of k cards drawn without replacement from the multiset vals]."""
    n = len(vals)
    if n == 0 or k <= 0:
        return 0.0
    k = min(k, n)
    vs = sorted(vals, reverse=True)
    total = math.comb(n, k)
    return sum(v * math.comb(n - 1 - i, k - 1) for i, v in enumerate(vs) if n - 1 - i >= k - 1) / total


def choose_action(state, seat=AI, level=None, rng=None):
    """Pick an action for `seat` using only information that seat can see."""
    rng = rng or SR
    level = level or state["level"]
    acts = legal_actions(state, seat)
    if not acts:
        raise IllegalMove("no_legal_action")
    if level == "easy":
        return rng.choice(acts)
    rules, table = state["rules"], state["table"]
    last_play = (not state["deck"]) and len(state["hands"][0]) + len(state["hands"][1]) == 1
    sur_ok = (not last_play) or rules["last_sur_counts"]
    unseen = None
    opt_cache = {}
    if level == "hard":
        seen = set(table) | set(state["hands"][seat]) | set(state["captured"][0]) | set(state["captured"][1])
        unseen = [c for c in ALL_CARDS if c not in seen]
        opp_k = len(state["hands"][1 - seat])

    def opp_best(tbl, u):
        key = (frozenset(tbl), rank(u))
        if key not in opt_cache:
            opt_cache[key] = capture_options(tbl, u, rules)
        opts = opt_cache[key]
        return max((_gain(tbl, u, o, rules, True) for o in opts), default=0.0)

    best, best_v = None, None
    for a in acts:
        card, cap = a["card"], a["capture"]
        if cap:
            v = _gain(table, card, cap, rules, sur_ok)
            if rank(card) == "J" and len(cap) < 3:
                v -= 0.7  # keep the Jack for a bigger capture
        else:
            v = -0.5 * _card_value(card, rules)  # placing leaves the card to the opponent
        if level == "hard":
            cs = set(cap)
            after = [c for c in table if c not in cs] + ([] if cap else [card])
            v -= _expected_max([opp_best(after, u) for u in unseen if u != card], opp_k)
        v += rng.random() * 1e-6
        if best_v is None or v > best_v:
            best, best_v = a, v
    return best


def play_ai_turns(state, rng=None):
    """Let the AI play until it is the human's turn (or the game ends). Returns a NEW state."""
    st = copy.deepcopy(state)
    rng = rng or SR
    for _ in range(1000):
        if st["finished"] or st["turn"] != AI:
            return st
        a = choose_action(st, AI, st["level"], rng)
        _play(st, AI, a["card"], a["capture"], rng)
    raise RuntimeError("AI loop did not terminate")


# ----------------------------- views / results -----------------------------
def public_view(state):
    """What the browser may see: NOT the deck, NOT the AI's hand."""
    human_turn = (not state["finished"]) and state["turn"] == HUMAN
    return {
        "level": state["level"], "rules": state["rules"], "round": state["round"],
        "scores": state["scores"], "target_score": state["rules"]["target_score"],
        "turn": state["turn"], "finished": state["finished"], "winner": state["winner"],
        "draw": state["draw"], "moves_count": state["moves_count"],
        "resigned": state.get("resigned", False),
        "table": state["table"], "hand": state["hands"][HUMAN],
        "opponent_hand_count": len(state["hands"][AI]), "deck_count": len(state["deck"]),
        "captured_count": [len(state["captured"][0]), len(state["captured"][1])],
        "sur": state["sur"], "last_capturer": state["last_capturer"],
        "round_log": state["round_log"], "events": state["events"],
        "legal_actions": legal_actions(state, HUMAN) if human_turn else [],
    }


def finish_info(state):
    """(result, score_text, stats) for finish_match. Decided purely by the server-side state."""
    if not state["finished"]:
        raise ValueError("game not finished")
    s0, s1 = state["scores"]
    result = "draw" if state["winner"] is None else ("win" if state["winner"] == HUMAN else "loss")
    stats = {"level": state["level"], "rounds": state["round"], "scores": [s0, s1],
             "sur": state["sur_total"], "moves": state["moves_count"], "rules": state["rules"]}
    return result, f"{s0}-{s1}", stats
