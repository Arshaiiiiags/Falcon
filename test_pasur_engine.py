"""Tests for pasur_engine (pure Python). Run: python -m unittest test_pasur_engine -v"""
import copy
import json
import random
import unittest

import pasur_engine as P

R = P.DEFAULT_RULES


def mk(table, h0, h1, deck=None, turn=0, rules=None, last_capturer=None, captured=None, sur=None):
    """Build a custom mid-round state from a fresh game (only for rule tests)."""
    st = P.new_game("medium", rules, rng=random.Random(1))
    st["table"] = list(table)
    st["hands"] = [list(h0), list(h1)]
    st["deck"] = list(deck or [])
    st["turn"] = turn
    st["last_capturer"] = last_capturer
    st["captured"] = copy.deepcopy(captured) if captured else [[], []]
    st["sur"] = list(sur) if sur else [0, 0]
    return st


def opts(table, card, rules=None):
    return {frozenset(o) for o in P.capture_options(table, card, P.validate_rules(rules))}


def all_cards(st):
    return (list(st["deck"]) + list(st["table"]) + st["hands"][0] + st["hands"][1]
            + st["captured"][0] + st["captured"][1])


class Setup(unittest.TestCase):
    def test_new_game_layout(self):
        st = P.new_game("easy")
        self.assertEqual((len(st["table"]), len(st["hands"][0]), len(st["hands"][1]), len(st["deck"])), (4, 4, 4, 40))
        self.assertEqual(sorted(all_cards(st)), sorted(P.ALL_CARDS))
        self.assertEqual((st["turn"], st["round"], st["scores"]), (P.HUMAN, 1, [0, 0]))

    def test_no_jack_on_initial_table_rule(self):
        for seed in range(300):
            st = P.new_game("easy", rng=random.Random(seed))
            self.assertFalse(any(P.rank(c) == "J" for c in st["table"]), seed)
            self.assertEqual(len(set(all_cards(st))), 52)
        seen = any(any(P.rank(c) == "J" for c in P.new_game("easy", {"no_jack_on_initial_table": False},
                                                            rng=random.Random(s))["table"]) for s in range(300))
        self.assertTrue(seen)  # with the rule off a Jack can start on the table

    def test_seeded_rng_is_deterministic_and_bad_level(self):
        a = P.new_game("easy", rng=random.Random(5)); b = P.new_game("easy", rng=random.Random(5))
        self.assertEqual(a, b)
        with self.assertRaises(ValueError):
            P.new_game("godlike")


class Rules(unittest.TestCase):
    def test_validate_rules(self):
        self.assertEqual(P.validate_rules(None), R)
        self.assertEqual(P.validate_rules({"target_score": 100})["target_score"], 100)
        for bad in ({"nope": 1}, {"target_score": "100"}, {"target_score": True}, {"target_score": 0},
                    {"capture_mandatory": 1}, {"sur_points": -1}, {"max_rounds": 10 ** 6}, [], "x"):
            with self.assertRaises(P.RulesError, msg=str(bad)):
                P.validate_rules(bad)

    def test_number_card_sums_to_eleven(self):
        t = ["D7", "S3", "H4", "C2", "SK"]
        self.assertEqual(opts(t, "C4"), {frozenset({"D7"}), frozenset({"S3", "H4"}), frozenset({"D7", "S3", "H4"})})
        self.assertEqual(opts(t, "C4", {"multi_group_capture": False}),
                         {frozenset({"D7"}), frozenset({"S3", "H4"})})

    def test_ace_and_ten(self):
        self.assertEqual(opts(["D10", "S4", "H6", "C3"], "HA"),
                         {frozenset({"D10"}), frozenset({"S4", "H6"}), frozenset({"D10", "S4", "H6"})})
        self.assertEqual(opts(["HA", "S5"], "C10"), {frozenset({"HA"})})

    def test_face_cards_never_in_sums_and_no_same_rank_for_numbers(self):
        self.assertEqual(opts(["SK", "HQ", "D4"], "C7"), {frozenset({"D4"})})
        self.assertEqual(opts(["D7"], "C7"), set())  # 7+7 != 11, same number does not capture

    def test_jack_takes_all_but_kings_and_queens(self):
        self.assertEqual(opts(["D5", "SK", "HQ", "C9", "HJ"], "SJ"), {frozenset({"D5", "C9", "HJ"})})
        self.assertEqual(opts(["SK", "HQ"], "SJ"), set())
        self.assertEqual(opts([], "SJ"), set())

    def test_queen_and_king_capture_one_of_same_rank(self):
        self.assertEqual(opts(["HQ", "DQ", "SK", "C5"], "CQ"), {frozenset({"HQ"}), frozenset({"DQ"})})
        self.assertEqual(opts(["HQ", "DQ", "SK", "C5"], "HK"), {frozenset({"SK"})})
        self.assertEqual(opts(["C5"], "HK"), set())

    def test_options_are_exactly_the_valid_sums_bruteforce(self):
        rnd = random.Random(3)
        from itertools import combinations
        for _ in range(60):
            t = rnd.sample([c for c in P.ALL_CARDS if P.rank(c) in P.NUM], rnd.randint(1, 8))
            card = rnd.choice([c for c in P.ALL_CARDS if P.rank(c) in P.NUM and c not in t])
            need = 11 - P.NUM[P.rank(card)]
            single = {frozenset(s) for n in range(1, len(t) + 1) for s in combinations(t, n)
                      if sum(P.NUM[P.rank(x)] for x in s) == need}
            self.assertEqual(opts(t, card, {"multi_group_capture": False}), single)
            for o in opts(t, card):  # every multi option splits into groups, each summing to `need`
                total = sum(P.NUM[P.rank(x)] for x in o)
                self.assertEqual(total % need, 0)


