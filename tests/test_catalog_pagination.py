"""Pagination contract tests using actual firmware JSON and actual app scan code."""

from __future__ import annotations

import copy
import json
import re
import shutil
import subprocess

import pytest

from helpers import run_checked


ATT_VALUE_LIMIT = 512


def production_function(source, name):
    match = re.search(rf"^[A-Za-z_][^\n;{{}}]*\b{re.escape(name)}\([^;]*?\) \{{",
                      source, re.MULTILINE)
    assert match, f"Missing production function: {name}"
    line_end = source.index("\n", match.end())
    if source[match.end():line_end].rstrip().endswith("}"):
        return source[match.start():line_end]
    return source[match.start():source.index("\n}", match.end()) + 2]


@pytest.fixture(scope="module")
def catalog_scan_exe(repo_root, tmp_path_factory):
    compiler = shutil.which("c++")
    if not compiler:
        pytest.skip("A C++ compiler is required for catalog pagination tests.")
    json_include = next((
        base / "firmware/esp32/.pio/libdeps/sweetyaar/ArduinoJson/src"
        for base in (repo_root, *repo_root.parents)
        if (base / "firmware/esp32/.pio/libdeps/sweetyaar/ArduinoJson/src/ArduinoJson.h").exists()
    ), None)
    assert json_include, "Run make build to install the pinned ArduinoJson dependency."
    src = repo_root / "firmware/esp32/src"
    source = (src / "ContentCatalog.cpp").read_text()
    build = tmp_path_factory.mktemp("catalog_scan")
    (build / "catalog_scan_production.inc").write_text("\n".join(
        production_function(source, name) for name in (
            "jsonEscape", "isAnimalsTheme", "appendThemeRow", "appendSongRow",
            "mutableFindTheme", "themeCount", "themeAt", "findTheme",
            "scanThemeStats", "scanPageHeader", "scanPageTail", "songPageHeader",
            "scanSizeError", "buildThemesPageJson", "buildSongsPageJson",
            "validThemeId", "worstCaseStats", "themeEntryFits", "songEntryFits",
            "utf8Prefix", "recordOversizedEntry", "validateCatalog", "catalogWarning",
        )
    ))
    exe = build / "catalog_scan"
    run_checked([
        compiler, "-std=c++17", "-Wall", "-Wextra",
        "-I", repo_root / "tests/json_file_stubs",
        "-I", repo_root / "tests/native_stubs",
        "-I", src, "-I", json_include, "-I", build,
        repo_root / "tests/catalog_scan_native_test.cpp", "-o", exe,
    ])
    return exe


def catalog_fixture(op, count, variant="plain", page_size=0):
    def song(index):
        name = f"s{index:03d}.wav"
        if variant == "unicode":
            name = f'שיר_{index:03d}_🌙.wav'
        return dict(file=name, supported=index % 5 != 4, disabled=index % 3 == 1,
                    sizeBytes=4294967295 if variant == "unicode" else 123456,
                    durationMs=4294967295 if variant == "unicode" else 12345,
                    error='Bad "WAV"\nheader\\x' if index % 5 == 4 else "")

    def theme(index, songs):
        return dict(id=f"t{index:03d}",
                    name=f'ים "🌙"\\{index:03d}' if variant == "unicode" else f"T{index:03d}",
                    shuffle=index % 2 == 0, disabledByUser=index % 3 == 1,
                    special=False, songs=songs)

    if op == "scanThemes":
        themes = [theme(i, [song(j) for j in range(i % 7)]) for i in range(count)]
        if themes:
            themes[-1].update(id="__animals", special=True, disabledByUser=False)
    else:
        themes = [theme(0, [song(i) for i in range(count)])]
    return dict(op=op, themes=themes, theme="t000", maxBytes=page_size,
                id=4294960000 if variant == "unicode" else 1)


def expected_rows(request):
    if request["op"] == "scanSongs":
        return [dict(file=song["file"], enabled=not song["disabled"],
                     ok=song["supported"], sizeBytes=song["sizeBytes"],
                     durationMs=song["durationMs"],
                     **({"error": song["error"]} if not song["supported"] else {}))
                for song in request["themes"][0]["songs"]]
    result = []
    for theme in request["themes"]:
        playable = sum(s["supported"] and not s["disabled"] for s in theme["songs"])
        result.append(dict(
            id=theme["id"], name=theme["name"],
            enabled=not theme["disabledByUser"] and playable > 0,
            disabledByUser=theme["disabledByUser"], shuffle=theme["shuffle"],
            special=theme["special"], canDisable=not theme["special"],
            canSetDefault=not theme["special"], activeValid=playable,
            total=len(theme["songs"]), errors=sum(not s["supported"] for s in theme["songs"]),
        ))
    return result


