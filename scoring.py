"""Сбор данных профиля и подсчёт баллов (0-10 по каждой метрике)."""
import io
import math
from dataclasses import dataclass
from datetime import datetime, timezone

LEAGUES = [(0, "SUB-5"), (5, "LTN"), (6, "MTN"), (7, "HTN"), (8, "Chadlite"), (9, "Chad")]
WEIGHTS = {"avatar": 0.20, "username": 0.15, "about": 0.10, "gifts": 0.15,
           "cost": 0.10, "reg": 0.15, "level": 0.15}
MONTHS = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]

# Приблизительные якоря "ID -> месяц регистрации". Bot API не отдаёт дату,
# поэтому оцениваем по ID. Точность ±1-3 мес. Можно подправить под себя.
ANCHORS = [
    (2768409, "2013-11"), (7679610, "2014-08"), (11538514, "2015-02"),
    (23646077, "2015-12"), (46145305, "2016-10"), (101260938, "2017-10"),
    (134791200, "2018-06"), (195271186, "2019-01"), (400000000, "2019-11"),
    (1000000000, "2020-09"), (1500000000, "2021-03"), (2000000000, "2021-11"),
    (5000000000, "2022-09"), (6000000000, "2023-06"), (7000000000, "2024-06"),
    (8000000000, "2025-06"), (8600000000, "2026-03"),
]


@dataclass
class Metric:
    key: str
    label: str
    sub: str
    score: float


@dataclass
class Profile:
    user_id: int
    name: str
    username: str | None
    metrics: list
    total: float
    league: str
    avatar: bytes | None = None
    color: str | None = None


def league_of(total: float) -> str:
    name = LEAGUES[0][1]
    for th, n in LEAGUES:
        if total >= th:
            name = n
    return name


def next_league(total: float):
    for th, n in LEAGUES:
        if total < th:
            return n, round(th - total, 2)
    return None


def _ts(s: str) -> float:
    y, m = map(int, s.split("-"))
    return datetime(y, m, 1, tzinfo=timezone.utc).timestamp()


def est_reg(uid: int) -> datetime:
    pts = [(i, _ts(d)) for i, d in ANCHORS]
    if uid <= pts[0][0]:
        t = pts[0][1]
    elif uid >= pts[-1][0]:
        t = pts[-1][1]
    else:
        t = pts[-1][1]
        for (i1, t1), (i2, t2) in zip(pts, pts[1:]):
            if i1 <= uid <= i2:
                t = t1 + (t2 - t1) * (uid - i1) / (i2 - i1)
                break
    return datetime.fromtimestamp(t, tz=timezone.utc)


def _sat(x: float, k: float) -> float:
    return 3 + 7 * (1 - math.exp(-x / k))


def s_avatar(n):
    table = {0: 1.0, 1: 6.0, 2: 7.2, 3: 8.0, 4: 8.7}
    sc = table.get(n, 9.5)
    return sc, ("нет фото" if n == 0 else f"{n} фото")


def s_username(un):
    if not un:
        return 1.0, "нет username"
    L = len(un)
    sc = max(2.0, 10 - (L - 3) * 0.6)
    tags = [f"{L} симв."]
    if any(c.isdigit() for c in un):
        sc -= 1.5
        tags.append("цифры")
    if "_" in un:
        sc -= 1.0
        tags.append("_")
    if un.isalpha():
        sc += 0.4
        tags.append("только буквы")
    return max(1.0, min(10.0, sc)), " • ".join(tags)


def s_about(bio):
    n = len((bio or "").strip())
    if n == 0:
        return 2.85, "пусто"
    return min(10.0, 4 + n / 12), f"{n} симв."


def s_gifts(n):
    return _sat(n, 6), f"{n} шт."


def s_cost(stars):
    usd = stars * 0.013
    return _sat(usd, 200), f"~${usd:.2f}"


def s_reg(uid):
    dt = est_reg(uid)
    age = (datetime.now(timezone.utc) - dt).days / 365.25
    return min(10.0, 3 + age * 0.65), f"{MONTHS[dt.month - 1]} {dt.year}"


def s_level(premium, gifts):
    lvl = 1 + (2 if premium else 0) + (1 if gifts else 0) + min(2, gifts // 5)
    return min(10.0, 3 + lvl * 0.72), f"{lvl}" + (" • Premium" if premium else "")


async def _gifts(bot, uid):
    fn = getattr(bot, "get_user_gifts", None)
    if not fn:
        return 0, 0
    try:
        r = await fn(user_id=uid, limit=100)
        stars = sum((getattr(getattr(g, "gift", None), "star_count", 0) or 0) for g in r.gifts)
        return r.total_count, stars
    except Exception:
        return 0, 0


async def collect(bot, user) -> Profile:
    photos_n, avatar = 0, None
    try:
        ph = await bot.get_user_profile_photos(user.id, limit=1)
        photos_n = ph.total_count
        if ph.photos:
            buf = io.BytesIO()
            await bot.download(ph.photos[0][-1].file_id, destination=buf)
            avatar = buf.getvalue()
    except Exception:
        pass
    bio = ""
    try:
        bio = (await bot.get_chat(user.id)).bio or ""
    except Exception:
        pass
    g_n, g_stars = await _gifts(bot, user.id)
    premium = bool(getattr(user, "is_premium", False))

    raw = [
        ("avatar", "Аватар", s_avatar(photos_n)),
        ("username", "@username", s_username(user.username)),
        ("about", "О себе", s_about(bio)),
        ("gifts", "Подарки", s_gifts(g_n)),
        ("cost", "Стоимость", s_cost(g_stars)),
        ("reg", "Регистрация", s_reg(user.id)),
        ("level", "Уровень TG", s_level(premium, g_n)),
    ]
    metrics = [Metric(k, lbl, sub, round(sc, 2)) for k, lbl, (sc, sub) in raw]
    total = round(sum(m.score * WEIGHTS[m.key] for m in metrics) / sum(WEIGHTS.values()), 2)
    return Profile(user.id, user.full_name, user.username, metrics, total, league_of(total), avatar)
