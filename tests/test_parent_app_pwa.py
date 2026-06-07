from __future__ import annotations

import json
import re
import struct
import zlib


def png_size(path):
    with path.open("rb") as image:
        header = image.read(24)
    assert header.startswith(b"\x89PNG\r\n\x1a\n")
    return struct.unpack(">II", header[16:24])


def png_rgba_alpha_stats(path):
    data = path.read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n")

    offset = 8
    width = height = bit_depth = color_type = None
    chunks = []
    while offset < len(data):
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        chunk_type = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + length]
        offset += 12 + length
        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type, _, _, _ = struct.unpack(">IIBBBBB", payload)
        elif chunk_type == b"IDAT":
            chunks.append(payload)
        elif chunk_type == b"IEND":
            break

    assert width and height
    assert bit_depth == 8
    assert color_type == 6

    bytes_per_pixel = 4
    stride = width * bytes_per_pixel
    stream = zlib.decompress(b"".join(chunks))
    previous = [0] * stride
    min_alpha = 255
    max_alpha = 0
    points = []
    cursor = 0

    for y in range(height):
        filter_type = stream[cursor]
        cursor += 1
        source = list(stream[cursor:cursor + stride])
        cursor += stride
        row = [0] * stride

        for x, value in enumerate(source):
            left = row[x - bytes_per_pixel] if x >= bytes_per_pixel else 0
            up = previous[x]
            upper_left = previous[x - bytes_per_pixel] if x >= bytes_per_pixel else 0
            if filter_type == 0:
                predicted = 0
            elif filter_type == 1:
                predicted = left
            elif filter_type == 2:
                predicted = up
            elif filter_type == 3:
                predicted = (left + up) // 2
            elif filter_type == 4:
                p = left + up - upper_left
                choices = [(abs(p - left), left), (abs(p - up), up), (abs(p - upper_left), upper_left)]
                predicted = min(choices, key=lambda item: item[0])[1]
            else:
                raise AssertionError(f"Unsupported PNG filter: {filter_type}")
            row[x] = (value + predicted) & 0xFF

        for x in range(width):
            alpha = row[x * bytes_per_pixel + 3]
            min_alpha = min(min_alpha, alpha)
            max_alpha = max(max_alpha, alpha)
            if alpha > 10:
                points.append((x, y))
        previous = row

    assert points
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return {
        "width": width,
        "height": height,
        "alpha": (min_alpha, max_alpha),
        "bounds": (min(xs), min(ys), max(xs), max(ys)),
    }


def png_rgba_alpha_bounds(path):
    stats = png_rgba_alpha_stats(path)
    return stats["width"], stats["height"], stats["bounds"]


def test_parent_app_manifest_contract(repo_root) -> None:
    docs_dir = repo_root / "docs"
    manifest_path = docs_dir / "manifest.webmanifest"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["name"] == "SweetYaar Parent Remote"
    assert manifest["short_name"] == "SweetYaar"
    assert manifest["id"] == "./"
    assert manifest["start_url"] == "./"
    assert manifest["scope"] == "./"
    assert manifest["display"] == "standalone"
    assert manifest["orientation"] == "portrait"
    assert manifest["theme_color"] == "#08736c"
    assert manifest["background_color"] == "#fcf8f3"

    icons = {icon["src"]: icon for icon in manifest["icons"]}
    assert icons["assets/pwa-icon-192.png"]["sizes"] == "192x192"
    assert icons["assets/pwa-icon-512.png"]["sizes"] == "512x512"
    assert icons["assets/pwa-icon-maskable-192.png"]["purpose"] == "maskable"
    assert icons["assets/pwa-icon-maskable-192.png"]["sizes"] == "192x192"
    assert icons["assets/pwa-icon-maskable-512.png"]["purpose"] == "maskable"
    assert icons["assets/pwa-icon-maskable-512.png"]["sizes"] == "512x512"

    for icon_src, icon in icons.items():
        icon_path = docs_dir / icon_src
        assert icon_path.exists(), icon_src
        expected_size = tuple(int(value) for value in icon["sizes"].split("x"))
        assert png_size(icon_path) == expected_size


