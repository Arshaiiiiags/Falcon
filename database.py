"""Database layer - Python standard library only (sqlite3). No SQLAlchemy needed.
Run `python database.py` to create tables (idempotent). File: club.db next to this file
(override with DATABASE_PATH). NOTE: PostgreSQL / DATABASE_URL is no longer supported."""
import os, sqlite3
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path

INITIAL_COINS = 100
MATCH_FEE = 5
GAMES = {"pasur": ("پاسور", "Pasur"), "backgammon": ("تخته‌نرد", "Backgammon"),
         "hokm": ("حکم چهار نفره", "Four-player Hokm")}
THEMES = ("royal-gold", "midnight-purple", "persian-turquoise", "dark-minimal", "light-ivory")
LANGS = ("fa", "en")
ACHIEVEMENTS = {  # key: (fa, en) - awarded only by the server inside finish_match
    "first_win": ("اولین برد", "First win"),
    "ten_wins": ("۱۰ برد", "10 wins"),
    "played_10": ("۱۰ مسابقه", "10 matches played"),
    "pasur_win": ("برد در پاسور", "Won a Pasur match"),
    "hokm_win": ("برد در حکم", "Won a Hokm match"),
    "backgammon_win": ("برد در تخته‌نرد", "Won a Backgammon match"),
    "gammon_win": ("برد با گمون", "Won by gammon or backgammon"),
}
MATCH_STATUSES = ("pending", "active", "completed", "cancelled", "abandoned")
PATH = os.environ.get("DATABASE_PATH") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "club.db")
IntegrityError = sqlite3.IntegrityError

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT NOT NULL,
  username_lower TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  coins INTEGER NOT NULL DEFAULT 0 CHECK (coins >= 0),
  created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS user_settings (
  user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  language TEXT NOT NULL DEFAULT 'fa', theme TEXT NOT NULL DEFAULT 'royal-gold');
CREATE TABLE IF NOT EXISTS games (key TEXT PRIMARY KEY, name_fa TEXT NOT NULL, name_en TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS matches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  game_key TEXT NOT NULL REFERENCES games(key),
  opponent_type TEXT NOT NULL DEFAULT 'ai',
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','active','completed','cancelled','abandoned')),
  entry_fee INTEGER NOT NULL DEFAULT 5,
  idem_key TEXT NOT NULL,
  created_at TEXT NOT NULL, started_at TEXT, ended_at TEXT,
  UNIQUE (user_id, idem_key));
CREATE INDEX IF NOT EXISTS ix_matches_user_game ON matches(user_id, game_key, created_at);
CREATE TABLE IF NOT EXISTS match_players (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
  user_id INTEGER REFERENCES users(id), seat INTEGER NOT NULL,
  UNIQUE (match_id, seat));
CREATE TABLE IF NOT EXISTS match_results (
  match_id INTEGER PRIMARY KEY REFERENCES matches(id) ON DELETE CASCADE,
  result TEXT NOT NULL CHECK (result IN ('win','loss','draw')),
  score TEXT, stats_json TEXT);
CREATE TABLE IF NOT EXISTS coin_transactions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  match_id INTEGER REFERENCES matches(id),
  amount INTEGER NOT NULL, balance_after INTEGER NOT NULL,
  kind TEXT NOT NULL, unique_key TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_coin_user ON coin_transactions(user_id, created_at);
