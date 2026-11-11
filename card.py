"""Генерация картинок: карточка профиля, карточка баттла, заглушка вызова."""
import functools
import io
import os

from PIL import Image, ImageDraw, ImageFont, ImageOps

BOT_TAG = "@mog_bot"
DEFAULT_ACCENT = "#8ab4ff"
HERE = os.path.dirname(os.path.abspath(__file__))

BOLD = [os.path.join(HERE, "font-bold.ttf"), os.path.join(HERE, "assets", "font-bold.ttf"),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/segoeuib.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf"]
REG = [os.path.join(HERE, "font.ttf"), os.path.join(HERE, "assets", "font.ttf"),
       "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
       "/usr/share/fonts/dejavu/DejaVuSans.ttf",
       "/usr/share/fonts/TTF/DejaVuSans.ttf",
       "C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/segoeui.ttf",
       "/System/Library/Fonts/Supplemental/Arial.ttf"]


@functools.lru_cache(None)
def font(size, bold=False):
    for p in (BOLD if bold else REG):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size)


def rgb(h):
    h = (h or DEFAULT_ACCENT).lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def bg(w, h, acc):
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / h
        d.line([(0, y), (w, y)], fill=(int(16 + 14 * t + acc[0] * 0.05),
                                       int(18 + 16 * t + acc[1] * 0.05),
                                       int(26 + 20 * t + acc[2] * 0.07)))
    return img