def test_parent_app_index_links_pwa_assets(repo_root) -> None:
    index_html = (repo_root / "docs" / "index.html").read_text(encoding="utf-8")

    assert '<meta name="theme-color" content="#08736c">' in index_html
    assert '<meta name="mobile-web-app-capable" content="yes">' in index_html
    assert "apple-mobile-web-app-capable" not in index_html
    assert '<link rel="manifest" href="manifest.webmanifest">' in index_html
    assert 'href="favicon.ico"' in index_html
    assert 'href="assets/favicon-16.png"' in index_html
    assert 'href="assets/favicon-32.png"' in index_html
    assert 'href="assets/favicon-48.png"' in index_html
    assert 'href="assets/pwa-icon-192.png"' in index_html
    assert '<link rel="apple-touch-icon" sizes="180x180" href="assets/apple-touch-icon.png">' in index_html
    assert 'class="install-app-icon" src="assets/pwa-icon-192.png"' in index_html
    assert 'id="installBanner"' in index_html
    assert 'id="installButton"' in index_html
    assert 'id="installDismissButton"' in index_html
    assert 'src="assets/icon-settings-sliders.svg"' in index_html
    assert ">⚙<" not in index_html
    assert 'settings-back .button-glyph::before' in index_html
    assert ">←<" not in index_html
    assert 'window.addEventListener("beforeinstallprompt"' in index_html
    assert 'window.addEventListener("appinstalled"' in index_html
    assert "promptInstall" in index_html
    assert 'navigator.serviceWorker.register("sw.js", { scope: "./" })' in index_html
    assert "registration.update" in index_html


def test_parent_app_icon_alpha_contract(repo_root) -> None:
    docs_dir = repo_root / "docs"

    for icon_name in [
        "apple-touch-icon.png",
        "pwa-icon-192.png",
        "pwa-icon-512.png",
        "pwa-icon-maskable-192.png",
        "pwa-icon-maskable-512.png",
    ]:
        stats = png_rgba_alpha_stats(docs_dir / "assets" / icon_name)
        assert stats["alpha"] == (255, 255), icon_name
        assert stats["bounds"] == (0, 0, stats["width"] - 1, stats["height"] - 1), icon_name

    for icon_name in ["favicon-16.png", "favicon-32.png", "favicon-48.png"]:
        stats = png_rgba_alpha_stats(docs_dir / "assets" / icon_name)
        assert stats["alpha"] == (0, 255), icon_name
        min_x, min_y, max_x, max_y = stats["bounds"]
        assert min_x > 0 or min_y > 0, icon_name
        assert max_x < stats["width"] - 1 or max_y < stats["height"] - 1, icon_name


def test_parent_app_service_worker_precache_contract(repo_root) -> None:
    docs_dir = repo_root / "docs"
    sw_path = docs_dir / "sw.js"
    sw_source = sw_path.read_text(encoding="utf-8")
    precache_match = re.search(
        r"const PRECACHE_URLS = \[(?P<urls>.*?)\];",
        sw_source,
        flags=re.DOTALL,
    )
    assert precache_match, "sw.js must define PRECACHE_URLS"

    urls = re.findall(r'"([^"]+)"', precache_match.group("urls"))
    assert "./" in urls
    assert "./favicon.ico" in urls
    assert "./index.html" in urls
    assert "./manifest.webmanifest" in urls
    assert "./assets/favicon-16.png" in urls
    assert "./assets/favicon-32.png" in urls
    assert "./assets/favicon-48.png" in urls
    assert "./assets/icon-settings-sliders.svg" in urls
    assert "./assets/pwa-icon-192.png" in urls
    assert "./assets/pwa-icon-512.png" in urls
    assert "./assets/pwa-icon-maskable-192.png" in urls
    assert "./assets/pwa-icon-maskable-512.png" in urls

    for url in urls:
        if url == "./":
            continue
        assert url.startswith("./"), url
        asset_path = docs_dir / url.removeprefix("./")
        assert asset_path.exists(), url

    assert 'const CACHE_PREFIX = "sweetyaar-parent";' in sw_source
    assert 'const CACHE_VERSION = "sweetyaar-parent-v10";' in sw_source
    assert "cache.addAll(PRECACHE_URLS)" in sw_source
    assert "self.skipWaiting()" in sw_source
    assert "self.clients.claim()" in sw_source
    assert "function networkFirst" in sw_source
    assert "function staleWhileRevalidate" in sw_source
    assert "request.method === \"GET\"" in sw_source


def test_parent_app_control_icons_are_centered(repo_root) -> None:
    width, height, bounds = png_rgba_alpha_bounds(repo_root / "docs" / "assets" / "icon-volume.png")
    min_x, min_y, max_x, max_y = bounds
    center_x = (min_x + max_x) / 2
    center_y = (min_y + max_y) / 2
    assert abs(center_x - ((width - 1) / 2)) <= 1
    assert abs(center_y - ((height - 1) / 2)) <= 1