CREATE TABLE IF NOT EXISTS achievements (key TEXT PRIMARY KEY, name_fa TEXT NOT NULL, name_en TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS user_achievements (
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  achievement_key TEXT NOT NULL REFERENCES achievements(key),
  earned_at TEXT NOT NULL, PRIMARY KEY (user_id, achievement_key));
CREATE TABLE IF NOT EXISTS rate_limit_hits (
  id INTEGER PRIMARY KEY,
  bucket TEXT NOT NULL, address TEXT NOT NULL, created_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS ix_rate_bucket ON rate_limit_hits(bucket,address,created_at);
CREATE INDEX IF NOT EXISTS ix_rate_time ON rate_limit_hits(created_at);
CREATE TABLE IF NOT EXISTS game_states (
  match_id INTEGER PRIMARY KEY REFERENCES matches(id) ON DELETE CASCADE,
  state_json TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL);
-- Groups ("parties"): shared text chat plus one human-vs-human Hokm table per group.
CREATE TABLE IF NOT EXISTS parties (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
  owner_id INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS party_members (
  party_id INTEGER NOT NULL REFERENCES parties(id) ON DELETE CASCADE,
  user_id INTEGER NOT NULL REFERENCES users(id),
  joined_at TEXT NOT NULL, last_seen REAL NOT NULL DEFAULT 0,
  PRIMARY KEY (party_id, user_id));
CREATE INDEX IF NOT EXISTS ix_party_members_user ON party_members(user_id);
CREATE TABLE IF NOT EXISTS party_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  party_id INTEGER NOT NULL REFERENCES parties(id) ON DELETE CASCADE,
  user_id INTEGER REFERENCES users(id), username TEXT NOT NULL DEFAULT '',
  kind TEXT NOT NULL DEFAULT 'text' CHECK (kind IN ('text','system')),
  body TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_party_messages ON party_messages(party_id, id);
CREATE TABLE IF NOT EXISTS party_rooms (
  party_id INTEGER PRIMARY KEY REFERENCES parties(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'lobby' CHECK (status IN ('lobby','active','finished')),
  seats_json TEXT NOT NULL, level TEXT NOT NULL DEFAULT 'medium',
  state_json TEXT, version INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL);
"""


def now():
    """UTC, naive, as sortable ISO text (also what is stored in the TEXT date columns)."""
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=" ")


def _connect():
    c = sqlite3.connect(PATH, timeout=15, isolation_level=None)  # we manage transactions ourselves
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("PRAGMA busy_timeout=15000")
    return c


class Tx:
    """Tiny helper around one connection/transaction."""
    def __init__(self, c): self.c = c
    def execute(self, sql, params=()): return self.c.execute(sql, params)
    def one(self, sql, params=()): return self.c.execute(sql, params).fetchone()
    def all(self, sql, params=()): return self.c.execute(sql, params).fetchall()
    def scalar(self, sql, params=()):
        r = self.c.execute(sql, params).fetchone()
        return r[0] if r else None


@contextmanager
def session_scope(write=True):
    """One transaction. write=True takes the write lock up front (BEGIN IMMEDIATE), so a
    read-then-update sequence cannot interleave with another writer."""
    c = _connect()
    try:
        c.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        try:
            yield Tx(c)
            c.execute("COMMIT")
        except BaseException:
            if c.in_transaction: c.execute("ROLLBACK")
            raise
    finally:
        c.close()


def init_db():
    # On hosts with a mounted volume (e.g. Railway) the folder may not exist yet.
    os.makedirs(os.path.dirname(os.path.abspath(PATH)), exist_ok=True)
    c = _connect()
    try:
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(SCHEMA)
        # Serialize migrations across workers; an existing database is upgraded in place.
        c.execute("BEGIN IMMEDIATE")
        try:
            version = c.execute("PRAGMA user_version").fetchone()[0]
            if version > 1:
                raise RuntimeError("Database schema is newer than this application")
            if version < 1:
                columns = {row[1] for row in c.execute("PRAGMA table_info(users)")}
                if "auth_version" not in columns:
                    c.execute("ALTER TABLE users ADD COLUMN auth_version INTEGER NOT NULL DEFAULT 0")
                c.execute("PRAGMA user_version=1")
            c.execute("COMMIT")
        except BaseException:
            if c.in_transaction: c.execute("ROLLBACK")
            raise
        for k, (fa, en) in GAMES.items():
            c.execute("INSERT OR IGNORE INTO games(key,name_fa,name_en) VALUES(?,?,?)", (k, fa, en))
        for k, (fa, en) in ACHIEVEMENTS.items():
            c.execute("INSERT OR IGNORE INTO achievements(key,name_fa,name_en) VALUES(?,?,?)", (k, fa, en))
    finally:
        c.close()


def backup_database(destination):
    """Consistent online SQLite backup, including WAL data; never overwrite a file."""
    source = Path(PATH).resolve()
    target = Path(destination).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    # Reserve the name exclusively before opening it with SQLite.
    fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    try:
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as src:
            with closing(sqlite3.connect(target)) as dst:
                src.backup(dst)
                if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise RuntimeError("Backup integrity check failed")
    except BaseException:
        target.unlink()
        raise
    return target


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Initialize/upgrade the database or create a safe online backup.")
    parser.add_argument("--backup", metavar="PATH", help="back up the current database without upgrading it")
    args = parser.parse_args()
    if args.backup:
        print("Backup created:", backup_database(args.backup))
    else:
        init_db()
        print("Database ready:", PATH)
