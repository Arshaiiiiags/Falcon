"""Real HTTP checks against two local production-mode Gunicorn workers.

Run: python smoke_test.py. Uses throwaway storage and stops its server afterward.
"""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from http.cookies import SimpleCookie
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class Client:
    def __init__(self, base, cookie="", csrf=""):
        self.base, self.cookie, self.csrf = base, cookie, csrf

    def request(self, method, path, data=None):
        headers = {"Cookie": self.cookie, "X-CSRF-Token": self.csrf}
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = Request(self.base + path, method=method, headers=headers,
                          data=json.dumps(data).encode() if data is not None else None)
        try:
            response = urlopen(request, timeout=15)
        except HTTPError as error:
            response = error
        with response:
            # Production cookies are Secure. Attach them explicitly only for this loopback HTTP test.
            if response.headers.get("Set-Cookie"):
                cookies = SimpleCookie(response.headers["Set-Cookie"])
                self.cookie = "session=" + cookies["session"].value
            body = json.loads(response.read())
            self.csrf = body.get("csrf", body.get("token", self.csrf))
            return response.status, body

    def clone(self):
        return Client(self.base, self.cookie, self.csrf)

    def create(self, key=None):
        return self.request("POST", "/api/matches", {"game": "backgammon", "idem_key": key or secrets.token_hex(16)})


def main():
    with tempfile.TemporaryDirectory() as directory:
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        env = dict(os.environ, APP_ENV="production", SECRET_KEY=secrets.token_hex(32),
                   TRUST_PROXY="0", DATABASE_PATH=str(Path(directory) / "smoke.db"))
        with open(Path(directory) / "server.log", "w+") as log:
            process = subprocess.Popen([sys.executable, "-m", "gunicorn", "app:app", "--workers", "2",
                                        "--bind", f"127.0.0.1:{port}"],
                                       cwd=Path(__file__).parent, env=env, stdout=log, stderr=log)
            try:
                client = Client(f"http://127.0.0.1:{port}")
                for _ in range(100):
                    if process.poll() is not None:
                        log.seek(0)
                        raise RuntimeError(log.read())
                    try:
                        assert client.request("GET", "/api/health") == (200, {"ok": True})
                        break
                    except URLError:
                        time.sleep(0.05)
                else:
                    raise RuntimeError("Server did not become healthy")
                client.request("GET", "/api/csrf")
                code, _ = client.request("POST", "/api/register", {"username": "smoke_player", "password": "password123", "confirm": "password123"})
                assert code == 200
                code, created = client.create()
                assert code == 201
                mid = created["match"]["id"]
                assert client.request("POST", f"/api/matches/{mid}/activate")[0] == 200
                code, game = client.request("POST", f"/api/matches/{mid}/bg/start", {"level": "hard", "cube": True})
                assert code == 201
                started = time.perf_counter()
                for _ in range(2000):
                    if game["match_status"] == "completed": break
                    state, version = game["state"], game["version"]
                    if state["must_respond"]:
                        action, payload = "respond", {"accept": True}
                    elif state["can_roll"]:
                        action, payload = "roll", {}
                    else:
                        action, payload = "move", state["legal_moves"][0]
                    code, game = client.request("POST", f"/api/matches/{mid}/bg/{action}", dict(payload, version=version))
                    assert code == 200, (code, game)
                assert game["match_status"] == "completed"
                print(f"PASS: complete hard backgammon game with cube over HTTP ({time.perf_counter()-started:.2f}s)")

                duplicate_clients = [client.clone() for _ in range(8)]
                with ThreadPoolExecutor(max_workers=8) as pool:
                    results = list(pool.map(lambda c: c.create("same-smoke-request"), duplicate_clients))
                assert sorted(code for code, _ in results) == [200] * 7 + [201]
                assert len({body["match"]["id"] for _, body in results}) == 1
                print("PASS: 8 simultaneous duplicate creates charge once")

                clients = [client.clone() for _ in range(30)]
                balance = client.request("GET", "/api/me")[1]["user"]["coins"]
                with ThreadPoolExecutor(max_workers=12) as pool:
                    codes = Counter(pool.map(lambda c: c.create()[0], clients))
                assert codes == Counter({201: balance // 5, 402: 30 - balance // 5}), codes
                assert client.request("GET", "/api/me")[1]["user"]["coins"] == 0
                print("PASS: 30 simultaneous match creates cannot overspend")

                with ThreadPoolExecutor(max_workers=8) as pool:
                    codes = Counter(pool.map(lambda c: c.request("POST", "/api/coins/refill")[0], duplicate_clients))
                assert codes == Counter({200: 1, 409: 7}), codes
                assert client.request("GET", "/api/me")[1]["user"]["coins"] == 100
                print("PASS: 8 simultaneous refill requests grant once")

                codes = [client.request("POST", "/api/login", {"username": "absent", "password": "invalid"})[0] for _ in range(10)]
                assert codes == [401] * 9 + [429], codes
                print("PASS: auth rate limit is shared across workers")
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__ == "__main__":
    main()