class Playing(unittest.TestCase):
    def test_capture_moves_cards_and_switches_turn(self):
        st = mk(["D7", "S2"], ["H4", "C9"], ["D3", "H8", "S6", "C5"], deck=["SA"] * 0)
        n = P.apply_move(st, "H4", ["D7"])
        self.assertEqual(n["table"], ["S2"])
        self.assertEqual(sorted(n["captured"][0]), ["D7", "H4"])
        self.assertEqual((n["turn"], n["last_capturer"], n["moves_count"]), (1, 0, 1))
        self.assertEqual(st["table"], ["D7", "S2"])  # input state untouched

    def test_place_without_capture(self):
        st = mk(["D7"], ["C9", "H4"], ["D3", "H8"])
        n = P.apply_move(st, "C9", [])
        self.assertEqual(n["table"], ["D7", "C9"])
        self.assertIsNone(n["last_capturer"])

    def test_illegal_moves_raise_illegalmove_only(self):
        st = mk(["D7", "S3", "SK"], ["H4", "C9"], ["D3", "H8"])
        bad = [("H5", []), (None, []), (5, []), ("H4", ["D8"]), ("H4", ["S3"]), ("H4", ["D7", "D7"]),
               ("H4", ["D7", "S3"]), ("H4", "D7"), ("H4", [1]), ("H4", ["SK"]), ("H4", [None]),
               ("H4", {"a": 1}), ("D3", [])]  # last one: D3 is the AI's card
        for card, cap in bad:
            with self.assertRaises(P.IllegalMove, msg=f"{card!r} {cap!r}"):
                P.apply_move(st, card, cap)

    def test_not_your_turn_and_finished(self):
        st = mk(["D7"], ["H4"], ["D3"], turn=1)
        with self.assertRaises(P.IllegalMove):
            P.apply_move(st, "H4", ["D7"])
        st = mk(["D7"], ["H4"], ["D3"]); st["finished"] = True
        with self.assertRaises(P.IllegalMove):
            P.apply_move(st, "H4", ["D7"])
        self.assertEqual(P.legal_actions(st), [])

    def test_capture_mandatory_rule(self):
        st = mk(["D7"], ["H4", "C9"], ["D3", "H8"], rules={"capture_mandatory": True})
        with self.assertRaises(P.IllegalMove):
            P.apply_move(st, "H4", [])  # H4 can capture D7, so it may not just be placed
        P.apply_move(st, "C9", [])      # C9 cannot capture, placing is fine
        free = mk(["D7"], ["H4", "C9"], ["D3", "H8"])
        P.apply_move(free, "H4", [])    # default rules: optional
        acts = P.legal_actions(st)
        self.assertNotIn({"card": "H4", "capture": []}, acts)
        self.assertIn({"card": "H4", "capture": ["D7"]}, acts)

    def test_legal_actions_are_all_accepted_by_engine(self):
        for seed in range(30):
            st = P.new_game("easy", rng=random.Random(seed))
            for a in P.legal_actions(st):
                P.apply_move(st, a["card"], a["capture"])


