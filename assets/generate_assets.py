"""Генератор визуальной айдентики NOEMA.

Запуск: python assets/generate_assets.py
Требуется Pillow. Скрипт создаёт все изображения, которые использует бот.
"""

from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
S = 2  # supersampling

BG_TOP = (5, 6, 11)
BG_BOTTOM = (10, 12, 21)
WHITE = (245, 246, 250)
MUTED = (137, 143, 164)
DIM = (90, 95, 116)
VIOLET = (124, 92, 255)
BLUE = (61, 123, 255)
MINT = (82, 229, 177)

FONT_LIGHT = None
FONT_REGULAR = None
FONT_SEMIBOLD = None
FONT_BOLD = None
FONT_MONO = None


def _find_font(names: list[str]) -> str:
    candidates: list[Path] = []
    for name in names:
        candidates.extend(
            [
                Path(r"C:\Windows\Fonts") / name,
                Path("/usr/share/fonts/truetype/dejavu") / name,
                Path("/Library/Fonts") / name,
            ]
        )
    for path in candidates:
        if path.exists():
            return str(path)
    raise FileNotFoundError(f"Не найден шрифт: {names}")


def load_fonts() -> None:
    global FONT_LIGHT, FONT_REGULAR, FONT_SEMIBOLD, FONT_BOLD, FONT_MONO
    FONT_LIGHT = _find_font(["segoeuil.ttf", "segoeui.ttf", "DejaVuSans.ttf", "Arial.ttf"])
    FONT_REGULAR = _find_font(["segoeui.ttf", "DejaVuSans.ttf", "Arial.ttf"])
    FONT_SEMIBOLD = _find_font(["seguisb.ttf", "segoeuib.ttf", "DejaVuSans-Bold.ttf", "Arial Bold.ttf"])
    FONT_BOLD = _find_font(["segoeuib.ttf", "DejaVuSans-Bold.ttf", "Arial Bold.ttf"])
    FONT_MONO = _find_font(["consola.ttf", "DejaVuSansMono.ttf", "cour.ttf"])


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, max(8, int(size * S)))


def px(value: float) -> int:
    return round(value * S)


def _css(color: tuple[int, int, int], alpha: int = 255) -> tuple[int, int, int, int]:
    return color[0], color[1], color[2], alpha


def vertical_gradient(width: int, height: int, top: tuple, bottom: tuple) -> Image.Image:
    small = Image.new("RGB", (2, 128))
    pixels = small.load()
    for y in range(128):
        t = y / 127
        color = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        for x in range(2):
            pixels[x, y] = color
    return small.resize((width, height), Image.Resampling.BICUBIC).convert("RGBA")


def radial_glow(
    size: tuple[int, int],
    center: tuple[float, float],
    radius: float,
    color: tuple[int, int, int],
    alpha: int = 120,
) -> Image.Image:
    w, h = size
    small_w, small_h = 240, max(120, int(240 * h / w))
    layer_small = Image.new("RGBA", (small_w, small_h), (0, 0, 0, 0))
    pixels = layer_small.load()
    cx = center[0] / w * small_w
    cy = center[1] / h * small_h
    r = radius / w * small_w
    for y in range(small_h):
        for x in range(small_w):
            d = math.hypot(x - cx, y - cy)
            if d >= r:
                continue
            strength = (1 - d / r) ** 2.1
            pixels[x, y] = _css(color, int(alpha * strength))
    return layer_small.resize((w, h), Image.Resampling.BICUBIC)


def add_grid(draw: ImageDraw.ImageDraw, width: int, height: int, step: int = 86) -> None:
    for x in range(0, width, px(step)):
        draw.line([(x, 0), (x, height)], fill=(255, 255, 255, 9), width=max(1, S))
    for y in range(0, height, px(step)):
        draw.line([(0, y), (width, y)], fill=(255, 255, 255, 9), width=max(1, S))


def add_vignette(image: Image.Image, strength: int = 130) -> Image.Image:
    w, h = image.size
    mask = Image.radial_gradient("L").resize((w, h), Image.Resampling.BICUBIC)
    mask = mask.point(lambda v: int((255 - v) * strength / 255))
    dark = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    dark.putalpha(mask)
    return Image.alpha_composite(image, dark)


