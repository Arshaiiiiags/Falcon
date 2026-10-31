"""Run: python -m unittest test_backgammon_engine -v   (no third-party packages needed)"""
import json
import random
import unittest

import backgammon_engine as bg


def mk(points=None, bar=(0, 0), off=(0, 0), turn=0, dice=(3, 1), level="medium"):
    pts = [0] * 24
    for i, v in (points or {}).items():
        pts[i] = v
    return {"points": pts, "bar": list(bar), "off": list(off), "turn": turn, "roll": list(dice),
            "dice": list(dice), "winner": None, "win_type": None, "points_won": 0,
            "level": level, "moves_count": 0, "events": [], "ai_turns": []}


def total(st, p):
    pts = st["points"]
    on = sum(v for v in pts if v > 0) if p == 0 else -sum(v for v in pts if v < 0)
    return on + st["bar"][p] + st["off"][p]


class EngineTests(unittest.TestCase):
    def test_initial_position(self):
        st = bg.new_game("easy", random.Random(1))
        self.assertEqual((total(st, 0), total(st, 1)), (15, 15))
        self.assertEqual(st["points"][23], 2)
        self.assertEqual(st["points"][0], -2)

    def test_state_is_json_serialisable_and_roundtrips(self):
        st = bg.new_game("medium", random.Random(2))
        st2 = json.loads(json.dumps(st))
        self.assertEqual(st, st2)
        json.dumps(bg.public_view(st))

    def test_hit_sends_blot_to_bar(self):
        st = mk({10: 2, 7: -1, 20: -2}, dice=(3, 5))
        st = bg.apply_move(st, 10, 7, 3, random.Random(0))
        self.assertEqual(st["bar"][1], 1)
        self.assertEqual(st["points"][7], 1)

    def test_blocked_point(self):
        st = mk({10: 2, 7: -2}, dice=(3, 6))
        moves = {(m["src"], m["dst"]) for m in bg.legal_moves(st)}
        self.assertNotIn((10, 7), moves)

    def test_must_enter_from_bar_first(self):
        st = mk({10: 2, 20: -2}, bar=(1, 0), dice=(3, 4))
        for m in bg.legal_moves(st):
            self.assertEqual(m["src"], "bar")

    def test_entry_blocked_means_pass(self):
        # seat 0 enters on index 24-die; block both 24-3=21 and 24-4=20 with 2 opposing checkers
        st = mk({21: -2, 20: -2, 5: 1}, bar=(1, 0), dice=(3, 4), off=(13, 0))
        st["bar"] = [1, 0]
        self.assertEqual(bg.legal_moves(st), [])
        bg._settle(st, random.Random(3))
        self.assertEqual(st["turn"], 1)
        self.assertEqual(st["events"][0]["type"], "pass")

    def test_no_bearing_off_unless_all_home(self):
        st = mk({2: 1, 10: 1}, off=(13, 0), dice=(6, 6))
        for m in bg.legal_moves(st):
            self.assertNotEqual(m["dst"], "off")

    def test_bearing_off_exact_and_higher(self):
        st = mk({2: 1, 0: 1}, off=(13, 0), dice=(3, 6))
        offs = {(m["src"], m["die"]) for m in bg.legal_moves(st) if m["dst"] == "off"}
        self.assertIn((2, 3), offs)      # exact
        self.assertIn((2, 6), offs)      # higher die from the farthest checker
        self.assertNotIn((0, 6), offs)   # a checker farther back exists -> can't use 6 on point 1

    def test_higher_die_off_only_if_nothing_farther(self):
        st = mk({1: 1}, off=(14, 0), dice=(5, 4))
        offs = [m for m in bg.legal_moves(st) if m["dst"] == "off"]
        self.assertTrue(offs)

    def test_larger_die_rule_when_only_one_can_be_played(self):
        # single checker on 11, point 0 blocked: 6 (->5) or 5 (->6) playable, never both
        st = mk({11: 1, 0: -2}, off=(14, 0), dice=(5, 6))
        lm = bg.legal_moves(st)
        self.assertEqual({m["die"] for m in lm}, {6})

    def test_must_use_both_dice_when_possible(self):
        st = mk({11: 1, 20: -2}, off=(14, 0), dice=(5, 6))
        out = bg.apply_move(st, 11, 5, 6, random.Random(0))
        self.assertEqual(len(out["dice"]) or 0, 1)

    def test_doubles_give_four_moves(self):
        st = mk(bg_points_start(), dice=(2, 2))
        st["dice"] = [2, 2, 2, 2]
        n = 0
        rng = random.Random(0)
        while st["turn"] == 0 and st["winner"] is None and n < 10:
            m = bg.legal_moves(st)[0]
            st = bg.apply_move(st, m["src"], m["dst"], m["die"], rng)
            n += 1
        self.assertEqual(n, 4)

    def test_illegal_inputs_rejected(self):
        st = mk(bg_points_start(), dice=(3, 1))
        for args in [(0, 3, None), ("x", 3, None), (23, 20, 5), (23, "off", None), (True, 3, None),
                     (23, 99, None), (None, None, None), ([1], 2, None), ("off", 3, None)]:
            with self.assertRaises(bg.IllegalMove, msg=str(args)):
                bg.apply_move(st, *args)

    def test_cannot_move_after_game_over(self):
        st = mk({0: 1}, off=(14, 0), dice=(1, 2))
        st = bg.apply_move(st, 0, "off", None, random.Random(0))
        self.assertEqual(st["winner"], 0)
        with self.assertRaises(bg.IllegalMove):
            bg.apply_move(st, 0, "off")

    def test_win_types(self):
        base = {"points": [0] * 24, "bar": [0, 0], "off": [15, 5]}
        self.assertEqual(bg.win_type(base, 0), 1)
        g = {"points": [0] * 24, "bar": [0, 0], "off": [15, 0]}
        g["points"][10] = -3
        self.assertEqual(bg.win_type(g, 0), 2)
        b1 = {"points": [0] * 24, "bar": [1, 0][::-1], "off": [15, 0]}
        self.assertEqual(bg.win_type(b1, 0), 3)           # loser on the bar
        b2 = {"points": [0] * 24, "bar": [0, 0], "off": [15, 0]}
        b2["points"][3] = -2                              # loser inside winner's home
        self.assertEqual(bg.win_type(b2, 0), 3)

    def test_win_sets_points_and_type(self):
        st = mk({0: 1, 12: -3}, off=(14, 0), dice=(1, 2))
        st = bg.apply_move(st, 0, "off", None, random.Random(0))
        self.assertEqual((st["winner"], st["win_type"], st["points_won"]), (0, "gammon", 2))

    def test_seat1_direction_and_bearing_off(self):
        st = mk({22: -1, 23: -1}, off=(0, 13), turn=1, dice=(2, 1))
        offs = {(m["src"], m["die"]) for m in bg.legal_moves(st) if m["dst"] == "off"}
        self.assertIn((22, 2), offs)
        self.assertIn((23, 1), offs)

    def test_ai_levels_play_complete_legal_games(self):
        """Human side plays random legal moves; AI plays at each level. Checks invariants every step."""
        for level in bg.LEVELS:
            games = 2 if level == "hard" else 4
            for g in range(games):
                rng = random.Random(100 * g + len(level))
                st = bg.play_ai_turns(bg.new_game(level, rng), rng)
                steps = 0
                while st["winner"] is None:
                    steps += 1
                    self.assertLess(steps, 3000, "game does not terminate")
                    lm = bg.legal_moves(st)
                    self.assertTrue(lm, "human turn with no legal moves must never be returned")
                    m = rng.choice(lm)
                    st = bg.apply_move(st, m["src"], m["dst"], m["die"], rng)
                    st = bg.play_ai_turns(st, rng)
                    self.assertEqual((total(st, 0), total(st, 1)), (15, 15))
                self.assertEqual(st["off"][st["winner"]], 15)
                self.assertIn(st["points_won"], (1, 2, 3))

    def test_dice_never_taken_from_input(self):
        st = bg.new_game("easy", random.Random(7))
        self.assertTrue(all(1 <= d <= 6 for d in st["dice"]))
        self.assertIn(len(st["dice"]), (2, 4))


