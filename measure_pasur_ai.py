"""Self-play measurement of the Pasur AI levels (dev tool, not used by the server).
Usage: python measure_pasur_ai.py [games_per_pair=100] [seed=1]
Each pair plays N full games; the two levels swap seats every game. Prints win counts."""
import random
import sys

import pasur_engine as P


def play_game(level_a, level_b, a_seat, rng):
    lv = {a_seat: level_a, 1 - a_seat: level_b}
    st = P.new_game("medium", rng=rng)
    while not st["finished"]:
        seat = st["turn"]
        act = P.choose_action(st, seat, lv[seat], rng)
        st = P.play_card(st, seat, act["card"], act["capture"], rng)
    return st["winner"]  # 0 / 1 / None


def main(n=100, seed=1):
    rng = random.Random(seed)
    for a, b in (("medium", "easy"), ("hard", "easy"), ("hard", "medium")):
        wa = wb = draws = 0
        for g in range(n):
            a_seat = g % 2
            w = play_game(a, b, a_seat, rng)
            if w is None:
                draws += 1
            elif w == a_seat:
                wa += 1
            else:
                wb += 1
        print(f"{a:6s} vs {b:6s}: {a} won {wa}, {b} won {wb}, draws {draws}  (of {n})")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 100, int(sys.argv[2]) if len(sys.argv) > 2 else 1)