def add_grain(image: Image.Image, alpha: int = 8) -> Image.Image:
    w, h = image.size
    noise = Image.effect_noise((max(80, w // 8), max(45, h // 8)), 22).convert("L")
    noise = noise.resize((w, h), Image.Resampling.BILINEAR)
    tint = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    tint.putalpha(noise.point(lambda v: int(v * alpha / 255)))
    return Image.alpha_composite(image, tint)


def tracked_width(draw: ImageDraw.ImageDraw, text: str, fnt, tracking: float) -> float:
    if not text:
        return 0
    width = sum(draw.textlength(ch, font=fnt) for ch in text)
    width += px(tracking) * (len(text) - 1)
    return width


def draw_tracked(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    fnt,
    fill,
    tracking: float = 0,
    anchor_right: bool = False,
) -> float:
    total = tracked_width(draw, text, fnt, tracking)
    x = xy[0] * S - total if anchor_right else xy[0] * S
    y = xy[1] * S
    for ch in text:
        draw.text((x, y), ch, font=fnt, fill=fill)
        x += draw.textlength(ch, font=fnt) + px(tracking)
    return total / S


def wrap_text(draw: ImageDraw.ImageDraw, text: str, fnt, max_width: float) -> list[str]:
    lines: list[str] = []
    for paragraph in text.split("\n"):
        if not paragraph:
            lines.append("")
            continue
        words = paragraph.split(" ")
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if draw.textlength(candidate, font=fnt) <= px(max_width) or not current:
                current = candidate
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
    return lines


def draw_lines(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    lines: list[str],
    fnt,
    fill,
    line_height: float,
) -> None:
    x, y = xy
    for line in lines:
        draw.text((px(x), px(y)), line, font=fnt, fill=fill)
        y += line_height


def base_canvas(width: int, height: int) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = vertical_gradient(px(width), px(height), BG_TOP, BG_BOTTOM)
    image = Image.alpha_composite(
        image,
        radial_glow(
            (px(width), px(height)),
            (width * 0.78 * S, height * 0.42 * S),
            width * 0.55 * S,
            VIOLET,
            95,
        ),
    )
    image = Image.alpha_composite(
        image,
        radial_glow(
            (px(width), px(height)),
            (width * 0.18 * S, height * 0.88 * S),
            width * 0.5 * S,
            BLUE,
            45,
        ),
    )
    draw = ImageDraw.Draw(image, "RGBA")
    add_grid(draw, px(width), px(height))
    return image, draw


def brand_header(
    draw: ImageDraw.ImageDraw,
    width: int,
    height: int,
    *,
    section: str,
    right: str,
    margin: int = 100,
) -> None:
    f_brand = font(FONT_SEMIBOLD, 27)
    f_small = font(FONT_REGULAR, 12)
    dot = px(4)
    cy = px(margin / 2 + 10)
    draw.ellipse(
        [(px(margin), cy - dot), (px(margin) + dot * 2, cy + dot)],
        fill=_css(VIOLET, 255),
    )
    draw_tracked(
        draw,
        (margin + 22, margin / 2),
        "NOEMA",
        f_brand,
        _css(WHITE, 245),
        tracking=7,
    )
    draw_tracked(
        draw,
        (margin + 23, margin / 2 + 42),
        section,
        f_small,
        _css(MUTED, 210),
        tracking=3.4,
    )
    draw_tracked(
        draw,
        (width - margin, margin / 2 + 10),
        right,
        f_small,
        _css(MUTED, 190),
        tracking=3.4,
        anchor_right=True,
    )
    draw.line(
        [(px(margin), px(margin + 72)), (px(width - margin), px(margin + 72))],
        fill=(255, 255, 255, 26),
        width=max(1, S),
    )


def footer(
    draw: ImageDraw.ImageDraw,
    width: int,
    height: int,
    text: str,
    *,
    margin: int = 100,
    color=MUTED,
) -> None:
    f = font(FONT_REGULAR, 12)
    y = height - 52
    draw.line(
        [(px(margin), px(y - 22)), (px(width - margin), px(y - 22))],
        fill=(255, 255, 255, 20),
        width=max(1, S),
    )
    draw_tracked(
        draw,
        (margin, y),
        text,
        f,
        _css(color, 180),
        tracking=3.2,
    )
    draw_tracked(
        draw,
        (width - margin, y),
        "INTELLECTUAL SERIES · 01",
        f,
        _css(color, 130),
        tracking=3.2,
        anchor_right=True,
    )


def circle_shape(
    draw: ImageDraw.ImageDraw,
    center: tuple[float, float],
    radius: float,
    color,
    width: float = 5,
) -> None:
    x, y = center
    draw.ellipse(
        [
            (px(x - radius), px(y - radius)),
            (px(x + radius), px(y + radius)),
        ],
        outline=color,
        width=max(S, int(width * S)),
    )


def square_shape(
    draw: ImageDraw.ImageDraw,
    center: tuple[float, float],
    size: float,
    color,
    width: float = 5,
) -> None:
    x, y = center
    half = size / 2
    draw.rounded_rectangle(
        [(px(x - half), px(y - half)), (px(x + half), px(y + half))],
        radius=px(6),
        outline=color,
        width=max(S, int(width * S)),
    )


def triangle_shape(
    draw: ImageDraw.ImageDraw,
    center: tuple[float, float],
    radius: float,
    color,
    width: float = 5,
) -> None:
    x, y = center
    points = []
    for angle in (-90, 30, 150):
        rad = math.radians(angle)
        points.append((px(x + radius * math.cos(rad)), px(y + radius * math.sin(rad) * 0.86)))
    draw.polygon(points, outline=color, width=max(S, int(width * S)))


def orbital_art(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    cx: float,
    cy: float,
    max_radius: float,
) -> None:
    glow = radial_glow(
        image.size, (cx * S, cy * S), max_radius * S * 0.75, VIOLET, 105
    )
    image.alpha_composite(glow)
    draw = ImageDraw.Draw(image, "RGBA")

    for index, radius in enumerate((0.28, 0.42, 0.56, 0.72, 0.9, 1.0)):
        alpha = 70 if index in (2, 4) else 34
        width = 2 if index not in (2,) else 3
        draw.ellipse(
            [
                (px(cx - max_radius * radius), px(cy - max_radius * radius)),
                (px(cx + max_radius * radius), px(cy + max_radius * radius)),
            ],
            outline=_css(VIOLET if index in (2, 4) else WHITE, alpha),
            width=max(1, width * S),
        )

    for angle in range(0, 360, 30):
        rad = math.radians(angle)
        x1 = cx + max_radius * 0.28 * math.cos(rad)
        y1 = cy + max_radius * 0.28 * math.sin(rad)
        x2 = cx + max_radius * math.cos(rad)
        y2 = cy + max_radius * math.sin(rad)
        draw.line(
            [(px(x1), px(y1)), (px(x2), px(y2))],
            fill=(255, 255, 255, 13),
            width=max(1, S),
        )

    core_r = max_radius * 0.13
    for r, alpha in ((core_r * 2.2, 18), (core_r * 1.55, 34)):
        draw.ellipse(
            [(px(cx - r), px(cy - r)), (px(cx + r), px(cy + r))],
            fill=_css(VIOLET, alpha),
        )
    draw.ellipse(
        [(px(cx - core_r), px(cy - core_r)), (px(cx + core_r), px(cy + core_r))],
        fill=_css(VIOLET, 255),
        outline=_css((178, 160, 255), 200),
        width=2 * S,
    )
    draw.ellipse(
        [
            (px(cx - core_r * 0.16), px(cy - core_r * 0.16)),
            (px(cx + core_r * 0.16), px(cy + core_r * 0.16)),
        ],
        fill=_css(WHITE, 250),
    )

    nodes = [
        (0.0, 0.56, 7, VIOLET),
        (52, 0.72, 5, WHITE),
        (118, 0.42, 4, BLUE),
        (205, 0.9, 6, VIOLET),
        (288, 0.72, 4, WHITE),
        (332, 0.56, 5, BLUE),
    ]
    for angle, radius, size, color in nodes:
        rad = math.radians(angle)
        x = cx + max_radius * radius * math.cos(rad)
        y = cy + max_radius * radius * math.sin(rad)
        draw.ellipse(
            [(px(x - size), px(y - size)), (px(x + size), px(y + size))],
            fill=_css(color, 245),
        )
        draw.ellipse(
            [(px(x - size * 2.8), px(y - size * 2.8)), (px(x + size * 2.8), px(y + size * 2.8))],
            outline=_css(color, 55),
            width=max(1, S),
        )

    f_label = font(FONT_REGULAR, 11)
    labels = [
        (cx - max_radius * 0.93, cy - max_radius * 0.62, "LOGIC"),
        (cx + max_radius * 0.48, cy - max_radius * 0.96, "PATTERN"),
        (cx + max_radius * 0.66, cy + max_radius * 0.64, "SPATIAL"),
    ]
    for x, y, text in labels:
        draw_tracked(draw, (x, y), text, f_label, _css(MUTED, 190), tracking=4)


def save(image: Image.Image, name: str, quality: int = 94) -> None:
    final = image.resize(
        (image.width // S, image.height // S), Image.Resampling.LANCZOS
    ).convert("RGB")
    path = ROOT / name
    final.save(path, "JPEG", quality=quality, optimize=True, subsampling=1)
    print(f"  [ok] {name}  {final.width}x{final.height}  {path.stat().st_size // 1024} KB")


# ------------------------------------------------------------------ hero


def make_hero() -> None:
    width, height = 1600, 900
    image, draw = base_canvas(width, height)
    orbital_art(image, draw, 1215, 425, 315)
    draw = ImageDraw.Draw(image, "RGBA")

    brand_header(
        draw,
        width,
        height,
        section="INTELLECTUAL ASSESSMENT",
        right="EDITION 01 · PRIVATE SERIES",
        margin=108,
    )

    f_eyebrow = font(FONT_SEMIBOLD, 14)
    draw_tracked(
        draw,
        (110, 250),
        "АВТОРСКИЙ ИНТЕЛЛЕКТУАЛЬНЫЙ ТЕСТ",
        f_eyebrow,
        _css(VIOLET, 245),
        tracking=4.8,
    )

    f_head = font(FONT_LIGHT, 100)
    draw.text((px(104), px(286)), "ТВОЙ", font=f_head, fill=WHITE)
    draw.text((px(104), px(390)), "ИНТЕЛЛЕКТ.", font=f_head, fill=WHITE)

    draw.line([(px(112), px(524)), (px(474), px(524))], fill=_css(VIOLET, 230), width=3 * S)

    f_sub = font(FONT_LIGHT, 23)
    draw.text(
        (px(110), px(552)),
        "Не оценка. Точный снимок того,",
        font=f_sub,
        fill=(205, 208, 220, 240),
    )
    draw.text(
        (px(110), px(589)),
        "как ты думаешь.",
        font=f_sub,
        fill=(205, 208, 220, 240),
    )

    stats = [
        ("20", "ЗАДАНИЙ"),
        ("7", "КАТЕГОРИЙ"),
        ("1", "ОТЧЁТ"),
    ]
    start_x = 110
    f_num = font(FONT_SEMIBOLD, 34)
    f_cap = font(FONT_REGULAR, 10)
    for index, (number, label) in enumerate(stats):
        x = start_x + index * 188
        draw.text((px(x), px(716)), number, font=f_num, fill=WHITE)
        draw_tracked(
            draw,
            (x + 45, 735),
            label,
            f_cap,
            _css(MUTED, 220),
            tracking=3.5,
        )
        if index < 2:
            draw.line(
                [(px(x + 148), px(710)), (px(x + 148), px(762))],
                fill=(255, 255, 255, 28),
                width=max(1, S),
            )

    footer(draw, width, height, "NOEMA · PRIVATE INTELLECTUAL SERIES", margin=108)
    image = add_vignette(image, 120)
    image = add_grain(image, 7)
    save(image, "hero.jpg", 94)


# ------------------------------------------------------------------ analysis


def make_analysis() -> None:
    width, height = 1280, 720
    image, draw = base_canvas(width, height)

    brand_header(
        draw,
        width,
        height,
        section="ANALYTICAL ENGINE",
        right="PROCESSING · 20 ANSWERS",
        margin=84,
    )

    f_eyebrow = font(FONT_SEMIBOLD, 13)
    draw_tracked(
        draw,
        (86, 198),
        "NOEMA · INTELLIGENCE ANALYSIS",
        f_eyebrow,
        _css(VIOLET, 240),
        tracking=4.4,
    )
    f_head = font(FONT_LIGHT, 78)
    draw.text((px(82), px(232)), "АНАЛИТИЧЕСКИЙ", font=f_head, fill=WHITE)
    draw.text((px(82), px(316)), "ПРОЦЕСС", font=f_head, fill=WHITE)

    f_body = font(FONT_LIGHT, 22)
    draw.text(
        (px(87), px(428)),
        "Сверяем ответы. Строим профиль.",
        font=f_body,
        fill=(196, 200, 214, 235),
    )

    stages = [
        ("01", "СЧИТЫВАЕМ ОТВЕТЫ"),
        ("02", "СВЕРЯЕМ РЕШЕНИЯ"),
        ("03", "ФОРМИРУЕМ ОТЧЁТ"),
    ]
    f_num = font(FONT_MONO, 13)
    f_stage = font(FONT_SEMIBOLD, 10)
    for index, (number, label) in enumerate(stages):
        y = 505 + index * 40
        active = index == 0
        color = _css(VIOLET, 255) if active else _css(DIM, 190)
        if active:
            glow = radial_glow(image.size, (px(98), px(y + 7)), 40 * S, VIOLET, 70)
            image.alpha_composite(glow)
            draw = ImageDraw.Draw(image, "RGBA")
        draw.ellipse(
            [(px(92), px(y)), (px(105), px(y + 13))],
            fill=color if active else None,
            outline=color,
            width=max(1, S),
        )
        draw.text((px(120), px(y - 3)), number, font=f_num, fill=color)
        draw_tracked(
            draw,
            (158, y),
            label,
            f_stage,
            color,
            tracking=2.8,
        )

    # Scanner visualization
    cx, cy = 968, 360
    glow = radial_glow(image.size, (px(cx), px(cy)), 300 * S, BLUE, 60)
    image.alpha_composite(glow)
    draw = ImageDraw.Draw(image, "RGBA")

    rng = random.Random(9)
    bar_count = 28
    for i in range(bar_count):
        angle = math.radians(-124 + i * 9)
        radius_inner = 118 + rng.randint(0, 10)
        radius_outer = radius_inner + 38 + rng.randint(0, 85)
        x1 = cx + radius_inner * math.cos(angle)
        y1 = cy + radius_inner * math.sin(angle)
        x2 = cx + radius_outer * math.cos(angle)
        y2 = cy + radius_outer * math.sin(angle)
        alpha = 30 + int(70 * (1 - abs(i - bar_count / 2) / (bar_count / 2)))
        draw.line(
            [(px(x1), px(y1)), (px(x2), px(y2))],
            fill=_css(VIOLET if i % 3 else BLUE, alpha),
            width=max(2, int(3.2 * S)),
        )

    for radius in (118, 168, 228, 288):
        draw.ellipse(
            [(px(cx - radius), px(cy - radius)), (px(cx + radius), px(cy + radius))],
            outline=(255, 255, 255, 32),
            width=max(1, S),
        )
    draw.arc(
        [(px(cx - 228), px(cy - 228)), (px(cx + 228), px(cy + 228))],
        start=200,
        end=342,
        fill=_css(VIOLET, 235),
        width=3 * S,
    )
    draw.arc(
        [(px(cx - 288), px(cy - 288)), (px(cx + 288), px(cy + 288))],
        start=18,
        end=118,
        fill=_css(BLUE, 190),
        width=2 * S,
    )

    draw.ellipse(
        [(px(cx - 50), px(cy - 50)), (px(cx + 50), px(cy + 50))],
        fill=_css((12, 14, 24), 255),
        outline=_css(VIOLET, 160),
        width=2 * S,
    )
    draw.ellipse(
        [(px(cx - 82), px(cy - 82)), (px(cx + 82), px(cy + 82))],
        outline=_css(VIOLET, 70),
        width=2 * S,
    )
    f_core = font(FONT_SEMIBOLD, 19)
    draw_tracked(
        draw,
        (cx - 26, cy - 12),
        "IQ",
        f_core,
        _css(WHITE, 245),
        tracking=2,
    )

    footer(draw, width, height, "20 ANSWERS · 7 CATEGORIES · 1 REPORT", margin=84)
    image = add_vignette(image, 125)
    image = add_grain(image, 7)
    save(image, "analysis.jpg", 94)


# ------------------------------------------------------------------ locked


def draw_lock(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    cx: float,
    cy: float,
    scale: float = 1.0,
) -> None:
    glow = radial_glow(image.size, (px(cx), px(cy)), 220 * scale * S, VIOLET, 80)
    image.alpha_composite(glow)
    draw = ImageDraw.Draw(image, "RGBA")

    for radius in (150, 205, 260):
        draw.ellipse(
            [
                (px(cx - radius * scale), px(cy - radius * scale)),
                (px(cx + radius * scale), px(cy + radius * scale)),
            ],
            outline=(255, 255, 255, 25 if radius == 260 else 38),
            width=max(1, S),
        )

    body_w = 170 * scale
    body_h = 132 * scale
    body_top = cy - 10 * scale
    draw.rounded_rectangle(
        [
            (px(cx - body_w / 2), px(body_top)),
            (px(cx + body_w / 2), px(body_top + body_h)),
        ],
        radius=px(22 * scale),
        outline=_css(WHITE, 235),
        width=max(2, int(3 * S)),
    )
    draw.rounded_rectangle(
        [
            (px(cx - body_w / 2 + 12), px(body_top + 12)),
            (px(cx + body_w / 2 - 12), px(body_top + body_h - 12)),
        ],
        radius=px(15 * scale),
        fill=_css(VIOLET, 24),
    )

    shackle_w = 104 * scale
    shackle_top = body_top - 94 * scale
    draw.arc(
        [
            (px(cx - shackle_w / 2), px(shackle_top)),
            (px(cx + shackle_w / 2), px(shackle_top + 120 * scale)),
        ],
        start=180,
        end=360,
        fill=_css(WHITE, 225),
        width=max(2, int(4 * S)),
    )
    draw.line(
        [
            (px(cx - shackle_w / 2), px(body_top - 30 * scale)),
            (px(cx - shackle_w / 2), px(body_top - 20 * scale)),
        ],
        fill=_css(WHITE, 225),
        width=max(2, int(4 * S)),
    )
    draw.line(
        [
            (px(cx + shackle_w / 2), px(body_top - 30 * scale)),
            (px(cx + shackle_w / 2), px(body_top - 20 * scale)),
        ],
        fill=_css(WHITE, 225),
        width=max(2, int(4 * S)),
    )

    keyhole_r = 13 * scale
    keyhole_cy = body_top + 48 * scale
    draw.ellipse(
        [
            (px(cx - keyhole_r), px(keyhole_cy - keyhole_r)),
            (px(cx + keyhole_r), px(keyhole_cy + keyhole_r)),
        ],
        fill=_css(VIOLET, 245),
    )
    draw.polygon(
        [
            (px(cx - 8 * scale), px(keyhole_cy + 8 * scale)),
            (px(cx + 8 * scale), px(keyhole_cy + 8 * scale)),
            (px(cx + 4 * scale), px(keyhole_cy + 38 * scale)),
            (px(cx - 4 * scale), px(keyhole_cy + 38 * scale)),
        ],
        fill=_css(VIOLET, 245),
    )


def make_locked() -> None:
    width, height = 1280, 720
    image, draw = base_canvas(width, height)
    draw_lock(image, draw, 962, 344, scale=1.0)
    draw = ImageDraw.Draw(image, "RGBA")

    brand_header(
        draw,
        width,
        height,
        section="SECURE REPORT",
        right="ACCESS PROTECTED",
        margin=84,
    )

    f_eyebrow = font(FONT_SEMIBOLD, 13)
    draw_tracked(
        draw,
        (86, 212),
        "NOEMA · REPORT LOCKED",
        f_eyebrow,
        _css(VIOLET, 240),
        tracking=4.4,
    )
    f_head = font(FONT_LIGHT, 84)
    draw.text((px(82), px(248)), "ОТЧЁТ", font=f_head, fill=WHITE)
    draw.text((px(82), px(338)), "ЗАЩИЩЁН", font=f_head, fill=WHITE)

    f_body = font(FONT_LIGHT, 21)
    draw.text(
        (px(87), px(470)),
        "Полный результат, профиль",
        font=f_body,
        fill=(196, 200, 214, 235),
    )
    draw.text(
        (px(87), px(503)),
        "и разбор решений доступны",
        font=f_body,
        fill=(196, 200, 214, 235),
    )
    draw.text(
        (px(87), px(536)),
        "после подтверждения оплаты.",
        font=f_body,
        fill=(196, 200, 214, 235),
    )

    f_tag = font(FONT_MONO, 10)
    draw_tracked(
        draw,
        (87, 605),
        "ENCRYPTED · PERSONAL · LIFETIME",
        f_tag,
        _css(DIM, 210),
        tracking=2.4,
    )

    footer(draw, width, height, "PREMIUM INTELLECTUAL REPORT", margin=84)
    image = add_vignette(image, 150)
    image = add_grain(image, 7)
    save(image, "locked.jpg", 94)


# ------------------------------------------------------------------ unlocked


def draw_check_ring(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    cx: float,
    cy: float,
) -> None:
    glow = radial_glow(image.size, (px(cx), px(cy)), 250 * S, MINT, 65)
    image.alpha_composite(glow)
    draw = ImageDraw.Draw(image, "RGBA")

    for radius, alpha, width in ((170, 55, 2), (224, 30, 1), (285, 22, 1)):
        draw.ellipse(
            [(px(cx - radius), px(cy - radius)), (px(cx + radius), px(cy + radius))],
            outline=(255, 255, 255, alpha),
            width=max(1, width * S),
        )
    draw.arc(
        [(px(cx - 170), px(cy - 170)), (px(cx + 170), px(cy + 170))],
        start=208,
        end=330,
        fill=_css(MINT, 235),
        width=3 * S,
    )
    draw.ellipse(
        [(px(cx - 112), px(cy - 112)), (px(cx + 112), px(cy + 112))],
        fill=_css(VIOLET, 30),
        outline=_css(WHITE, 100),
        width=2 * S,
    )
    points = [
        (px(cx - 55), px(cy + 2)),
        (px(cx - 16), px(cy + 42)),
        (px(cx + 62), px(cy - 42)),
    ]
    draw.line(points, fill=_css(WHITE, 245), width=8 * S, joint="curve")
    draw.line(
        [(px(cx - 55), px(cy + 2)), (px(cx - 16), px(cy + 42))],
        fill=_css(MINT, 255),
        width=8 * S,
        joint="curve",
    )


def make_unlocked() -> None:
    width, height = 1280, 720
    image, draw = base_canvas(width, height)
    draw_check_ring(image, draw, 960, 350)
    draw = ImageDraw.Draw(image, "RGBA")

    brand_header(
        draw,
        width,
        height,
        section="PAYMENT CONFIRMED",
        right="ACCESS GRANTED",
        margin=84,
    )

    f_eyebrow = font(FONT_SEMIBOLD, 13)
    draw_tracked(
        draw,
        (86, 216),
        "NOEMA · PERSONAL REPORT",
        f_eyebrow,
        _css(MINT, 240),
        tracking=4.4,
    )
    f_head = font(FONT_LIGHT, 84)
    draw.text((px(82), px(252)), "ДОСТУП", font=f_head, fill=WHITE)
    draw.text((px(82), px(342)), "ОТКРЫТ", font=f_head, fill=WHITE)

    f_body = font(FONT_LIGHT, 22)
    draw.text(
        (px(87), px(476)),
        "Персональный отчёт",
        font=f_body,
        fill=(205, 209, 222, 238),
    )
    draw.text(
        (px(87), px(509)),
        "разблокирован навсегда.",
        font=f_body,
        fill=(205, 209, 222, 238),
    )

    f_tag = font(FONT_MONO, 10)
    draw_tracked(
        draw,
        (87, 600),
        "20 ANSWERS · 7 CATEGORIES · FULL BREAKDOWN",
        f_tag,
        _css(DIM, 210),
        tracking=2.2,
    )

    footer(draw, width, height, "REPORT UNLOCKED · LIFETIME ACCESS", margin=84)
    image = add_vignette(image, 135)
    image = add_grain(image, 7)
    save(image, "unlocked.jpg", 94)


# ------------------------------------------------------------------ report


def make_report() -> None:
    width, height = 1280, 720
    image, draw = base_canvas(width, height)

    brand_header(
        draw,
        width,
        height,
        section="PERSONAL REPORT",
        right="NOEMA · INTELLECTUAL SERIES",
        margin=84,
    )

    f_eyebrow = font(FONT_SEMIBOLD, 13)
    draw_tracked(
        draw,
        (86, 210),
        "NOEMA · ANALYTICAL PROFILE",
        f_eyebrow,
        _css(VIOLET, 240),
        tracking=4.4,
    )
    f_head = font(FONT_LIGHT, 86)
    draw.text((px(82), px(246)), "ТВОЙ", font=f_head, fill=WHITE)
    draw.text((px(82), px(338)), "ПРОФИЛЬ", font=f_head, fill=WHITE)

    f_body = font(FONT_LIGHT, 21)
    draw.text(
        (px(87), px(472)),
        "20 заданий · 7 категорий",
        font=f_body,
        fill=(196, 200, 214, 235),
    )
    draw.text(
        (px(87), px(505)),
        "подробный разбор решений",
        font=f_body,
        fill=(196, 200, 214, 235),
    )

    # Abstract profile chart
    cx, cy = 952, 356
    radius = 214
    glow = radial_glow(image.size, (px(cx), px(cy)), 290 * S, VIOLET, 55)
    image.alpha_composite(glow)
    draw = ImageDraw.Draw(image, "RGBA")

    points_outer = []
    points_inner = []
    values = (0.78, 0.62, 0.88, 0.54, 0.72, 0.94, 0.68)
    for i in range(7):
        angle = math.radians(-90 + i * 360 / 7)
        for ring in (0.33, 0.66, 1.0):
            x1 = cx + radius * ring * math.cos(angle)
            y1 = cy + radius * ring * math.sin(angle)
            x2 = cx + radius * ring * math.cos(angle + math.radians(360 / 7))
            y2 = cy + radius * ring * math.sin(angle + math.radians(360 / 7))
            draw.line(
                [(px(x1), px(y1)), (px(x2), px(y2))],
                fill=(255, 255, 255, 30 if ring == 1.0 else 18),
                width=max(1, S),
            )
        draw.line(
            [(px(cx), px(cy)), (px(cx + radius * math.cos(angle)), px(cy + radius * math.sin(angle)))],
            fill=(255, 255, 255, 18),
            width=max(1, S),
        )
        points_outer.append(
            (px(cx + radius * math.cos(angle)), px(cy + radius * math.sin(angle)))
        )
        points_inner.append(
            (
                px(cx + radius * values[i] * math.cos(angle)),
                px(cy + radius * values[i] * math.sin(angle)),
            )
        )
    draw.polygon(points_inner, fill=_css(VIOLET, 38), outline=_css(VIOLET, 210))
    draw.line(points_inner + [points_inner[0]], fill=_css(VIOLET, 220), width=2 * S)
    for x, y in points_inner:
        draw.ellipse(
            [(x - 4 * S, y - 4 * S), (x + 4 * S, y + 4 * S)],
            fill=_css(WHITE, 245),
        )
    draw.ellipse(
        [(px(cx - 5), px(cy - 5)), (px(cx + 5), px(cy + 5))],
        fill=_css(VIOLET, 255),
    )

    footer(draw, width, height, "PERSONAL REPORT · CONFIDENTIAL", margin=84)
    image = add_vignette(image, 130)
    image = add_grain(image, 7)
    save(image, "report.jpg", 94)


# ------------------------------------------------------------------ matrix q09


def make_matrix() -> None:
    width = height = 1080
    image, draw = base_canvas(width, height)

    f_title = font(FONT_SEMIBOLD, 20)
    f_small = font(FONT_REGULAR, 11)
    draw_tracked(draw, (74, 62), "МАТРИЦА · 09", f_title, _css(WHITE, 240), tracking=3.4)
    draw_tracked(
        draw,
        (width - 74, 65),
        "ABSTRACT REASONING",
        f_small,
        _css(MUTED, 210),
        tracking=3.2,
        anchor_right=True,
    )
    draw.line([(px(74), px(112)), (px(width - 74), px(112))], fill=(255, 255, 255, 30), width=max(1, S))

    grid_x, grid_y = 158, 182
    cell = 254
    total = cell * 3

    # soft panel
    draw.rounded_rectangle(
        [(px(grid_x - 26), px(grid_y - 26)), (px(grid_x + total + 26), px(grid_y + total + 26))],
        radius=px(26),
        fill=(255, 255, 255, 8),
        outline=(255, 255, 255, 28),
        width=max(1, S),
    )

    for i in range(4):
        offset = i * cell
        draw.line(
            [(px(grid_x + offset), px(grid_y)), (px(grid_x + offset), px(grid_y + total))],
            fill=(255, 255, 255, 36 if i in (0, 3) else 20),
            width=max(1, 2 * S if i in (0, 3) else S),
        )
        draw.line(
            [(px(grid_x), px(grid_y + offset)), (px(grid_x + total), px(grid_y + offset))],
            fill=(255, 255, 255, 36 if i in (0, 3) else 20),
            width=max(1, 2 * S if i in (0, 3) else S),
        )

    centers = [
        (grid_x + cell / 2 + col * cell, grid_y + cell / 2 + row * cell)
        for row in range(3)
        for col in range(3)
    ]
    shapes = ["circle", "square", "triangle", "triangle", "circle", "square", "square", "triangle", None]
    for center, shape in zip(centers, shapes):
        if shape == "circle":
            circle_shape(draw, center, 54, _css(WHITE, 225), width=4)
        elif shape == "square":
            square_shape(draw, center, 98, _css(WHITE, 225), width=4)
        elif shape == "triangle":
            triangle_shape(draw, center, 62, _css(WHITE, 225), width=4)
        else:
            glow = radial_glow(image.size, (px(center[0]), px(center[1])), 100 * S, VIOLET, 95)
            image.alpha_composite(glow)
            draw = ImageDraw.Draw(image, "RGBA")
            draw.rounded_rectangle(
                [
                    (px(center[0] - 68), px(center[1] - 68)),
                    (px(center[0] + 68), px(center[1] + 68)),
                ],
                radius=px(12),
                outline=_css(VIOLET, 160),
                width=max(1, 2 * S),
            )
            f_q = font(FONT_LIGHT, 92)
            draw.text(
                (px(center[0] - 27), px(center[1] - 58)),
                "?",
                font=f_q,
                fill=_css(VIOLET, 245),
            )

    f_footer = font(FONT_REGULAR, 11)
    draw.line([(px(74), px(1000)), (px(width - 74), px(1000))], fill=(255, 255, 255, 24), width=max(1, S))
    draw_tracked(
        draw,
        (74, 1024),
        "NOEMA · INTELLECTUAL ASSESSMENT",
        f_footer,
        _css(DIM, 190),
        tracking=2.8,
    )
    draw_tracked(
        draw,
        (width - 74, 1024),
        "01 - 20",
        f_footer,
        _css(DIM, 190),
        tracking=2.8,
        anchor_right=True,
    )

    image = add_vignette(image, 130)
    image = add_grain(image, 6)
    save(image, "q09.jpg", 95)


def main() -> None:
    load_fonts()
    print("Генерация визуальной айдентики NOEMA...")
    make_hero()
    make_analysis()
    make_locked()
    make_unlocked()
    make_report()
    make_matrix()
    print("Готово.")


if __name__ == "__main__":
    main()