def mkc(points=None, turn=0, level="medium", value=1, owner=None, pending=None, bar=(0, 0), off=(0, 0)):
    """A cube game at the start of a turn (before rolling)."""
    st = mk(points, bar=bar, off=off, turn=turn, dice=(), level=level)
    st["roll"], st["dice"] = [], []
    st["phase"] = "pre_roll"
    st["cube"] = {"enabled": True, "value": value, "owner": owner, "pending": pending}
    return st


# human far behind in the race (human pips 360 vs AI pips 30) / the reverse
AI_AHEAD = {23: 15, 22: -15}
HUMAN_AHEAD = {0: 15, 1: -15}


class DoublingCube(unittest.TestCase):
    def test_cube_is_off_by_default_and_old_states_still_work(self):
        st = bg.new_game("easy", random.Random(1))
        self.assertFalse(st["cube"]["enabled"])
        v = bg.public_view(st)
        self.assertFalse(v["cube"]["enabled"])
        self.assertFalse(v["can_double"] or v["can_roll"] or v["must_respond"])
        old = mk({10: 2}, dice=(3, 1))  # a state saved before the cube existed: no cube/phase keys
        v = bg.public_view(old)
        self.assertEqual((v["phase"], v["cube"]["value"], v["can_double"]), ("move", 1, False))
        self.assertFalse(bg.can_double(old, 0))

    def test_turn_ends_in_pre_roll_when_cube_is_on(self):
        st = bg.new_game("easy", random.Random(3), cube=True)
        self.assertEqual(st["phase"], "move")  # opening roll is never doubled
        for _ in range(200):
            if st["phase"] == "pre_roll" or st["winner"] is not None:
                break
            m = bg.legal_moves(st)
            st = bg.apply_move(st, m[0]["src"], m[0]["dst"], m[0]["die"], random.Random(5)) if st["turn"] == 0 \
                else bg.play_ai_turns(st, random.Random(5))
        self.assertEqual(st["phase"], "pre_roll")
        self.assertEqual((st["dice"], st["roll"]), ([], []))
        self.assertEqual(bg.legal_moves(st), [])
        with self.assertRaises(bg.IllegalMove):  # nobody can move before rolling
            bg.apply_move(st, 0, 1)

    def test_who_may_double(self):
        st = mkc(AI_AHEAD)
        self.assertTrue(bg.can_double(st, 0))
        self.assertFalse(bg.can_double(st, 1))                    # not their turn
        self.assertFalse(bg.can_double(mkc(AI_AHEAD, owner=1), 0))  # opponent owns the cube
        self.assertTrue(bg.can_double(mkc(AI_AHEAD, owner=0, value=2), 0))
        self.assertFalse(bg.can_double(mkc(AI_AHEAD, owner=0, value=64), 0))  # cube maximum
        self.assertFalse(bg.can_double(mkc(AI_AHEAD, pending={"by": 1, "value": 2}), 0))
        mv = mk({10: 2}, dice=(3, 1)); mv["cube"] = {"enabled": True, "value": 1, "owner": None, "pending": None}
        self.assertFalse(bg.can_double(mv, 0))                     # only before rolling
        with self.assertRaises(bg.IllegalMove):
            bg.offer_double(mkc(AI_AHEAD, owner=1), 0)

    def test_take_doubles_value_and_gives_cube_to_responder(self):
        st = bg.offer_double(mkc(AI_AHEAD, turn=0), 0)
        self.assertEqual(st["cube"]["pending"], {"by": 0, "value": 2})
        with self.assertRaises(bg.IllegalMove):                    # cannot roll while an offer is open
            bg.roll_dice(st)
        st = bg.respond_double(st, True)
        self.assertEqual((st["cube"]["value"], st["cube"]["owner"], st["cube"]["pending"]), (2, 1, None))
        self.assertEqual((st["turn"], st["phase"], st["winner"]), (0, "pre_roll", None))
        self.assertFalse(bg.can_double(st, 0))  # the doubler lost the right to redouble
        st["turn"] = 1
        self.assertTrue(bg.can_double(st, 1))   # the owner may redouble
        st = bg.respond_double(bg.offer_double(st, 1), True)
        self.assertEqual((st["cube"]["value"], st["cube"]["owner"]), (4, 0))

    def test_drop_ends_game_with_previous_cube_value(self):
        st = bg.respond_double(bg.offer_double(mkc(AI_AHEAD, value=2, owner=0), 0), False)
        self.assertEqual((st["winner"], st["win_type"], st["points_won"]), (0, "cube_drop", 2))
        st = bg.respond_double(bg.offer_double(mkc(AI_AHEAD), 0), False)
        self.assertEqual(st["points_won"], 1)
        with self.assertRaises(bg.IllegalMove):
            bg.respond_double(st, True)  # nothing pending any more
        with self.assertRaises(bg.IllegalMove):
            bg.respond_double(mkc(AI_AHEAD), True)

    def test_roll_dice_is_server_side_and_passes_when_blocked(self):
        st = bg.roll_dice(mkc({10: 2, 20: -2}), random.Random(4))
        self.assertEqual(st["phase"], "move")
        self.assertTrue(all(1 <= d <= 6 for d in st["dice"]) and len(st["roll"]) == 2)
        with self.assertRaises(bg.IllegalMove):
            bg.roll_dice(st)  # already rolled
        # human on the bar and every entry point blocked -> any roll is an automatic pass
        blocked = {i: -2 for i in range(18, 24)}
        blocked[10] = 1
        st = mkc(blocked, bar=(1, 0))
        st = bg.roll_dice(st, random.Random(9))
        self.assertEqual((st["turn"], st["phase"], st["dice"]), (1, "pre_roll", []))
        self.assertEqual(st["events"][-1]["type"], "pass")

    def test_cube_value_multiplies_game_points(self):
        for value, last_pts_expected in ((1, 2), (4, 8)):
            st = mkc({0: 1, 11: -15}, off=(14, 0), value=value, owner=1)
            st = bg.roll_dice(st, random.Random(1))
            st["dice"], st["roll"] = [1], [1, 1]
            st = bg.apply_move(st, 0, "off", 1, random.Random(0))
            self.assertEqual((st["winner"], st["win_type"], st["points_won"]), (0, "gammon", last_pts_expected))

    def test_ai_double_and_take_heuristics(self):
        self.assertTrue(bg.ai_should_double(mkc(AI_AHEAD, turn=1, level="medium")))
        self.assertTrue(bg.ai_should_double(mkc(AI_AHEAD, turn=1, level="hard")))
        self.assertFalse(bg.ai_should_double(mkc(AI_AHEAD, turn=1, level="easy")))
        self.assertFalse(bg.ai_should_double(mkc(HUMAN_AHEAD, turn=1)))                   # behind
        self.assertFalse(bg.ai_should_double(mkc(AI_AHEAD, turn=1, owner=0)))             # human owns cube
        self.assertFalse(bg.ai_should_double(mkc(AI_AHEAD, turn=0)))                      # not AI's turn
        self.assertFalse(bg.ai_should_double(mkc({23: 14, 22: -14}, turn=1, bar=(0, 1))))  # AI checker on bar
        self.assertTrue(bg.ai_takes_double(mkc(AI_AHEAD, level="hard")))
        self.assertFalse(bg.ai_takes_double(mkc(HUMAN_AHEAD, level="hard")))            # far behind: drop
        self.assertFalse(bg.ai_takes_double(mkc(HUMAN_AHEAD, level="medium")))
        self.assertTrue(bg.ai_takes_double(mkc(HUMAN_AHEAD, level="easy")))             # easy always takes

    def test_human_double_resolved_by_ai(self):
        st = bg.human_double(mkc(HUMAN_AHEAD, level="hard"))   # AI far behind -> drops
        self.assertEqual((st["winner"], st["win_type"], st["points_won"]), (0, "cube_drop", 1))
        st = bg.human_double(mkc(AI_AHEAD, level="hard"))      # AI far ahead -> takes
        self.assertEqual((st["winner"], st["cube"]["value"], st["cube"]["owner"]), (None, 2, 1))

    def test_ai_turn_in_cube_game(self):
        # AI ahead: it offers a double instead of rolling, then waits for the human
        st = bg.play_ai_turns(mkc(AI_AHEAD, turn=1, level="hard"), random.Random(2))
        self.assertEqual(st["cube"]["pending"], {"by": 1, "value": 2})
        self.assertEqual(st["dice"], [])
        v = bg.public_view(st)
        self.assertTrue(v["must_respond"] and not v["can_roll"] and not v["can_double"])
        self.assertEqual(bg.play_ai_turns(st, random.Random(2)), st)  # still waiting, nothing changes
        st2 = bg.play_ai_turns(bg.respond_double(st, True), random.Random(2))  # human takes -> AI rolls and plays
        self.assertEqual(st2["cube"]["owner"], 0)
        self.assertEqual((st2["turn"], st2["winner"] is not None), (0, st2["winner"] is not None))
        # AI not ahead: it just rolls and plays, never offering
        st3 = bg.play_ai_turns(mkc({0: 3, 23: 3, 5: -3, 12: -3}, turn=1, level="medium"), random.Random(2))
        self.assertIsNone(st3["cube"]["pending"])
        self.assertEqual(st3["turn"], 0)
        self.assertEqual(st3["phase"], "pre_roll")

    def test_full_random_cube_games_keep_invariants(self):
        for seed, level in enumerate(("easy", "medium", "easy", "medium", "easy", "medium")):
            rng = random.Random(100 + seed)
            st = bg.play_ai_turns(bg.new_game(level, rng, cube=True), rng)
            for _ in range(6000):
                v = bg.public_view(st)
                json.dumps(v)
                self.assertEqual((total(st, 0), total(st, 1)), (15, 15))
                self.assertIn(st["cube"]["value"], (1, 2, 4, 8, 16, 32, 64))
                if st["winner"] is not None:
                    break
                if v["must_respond"]:
                    st = bg.respond_double(st, rng.random() < 0.7)
                elif v["can_roll"]:
                    st = bg.human_double(st) if v["can_double"] and rng.random() < 0.2 else bg.roll_dice(st, rng)
                else:
                    m = rng.choice(v["legal_moves"])
                    st = bg.apply_move(st, m["src"], m["dst"], m["die"], rng)
                st = bg.play_ai_turns(st, rng)
            self.assertIsNotNone(st["winner"], (seed, level))
            self.assertGreaterEqual(st["points_won"], st["cube"]["value"] if st["win_type"] != "cube_drop" else 1)


def bg_points_start():
    return {23: 2, 12: 5, 7: 3, 5: 5, 0: -2, 11: -5, 16: -3, 18: -5}


if __name__ == "__main__":
    unittest.main()
