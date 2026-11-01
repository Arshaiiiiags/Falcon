"""One-command test runner.

    python run_tests.py              # all tests with the current Python (pip only if required imports are missing)

Output is printed and saved to test_output.txt for review.
"""
import os, subprocess, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "test_output.txt")
ALL = ["test_app", "test_regressions", "test_backgammon_engine", "test_pasur_engine", "test_hokm_engine", "test_hokm_api", "test_party", "test_party_games"]


def run(cmd, log):
    log.write("$ " + " ".join(cmd) + "\n"); log.flush()
    p = subprocess.run(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    sys.stdout.write(p.stdout); log.write(p.stdout)
    log.write(f"[exit code {p.returncode}]\n\n"); log.flush()
    return p.returncode


def main():
    """Install missing runtime dependencies, then execute every suite."""
    with open(OUT, "w", encoding="utf-8") as log:
        py = sys.executable
        if subprocess.run([py, "-c", "import flask, dotenv"], cwd=ROOT, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL).returncode != 0:
            if run([py, "-m", "pip", "install", "-r", "requirements.txt"], log) != 0:
                msg = "pip install FAILED - app tests were NOT run.\n"
                sys.stdout.write(msg); log.write(msg)
                return 2
        rc = run([py, "-m", "unittest", *ALL, "-v"], log)
        log.write(("ALL REQUESTED TESTS PASSED\n" if rc == 0 else "SOME TESTS FAILED\n"))
        return rc


if __name__ == "__main__":
    sys.exit(main())