class Sur(unittest.TestCase):
    def test_sur_counts_when_table_cleared(self):
        st = mk(["D7"], ["H4", "C9"], ["D3", "H8"], deck=["S2", "S3", "S5", "S6"])
        n = P.apply_move(st, "H4", ["D7"])
        self.assertEqual((n["sur"], n["sur_total"]), ([1, 0], [1, 0]))
        self.assertTrue(n["events"][0]["sur"])

    def test_no_sur_if_cards_remain(self):
        st = mk(["D7", "S2"], ["H4", "C9"], ["D3", "H8"], deck=["S3", "S5", "S6", "S9"])
        self.assertEqual(P.apply_move(st, "H4", ["D7"])["sur"], [0, 0])

    def test_jack_sur_does_not_count_by_default(self):
        st = mk(["D7", "S2"], ["HJ", "C9"], ["D3", "H8"], deck=["S3", "S5", "S6", "S9"])
        self.assertEqual(P.apply_move(st, "HJ", ["D7", "S2"])["sur"], [0, 0])
        st2 = mk(["D7", "S2"], ["HJ", "C9"], ["D3", "H8"], deck=["S3", "S5", "S6", "S9"], rules={"jack_sur_counts": True})
        self.assertEqual(P.apply_move(st2, "HJ", ["D7", "S2"])["sur"], [1, 0])

    def test_last_play_sur_does_not_count_by_default(self):
        st = mk(["D7"], ["H4"], [], deck=[], last_capturer=1)
        n = P.apply_move(st, "H4", ["D7"])
        self.assertEqual(n["sur_total"], [0, 0])
        st2 = mk(["D7"], ["H4"], [], deck=[], last_capturer=1, rules={"last_sur_counts": True})
        self.assertEqual(P.apply_move(st2, "H4", ["D7"])["sur_total"], [1, 0])


class Scoring(unittest.TestCase):
    def test_full_breakdown(self):
        clubs = ["C" + r for r in ("A", "2", "3", "4", "5", "6", "7", "8")]  # 8 clubs incl. C2 and CA
        p0 = clubs + ["D10", "SA", "HJ", "DK", "HK", "SQ", "H3", "H5", "H6", "H7"]
        p1 = [c for c in P.ALL_CARDS if c not in p0]
        pts, br = P.score_round([p0, p1], [1, 0], R)
        # p0: cards 18 vs 34 -> 0 ; clubs 8 vs 5 -> 7 ; D10 3 ; C2 2 ; aces CA+SA=2 ; jacks 1 ; sur 5
        self.assertEqual(br[0]["most_cards"], 0)
        self.assertEqual(br[0]["total"], 7 + 3 + 2 + 2 + 1 + 5)
        # p1: cards 34 -> 3 ; clubs 5 -> 0 ; aces DA,HA = 2 ; jacks CJ,DJ,SJ = 3
        self.assertEqual(br[1]["total"], 3 + 2 + 3)
        self.assertEqual(pts, [br[0]["total"], br[1]["total"]])

    def test_ties_score_nothing_and_rules_change_values(self):
        a = P.ALL_CARDS[:26]; b = P.ALL_CARDS[26:]
        pts, br = P.score_round([a, b], [0, 0], R)
        self.assertEqual(br[0]["most_cards"] + br[1]["most_cards"], 0)
        a2 = [c for c in P.ALL_CARDS if P.suit(c) == "C"][:6]
        b2 = [c for c in P.ALL_CARDS if P.suit(c) == "C"][6:]
        _, br2 = P.score_round([a2, b2], [0, 0], R)
        self.assertEqual(br2[1]["most_clubs"], 7)
        r = P.validate_rules({"most_clubs_points": 9, "sur_points": 10})
        _, br3 = P.score_round([a2, b2], [2, 0], r)
        self.assertEqual((br3[1]["most_clubs"], br3[0]["sur"]), (9, 20))

    def test_total_available_without_sur_is_23(self):
        # clubs 7 + cards 3 + D10 3 + C2 2 + aces 4 + jacks 4 = 23 split between the players
        top = P.score_round([list(P.ALL_CARDS), []], [0, 0], R)[0][0]
        self.assertEqual(top, 23)


