"""SQLite store: JSON documents, an append-only event log, and the idempotent action ledger."""
import json
import sqlite3
import threading
import uuid

from . import config
from .models import now

_local = threading.local()
SCHEMA = """
CREATE TABLE IF NOT EXISTS docs(kind TEXT, id TEXT, data TEXT, updated TEXT, PRIMARY KEY(kind, id));
CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, deal_id TEXT, ts TEXT, type TEXT, data TEXT);
CREATE TABLE IF NOT EXISTS ledger(key TEXT PRIMARY KEY, deal_id TEXT, kind TEXT, payload TEXT, ts TEXT);
CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY, value TEXT, fetched_at TEXT, credits REAL);
"""


def conn() -> sqlite3.Connection:
    c = getattr(_local, 'c', None)
    if c is None or getattr(_local, 'path', None) != config.DB_PATH:
        c = sqlite3.connect(config.DB_PATH, timeout=30, isolation_level=None)
        c.execute('PRAGMA journal_mode=WAL')
        c.execute('PRAGMA synchronous=NORMAL')      # Safe across a process crash, and much faster per event.
        c.executescript(SCHEMA)
        _local.c, _local.path = c, config.DB_PATH
    return c


def new_id(prefix: str) -> str:
    return f'{prefix}_{uuid.uuid4().hex[:10]}'


def put(kind: str, id_: str, data: dict) -> dict:
    conn().execute('INSERT OR REPLACE INTO docs VALUES(?,?,?,?)', (kind, id_, json.dumps(data, default=str), now()))
    return data


def get(kind: str, id_: str):
    r = conn().execute('SELECT data FROM docs WHERE kind=? AND id=?', (kind, id_)).fetchone()
    return json.loads(r[0]) if r else None


def all_docs(kind: str) -> list[dict]:
    return [json.loads(r[0]) for r in conn().execute('SELECT data FROM docs WHERE kind=? ORDER BY updated', (kind,))]


def event(deal_id: str, type_: str, data: dict | None = None) -> None:
    conn().execute('INSERT INTO events(deal_id, ts, type, data) VALUES(?,?,?,?)', (deal_id, now(), type_, json.dumps(data or {}, default=str)))


def events(deal_id: str, after: int = 0) -> list[dict]:
    q = 'SELECT seq, ts, type, data FROM events WHERE deal_id=? AND seq>? ORDER BY seq'
    return [{'seq': s, 'ts': t, 'type': ty, 'data': json.loads(d)} for s, t, ty, d in conn().execute(q, (deal_id, after))]


def act(key: str, deal_id: str, kind: str, payload: dict) -> bool:
    """Record an action exactly once. Returns True only the first time this key is used."""
    cur = conn().execute('INSERT OR IGNORE INTO ledger VALUES(?,?,?,?,?)', (key, deal_id, kind, json.dumps(payload, default=str), now()))
    return cur.rowcount == 1


def ledger(deal_id: str | None = None) -> list[dict]:
    sql, args = ('SELECT key, deal_id, kind, payload, ts FROM ledger WHERE deal_id=? ORDER BY ts, rowid', (deal_id,)) if deal_id else ('SELECT key, deal_id, kind, payload, ts FROM ledger ORDER BY ts, rowid', ())
    return [{'key': k, 'deal_id': d, 'kind': ki, 'payload': json.loads(p), 'ts': t} for k, d, ki, p, t in conn().execute(sql, args)]


def ledger_owner(key: str):
    r = conn().execute('SELECT deal_id FROM ledger WHERE key=?', (key,)).fetchone()
    return r[0] if r else None


def cache_get(key: str):
    r = conn().execute('SELECT value, fetched_at FROM cache WHERE key=?', (key,)).fetchone()
    return (json.loads(r[0]), r[1]) if r else None


def cache_put(key: str, value, fetched_at: str, credits: float) -> None:
    conn().execute('INSERT OR REPLACE INTO cache VALUES(?,?,?,?)', (key, json.dumps(value), fetched_at, credits))


def credits_used() -> float:
    return conn().execute('SELECT COALESCE(SUM(credits),0) FROM cache').fetchone()[0]
