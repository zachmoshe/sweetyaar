from __future__ import annotations

from pathlib import Path
from collections import deque
from io import BytesIO
from zipfile import ZipFile

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "final"
SOURCE = Path("/Users/zmoshe/Downloads/after.png")
DESIGNER_PACKET = Path("/Users/zmoshe/Downloads/sweetyaar_design_kit_pixel_matched.zip")
GENERATED_FOOTER_SOURCE = ROOT / "assets" / "source" / "footer-generated-alpha.png"
GENERATED_TOP_SOURCE = ROOT / "assets" / "source" / "top-generated-alpha.png"

SCREEN_W = 432


def lerp(a: int, b: int, t: float) -> int:
    return round(a + (b - a) * t)


def mix(c1: tuple[int, int, int], c2: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(lerp(a, b, t) for a, b in zip(c1, c2))


def viewport_bg(screen_y: int, *, force_sky: bool = False) -> tuple[int, int, int]:
    sky_top = (218, 244, 241)
    sky_bottom = (203, 237, 234)
    body_top = (255, 251, 246)
    body_bottom = (253, 244, 235)

    if force_sky or screen_y <= 185:
        return mix(sky_top, sky_bottom, min(max(screen_y / 185, 0), 1))

    return mix(body_top, body_bottom, min(max((screen_y - 185) / 650, 0), 1))


def make_base_background() -> Image.Image:
    height = 1200
    image = Image.new("RGB", (SCREEN_W, height))
    draw = ImageDraw.Draw(image)

    for y in range(height):
        draw.line([(0, y), (SCREEN_W, y)], fill=viewport_bg(y))

    return image


def extract_against_bg(
    crop: Image.Image,
    y_offset: int,
    *,
    force_sky_bg: bool = False,
    low: int = 8,
    high: int = 42,
    erase_rects: list[tuple[int, int, int, int]] | None = None,
) -> Image.Image:
    crop = crop.convert("RGBA")
    px = crop.load()
    width, height = crop.size

    for y in range(height):
        bg = viewport_bg(y + y_offset, force_sky=force_sky_bg)
        for x in range(width):
            r, g, b, _ = px[x, y]
            diff = max(abs(r - bg[0]), abs(g - bg[1]), abs(b - bg[2]))
            if diff <= low:
                a = 0
            elif diff >= high:
                a = 255
            else:
                a = int((diff - low) / (high - low) * 255)
            px[x, y] = (r, g, b, a)

    if erase_rects:
        draw = ImageDraw.Draw(crop)
        for rect in erase_rects:
            draw.rectangle(rect, fill=(0, 0, 0, 0))

    return crop


def clear_matching_pixels(
    image: Image.Image,
    predicate,
) -> Image.Image:
    image = image.convert("RGBA")
    px = image.load()
    width, height = image.size

    for y in range(height):
        for x in range(width):
            r, g, b, a = px[x, y]
            if a and predicate(r, g, b):
                px[x, y] = (r, g, b, 0)

    return image


def is_sky_pixel(r: int, g: int, b: int) -> bool:
    return 188 <= r <= 226 and 220 <= g <= 249 and 220 <= b <= 249 and 14 <= (g - r) <= 48 and abs(g - b) <= 18


def is_body_pixel(r: int, g: int, b: int) -> bool:
    warm_neutral = r >= 230 and g >= 218 and b >= 202 and max(r, g, b) - min(r, g, b) <= 48
    pale_pink_panel = r >= 235 and g >= 205 and b >= 212 and (r - g) <= 52 and (b - g) <= 34
    return warm_neutral or pale_pink_panel


def is_near_black(r: int, g: int, b: int) -> bool:
    return max(r, g, b) <= 35


def add_ready_hill_fill(image: Image.Image) -> Image.Image:
    image = image.convert("RGBA")
    hill = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(hill)
    draw.ellipse((-56, 49, SCREEN_W + 56, 176), fill=(201, 219, 117, 255))
    draw.arc((-56, 49, SCREEN_W + 56, 176), 181, 359, fill=(159, 178, 75), width=2)
    hill.alpha_composite(image)
    return hill


def scrub_transparent_rgb(image: Image.Image, *, sky_backfill: bool = False) -> Image.Image:
    image = image.convert("RGBA")
    values = np.array(image)
    height, width = values.shape[:2]

    for y in range(height):
        if sky_backfill:
            t = y / max(height - 1, 1)
            rgb = (
                round(216 + (189 - 216) * t),
                round(244 + (231 - 244) * t),
                round(240 + (226 - 240) * t),
            )
        else:
            rgb = (0, 0, 0)
        transparent = values[y, :, 3] < 4
        values[y, transparent, 0] = rgb[0]
        values[y, transparent, 1] = rgb[1]
        values[y, transparent, 2] = rgb[2]

    return Image.fromarray(values, "RGBA")


def decontaminate_alpha_edges(image: Image.Image, *, radius: int = 3) -> Image.Image:
    image = image.convert("RGBA")
    values = np.array(image)
    alpha = values[:, :, 3]
    semi = np.argwhere((alpha > 0) & (alpha < 255))
    opaque = alpha > 220

    for y, x in semi:
        y1 = max(0, y - radius)
        y2 = min(values.shape[0], y + radius + 1)
        x1 = max(0, x - radius)
        x2 = min(values.shape[1], x + radius + 1)
        neighbor_mask = opaque[y1:y2, x1:x2]
        if neighbor_mask.any():
            neighbor_rgb = values[y1:y2, x1:x2, :3][neighbor_mask]
            values[y, x, :3] = np.round(neighbor_rgb.mean(axis=0)).astype(np.uint8)

    return Image.fromarray(values, "RGBA")


def soften_alpha(image: Image.Image, *, blur: float = 0.35) -> Image.Image:
    image = image.convert("RGBA")
    alpha = image.getchannel("A").filter(ImageFilter.GaussianBlur(blur))
    image.putalpha(alpha)
    return image


def polish_opening_hero(image: Image.Image) -> Image.Image:
    image = image.convert("RGBA")
    values = np.array(image)
    height = values.shape[0]

    # Keep the high-res asset's own antialiasing. Only feather the bottom floor
    # shadow so it dissolves into the app background instead of ending as a slab.
    alpha = values[:, :, 3].astype(np.float32)
    y = np.arange(height, dtype=np.float32)[:, None]
    fade_start = height * 0.825
    fade_end = height * 0.925
    bottom_fade = np.clip((fade_end - y) / max(fade_end - fade_start, 1), 0, 1)
    alpha = np.where(y > fade_start, alpha * bottom_fade, alpha)
    x = np.arange(values.shape[1], dtype=np.float32)[None, :]
    left_fade = np.clip((x - 1) / 10, 0, 1)
    alpha = np.where(x < 12, alpha * left_fade, alpha)
    values[:, :, 3] = np.clip(alpha, 0, 255).astype(np.uint8)
    return Image.fromarray(values, "RGBA")


def place_opening_hero(image: Image.Image, size: tuple[int, int] = (432, 245)) -> Image.Image:
    image = image.convert("RGBA")
    target_width = 428
    if image.width != target_width:
        target_height = round(image.height * target_width / image.width)
        image = image.resize((target_width, target_height), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    paste_x = round((size[0] - image.width) / 2)
    # Keep the speaker and toys at the same vertical position as the mock crop.
    paste_y = 3
    canvas.alpha_composite(image, (paste_x, paste_y))
    return canvas


def polish_streaming_hero(image: Image.Image) -> Image.Image:
    image = image.convert("RGBA")
    values = np.array(image)
    alpha = values[:, :, 3].astype(np.float32)
    y = np.arange(values.shape[0], dtype=np.float32)[:, None]
    top_fade = np.clip(y / 26, 0, 1)
    alpha = np.where(y < 26, alpha * top_fade, alpha)
    values[:, :, 3] = np.clip(alpha, 0, 255).astype(np.uint8)
    return Image.fromarray(values, "RGBA")


def repair_header_overlay(image: Image.Image) -> Image.Image:
    image = scrub_transparent_rgb(image, sky_backfill=True)
    width, height = image.size
    scale = width / 428
    left_cols = max(2, round(2 * scale))

    # Crop off the captured phone-frame edge rather than erasing it, so the
    # cloud divider and branch still reach the left edge of the overlay.
    image = image.crop((left_cols, 0, width, height)).resize((width, height), Image.Resampling.LANCZOS)
    image = decontaminate_alpha_edges(image, radius=max(3, round(3 * scale)))

    alpha = image.getchannel("A")
    softened = alpha.filter(ImageFilter.GaussianBlur(0.18 * scale))
    image.putalpha(softened)
    return image


def fit_generated_ready_footer(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    image = image.convert("RGBA")
    bbox = image.getbbox()
    if bbox is None:
        return Image.new("RGBA", size, (0, 0, 0, 0))

    target_w, target_h = size
    bbox_w = bbox[2] - bbox[0]
    bbox_h = bbox[3] - bbox[1]
    top_pad = round(target_h * 0.06)
    scale = min(target_w / bbox_w, (target_h - top_pad) / bbox_h)
    resized = image.resize(
        (round(image.width * scale), round(image.height * scale)),
        Image.Resampling.LANCZOS,
    )

    scaled_bbox = tuple(round(value * scale) for value in bbox)
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.ellipse(
        (
            -round(target_w * 0.18),
            round(target_h * 0.42),
            target_w + round(target_w * 0.18),
            target_h + round(target_h * 0.72),
        ),
        fill=(202, 218, 116, 255),
    )
    paste_x = round((target_w - (scaled_bbox[2] - scaled_bbox[0])) / 2 - scaled_bbox[0])
    paste_y = target_h - scaled_bbox[3]
    canvas.alpha_composite(resized, (paste_x, paste_y))
    return canvas


def make_generated_top_overlay(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    width, height = size
    y = np.linspace(0, 1, height, dtype=np.float32)[:, None]
    sky_top = np.array((221, 250, 247), dtype=np.float32)
    sky_bottom = np.array((201, 242, 238), dtype=np.float32)
    rgb = (sky_top * (1 - y) + sky_bottom * y).astype(np.uint8)
    rgb = np.repeat(rgb[:, None, :], width, axis=1)

    yy, xx = np.mgrid[0:height, 0:width]
    center_x = width * 0.5
    center_y = height * 0.26
    radius = width * 0.32
    feather = width * 0.055
    distance = np.sqrt((xx - center_x) ** 2 + (yy - center_y) ** 2)
    radial_alpha = np.clip((radius + feather - distance) / feather, 0, 1) * 0.48
    rgb = (rgb * (1 - radial_alpha[:, :, None]) + 255 * radial_alpha[:, :, None]).astype(np.uint8)

    sky = Image.fromarray(np.dstack([rgb, np.full((height, width), 255, dtype=np.uint8)]), "RGBA")
    mask = make_header_cloud_mask(size).getchannel("A")
    sky.putalpha(mask)

    decor = image.convert("RGBA").resize(size, Image.Resampling.LANCZOS)
    sky.alpha_composite(decor)
    return sky


def make_header_cloud_mask(size: tuple[int, int]) -> Image.Image:
    width, height = size
    supersample = 4
    w = width * supersample
    h = height * supersample
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)

    base_y = round(151 * height / 188 * supersample)
    amplitude = round(10 * height / 188 * supersample)
    period = round(52 * width / 428 * supersample)

    points = [(0, 0), (w, 0), (w, base_y)]
    for x in range(w, -1, -1):
        phase = (x % period) / period
        arch = np.sin(np.pi * phase)
        y = round(base_y - amplitude * arch)
        points.append((x, y))
    points.append((0, 0))
    draw.polygon(points, fill=255)

    mask = mask.resize(size, Image.Resampling.LANCZOS)
    image = Image.new("RGBA", size, (255, 255, 255, 0))
    image.putalpha(mask)
    return image


def repair_ready_footer(image: Image.Image) -> Image.Image:
    image = scrub_transparent_rgb(image)
    values = np.array(image)

    # Fill the tiny transparent extraction hole in the ring-stacker toy.
    for x1, y1, x2, y2 in ((168, 57, 196, 69), (168, 68, 190, 79)):
        region = values[y1:y2, x1:x2]
        opaque = np.argwhere(region[:, :, 3] > 220)
        if len(opaque):
            for y, x in np.argwhere(region[:, :, 3] < 180):
                distances = (opaque[:, 0] - y) ** 2 + (opaque[:, 1] - x) ** 2
                nearest_y, nearest_x = opaque[distances.argmin()]
                region[y, x] = region[nearest_y, nearest_x]
            values[y1:y2, x1:x2] = region

    return Image.fromarray(values, "RGBA")


def make_theme_icon(size: int = 56) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    scale = size / 56

    def xy(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
        return [(x * scale, y * scale) for x, y in points]

    shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.rounded_rectangle((9 * scale, 16 * scale, 28 * scale, 43 * scale), radius=3 * scale, fill=(77, 58, 128, 70))
    shadow_draw.rounded_rectangle((28 * scale, 16 * scale, 47 * scale, 43 * scale), radius=3 * scale, fill=(77, 58, 128, 70))
    shadow = shadow.filter(ImageFilter.GaussianBlur(1.4 * scale))
    image.alpha_composite(shadow, (0, round(2 * scale)))

    draw = ImageDraw.Draw(image)
    draw.polygon(xy([(10, 14), (25, 18), (27, 45), (10, 40)]), fill=(130, 105, 202, 255))
    draw.polygon(xy([(46, 14), (31, 18), (29, 45), (46, 40)]), fill=(151, 126, 216, 255))
    draw.line(xy([(13, 17), (24, 20), (25, 41), (13, 37)]), fill=(174, 154, 232, 105), width=max(1, round(scale)))
    draw.line(xy([(43, 17), (32, 20), (31, 41), (43, 37)]), fill=(198, 185, 245, 100), width=max(1, round(scale)))
    draw.rounded_rectangle((26 * scale, 16 * scale, 30 * scale, 45 * scale), radius=2 * scale, fill=(101, 78, 178, 255))
    draw.line(xy([(28, 18), (28, 44)]), fill=(210, 200, 250, 65), width=max(1, round(scale)))

    return image


def extract_icon(
    screen: Image.Image,
    box: tuple[int, int, int, int],
    bg_sample: tuple[int, int],
    *,
    low: int = 10,
    high: int = 46,
) -> Image.Image:
    icon = screen.crop(box).convert("RGBA")
    bg = screen.convert("RGB").getpixel(bg_sample)
    px = icon.load()
    width, height = icon.size

    for y in range(height):
        for x in range(width):
            r, g, b, _ = px[x, y]
            diff = max(abs(r - bg[0]), abs(g - bg[1]), abs(b - bg[2]))
            if diff <= low:
                a = 0
            elif diff >= high:
                a = 255
            else:
                a = int((diff - low) / (high - low) * 255)
            px[x, y] = (r, g, b, a)

    return icon


def dilate_mask(mask: np.ndarray, passes: int = 1) -> np.ndarray:
    for _ in range(passes):
        padded = np.pad(mask, 1, constant_values=False)
        mask = (
            padded[1:-1, 1:-1]
            | padded[:-2, 1:-1]
            | padded[2:, 1:-1]
            | padded[1:-1, :-2]
            | padded[1:-1, 2:]
            | padded[:-2, :-2]
            | padded[:-2, 2:]
            | padded[2:, :-2]
            | padded[2:, 2:]
        )

    return mask


def erode_mask(mask: np.ndarray, passes: int = 1) -> np.ndarray:
    for _ in range(passes):
        padded = np.pad(mask, 1, constant_values=False)
        mask = (
            padded[1:-1, 1:-1]
            & padded[:-2, 1:-1]
            & padded[2:, 1:-1]
            & padded[1:-1, :-2]
            & padded[1:-1, 2:]
            & padded[:-2, :-2]
            & padded[:-2, 2:]
            & padded[2:, :-2]
            & padded[2:, 2:]
        )

    return mask


def close_mask(mask: np.ndarray, passes: int = 1) -> np.ndarray:
    return erode_mask(dilate_mask(mask, passes), passes)


def fill_mask_holes(mask: np.ndarray) -> np.ndarray:
    height, width = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    queue: deque[tuple[int, int]] = deque()

    for x in range(width):
        for y in (0, height - 1):
            if not mask[y, x] and not seen[y, x]:
                seen[y, x] = True
                queue.append((x, y))

    for y in range(height):
        for x in (0, width - 1):
            if not mask[y, x] and not seen[y, x]:
                seen[y, x] = True
                queue.append((x, y))

    while queue:
        x, y = queue.popleft()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < width and 0 <= ny < height and not mask[ny, nx] and not seen[ny, nx]:
                seen[ny, nx] = True
                queue.append((nx, ny))

    return mask | ~seen


def keep_components(mask: np.ndarray, min_area: int = 12, center_only: bool = False) -> np.ndarray:
    height, width = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    components: list[list[tuple[int, int]]] = []

    for y in range(height):
        for x in range(width):
            if not mask[y, x] or seen[y, x]:
                continue

            stack = [(x, y)]
            seen[y, x] = True
            points: list[tuple[int, int]] = []

            while stack:
                cx, cy = stack.pop()
                points.append((cx, cy))

                for nx in range(cx - 1, cx + 2):
                    for ny in range(cy - 1, cy + 2):
                        if 0 <= nx < width and 0 <= ny < height and mask[ny, nx] and not seen[ny, nx]:
                            seen[ny, nx] = True
                            stack.append((nx, ny))

            if len(points) >= min_area:
                components.append(points)

    output = np.zeros_like(mask, dtype=bool)
    if center_only and components:
        center_x = width / 2
        center_y = height / 2

        def score(points: list[tuple[int, int]]) -> float:
            avg_x = sum(x for x, _ in points) / len(points)
            avg_y = sum(y for _, y in points) / len(points)
            return len(points) - 0.25 * ((avg_x - center_x) ** 2 + (avg_y - center_y) ** 2)

        components = [max(components, key=score)]

    for points in components:
        for x, y in points:
            output[y, x] = True

    return output


def centered_masked_icon(crop: Image.Image, mask: np.ndarray, canvas_size: int) -> Image.Image:
    mask = fill_mask_holes(close_mask(mask, 1))
    alpha = Image.fromarray((mask.astype(np.uint8) * 255), "L").filter(ImageFilter.GaussianBlur(0.65))
    alpha_array = np.maximum(np.array(alpha), mask.astype(np.uint8) * 255)
    alpha = Image.fromarray(alpha_array, "L")

    rgba = crop.convert("RGBA")
    rgba.putalpha(alpha)
    bbox = Image.fromarray(((alpha_array > 18).astype(np.uint8) * 255), "L").getbbox()
    output = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))

    if bbox:
        piece = rgba.crop(bbox)
        output.alpha_composite(piece, ((canvas_size - piece.width) // 2, (canvas_size - piece.height) // 2))

    return output


def extract_control_icon(screen: Image.Image, kind: str) -> Image.Image:
    boxes = {
        "song": ((38, 296, 118, 362), 64),
        "teddy": ((168, 283, 262, 366), 76),
        "stop": ((328, 304, 392, 364), 64),
        "pause": ((20, 612, 92, 688), 76),
    }
    crop_box, canvas_size = boxes[kind]
    crop = screen.crop(crop_box).convert("RGB")
    values = np.asarray(crop)
    red = values[:, :, 0]
    green = values[:, :, 1]
    blue = values[:, :, 2]

    if kind == "song":
        mask = ((red < 145) & (green > 105) & (blue > 105) & ((green - red) > 35)) | (
            (red < 80) & (green > 120) & (blue > 120)
        )
        mask = keep_components(dilate_mask(mask, 1), min_area=8)
    elif kind == "teddy":
        mask = (
            ((red < 242) & (green < 205) & (blue < 170))
            | ((red < 95) & (green < 95) & (blue < 80))
            | ((red < 230) & (green < 180) & (blue < 130))
        )
        mask = keep_components(dilate_mask(mask, 1), min_area=12)
    elif kind == "stop":
        mask = ((red < 235) & (green < 155) & (blue < 170) & ((red - green) > 60)) | (
            (red < 210) & (green < 120) & (blue < 145)
        )
        mask = keep_components(dilate_mask(mask, 1), min_area=30, center_only=True)
    else:
        mask = (
            ((red > 230) & (green > 235) & (blue > 230))
            | ((red > 165) & (green > 95) & (green < 230) & (blue < 165) & ((red - blue) > 55))
            | ((blue > 130) & (green > 120) & (red < 180))
            | ((red < 120) & (green < 120) & (blue < 105))
        )
        mask &= ~((red > 245) & (green > 210) & (blue > 215) & (green < 237) & (blue < 245))
        mask = keep_components(dilate_mask(mask, 1), min_area=12)

    return centered_masked_icon(crop, mask, canvas_size)


def save_asset(name: str, image: Image.Image) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    image.save(OUT / name)


def load_designer_packet_asset(zip_file: ZipFile, source_name: str) -> Image.Image:
    with zip_file.open(source_name) as asset_file:
        return Image.open(BytesIO(asset_file.read())).convert("RGBA")


def save_designer_packet_asset(zip_file: ZipFile, source_name: str, output_name: str) -> None:
    image = load_designer_packet_asset(zip_file, source_name)
    save_asset(output_name, image)


def main() -> None:
    source = Image.open(SOURCE).convert("RGB")
    screens = [
        source.crop((96, 77, 528, 911)),
        source.crop((626, 77, 1058, 911)),
        source.crop((1155, 77, 1587, 911)),
    ]

    used_packet_header = False
    designer_opening_art: Image.Image | None = None
    if DESIGNER_PACKET.exists():
        with ZipFile(DESIGNER_PACKET) as zip_file:
            save_designer_packet_asset(
                zip_file,
                "sweetyaar_design_kit_v2/assets/backgrounds/top-decor.png",
                "top-overlay.png",
            )
            save_designer_packet_asset(
                zip_file,
                "sweetyaar_design_kit_v2/assets/backgrounds/top-decor@2x.png",
                "top-overlay@2x.png",
            )
            save_designer_packet_asset(
                zip_file,
                "sweetyaar_design_kit_v2/assets/illustrations/footer-ready-raster.png",
                "ready-bottom-overlay.png",
            )
            save_designer_packet_asset(
                zip_file,
                "sweetyaar_design_kit_v2/assets/illustrations/footer-ready-raster@2x.png",
                "ready-bottom-overlay@2x.png",
            )
            designer_opening_art = load_designer_packet_asset(
                zip_file,
                "sweetyaar_design_kit_v2/assets/illustrations/hero-opening-raster@2x.png",
            )
        used_packet_header = True

        if GENERATED_TOP_SOURCE.exists():
            generated_top = Image.open(GENERATED_TOP_SOURCE)
            save_asset("top-overlay.png", make_generated_top_overlay(generated_top, (428, 188)))
            save_asset("top-overlay@2x.png", make_generated_top_overlay(generated_top, (856, 376)))
        else:
            top_overlay = repair_header_overlay(Image.open(OUT / "top-overlay.png"))
            top_overlay_2x = repair_header_overlay(Image.open(OUT / "top-overlay@2x.png"))
            save_asset("top-overlay.png", top_overlay)
            save_asset("top-overlay@2x.png", top_overlay_2x)

        if GENERATED_FOOTER_SOURCE.exists():
            generated_footer = Image.open(GENERATED_FOOTER_SOURCE)
            save_asset("ready-bottom-overlay.png", fit_generated_ready_footer(generated_footer, (428, 134)))
            save_asset("ready-bottom-overlay@2x.png", fit_generated_ready_footer(generated_footer, (856, 268)))
        else:
            ready_footer = repair_ready_footer(Image.open(OUT / "ready-bottom-overlay.png"))
            save_asset("ready-bottom-overlay.png", ready_footer)
            save_asset("ready-bottom-overlay@2x.png", ready_footer.resize((856, 268), Image.Resampling.LANCZOS))

    if not used_packet_header:
        top = screens[2].crop((0, 0, SCREEN_W, 185))
        top_art = extract_against_bg(
            top,
            0,
            force_sky_bg=True,
            low=7,
            high=40,
            erase_rects=[
                (0, 0, SCREEN_W, 39),
                (95, 34, 338, 145),
                (0, 0, 4, 185),
                (428, 0, 432, 185),
            ],
        )
        top_art = clear_matching_pixels(top_art, is_sky_pixel)
        top_art = clear_matching_pixels(top_art, is_near_black)
        save_asset("top-overlay.png", top_art)

    if designer_opening_art is not None:
        opening_art = place_opening_hero(designer_opening_art)
    else:
        opening = screens[0].crop((0, 445, SCREEN_W, 690))
        opening_art = extract_against_bg(opening, 445, low=6, high=34)
        opening_art = clear_matching_pixels(opening_art, is_body_pixel)
    opening_art = polish_opening_hero(opening_art)
    save_asset("opening-hero.png", opening_art)

    streaming = screens[1].crop((0, 288, SCREEN_W, 610))
    streaming_art = extract_against_bg(streaming, 288, low=6, high=34)
    streaming_art = polish_streaming_hero(streaming_art)
    save_asset("streaming-hero.png", streaming_art)

    if not used_packet_header:
        ready_bottom = screens[2].crop((0, 704, SCREEN_W, 834))
        ready_art = extract_against_bg(
            ready_bottom,
            704,
            low=6,
            high=34,
            erase_rects=[
                (126, 111, 306, 130),
                (0, 0, 180, 35),
                (214, 0, 432, 35),
                (0, 100, 12, 130),
                (420, 100, 432, 130),
                (0, 0, 3, 130),
                (429, 0, 432, 130),
            ],
        )
        ready_art = clear_matching_pixels(ready_art, is_body_pixel)
        ready_art = clear_matching_pixels(ready_art, is_near_black)
        ready_art = add_ready_hill_fill(ready_art)
        save_asset("ready-bottom-overlay.png", ready_art)

    # Button/panel icons, separated from their card backgrounds and centered on transparent canvases.
    save_asset("icon-song.png", extract_control_icon(screens[2], "song"))
    save_asset("icon-teddy.png", extract_control_icon(screens[2], "teddy"))
    save_asset("icon-stop.png", extract_control_icon(screens[2], "stop"))
    save_asset("icon-pause-moon.png", extract_control_icon(screens[2], "pause"))
    save_asset("icon-theme.png", make_theme_icon())


if __name__ == "__main__":
    main()