class RoundAndGameFlow(unittest.TestCase):
    def test_last_capturer_takes_table_and_round_ends(self):
        st = mk(["D7", "S2"], ["H4"], [], deck=[], last_capturer=1,
                captured=[[], ["CA"]])
        n = P.apply_move(st, "H4", ["D7"])
        log = n["round_log"][0]
        self.assertEqual(log["breakdown"][0]["cards"], 3)  # H4 + D7 + leftover S2 (human captured last)
        self.assertEqual((n["round"], n["leader"], n["turn"]), (2, P.AI, P.AI))  # new round, AI leads
        self.assertEqual(len(n["table"]), 4)
        self.assertEqual(len(set(all_cards(n))), 52)

    def test_leftover_discarded_when_rule_off(self):
        st = mk(["D7", "S2"], ["H4"], [], deck=[], last_capturer=1, rules={"last_capturer_takes_table": False})
        n = P.apply_move(st, "H4", ["D7"])
        self.assertEqual(n["round_log"][0]["breakdown"][0]["cards"], 2)

    def _near_end(self, scores, rules=None, rnd=1):
        st = mk(["D7"], ["H4"], [], deck=[], last_capturer=0, rules=rules)
        st["scores"] = list(scores); st["round"] = rnd
        return st

    def test_game_ends_at_target_and_winner_is_higher(self):
        n = P.apply_move(self._near_end([60, 20]), "H4", ["D7"])
        self.assertTrue(n["finished"])
        self.assertEqual(n["winner"], P.HUMAN)
        self.assertIsNone(n["turn"])
        self.assertEqual(P.legal_actions(n), [])
        res, score, stats = P.finish_info(n)
        self.assertEqual(res, "win")
        self.assertEqual(score, f"{n['scores'][0]}-{n['scores'][1]}")
        self.assertEqual(stats["rounds"], 1)

    def test_ai_wins_gives_loss(self):
        n = P.apply_move(self._near_end([0, 90]), "H4", ["D7"])
        self.assertTrue(n["finished"])
        self.assertEqual(P.finish_info(n)[0], "loss")

    def test_below_target_continues(self):
        n = P.apply_move(self._near_end([1, 1], {"target_score": 500}), "H4", ["D7"])
        self.assertFalse(n["finished"])
        self.assertEqual(n["round"], 2)

    def test_tie_at_target_plays_another_round(self):
        st = self._near_end([30, 30], {"target_score": 10})
        # zero every point value so the round adds nothing: the totals stay tied at/after the target
        for k in ("most_cards_points", "most_clubs_points", "ten_diamonds_points", "two_clubs_points",
                  "ace_points", "jack_points", "sur_points"):
            st["rules"][k] = 0
        n = P.apply_move(st, "H4", ["D7"])
        self.assertFalse(n["finished"])  # tied at/after target -> another round
        self.assertEqual(n["round"], 2)

    def test_max_rounds_draw(self):
        st = self._near_end([30, 30], {"max_rounds": 1, "target_score": 1000})
        for k in ("most_cards_points", "most_clubs_points", "ten_diamonds_points", "two_clubs_points",
                  "ace_points", "jack_points", "sur_points"):
            st["rules"][k] = 0
        n = P.apply_move(st, "H4", ["D7"])
        self.assertTrue(n["finished"] and n["draw"] and n["winner"] is None)
        self.assertEqual(P.finish_info(n)[0], "draw")

    def test_finish_info_requires_finished(self):
        with self.assertRaises(ValueError):
            P.finish_info(P.new_game("easy"))


class FullGames(unittest.TestCase):
    def _play(self, level_h, level_a, seed, check=True):
        rng = random.Random(seed)
        st = P.new_game("medium", rng=rng)
        steps = 0
        while not st["finished"]:
            seat = st["turn"]
            a = P.choose_action(st, seat, level_h if seat == 0 else level_a, rng)
            st = P.play_card(st, seat, a["card"], a["capture"], rng)
            steps += 1
            if check:
                if not st["finished"]:  # mid-game: every one of the 52 cards is somewhere, exactly once
                    self.assertEqual(sorted(all_cards(st)), sorted(P.ALL_CARDS))
                self.assertEqual(json.loads(json.dumps(st)), st)  # JSON-safe round trip
            self.assertLess(steps, 3000)
        return st

    def test_all_level_pairs_finish_with_invariants(self):
        for lv in P.LEVELS:
            st = self._play(lv, lv, seed=11)
            self.assertTrue(st["finished"])
            self.assertEqual(sum(b["cards"] for b in st["round_log"][-1]["breakdown"]), 52)

    def test_every_round_accounts_for_all_52_cards(self):
        st = self._play("easy", "medium", seed=5, check=False)
        for rl in st["round_log"]:
            self.assertEqual(sum(b["cards"] for b in rl["breakdown"]), 52)

    def test_apply_move_and_play_ai_turns_do_not_mutate_input(self):
        st = P.new_game("medium", rng=random.Random(2))
        snap = copy.deepcopy(st)
        a = P.legal_actions(st)[0]
        n = P.apply_move(st, a["card"], a["capture"])
        P.play_ai_turns(n)
        self.assertEqual(st, snap)

    def test_play_ai_turns_stops_on_human_turn_and_finished(self):
        st = P.new_game("hard", rng=random.Random(4))
        a = P.legal_actions(st)[0]
        n = P.play_ai_turns(P.apply_move(st, a["card"], a["capture"]))
        self.assertIn(n["turn"], (P.HUMAN, None))
        self.assertEqual(P.play_ai_turns(n), n)  # nothing left for the AI to do


