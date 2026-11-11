import time
import aiosqlite
from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
    user_id INTEGER PRIMARY KEY, username TEXT, name TEXT,
    premium INTEGER DEFAULT 0, color TEXT);
CREATE TABLE IF NOT EXISTS battles(
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER, chat_id INTEGER,
    winner_id INTEGER, loser_id INTEGER, w_score REAL, l_score REAL);
CREATE INDEX IF NOT EXISTS ix_b_ts ON battles(ts);
"""


async def init():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()


async def upsert_user(u):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO users(user_id,username,name,premium) VALUES(?,?,?,?)
               ON CONFLICT(user_id) DO UPDATE SET username=excluded.username,
               name=excluded.name, premium=excluded.premium""",
            (u.id, u.username, u.full_name, int(bool(getattr(u, "is_premium", False)))),
        )
        await db.commit()


async def _one(sql, args=()):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(sql, args)
        return await cur.fetchone()


async def _all(sql, args=()):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(sql, args)
        return await cur.fetchall()


async def by_username(name: str):
    return await _one("SELECT * FROM users WHERE username = ? COLLATE NOCASE", (name,))


async def get_user(uid: int):
    return await _one("SELECT * FROM users WHERE user_id = ?", (uid,))


async def get_color(uid: int):
    r = await _one("SELECT color FROM users WHERE user_id = ?", (uid,))
    return r["color"] if r else None


async def set_color(uid: int, color):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET color=? WHERE user_id=?", (color, uid))
        await db.commit()


async def save_battle(chat_id, winner_id, loser_id, w_score, l_score):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO battles(ts,chat_id,winner_id,loser_id,w_score,l_score) VALUES(?,?,?,?,?,?)",
            (int(time.time()), chat_id, winner_id, loser_id, w_score, l_score),
        )
        await db.commit()


async def period_top(days: int, limit: int = 10):
    since = int(time.time()) - days * 86400
    return await _all(
        """SELECT t.uid, SUM(t.w) wins, SUM(t.l) losses, AVG(t.sc) avg,
                  COALESCE('@'||u.username, u.name, CAST(t.uid AS TEXT)) AS nm
           FROM (
             SELECT winner_id uid, 1 w, 0 l, w_score sc FROM battles WHERE ts>?
             UNION ALL
             SELECT loser_id, 0, 1, l_score FROM battles WHERE ts>?
           ) t LEFT JOIN users u ON u.user_id = t.uid
           GROUP BY t.uid ORDER BY wins DESC, losses ASC LIMIT ?""",
        (since, since, limit),
    )


async def user_period(uid: int, days: int):
    since = int(time.time()) - days * 86400
    r = await _one(
        """SELECT SUM(CASE WHEN winner_id=? THEN 1 ELSE 0 END) w,
                  SUM(CASE WHEN loser_id=? THEN 1 ELSE 0 END) l
           FROM battles WHERE ts>? AND (winner_id=? OR loser_id=?)""",
        (uid, uid, since, uid, uid),
    )
    return (r["w"] or 0, r["l"] or 0)


async def total_battles(uid: int) -> int:
    r = await _one("SELECT COUNT(*) c FROM battles WHERE winner_id=? OR loser_id=?", (uid, uid))
    return r["c"]


async def streaks(days: int, limit: int = 10):
    since = int(time.time()) - days * 86400
    rows = await _all("SELECT winner_id, loser_id FROM battles WHERE ts>? ORDER BY ts", (since,))
    cur, best = {}, {}
    for r in rows:
        w, l = r["winner_id"], r["loser_id"]
        cur[w] = cur.get(w, 0) + 1
        best[w] = max(best.get(w, 0), cur[w])
        cur[l] = 0
    top = sorted(best.items(), key=lambda x: -x[1])[:limit]
    out = []
    for uid, b in top:
        u = await get_user(uid)
        nm = ("@" + u["username"]) if u and u["username"] else (u["name"] if u else str(uid))
        out.append((nm, b))
    return out
