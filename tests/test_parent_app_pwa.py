from __future__ import annotations

import json
import re
import struct


def png_size(path):
    with path.open("rb") as image:
        header = image.read(24)
    assert header.startswith(b"\x89PNG\r\n\x1a\n")
    return struct.unpack(">II", header[16:24])


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
    assert icons["assets/pwa-icon-maskable-512.png"]["purpose"] == "maskable"

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
    assert 'href="assets/pwa-icon-192.png"' in index_html
    assert 'href="assets/apple-touch-icon.png"' in index_html
    assert 'id="installBanner"' in index_html
    assert 'id="installButton"' in index_html
    assert 'id="installDismissButton"' in index_html
    assert 'window.addEventListener("beforeinstallprompt"' in index_html
    assert 'window.addEventListener("appinstalled"' in index_html
    assert "promptInstall" in index_html
    assert 'navigator.serviceWorker.register("sw.js", { scope: "./" })' in index_html
    assert "registration.update" in index_html


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
    assert "./index.html" in urls
    assert "./manifest.webmanifest" in urls
    assert "./assets/pwa-icon-192.png" in urls
    assert "./assets/pwa-icon-512.png" in urls
    assert "./assets/pwa-icon-maskable-512.png" in urls

    for url in urls:
        if url == "./":
            continue
        assert url.startswith("./"), url
        asset_path = docs_dir / url.removeprefix("./")
        assert asset_path.exists(), url

    assert 'const CACHE_PREFIX = "sweetyaar-parent";' in sw_source
    assert 'const CACHE_VERSION = "sweetyaar-parent-v6";' in sw_source
    assert "cache.addAll(PRECACHE_URLS)" in sw_source
    assert "self.skipWaiting()" in sw_source
    assert "self.clients.claim()" in sw_source
    assert "function networkFirst" in sw_source
    assert "function staleWhileRevalidate" in sw_source
    assert "request.method === \"GET\"" in sw_source
