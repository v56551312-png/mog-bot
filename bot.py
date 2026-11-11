import asyncio
import html
import logging
import random
from datetime import datetime

from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import (BotCommand, BufferedInputFile, CallbackQuery, InlineKeyboardButton,
                           InlineKeyboardMarkup, InlineQuery, InlineQueryResultArticle,
                           InlineQueryResultCachedPhoto, InputMediaPhoto, InputTextMessageContent,
                           LabeledPrice, Message, PreCheckoutQuery, User)

import card
import config
import db
import scoring

log = logging.getLogger("mog")
router = Router()
STATE = {"bot_username": "", "challenge_fid": None}
PROCESSING: set = set()
PERIOD = config.PERIOD_DAYS

COLORS = {"red": ("🔴 Красный", "#ff5a5f"), "violet": ("🟣 Фиолетовый", "#a77bff"),
          "blue": ("🔵 Синий", "#4da3ff"), "green": ("🟢 Зелёный", "#4cd37b"),
          "gold": ("🟡 Золотой", "#ffc84a"), "pink": ("🩷 Розовый", "#ff7eb6")}
MEDALS = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
WEAK = {"avatar": "аватар", "username": "username", "about": "о себе", "gifts": "подарки",
        "cost": "стоимость подарков", "reg": "возраст аккаунта", "level": "уровень TG"}
TIPS = {"about": "Напиши пару слов о себе.", "avatar": "Поставь больше фото.",
        "username": "Сделай username короче и без цифр.", "gifts": "Добавь подарки.",
        "cost": "Подарки подороже подтянут балл.", "reg": "Возраст аккаунта не изменить 🙂",
        "level": "Premium подтянет уровень."}

HOW_TO = (
    "<u>Как бросить вызов</u>\n"
    "• В любом чате: <code>@{bot}</code> — и выбери «Бросить вызов». Кто первый нажмёт кнопку, тот и соперник.\n"
    "• Конкретному человеку: <code>@{bot} @ник</code>\n"
    "• Там, где я в чате, хватит слова <code>мог</code>\n\n"
    "<blockquote expandable><u>Ещё способы</u>\n"
    "мог @ник — вызов конкретному\n"
    "мог ответом на сообщение — баттл сразу, без ожидания</blockquote>\n"
    "Победы за период идут в топ. Проигравшему прилетает штамп MOGGED."
)
INTRO = "Сравниваю профили Telegram по семи метрикам и рисую карточку с победителем.\n\n"


# ---------- клавиатуры ----------
def kb(kind: str) -> InlineKeyboardMarkup:
    challenge = [InlineKeyboardButton(text="⚔️ Бросить вызов в чат", switch_inline_query="")]
    rating = InlineKeyboardButton(text="🏆 Рейтинг", callback_data="rating")
    how = InlineKeyboardButton(text="❓ Как считается", callback_data="how")
    if kind == "start":
        rows = [challenge, [InlineKeyboardButton(text="👤 Мой профиль", callback_data="me"), rating], [how]]
    else:
        rows = [challenge, [InlineKeyboardButton(text=f"⭐ Свой цвет · {config.COLOR_PRICE}", callback_data="color")],
                [rating, how]]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_top() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🏆 Победы", callback_data="top:wins"),
        InlineKeyboardButton(text="🔥 Серии", callback_data="top:streak")]])