class AiAndViews(unittest.TestCase):
    def test_ai_does_not_peek_at_hidden_cards(self):
        """Same visible information => same choice, whatever the opponent's hand / deck order is."""
        for level in ("medium", "hard"):
            for seed in range(8):
                st = P.new_game(level, rng=random.Random(seed))
                st["turn"] = P.AI  # AI (seat 1) to move
                other = copy.deepcopy(st)
                # swap the HUMAN hand with the same number of deck cards, and reshuffle the deck
                h = other["hands"][0]; k = len(h)
                other["hands"][0], other["deck"] = other["deck"][:k], h + other["deck"][k:]
                random.Random(99).shuffle(other["deck"])
                a = P.choose_action(st, P.AI, level, random.Random(7))
                b = P.choose_action(other, P.AI, level, random.Random(7))
                self.assertEqual(a, b, (level, seed))

    def test_public_view_hides_deck_and_ai_hand(self):
        st = P.new_game("hard", rng=random.Random(8))
        v = P.public_view(st)
        text = json.dumps(v)
        self.assertNotIn("deck", v)
        self.assertNotIn("hands", v)
        self.assertEqual(v["opponent_hand_count"], 4)
        self.assertEqual(v["deck_count"], 40)
        self.assertEqual(v["hand"], st["hands"][0])
        for c in st["hands"][1]:
            self.assertNotIn(f'"{c}"', text)  # AI hand cards appear nowhere in the view
        for c in st["deck"]:
            self.assertNotIn(f'"{c}"', text)

    def test_public_view_legal_actions_only_on_human_turn(self):
        st = P.new_game("easy", rng=random.Random(1))
        self.assertTrue(P.public_view(st)["legal_actions"])
        st["turn"] = P.AI
        self.assertEqual(P.public_view(st)["legal_actions"], [])

    def test_ai_prefers_big_capture_over_placing(self):
        # AI holds the ten of diamonds; table has an Ace -> medium/hard should take it (and not just place)
        st = mk(["HA", "S5"], ["C6"], ["D10", "H8"], deck=[], turn=1)
        for level in ("medium", "hard"):
            a = P.choose_action(st, P.AI, level, random.Random(0))
            self.assertEqual(a["card"], "D10")
            self.assertEqual(a["capture"], ["HA"])


class EndpointFlowWithoutHttp(unittest.TestCase):
    """Replays what app.py's pasur_start/pasur_move do with the stored JSON, minus Flask and the database
    (those parts are NOT covered here - see test_app.py, which has never been run)."""

    def test_stored_json_roundtrip_whole_game(self):
        for level in P.LEVELS:
            stored = json.dumps(P.play_ai_turns(P.new_game(level)))          # pasur_start
            for _ in range(1000):
                st = json.loads(stored)
                view = P.public_view(st)
                json.dumps(view)
                if st["finished"]:
                    break
                self.assertEqual(st["turn"], P.HUMAN)
                a = view["legal_actions"][0]
                st = P.play_ai_turns(P.apply_move(st, a["card"], a["capture"]))  # pasur_move
                stored = json.dumps(st)
            st = json.loads(stored)
            self.assertTrue(st["finished"])
            result, score, stats = P.finish_info(st)
            self.assertIn(result, ("win", "loss", "draw"))
            json.dumps(stats)
            self.assertLessEqual(len(score), 32)  # match_results.score is String(32)


class AiStrength(unittest.TestCase):
    """Fixed seeds => deterministic, not flaky. Thresholds are far below the measured rates
    (medium vs easy 100%, hard vs medium ~73% over 200 games) - see measure_pasur_ai.py."""

    def _wins(self, a, b, n, seed):
        import measure_pasur_ai as M
        rng = random.Random(seed)
        w = 0
        for g in range(n):
            res = M.play_game(a, b, g % 2, rng)
            w += (res == g % 2)
        return w

    def test_medium_beats_easy(self):
        self.assertGreaterEqual(self._wins("medium", "easy", 30, 21), 24)

    def test_hard_beats_medium(self):
        self.assertGreaterEqual(self._wins("hard", "medium", 60, 22), 36)


if __name__ == "__main__":
    unittest.main()
