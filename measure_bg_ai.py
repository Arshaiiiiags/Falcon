"""Self-play strength measurement for the backgammon AI levels (pure Python).
Usage: python measure_bg_ai.py GAMES LEVEL_A LEVEL_B [seed]
Each game both levels play; seats alternate every game. Reports how many games LEVEL_A won
(plain wins, and points) with a rough 95% interval so noise is not mistaken for strength."""
import math
import random
import sys
import time

import backgammon_engine as bg


def play(levels, rng):
    """levels = (level of seat 0, level of seat 1). Returns winner seat and points."""
    st = bg.new_game("medium", rng)
    for _ in range(3000):
        if st["winner"] is not None:
            return st["winner"], st["points_won"]
        st["level"] = levels[st["turn"]]
        plan = bg.ai_plan(st, rng)
        if not plan:
            break
        for s, d, die in plan:
            st = bg.apply_move(st, s, d, die, rng)
    raise RuntimeError("game did not finish")


def main():
    games = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    a = sys.argv[2] if len(sys.argv) > 2 else "hard"
    b = sys.argv[3] if len(sys.argv) > 3 else "medium"
    seed = int(sys.argv[4]) if len(sys.argv) > 4 else 1
    rng = random.Random(seed)
    wins = pts = 0
    t0 = time.time()
    for g in range(games):
        a_seat = g % 2
        levels = (a, b) if a_seat == 0 else (b, a)
        w, p = play(levels, rng)
        if w == a_seat:
            wins += 1
            pts += p
        else:
            pts -= p
    n = games
    rate = wins / n
    ci = 1.96 * math.sqrt(rate * (1 - rate) / n)
    print(f"{a} vs {b}: {wins}/{n} wins = {rate:.1%} (95% CI ±{ci:.1%}); net points {pts:+d}; "
          f"{time.time() - t0:.1f}s total, {(time.time() - t0) / n:.2f}s/game")


if __name__ == "__main__":
    main()