def kb_accept(uid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⚔️ Принять вызов", callback_data=f"acc:{uid}")]])


# ---------- вспомогательное ----------
class Track(BaseMiddleware):
    """Запоминаем всех, кого видим — нужно для поиска по @нику."""
    async def __call__(self, handler, event, data):
        try:
            if isinstance(event, Message):
                if event.from_user and not event.from_user.is_bot:
                    await db.upsert_user(event.from_user)
                r = event.reply_to_message
                if r and r.from_user and not r.from_user.is_bot:
                    await db.upsert_user(r.from_user)
            elif event.from_user:
                await db.upsert_user(event.from_user)
        except Exception:
            log.exception("track")
        return await handler(event, data)


async def load_profile(bot: Bot, user: User):
    p = await scoring.collect(bot, user)
    p.color = await db.get_color(user.id)
    return p


async def profile_caption(p) -> str:
    wins, losses = await db.user_period(p.user_id, PERIOD)
    total = await db.total_battles(p.user_id)
    nl = scoring.next_league(p.total)
    weak = sorted(p.metrics, key=lambda m: m.score)[:2]
    text = f"<b>{html.escape(p.name)}</b> — {p.total:.2f} · лига {p.league}\n"
    if nl:
        text += f"до {nl[0]} не хватает {nl[1]:.2f}\n"
    text += f"\nПобед за период: {wins}   Поражений: {losses}\nБаттлов всего: {total}\n\n"
    text += f"💬 Слабые места — {WEAK[weak[0].key]} и {WEAK[weak[1].key]}. {TIPS[weak[0].key]}"
    return text


async def run_battle(bot: Bot, u1: User, u2: User, chat_id: int):
    p1, p2 = await asyncio.gather(load_profile(bot, u1), load_profile(bot, u2))
    win = random.choice([0, 1]) if p1.total == p2.total else (0 if p1.total > p2.total else 1)
    w, l = (p1, p2) if win == 0 else (p2, p1)
    await db.save_battle(chat_id, w.user_id, l.user_id, w.total, l.total)
    img = await asyncio.to_thread(card.battle_card, p1, p2, win)
    caption = (f"⚔️ <b>{html.escape(p1.name)}</b> vs <b>{html.escape(p2.name)}</b>\n\n"
               f"🏆 Победил <b>{html.escape(w.name)}</b> — {w.total:.2f} против {l.total:.2f}\n"
               f"💀 {html.escape(l.name)} получает штамп MOGGED")
    return img, caption


async def find_target(m: Message, bot: Bot):
    if m.reply_to_message and m.reply_to_message.from_user and not m.reply_to_message.from_user.is_bot:
        return m.reply_to_message.from_user
    me = STATE["bot_username"].lower()
    for e in (m.entities or []):
        if e.type == "text_mention" and e.user and not e.user.is_bot:
            return e.user
        if e.type == "mention":
            uname = e.extract_from(m.text)[1:]
            if uname.lower() == me:
                continue
            row = await db.by_username(uname)
            if not row:
                return "unknown"
            try:
                return (await bot.get_chat_member(m.chat.id, row["user_id"])).user
            except Exception:
                return User(id=row["user_id"], is_bot=False, first_name=row["name"] or "user",
                            username=row["username"], is_premium=bool(row["premium"]))
    return None


# ---------- команды ----------
@router.message(Command("start", "help"))
async def cmd_start(m: Message):
    await m.answer(INTRO + HOW_TO.format(bot=STATE["bot_username"]), reply_markup=kb("start"))


@router.message(Command("me"))
async def cmd_me(m: Message, bot: Bot):
    await send_profile(bot, m.chat.id, m.from_user)


async def send_profile(bot: Bot, chat_id: int, user: User):
    p = await load_profile(bot, user)
    img = await asyncio.to_thread(card.profile_card, p)
    await bot.send_photo(chat_id, BufferedInputFile(img, "profile.png"),
                         caption=await profile_caption(p), reply_markup=kb("profile"))


@router.message(Command("how"))
async def cmd_how(m: Message):
    await m.answer(how_text())


def how_text() -> str:
    w = scoring.WEIGHTS
    names = {"avatar": "Аватар", "username": "Username", "about": "О себе", "gifts": "Подарки",
             "cost": "Стоимость подарков", "reg": "Регистрация (по ID, примерно)", "level": "Уровень TG"}
    lines = [f"• {names[k]} — {int(v * 100)}%" for k, v in w.items()]
    leagues = " → ".join(f"{n} ({t}+)" if t else n for t, n in scoring.LEAGUES)
    return ("<b>Как считается балл</b>\nКаждая метрика от 0 до 10, итог — взвешенное среднее:\n"
            + "\n".join(lines) + f"\n\n<b>Лиги:</b> {leagues}\n\n"
            "Чем больше фото, короче username, старше аккаунт, больше подарков — тем выше балл.")


@router.message(Command("season"))
async def cmd_season(m: Message):
    try:
        end = datetime.strptime(config.SEASON_END, "%Y-%m-%d").replace(hour=23, minute=59)
        left = end - datetime.now()
        timer = f"{left.days} д {left.seconds // 3600} ч" if left.total_seconds() > 0 else "сезон завершён"
    except ValueError:
        timer = "—"
    await m.answer(f"🏆 <b>Сезон</b>\nПризовой фонд: {html.escape(config.PRIZE_TEXT)}\n"
                   f"До конца: {timer}\n\nПобеждай в баттлах — попадай в топ!", reply_markup=kb("start"))


async def top_text(kind: str) -> str:
    if kind == "streak":
        rows = await db.streaks(PERIOD)
        if not rows:
            return f"<b>Серии побед ({PERIOD} дн.)</b>\n\nПока пусто."
        body = "\n".join(f"{MEDALS[i]} {html.escape(n)} — {b} подряд" for i, (n, b) in enumerate(rows))
        return f"<b>Серии побед ({PERIOD} дн.)</b>\n\n{body}"
    rows = await db.period_top(PERIOD)
    if not rows:
        return f"<b>Топ периода ({PERIOD} дн.)</b>\n\nПока пусто — брось первый вызов!"
    body = "\n".join(f"{MEDALS[i]} {html.escape(r['nm'])} — {r['wins']} W / {r['losses']} L · {r['avg']:.2f}"
                     for i, r in enumerate(rows))
    return f"<b>Топ периода ({PERIOD} дн.)</b>\n\n{body}"


@router.message(Command("top"))
async def cmd_top(m: Message):
    await m.answer(await top_text("wins"), reply_markup=kb_top())


# ---------- баттл в чате ----------
@router.message(Command("mog"))
@router.message(F.text.regexp(r"(?i)^мог(\s|$)"))
async def cmd_mog(m: Message, bot: Bot):
    target = await find_target(m, bot)
    if target == "unknown":
        await m.reply("Не знаю такого. Пусть он что-нибудь напишет в чат (или ответь на его сообщение).")
        return
    if target is None:
        name = html.escape(m.from_user.full_name)
        await m.answer(f"⚔️ <b>{name}</b> бросает вызов!\nКто первый нажмёт кнопку — тот и соперник.",
                       reply_markup=kb_accept(m.from_user.id))
        return
    if target.id == m.from_user.id:
        await m.reply("Сам с собой нельзя 🙂")
        return
    await bot.send_chat_action(m.chat.id, "upload_photo")
    img, caption = await run_battle(bot, m.from_user, target, m.chat.id)
    await m.reply_photo(BufferedInputFile(img, "battle.png"), caption=caption)


# ---------- inline-вызов ----------
@router.inline_query()
async def inline(q: InlineQuery):
    name = html.escape(q.from_user.full_name)
    cap = f"⚔️ <b>{name}</b> бросает вызов!\nКто первый нажмёт кнопку — тот и соперник."
    if STATE["challenge_fid"]:
        res = InlineQueryResultCachedPhoto(id=f"ch{q.from_user.id}", photo_file_id=STATE["challenge_fid"],
                                           title="⚔️ Бросить вызов", description="Кто первый нажмёт — тот и соперник",
                                           caption=cap, reply_markup=kb_accept(q.from_user.id))
    else:
        res = InlineQueryResultArticle(id=f"ch{q.from_user.id}", title="⚔️ Бросить вызов",
                                       description="Кто первый нажмёт — тот и соперник",
                                       input_message_content=InputTextMessageContent(message_text=cap),
                                       reply_markup=kb_accept(q.from_user.id))
    await q.answer([res], cache_time=0, is_personal=True)


@router.callback_query(F.data.startswith("acc:"))
async def accept(cb: CallbackQuery, bot: Bot):
    cid = int(cb.data.split(":")[1])
    if cb.from_user.id == cid:
        await cb.answer("Это твой вызов — жди соперника 😉", show_alert=True)
        return
    key = cb.inline_message_id or f"{cb.message.chat.id}:{cb.message.message_id}"
    if key in PROCESSING:
        await cb.answer("Вызов уже принят")
        return
    PROCESSING.add(key)
    try:
        row = await db.get_user(cid)
        if not row:
            await cb.answer("Не нашёл соперника, брось вызов заново", show_alert=True)
            return
        challenger = User(id=cid, is_bot=False, first_name=row["name"] or "user",
                          username=row["username"], is_premium=bool(row["premium"]))
        await cb.answer("Считаю баллы…")
        chat_id = cb.message.chat.id if cb.message else 0
        img, caption = await run_battle(bot, challenger, cb.from_user, chat_id)
        file = BufferedInputFile(img, "battle.png")
        if cb.inline_message_id:
            if STATE["challenge_fid"] and config.STORAGE_CHAT_ID:
                sent = await bot.send_photo(config.STORAGE_CHAT_ID, file)
                await bot.edit_message_media(
                    media=InputMediaPhoto(media=sent.photo[-1].file_id, caption=caption),
                    inline_message_id=cb.inline_message_id, reply_markup=kb("profile"))
            else:
                await bot.edit_message_text(caption, inline_message_id=cb.inline_message_id)
        else:
            await bot.send_photo(chat_id, file, caption=caption, reply_to_message_id=cb.message.message_id)
            await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        log.exception("accept")
        PROCESSING.discard(key)
        await cb.answer("Что-то пошло не так, попробуй ещё раз", show_alert=True)


# ---------- кнопки ----------
@router.callback_query(F.data == "me")
async def cb_me(cb: CallbackQuery, bot: Bot):
    await cb.answer()
    await send_profile(bot, cb.from_user.id if not cb.message else cb.message.chat.id, cb.from_user)


@router.callback_query(F.data == "rating")
async def cb_rating(cb: CallbackQuery, bot: Bot):
    await cb.answer()
    if cb.message:
        await cb.message.answer(await top_text("wins"), reply_markup=kb_top())


@router.callback_query(F.data.startswith("top:"))
async def cb_top(cb: CallbackQuery):
    try:
        await cb.message.edit_text(await top_text(cb.data.split(":")[1]), reply_markup=kb_top())
    except Exception:
        pass
    await cb.answer()


@router.callback_query(F.data == "how")
async def cb_how(cb: CallbackQuery):
    await cb.answer()
    if cb.message:
        await cb.message.answer(how_text())


# ---------- свой цвет за Stars ----------
@router.callback_query(F.data == "color")
async def cb_color(cb: CallbackQuery):
    await cb.answer()
    rows = [[InlineKeyboardButton(text=name, callback_data=f"buy:{k}")] for k, (name, _) in COLORS.items()]
    rows.append([InlineKeyboardButton(text="♻️ Сбросить цвет (бесплатно)", callback_data="buy:reset")])
    await cb.message.answer(f"Выбери цвет карточки. Стоимость — {config.COLOR_PRICE} ⭐",
                            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("buy:"))
async def cb_buy(cb: CallbackQuery, bot: Bot):
    key = cb.data.split(":")[1]
    if key == "reset":
        await db.set_color(cb.from_user.id, None)
        await cb.answer("Цвет сброшен", show_alert=True)
        return
    if key not in COLORS:
        await cb.answer()
        return
    try:
        await bot.send_invoice(chat_id=cb.from_user.id, title=f"Цвет карточки: {COLORS[key][0]}",
                               description="Меняет акцентный цвет твоей карточки профиля и баттлов",
                               payload=f"color:{key}", currency="XTR", provider_token="",
                               prices=[LabeledPrice(label="Цвет карточки", amount=config.COLOR_PRICE)])
        await cb.answer()
    except Exception:
        await cb.answer("Открой бота в личке и нажми /start, потом повтори", show_alert=True)


@router.pre_checkout_query()
async def pre_checkout(q: PreCheckoutQuery):
    await q.answer(ok=True)


@router.message(F.successful_payment)
async def paid(m: Message):
    key = m.successful_payment.invoice_payload.split(":")[1]
    if key in COLORS:
        await db.set_color(m.from_user.id, COLORS[key][1])
        await m.answer(f"Готово! Цвет {COLORS[key][0]} применён. Проверь: /me")


# ---------- запуск ----------
async def main():
    logging.basicConfig(level=logging.INFO)
    if not config.TOKEN:
        raise SystemExit("Укажи BOT_TOKEN в файле .env")
    await db.init()
    bot = Bot(config.TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    me = await bot.get_me()
    STATE["bot_username"] = me.username
    card.BOT_TAG = f"@{me.username}"
    if config.STORAGE_CHAT_ID:
        try:
            sent = await bot.send_photo(config.STORAGE_CHAT_ID,
                                        BufferedInputFile(card.challenge_card(), "challenge.png"))
            STATE["challenge_fid"] = sent.photo[-1].file_id
        except Exception:
            log.exception("Не смог загрузить картинку вызова — проверь STORAGE_CHAT_ID и нажми /start у бота")
    else:
        log.warning("STORAGE_CHAT_ID не задан: inline-вызов будет текстовым, без картинки")
    await bot.set_my_commands([
        BotCommand(command="mog", description="Баттл: ответом на сообщение или @ник"),
        BotCommand(command="me", description="Мой профиль и баллы"),
        BotCommand(command="season", description="Сезон: призы, таймер"),
        BotCommand(command="top", description="Топ периода и серии побед"),
        BotCommand(command="how", description="Как считается балл")])
    for ev in (router.message, router.callback_query, router.inline_query):
        ev.outer_middleware(Track())
    dp = Dispatcher()
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
