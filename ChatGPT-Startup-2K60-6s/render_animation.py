from __future__ import annotations

import argparse
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parent
WIDTH = 2560
HEIGHT = 1440
FPS = 60
DURATION = 6.0
FRAME_COUNT = int(round(FPS * DURATION))

IMAGE1 = ROOT / "assets" / "image1-color.jpg"
IMAGE2 = ROOT / "assets" / "image2-line.png"
OUTPUT = ROOT / "output" / "chatgpt-startup-2k60-6s.mp4"
POSTER = ROOT / "output" / "chatgpt-startup-2k60-6s-poster.png"
FIRST_FRAME = ROOT / "output" / "chatgpt-startup-2k60-6s-firstframe.jpg"
SAMPLES = ROOT / "samples"

FONT_SC_PATH = Path(r"C:\Windows\Fonts\NotoSansSC-VF.ttf")

# Welcome stays at the upper left, while the larger title, its Esc hint and
# the loading rail form a separate lower-left group.
TEXT_LEFT = 112
WELCOME_TOP = 94
ESC_TOP = 1098
TITLE_TOP = 1158
TITLE_FONT_SIZE = 214
WELCOME_FONT_SIZE = 58
ESC_FONT_SIZE = 21
PROGRESS_TOP = 1414
PROGRESS_WIDTH = 730
PROGRESS_HEIGHT = 6