def avatar_img(data, size, name, acc):
    im = None
    if data:
        try:
            im = ImageOps.fit(Image.open(io.BytesIO(data)).convert("RGB"), (size, size))
        except Exception:
            im = None
    if im is None:
        im = Image.new("RGB", (size, size), (46, 50, 64))
        ImageDraw.Draw(im).text((size // 2, size // 2), (name or "?")[:1].upper(),
                                font=font(size // 2, True), fill=acc, anchor="mm")
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    out = Image.new("RGBA", (size, size))
    out.paste(im, (0, 0), mask)
    return out


def paste_avatar(img, data, name, cx, cy, size, acc):
    d = ImageDraw.Draw(img)
    d.ellipse((cx - size // 2 - 5, cy - size // 2 - 5, cx + size // 2 + 5, cy + size // 2 + 5),
              outline=acc, width=4)
    av = avatar_img(data, size, name, acc)
    img.paste(av, (cx - size // 2, cy - size // 2), av)


def to_png(img):
    b = io.BytesIO()
    img.save(b, "PNG")
    return b.getvalue()


def _fit(text, f, maxw):
    while len(text) > 3 and f.getlength(text) > maxw:
        text = text[:-2] + "…" if not text.endswith("…") else text[:-2] + "…"
    return text


def profile_card(p):
    W, H = 720, 1080
    acc = rgb(p.color)
    img = bg(W, H, acc)
    d = ImageDraw.Draw(img)
    d.text((W // 2, 72), "MOG BATTLE", font=font(54, True), fill=(236, 236, 242), anchor="mm")
    d.text((W // 2, 116), "PROFILE", font=font(18, True), fill=(150, 156, 172), anchor="mm")
    d.rounded_rectangle((40, 150, W - 40, H - 90), radius=36, fill=(26, 29, 38), outline=acc, width=2)
    paste_avatar(img, p.avatar, p.name, 135, 245, 120, acc)
    d.text((215, 215), _fit(p.name, font(34, True), 300), font=font(34, True), fill=(240, 240, 245), anchor="lm")
    d.text((215, 252), f"@{p.username}" if p.username else "без username", font=font(20), fill=(140, 146, 162), anchor="lm")
    lw = font(18, True).getlength(p.league) + 36
    d.rounded_rectangle((215, 272, 215 + lw, 304), radius=16, outline=acc, width=2)
    d.text((215 + lw / 2, 288), p.league, font=font(18, True), fill=(230, 230, 236), anchor="mm")
    d.text((W - 70, 225), f"{p.total:.2f}", font=font(56, True), fill=acc, anchor="rm")
    d.text((70, 360), "STATS", font=font(26, True), fill=(240, 240, 245), anchor="lm")
    d.text((190, 360), "твои цифры)", font=font(20), fill=acc, anchor="lm")
    y = 415
    for m in p.metrics:
        d.text((70, y), m.label, font=font(24, True), fill=(235, 235, 240), anchor="lm")
        d.text((70, y + 30), m.sub, font=font(16), fill=(120, 126, 142), anchor="lm")
        d.text((W - 70, y + 6), f"{m.score:.2f}", font=font(26, True), fill=(235, 235, 240), anchor="rm")
        d.line([(70, y + 58), (W - 70, y + 58)], fill=(58, 62, 76), width=3)
        d.line([(70, y + 58), (70 + (W - 140) * m.score / 10, y + 58)], fill=acc, width=3)
        y += 78
    d.text((W // 2, H - 62), f"общий балл {p.total:.2f}  •  лига {p.league}", font=font(20, True),
           fill=(225, 225, 232), anchor="mm")
    d.text((W - 60, H - 28), BOT_TAG, font=font(16), fill=(120, 126, 142), anchor="rm")
    return to_png(img)


def stamp(img, cx, cy):
    layer = Image.new("RGBA", (320, 96), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    red = (232, 56, 56, 240)
    ld.rounded_rectangle((4, 4, 315, 91), radius=12, outline=red, width=7)
    ld.text((160, 49), "MOGGED", font=font(50, True), fill=red, anchor="mm")
    layer = layer.rotate(16, expand=True, resample=Image.BICUBIC)
    img.paste(layer, (cx - layer.width // 2, cy - layer.height // 2), layer)


def battle_card(p1, p2, win):
    W, H = 1100, 960
    winner = p1 if win == 0 else p2
    acc = rgb(winner.color)
    img = bg(W, H, acc)
    d = ImageDraw.Draw(img)
    d.text((W // 2, 50), "MOG BATTLE", font=font(44, True), fill=(236, 236, 242), anchor="mm")
    d.text((W // 2, 245), "VS", font=font(54, True), fill=(120, 126, 142), anchor="mm")
    cols = [(p1, 200), (p2, 900)]
    for i, (p, cx) in enumerate(cols):
        is_w = i == win
        x0, x1 = cx - 170, cx + 170
        d.rounded_rectangle((x0, 100, x1, H - 30), radius=30, fill=(26, 29, 38) if is_w else (22, 24, 32),
                            outline=acc if is_w else (50, 54, 66), width=4 if is_w else 2)
        if is_w:
            d.rounded_rectangle((cx - 70, 88, cx + 70, 118), radius=15, fill=acc)
            d.text((cx, 103), "WINNER", font=font(16, True), fill=(15, 17, 24), anchor="mm")
        paste_avatar(img, p.avatar, p.name, cx, 215, 150, acc if is_w else (90, 94, 108))
        d.text((cx, 330), _fit(p.name, font(26, True), 310), font=font(26, True), fill=(240, 240, 245), anchor="mm")
        d.text((cx, 362), f"@{p.username}" if p.username else "без username", font=font(17), fill=(140, 146, 162), anchor="mm")
        d.text((cx, 410), f"{p.total:.2f}", font=font(52, True), fill=acc if is_w else (150, 154, 168), anchor="mm")
        d.text((cx, 452), p.league, font=font(18, True), fill=(210, 212, 222), anchor="mm")
    y = 505
    for a, b in zip(p1.metrics, p2.metrics):
        if (y - 505) // 62 % 2 == 0:
            d.rectangle((40, y - 28, W - 40, y + 28), fill=(255, 255, 255, 0) if False else (30, 33, 43))
        d.text((W // 2, y), a.label, font=font(20, True), fill=(170, 176, 192), anchor="mm")
        for p, cx, s, o in ((p1, 200, a.score, b.score), (p2, 900, b.score, a.score)):
            d.text((cx, y), f"{s:.2f}", font=font(28, True),
                   fill=acc if s > o else ((235, 235, 240) if s == o else (110, 114, 128)), anchor="mm")
        y += 62
    loser_cx = 900 if win == 0 else 200
    stamp(img, loser_cx, 215)
    d.text((W // 2, H - 14), BOT_TAG, font=font(14), fill=(110, 114, 128), anchor="mm")
    return to_png(img)


def challenge_card():
    W, H = 1000, 560
    acc = rgb(DEFAULT_ACCENT)
    img = bg(W, H, acc)
    d = ImageDraw.Draw(img)
    d.text((W // 2, 130), "MOG BATTLE", font=font(80, True), fill=(236, 236, 242), anchor="mm")
    d.text((W // 2, 280), "ВЫЗОВ БРОШЕН", font=font(64, True), fill=acc, anchor="mm")
    d.text((W // 2, 400), "Кто первый нажмёт «Принять вызов» — тот и соперник",
           font=font(28), fill=(170, 176, 192), anchor="mm")
    d.text((W // 2, 500), BOT_TAG, font=font(22), fill=(120, 126, 142), anchor="mm")
    return to_png(img)