def serialized(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def scan(catalog_scan_exe, request):
    result = subprocess.run([str(catalog_scan_exe)], input=serialized(request),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            check=True, timeout=10)
    raw_pages = result.stdout.splitlines()
    rows_key = "themes" if request["op"] == "scanThemes" else "songs"
    pages = []
    rows = []
    for page_index, raw in enumerate(raw_pages):
        assert len(raw) <= ATT_VALUE_LIMIT, (
            f"{request['op']} page {page_index}: {len(raw)} UTF-8 bytes > {ATT_VALUE_LIMIT}"
        )
        page = json.loads(raw.decode("utf-8", errors="strict"))
        assert page["id"] == request["id"] + page_index
        assert page["op"] == request["op"] and page["ok"] is True
        assert page["cursor"] == len(rows)
        assert page["nextCursor"] == len(rows) + len(page[rows_key])
        assert type(page["hasMore"]) is bool
        if rows_key == "songs":
            theme = expected_rows({**request, "op": "scanThemes"})[0]
            for response_key, theme_key in (
                ("theme", "id"), ("name", "name"), ("themeEnabled", "enabled"),
                ("disabledByUser", "disabledByUser"), ("shuffle", "shuffle"),
                ("errors", "errors"),
            ):
                assert page[response_key] == theme[theme_key]
        if pages and pages[-1]["hasMore"] is False:
            assert page_index == len(raw_pages) - 1
            assert page[rows_key] == [] and page["hasMore"] is False
            break  # The additional request after the final page.
        assert not page["hasMore"] or page[rows_key], "Nonterminal page must make progress"
        pages.append(page)
        rows.extend(page[rows_key])
    assert pages and pages[-1]["hasMore"] is False
    assert len(raw_pages) == len(pages) + 1, "Missing the empty page after the scan ends"
    assert rows == expected_rows(request), "Scan must preserve every row and field, in order"
    identities = [row["id" if rows_key == "themes" else "file"] for row in rows]
    assert len(identities) == len(set(identities)), "Scan duplicated an entry"
    return pages


@pytest.mark.parametrize("op,counts", [
    ("scanThemes", (0, 1, 2, 3, 7, 16, 64, 81)),
    ("scanSongs", (0, 1, 2, 3, 5, 17, 128, 601)),
])
@pytest.mark.parametrize("variant", ["plain", "unicode"])
@pytest.mark.parametrize("page_size", [0, 400, 450])
def test_scan_pages_are_legal_and_complete(catalog_scan_exe, op, counts, variant, page_size):
    # Production defaults plus different divisions of the same catalog. Sizes
    # straddle page boundaries and the app's current fixed scan-loop limits.
    for count in counts:
        scan(catalog_scan_exe, catalog_fixture(op, count, variant, page_size))


@pytest.mark.parametrize("op", ["scanThemes", "scanSongs"])
def test_adjacent_scan_pages_cannot_fit_in_one_response(catalog_scan_exe, op):
    pages = scan(catalog_scan_exe, catalog_fixture(op, 7))
    key = "themes" if op == "scanThemes" else "songs"
    for first, second in zip(pages, pages[1:]):
        merged = copy.deepcopy(first)
        merged[key].extend(second[key])
        merged["hasMore"] = second["hasMore"]
        merged["nextCursor"] = second["nextCursor"]
        size = len(serialized(merged))
        # Count the response envelope only once, including the final hasMore
        # value. Equality also fits: avoid a needless page at exactly 512 bytes.
        assert size > ATT_VALUE_LIMIT, (
            f"{op} pages {first['cursor']} and {second['cursor']} combine into {size} bytes; "
            f"both fit in one {ATT_VALUE_LIMIT}-byte response"
        )


@pytest.mark.parametrize("op", ["scanThemes", "scanSongs"])
def test_nonfinal_scan_page_cannot_fit_next_entry(catalog_scan_exe, op):
    pages = scan(catalog_scan_exe, catalog_fixture(op, 7))
    key = "themes" if op == "scanThemes" else "songs"
    for first, second in zip(pages, pages[1:]):
        extended = copy.deepcopy(first)
        extended[key].append(second[key][0])
        extended["hasMore"] = second["hasMore"] or len(second[key]) > 1
        extended["nextCursor"] += 1
        size = len(serialized(extended))
        assert size > ATT_VALUE_LIMIT, (
            f"{op} page {first['cursor']} could include the next entry: "
            f"{size} bytes <= {ATT_VALUE_LIMIT}"
        )


@pytest.mark.parametrize("op,count", [
    ("scanThemes", 0), ("scanThemes", 1), ("scanThemes", 7), ("scanThemes", 64),
    ("scanThemes", 81),
    ("scanSongs", 0), ("scanSongs", 1), ("scanSongs", 7), ("scanSongs", 128),
    ("scanSongs", 601),
])
def test_app_consumes_all_firmware_scan_pages(catalog_scan_exe, repo_root, op, count):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required to exercise the real app scan functions.")
    request = catalog_fixture(op, count, "unicode")
    pages = scan(catalog_scan_exe, request)
    result = subprocess.run(
        [node, str(repo_root / "tests/catalog_scan_ui_test.js")],
        input=serialized(dict(op=op, theme=request["theme"], pages=pages,
                              expected=expected_rows(request))),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30,
    )
    assert result.returncode == 0, result.stdout.decode()


@pytest.mark.parametrize("character", ["a", "ש", "🌙", '"', "\\", "\n"])
def test_catalog_rejects_names_at_exact_encoded_byte_boundary(catalog_scan_exe, character):
    # Independently serialize worst-case envelopes. UTF-8 characters and JSON
    # escape sequences consume bytes, so a character-count limit is insufficient.
    themes = []
    expected_themes = []
    expected_songs = []
    for length in range(1, 360):
        name = character * length
        theme = dict(id="t", name=name, songs=[dict(file="a.wav", supported=True)])
        themes.append(theme)
        stats = dict(id="t", name=name, enabled=False, disabledByUser=False,
                     shuffle=False, special=False, canDisable=False, canSetDefault=False,
                     activeValid=2147483647, total=2147483647, errors=2147483647)
        envelope = dict(id=4294967295, ok=True, op="scanThemes", cursor=2147483647,
                        themes=[stats], nextCursor=2147483647, hasMore=False)
        song_header = dict(id=4294967295, ok=True, op="scanSongs", cursor=2147483647,
                           theme="t", name=name, themeEnabled=False, disabledByUser=False,
                           shuffle=False, errors=2147483647,
                           nextCursor=2147483647, hasMore=False)
        song = dict(file="a.wav", enabled=False, ok=True,
                    sizeBytes=4294967295, durationMs=4294967295)
        expected_themes.append(len(serialized(envelope)) <= 512 and
                               len(serialized({**song_header, "songs": [song]})) <= 512)

        filename = name + ".wav"
        theme = dict(id="t", name="T", songs=[dict(file=filename, supported=True)])
        themes.append(theme)
        song["file"] = filename
        song_header["name"] = "T"
        command = dict(id=4294967295, op="setSong", theme="t", file=filename, enabled=False)
        expected_songs.append(len(serialized({**song_header, "songs": [song]})) <= 512 and
                              len(serialized(command)) <= 383)
    result = subprocess.run([str(catalog_scan_exe)], input=serialized(dict(op="limits", themes=themes)),
                            stdout=subprocess.PIPE, check=True, timeout=10)
    result = json.loads(result.stdout.decode("utf-8", errors="strict"))
    assert [row["fits"] for row in result["themes"][::2]] == expected_themes
    assert [row["songs"][0] for row in result["themes"][1::2]] == expected_songs
    assert result["retainedThemes"] == sum(expected_themes) + len(expected_songs)
    assert result["retainedSongs"] == sum(expected_themes) + sum(expected_songs)
    assert "…" in result["warning"] and "�" not in result["warning"]
    assert len(serialized({"message": result["warning"]})) <= 512


@pytest.mark.parametrize("character", ["a", "ש", "🌙", '"', "\n"])
def test_theme_ids_fit_live_control_and_config_buffers(catalog_scan_exe, character):
    ids = [character * count for count in range(1, 80)]
    request = dict(op="limits", themes=[dict(id=value, name="T", songs=[]) for value in ids])
    result = subprocess.run([str(catalog_scan_exe)], input=serialized(request),
                            stdout=subprocess.PIPE, check=True, timeout=10)
    result = json.loads(result.stdout)
    expected = [len(value.encode()) <= 63 and len(serialized(value)) - 2 <= 126 for value in ids]
    assert [row["fits"] for row in result["themes"]] == expected
    assert result["retainedThemes"] == sum(expected)