def smoothstep(edge0: float, edge1: float, value):
    denominator = np.maximum(edge1 - edge0, 1e-8)
    x = np.clip((value - edge0) / denominator, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def smoothstep_scalar(edge0: float, edge1: float, value: float) -> float:
    denominator = max(edge1 - edge0, 1e-8)
    x = min(max((value - edge0) / denominator, 0.0), 1.0)
    return x * x * (3.0 - 2.0 * x)


def ease_out_cubic(value: float) -> float:
    x = min(max(value, 0.0), 1.0)
    return 1.0 - (1.0 - x) ** 3


def resize_cover(image: np.ndarray, width: int, height: int) -> np.ndarray:
    source_h, source_w = image.shape[:2]
    scale = max(width / source_w, height / source_h)
    resized_w = int(round(source_w * scale))
    resized_h = int(round(source_h * scale))
    resized = cv2.resize(image, (resized_w, resized_h), interpolation=cv2.INTER_LANCZOS4)
    left = max(0, (resized_w - width) // 2)
    top = max(0, (resized_h - height) // 2)
    return resized[top : top + height, left : left + width].copy()


def load_color_image() -> np.ndarray:
    image = cv2.imread(str(IMAGE1), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(IMAGE1)
    image = resize_cover(image, WIDTH, HEIGHT)
    # A restrained grade keeps the original illustration intact while matching
    # the cool cyan light used in the line-drawing phase.
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[..., 1] = np.clip(hsv[..., 1] * 1.035, 0, 255)
    image = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
    return image.astype(np.float32)


def make_paper() -> np.ndarray:
    y, x = np.mgrid[0:HEIGHT, 0:WIDTH].astype(np.float32)
    nx = x / (WIDTH - 1)
    ny = y / (HEIGHT - 1)

    base = np.empty((HEIGHT, WIDTH, 3), dtype=np.float32)
    base[..., 0] = 246.0  # B
    base[..., 1] = 249.0  # G
    base[..., 2] = 251.0  # R

    # Warm ivory near the lower-left, like the source paper.
    warm = np.exp(-(((nx - 0.02) / 0.58) ** 2 + ((ny - 0.92) / 0.42) ** 2))
    base[..., 0] -= 8.0 * warm
    base[..., 1] -= 5.0 * warm
    base[..., 2] -= 13.0 * warm

    # A broad, quiet highlight behind the two figures.
    glow = np.exp(-(((nx - 0.60) / 0.48) ** 2 + ((ny - 0.35) / 0.58) ** 2))
    base[..., 0] += 3.0 * glow
    base[..., 1] += 2.0 * glow
    base[..., 2] += 1.0 * glow

    edge = np.maximum(np.abs(nx - 0.5) / 0.5, np.abs(ny - 0.5) / 0.5)
    base *= (1.0 - 0.018 * edge[..., None])

    rng = np.random.default_rng(19)
    coarse = rng.normal(0.0, 1.0, (HEIGHT // 8, WIDTH // 8)).astype(np.float32)
    coarse = cv2.GaussianBlur(coarse, (0, 0), 3.2)
    coarse = cv2.resize(coarse, (WIDTH, HEIGHT), interpolation=cv2.INTER_CUBIC)
    fine = rng.normal(0.0, 0.55, (HEIGHT, WIDTH)).astype(np.float32)
    texture = coarse * 0.65 + fine
    base += texture[..., None]
    return np.clip(base, 0, 255)


def prepare_line_art() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    source = cv2.imread(str(IMAGE2), cv2.IMREAD_COLOR)
    if source is None:
        raise FileNotFoundError(IMAGE2)
    source = resize_cover(source, WIDTH, HEIGHT)

    gray = cv2.cvtColor(source, cv2.COLOR_BGR2GRAY)
    local_background = cv2.GaussianBlur(gray, (0, 0), 13.0)
    line_strength = np.clip((local_background.astype(np.float32) - gray) / 82.0, 0.0, 1.0)

    # It is line art, but a soft grayscale shading pass helps the thinner
    # interior construction lines remain visible after the ink glow fades.
    darkness = np.clip((226.0 - gray.astype(np.float32)) / 135.0, 0.0, 1.0)
    line_strength = np.maximum(line_strength, darkness * 0.78)
    background_selector = gray > 229
    line_strength[background_selector] *= 0.08
    line_strength[line_strength < 0.055] = 0.0
    line_strength = cv2.GaussianBlur(line_strength, (0, 0), 0.65)

    # The source has old typography. Remove it before the animation so the
    # replacement lettering can live on clean paper.
    remove = np.zeros((HEIGHT, WIDTH), dtype=np.uint8)
    remove[62:220, 88:445] = 255
    remove[1108:1310, 90:700] = 255
    source_clean = cv2.inpaint(source, remove, 7, cv2.INPAINT_TELEA)
    gray_clean = cv2.cvtColor(source_clean, cv2.COLOR_BGR2GRAY).astype(np.float32)
    local_clean = cv2.GaussianBlur(gray_clean, (0, 0), 13.0)
    clean_strength = np.clip((local_clean - gray_clean) / 82.0, 0.0, 1.0)
    clean_strength = np.maximum(clean_strength, np.clip((226.0 - gray_clean) / 135.0, 0.0, 1.0) * 0.78)
    clean_strength[gray_clean > 229] *= 0.08
    clean_strength[remove > 0] = 0.0
    line_strength = cv2.GaussianBlur(clean_strength, (0, 0), 0.65)

    # Cooling the strokes before composition ties them to the final image.
    line_rgb = source_clean.astype(np.float32)
    cool = np.array([16.0, 12.0, -1.0], dtype=np.float32)  # BGR
    line_rgb = np.clip(line_rgb + cool * line_strength[..., None], 0, 255)

    return line_rgb, line_strength, source_clean


def make_schedule(line_strength: np.ndarray) -> np.ndarray:
    y, x = np.mgrid[0:HEIGHT, 0:WIDTH].astype(np.float32)
    nx = x / (WIDTH - 1)
    ny = y / (HEIGHT - 1)

    left_hair = np.exp(-(((nx - 0.30) / 0.19) ** 2 + ((ny - 0.21) / 0.24) ** 2))
    right_hair = np.exp(-(((nx - 0.64) / 0.29) ** 2 + ((ny - 0.22) / 0.27) ** 2))
    hair = np.maximum(left_hair, right_hair)
    left_face = np.exp(-(((nx - 0.29) / 0.085) ** 2 + ((ny - 0.29) / 0.16) ** 2))
    right_face = np.exp(-(((nx - 0.65) / 0.11) ** 2 + ((ny - 0.35) / 0.18) ** 2))
    face = np.maximum(left_face, right_face)

    anchor_left = np.sqrt((x - 760.0) ** 2 + (y - 300.0) ** 2)
    anchor_right = np.sqrt((x - 1630.0) ** 2 + (y - 320.0) ** 2)
    anchor_distance = np.minimum(anchor_left, anchor_right)
    anchor_distance = np.clip(anchor_distance / 1220.0, 0.0, 1.0)

    body = smoothstep(560.0, 1050.0, y) * (1.0 - 0.45 * face)
    prop = smoothstep(740.0, 1230.0, y) * (
        smoothstep(760.0, 300.0, x) + smoothstep(1600.0, 2350.0, x)
    )
    prop = np.clip(prop, 0.0, 1.0)

    rng = np.random.default_rng(87)
    noise = rng.normal(0.0, 1.0, (HEIGHT // 12, WIDTH // 12)).astype(np.float32)
    noise = cv2.GaussianBlur(noise, (0, 0), 7.0)
    noise = cv2.resize(noise, (WIDTH, HEIGHT), interpolation=cv2.INTER_CUBIC)
    noise = (noise - noise.min()) / max(float(noise.max() - noise.min()), 1e-6)

    wave = 0.55 * nx + 0.45 * ny
    schedule = (
        0.43
        - 0.34 * hair
        - 0.13 * face
        + 0.17 * body
        + 0.14 * prop
        + 0.10 * anchor_distance
        + 0.07 * wave
        + 0.075 * noise
        + 0.12 * (1.0 - line_strength)
    )

    values = schedule[line_strength > 0.03]
    low, high = np.percentile(values, [0.8, 99.2])
    schedule = np.clip((schedule - low) / max(float(high - low), 1e-6), 0.0, 1.0)
    schedule = schedule * schedule * (3.0 - 2.0 * schedule)
    return schedule.astype(np.float32)


def gradient_text_mask(text: str, font_size: int, top: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    font = ImageFont.truetype(str(FONT_SC_PATH), font_size)
    try:
        font.set_variation_by_name("Bold")
    except Exception:
        pass

    mask = Image.new("L", (WIDTH, HEIGHT), 0)
    draw = ImageDraw.Draw(mask)
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=1)
    visible_top = bbox[1]
    draw.text(
        (TEXT_LEFT, top - visible_top),
        text,
        font=font,
        fill=255,
        stroke_width=1,
        stroke_fill=210,
    )
    alpha = np.asarray(mask, dtype=np.float32) / 255.0

    y, x = np.mgrid[0:HEIGHT, 0:WIDTH].astype(np.float32)
    vertical = np.clip((y - float(top)) / max(font_size * 1.12, 1.0), 0.0, 1.0)

    # Silver at the top, pale ice in the middle, saturated cyan-blue at the
    # bottom. Interpolation is done in float so the luminance ramps smoothly.
    stops = np.array(
        [
            [252, 255, 255],
            [240, 252, 255],
            [185, 235, 251],
            [88, 198, 240],
            [38, 132, 190],
        ],
        dtype=np.float32,
    )
    stop_positions = np.array([0.0, 0.38, 0.68, 0.88, 1.0], dtype=np.float32)
    rgb = np.empty((HEIGHT, WIDTH, 3), dtype=np.float32)
    for channel in range(3):
        rgb[..., channel] = np.interp(vertical, stop_positions, stops[:, channel])

    # Fine dark edge + cyan bloom. The dark line is what keeps silver text
    # readable against the pale paper.
    stroke_mask = Image.fromarray(np.uint8(np.clip(alpha * 255, 0, 255)), "L")
    stroke_mask = stroke_mask.filter(ImageFilter.MaxFilter(3))
    stroke_alpha = np.asarray(stroke_mask, dtype=np.float32) / 255.0
    stroke_alpha = np.maximum(stroke_alpha - alpha, 0.0)
    rgb = rgb * (1.0 - 0.78 * stroke_alpha[..., None]) + np.array([64, 52, 20], dtype=np.float32) * (
        0.78 * stroke_alpha[..., None]
    )
    rgb = rgb[..., ::-1].copy()  # RGB stops -> OpenCV BGR working frame

    glow_image = Image.fromarray(np.uint8(np.clip(alpha * 255, 0, 255)), "L")
    glow_image = glow_image.filter(ImageFilter.GaussianBlur(14))
    glow_alpha = np.asarray(glow_image, dtype=np.float32) / 255.0
    return rgb, alpha, glow_alpha


def make_text_assets():
    welcome_rgb, welcome_alpha, welcome_glow = gradient_text_mask(
        "欢迎使用", WELCOME_FONT_SIZE, WELCOME_TOP
    )
    # The previous title was 165 px. This is a full 30% increase while the
    # compact lines above keep the aligned block from feeling heavy.
    title_rgb, title_alpha, title_glow = gradient_text_mask(
        "ChatGPT", TITLE_FONT_SIZE, TITLE_TOP
    )
    esc_rgb, esc_alpha, esc_glow = gradient_text_mask("ESC  进入", ESC_FONT_SIZE, ESC_TOP)

    # Dim the hint while retaining a readable, intentional cyan outline.
    esc_rgb = esc_rgb * 0.74 + np.array([91, 80, 45], dtype=np.float32) * 0.26
    esc_alpha *= 0.78
    esc_glow *= 0.34

    return {
        "welcome": (welcome_rgb, welcome_alpha, welcome_glow),
        "title": (title_rgb, title_alpha, title_glow),
        "esc": (esc_rgb, esc_alpha, esc_glow),
    }


def make_loading_assets():
    """Build a quiet rail rather than a media seek bar or playhead."""
    left = TEXT_LEFT
    top = PROGRESS_TOP
    right = left + PROGRESS_WIDTH
    bottom = top + PROGRESS_HEIGHT

    track_image = Image.new("L", (WIDTH, HEIGHT), 0)
    track_draw = ImageDraw.Draw(track_image)
    track_draw.rounded_rectangle(
        (left, top, right, bottom),
        radius=PROGRESS_HEIGHT // 2,
        fill=255,
    )
    track_alpha = np.asarray(track_image, dtype=np.float32) / 255.0

    halo_image = track_image.filter(ImageFilter.GaussianBlur(13))
    halo_alpha = np.asarray(halo_image, dtype=np.float32) / 255.0

    y, _ = np.mgrid[0:HEIGHT, 0:WIDTH].astype(np.float32)
    ramp = np.clip((y - top) / max(PROGRESS_HEIGHT - 1, 1), 0.0, 1.0)
    silver = np.array([252.0, 254.0, 255.0], dtype=np.float32)
    cyan = np.array([214.0, 183.0, 74.0], dtype=np.float32)  # BGR
    fill_rgb = silver[None, None, :] * (1.0 - ramp[..., None]) + cyan[None, None, :] * ramp[..., None]
    fill_rgb = np.broadcast_to(fill_rgb, (HEIGHT, WIDTH, 3)).copy()

    x = np.arange(WIDTH, dtype=np.float32)[None, :]
    return {
        "left": left,
        "right": right,
        "track_alpha": track_alpha,
        "halo_alpha": halo_alpha,
        "fill_rgb": fill_rgb,
        "x": x,
    }


def alpha_composite(base: np.ndarray, rgb: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    a = alpha[..., None]
    return base * (1.0 - a) + rgb * a


def shifted_alpha(alpha: np.ndarray, offset_y: float) -> np.ndarray:
    if abs(offset_y) < 0.01:
        return alpha
    matrix = np.float32([[1.0, 0.0, 0.0], [0.0, 1.0, offset_y]])
    return cv2.warpAffine(alpha, matrix, (WIDTH, HEIGHT), flags=cv2.INTER_LINEAR, borderValue=0)


def text_visibility(time_seconds: float, start: float, rise: float = 0.45) -> tuple[float, float]:
    amount = smoothstep_scalar(start, start + rise, time_seconds)
    eased = ease_out_cubic((time_seconds - start) / rise if rise > 0 else 1.0)
    return amount, (1.0 - eased) * 15.0


def compose_text(frame: np.ndarray, time_seconds: float, text_assets) -> np.ndarray:
    welcome_amount, welcome_shift = text_visibility(time_seconds, 0.88)
    title_amount, title_shift = text_visibility(time_seconds, 1.15)
    esc_amount, esc_shift = text_visibility(time_seconds, 3.62, 0.62)

    # Soft upper-left and lower-left scrims stabilize the silver lettering
    # against both the paper and the much brighter final illustration, without
    # reading as rectangular UI panels.
    y, x = np.mgrid[0:HEIGHT, 0:WIDTH].astype(np.float32)
    upper_scrim = np.exp(-(((x - 270.0) / 480.0) ** 2 + ((y - 185.0) / 230.0) ** 2))
    lower_scrim = np.exp(-(((x - 415.0) / 650.0) ** 2 + ((y - 1285.0) / 285.0) ** 2))
    scrim = np.maximum(upper_scrim * 0.13, lower_scrim * 0.23)
    frame *= (1.0 - scrim[..., None] * 0.52)  # soft blue-black tint
    frame += scrim[..., None] * np.array([10.0, 17.0, 16.0], dtype=np.float32)

    for key, amount, shift in (
        ("welcome", welcome_amount, welcome_shift),
        ("title", title_amount, title_shift),
        ("esc", esc_amount, esc_shift),
    ):
        if amount <= 0.001:
            continue
        rgb, alpha, glow = text_assets[key]
        alpha_shifted = shifted_alpha(alpha, shift) * amount
        glow_shifted = shifted_alpha(glow, shift) * amount

        shadow = shifted_alpha(alpha, shift + 6.0)
        shadow = cv2.GaussianBlur(shadow, (0, 0), 9.0) * amount * 0.24
        frame *= (1.0 - shadow[..., None] * 0.55)
        frame += shadow[..., None] * np.array([5.0, 14.0, 18.0], dtype=np.float32)

        frame += glow_shifted[..., None] * np.array([255.0, 198.0, 54.0], dtype=np.float32) * 0.58
        frame = alpha_composite(frame, rgb, alpha_shifted)

        # A narrow moving silver highlight makes the gradient feel polished
        # without changing the typeface or alignment.
        if key == "title":
            sweep_center = 0.08 + 0.72 * min(max((time_seconds - 1.55) / 2.3, 0.0), 1.0)
            if time_seconds > 4.9:
                sweep_center = 0.05 + 0.60 * min(max((time_seconds - 4.9) / 1.1, 0.0), 1.0)
            sweep = np.exp(-(((x / WIDTH) - sweep_center) / 0.035) ** 2)
            highlight = alpha * sweep * amount * 0.48
            frame += highlight[..., None] * np.array([240.0, 245.0, 250.0], dtype=np.float32)

    return frame


def compose_loading(frame: np.ndarray, time_seconds: float, loading_assets) -> np.ndarray:
    reveal = smoothstep_scalar(0.78, 1.18, time_seconds)
    if reveal <= 0.001:
        return frame

    amount = smoothstep_scalar(0.90, 5.84, time_seconds)
    left = float(loading_assets["left"])
    right = float(loading_assets["right"])
    endpoint = left + (right - left) * amount
    track_alpha = loading_assets["track_alpha"]
    halo_alpha = loading_assets["halo_alpha"]
    x = loading_assets["x"]

    # The dark rail, cool halo and moving fill read as loading UI. There is no
    # knob, scrub handle, timestamp or media transport affordance.
    frame *= (1.0 - track_alpha[..., None] * reveal * 0.72)
    frame += track_alpha[..., None] * np.array([18.0, 26.0, 24.0], dtype=np.float32) * reveal
    frame += halo_alpha[..., None] * np.array([126.0, 87.0, 25.0], dtype=np.float32) * 0.26 * reveal

    column_gate = np.clip((endpoint - x + 1.0) / 2.0, 0.0, 1.0)
    fill_alpha = track_alpha * column_gate * reveal
    frame = alpha_composite(frame, loading_assets["fill_rgb"], fill_alpha * 0.98)

    pulse = 0.82 + 0.18 * math.sin(time_seconds * 7.4)
    head = np.exp(-(((x - endpoint) / 8.0) ** 2))
    head = head * (track_alpha > 0).astype(np.float32)
    frame += head[..., None] * np.array([255.0, 235.0, 175.0], dtype=np.float32) * 0.78 * reveal * pulse
    return frame


def compose_line_stage(
    paper: np.ndarray,
    color_image: np.ndarray,
    line_rgb: np.ndarray,
    line_strength: np.ndarray,
    schedule: np.ndarray,
    time_seconds: float,
) -> np.ndarray:
    # Two deliberately separate passes: confidence first, construction next.
    # Dense, darker contour pixels and the hair/face priority field form the
    # silhouette. Lighter construction sweeps and the fine line network follow.
    main_gate = smoothstep(line_strength, 0.24, 0.62)
    main_progress = smoothstep_scalar(0.04, 1.78, time_seconds)
    detail_progress = smoothstep_scalar(1.55, 3.02, time_seconds)
    main_order = np.clip(0.08 + 0.87 * schedule - 0.08 * (1.0 - main_gate), 0.0, 1.0)
    detail_order = np.clip(0.04 + 0.91 * schedule, 0.0, 1.0)
    main_age = main_progress - main_order
    detail_age = detail_progress - detail_order
    main_age = np.where(main_gate >= 0.16, main_age, -10.0)
    detail_age = np.where(main_gate < 0.94, detail_age, -10.0)
    age = np.maximum(main_age, detail_age)
    visible = age >= 0.0
    line_alpha = np.clip(age / 0.025, 0.0, 1.0) * visible
    trailing = np.where(visible, np.exp(-np.maximum(age, 0.0) / 0.055), 0.0)
    head = np.exp(-((age / 0.011) ** 2)) * visible
    head *= smoothstep_scalar(0.04, 0.11, time_seconds)
    head *= 1.0 - smoothstep_scalar(2.84, 3.06, time_seconds)

    line_presence = np.clip(line_strength * 1.85, 0.0, 1.0)
    ink_alpha = visible.astype(np.float32) * line_presence * line_alpha

    # Stronger, slightly thicker strokes for the luminous head.
    glow_small = cv2.resize(trailing, (WIDTH // 2, HEIGHT // 2), interpolation=cv2.INTER_AREA)
    glow_small = cv2.GaussianBlur(glow_small, (0, 0), 3.8)
    glow_small = cv2.resize(glow_small, (WIDTH, HEIGHT), interpolation=cv2.INTER_CUBIC)
    glow_small *= line_presence

    bloom_small = cv2.resize(head + 0.36 * trailing, (WIDTH // 4, HEIGHT // 4), interpolation=cv2.INTER_AREA)
    bloom_small = cv2.GaussianBlur(bloom_small, (0, 0), 5.6)
    bloom = cv2.resize(bloom_small, (WIDTH, HEIGHT), interpolation=cv2.INTER_CUBIC)

    color_factor = smoothstep_scalar(3.22, 4.36, time_seconds)
    frame = paper * (1.0 - color_factor) + color_image * color_factor

    line_fade = 1.0 - smoothstep_scalar(3.52, 4.42, time_seconds)
    if line_fade > 0.001:
        frame = alpha_composite(frame, line_rgb, ink_alpha * 0.90 * line_fade)
        frame += glow_small[..., None] * np.array([255.0, 190.0, 54.0], dtype=np.float32) * 0.50 * line_fade
        frame += bloom[..., None] * np.array([255.0, 220.0, 118.0], dtype=np.float32) * 0.64 * line_fade
        frame += head[..., None] * np.array([255.0, 248.0, 230.0], dtype=np.float32) * line_fade

    # Cyan pulse at the hand-off from drawn silhouette to full-color artwork.
    transition = math.exp(-((time_seconds - 3.76) / 0.44) ** 2)
    if transition > 0.001:
        y, x = np.mgrid[0:HEIGHT, 0:WIDTH].astype(np.float32)
        cx = 0.18 + 0.66 * min(max((time_seconds - 3.07) / 1.20, 0.0), 1.0)
        ribbon = np.exp(-(((x / WIDTH) - cx) / 0.14) ** 2)
        ribbon *= np.exp(-(((y / HEIGHT) - 0.48) / 0.55) ** 2)
        frame += ribbon[..., None] * np.array([135.0, 100.0, 34.0], dtype=np.float32) * 0.13 * transition

    return frame


def add_finishing(frame: np.ndarray, time_seconds: float, grain: np.ndarray, time_index: int) -> np.ndarray:
    y, x = np.mgrid[0:HEIGHT, 0:WIDTH].astype(np.float32)
    nx = x / (WIDTH - 1)
    ny = y / (HEIGHT - 1)

    vignette = np.clip(np.maximum(np.abs(nx - 0.5) / 0.5, np.abs(ny - 0.5) / 0.5), 0.0, 1.0)
    frame *= (1.0 - 0.045 * vignette[..., None] ** 2)

    # A slow cyan light sweep across the figures during the final hold.
    final_amount = smoothstep_scalar(4.15, 5.05, time_seconds)
    if final_amount > 0.0:
        sx = 0.40 + 0.090 * math.sin((time_seconds - 4.1) * 1.25)
        sy = 0.37 + 0.035 * math.cos((time_seconds - 4.1) * 0.9)
        glow = np.exp(-(((nx - sx) / 0.34) ** 2 + ((ny - sy) / 0.48) ** 2))
        frame += glow[..., None] * np.array([36.0, 20.0, 2.0], dtype=np.float32) * 0.065 * final_amount

    grain_offset_x = (time_index * 37) % 256
    grain_offset_y = (time_index * 73) % 192
    crop = grain[grain_offset_y : grain_offset_y + HEIGHT, grain_offset_x : grain_offset_x + WIDTH]
    frame += crop[..., None]

    return np.clip(frame, 0, 255).astype(np.uint8)


def make_grain() -> np.ndarray:
    rng = np.random.default_rng(501)
    large = rng.normal(0.0, 2.0, (HEIGHT + 240, WIDTH + 300)).astype(np.float32)
    return large * 0.55


def ffmpeg_path() -> str:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:
        raise RuntimeError("找不到 FFmpeg。请安装 imageio-ffmpeg。") from exc


class Renderer:
    def __init__(self):
        self.paper = make_paper()
        self.color_image = load_color_image()
        self.line_rgb, self.line_strength, _ = prepare_line_art()
        self.schedule = make_schedule(self.line_strength)
        self.text_assets = make_text_assets()
        self.loading_assets = make_loading_assets()
        self.grain = make_grain()

    def frame(self, time_seconds: float, time_index: int) -> np.ndarray:
        frame = compose_line_stage(
            self.paper,
            self.color_image,
            self.line_rgb,
            self.line_strength,
            self.schedule,
            time_seconds,
        )
        frame = compose_text(frame, time_seconds, self.text_assets)
        frame = compose_loading(frame, time_seconds, self.loading_assets)
        return add_finishing(frame, time_seconds, self.grain, time_index)


def render_samples(renderer: Renderer) -> None:
    SAMPLES.mkdir(parents=True, exist_ok=True)
    times = [0.25, 0.65, 1.10, 1.55, 2.00, 2.55, 3.05, 3.45, 3.85, 4.25, 4.85, 5.92]
    for seconds in times:
        index = int(round(seconds * FPS))
        frame = renderer.frame(seconds, index)
        cv2.imwrite(str(SAMPLES / f"frame-{seconds:04.2f}.png"), frame)
    cv2.imwrite(str(SAMPLES / "poster-preview.png"), renderer.frame(5.99, FRAME_COUNT - 1))


def render_video(renderer: Renderer) -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = ffmpeg_path()
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "bgr24",
        "-s",
        f"{WIDTH}x{HEIGHT}",
        "-r",
        str(FPS),
        "-i",
        "-",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "slow",
        "-crf",
        "21",
        "-tune",
        "fastdecode",
        "-pix_fmt",
        "yuv420p",
        "-profile:v",
        "main",
        "-level",
        "5.1",
        "-g",
        "60",
        "-bf",
        "0",
        "-movflags",
        "+faststart",
        str(OUTPUT),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    assert process.stdin is not None
    try:
        for index in range(FRAME_COUNT):
            frame = renderer.frame(index / FPS, index)
            process.stdin.write(frame.tobytes())
            if index % 30 == 0:
                print(f"rendered {index + 1}/{FRAME_COUNT}", flush=True)
    finally:
        process.stdin.close()
    result = process.wait()
    if result != 0:
        raise RuntimeError(f"FFmpeg 编码失败，退出码 {result}")
    poster = renderer.frame(5.99, FRAME_COUNT - 1)
    cv2.imwrite(str(POSTER), poster)
    first_frame = renderer.frame(0.0, 0)
    cv2.imwrite(str(FIRST_FRAME), first_frame, [cv2.IMWRITE_JPEG_QUALITY, 94])
    print(f"video: {OUTPUT}")
    print(f"poster: {POSTER}")
    print(f"first frame: {FIRST_FRAME}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", action="store_true")
    parser.add_argument("--render", action="store_true")
    args = parser.parse_args()
    if not args.samples and not args.render:
        parser.error("choose --samples or --render")

    renderer = Renderer()
    if args.samples:
        render_samples(renderer)
    if args.render:
        render_video(renderer)
    return 0


if __name__ == "__main__":
    sys.exit(main())
