#!/usr/bin/env python3
"""Turn a memtrack serial capture into a heap report.

Reads the `[Mem] site <bytes> <count> <pc0> <pc1> <pc2>` lines printed by the
sweetyaar-memtrack firmware (see firmware/esp32/src/MemProbe.h), resolves the
return addresses against the build's ELF and link map, and prints live heap
bytes by library and by function.

    memprobe_report.py <serial.log> [--section <label>] [--diff <label>]
                       [--build <dir>] [--top N]

A capture may hold several `sites-begin <label>` sections; the last one is used
unless --section names another. --diff prints what grew between two sections.
"""
import argparse
import bisect
import collections
import pathlib
import re
import subprocess

TOOLS = pathlib.Path.home() / ".platformio/packages/toolchain-xtensa-esp32/bin"
# Allocation helpers: a block belongs to whoever called these.
GENERIC = re.compile(
    r"^(__wrap_|malloc$|calloc$|realloc$|_malloc_r|_calloc_r|_realloc_r|operator new|"
    r"pvPortMalloc|heap_caps_|xQueue|xSemaphore|xRingbuffer|prvInitialise|xTaskCreate|"
    r"osi_|fixed_queue_|list_new|list_append|list_prepend|hash_map_|pkt_queue|"
    r"std::|__gnu_cxx|_Znwj|_Znaj|String::|FreeRTOS::|esp_ringbuf|"
    r"multi_heap|malloc_internal|semphr_|mutex_create|queue_create|.*_wrapper$|"
    r"btc_transfer_context|future_new|osi_alarm|allocator_|config_new|section_new|entry_new)")


def sections(text):
    found = collections.OrderedDict()
    label = None
    for line in text.splitlines():
        match = re.search(r"\[Mem\] sites-begin (\S+)", line)
        if match:
            label = match.group(1)
            while label in found:
                label += "'"
            found[label] = []
            continue
        if "[Mem] sites-end" in line:
            label = None
            continue
        match = re.search(r"\[Mem\] site (\d+) (\d+) ([0-9a-f]{8}) ([0-9a-f]{8}) ([0-9a-f]{8})", line)
        if match and label is not None:
            found[label].append((int(match.group(1)), int(match.group(2)),
                                 tuple(int(x, 16) for x in match.group(3, 4, 5))))
    return found


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("log")
    parser.add_argument("--section")
    parser.add_argument("--diff", help="baseline section; print growth to --section")
    parser.add_argument("--build", default="firmware/esp32/.pio/build/sweetyaar-memtrack")
    parser.add_argument("--top", type=int, default=45)
    parser.add_argument("--detail", help="list every call chain whose owner contains this text")
    args = parser.parse_args()

    found = sections(pathlib.Path(args.log).read_text(errors="ignore"))
    if not found:
        raise SystemExit("no [Mem] site lines in the capture")
    label = args.section or list(found)[-1]
    sites = found[label]

    build = pathlib.Path(args.build)
    map_text = (build / "firmware.map").read_text(errors="ignore")
    spans, names = [], []
    for match in re.finditer(r"^\s+0x([0-9a-f]{8,16})\s+0x([0-9a-f]+)\s+(\S+)$", map_text, re.M):
        start, size, where = int(match.group(1), 16), int(match.group(2), 16), match.group(3)
        if size and 0x40000000 <= start < 0x40500000 and (".a(" in where or where.endswith(".o")):
            archive = re.sub(r"\(.*", "", where).split("/")[-1]
            spans.append((start, start + size, archive))
    spans.sort()
    starts = [span[0] for span in spans]

    def archive(pc):
        index = bisect.bisect_right(starts, pc) - 1
        return spans[index][2] if index >= 0 and pc < spans[index][1] else "?"

    pcs = sorted({pc for _, _, chain in sites for pc in chain if pc} |
                 {pc for other in found.values() for _, _, chain in other for pc in chain if pc})
    out = subprocess.run([str(TOOLS / "xtensa-esp32-elf-addr2line"), "-f", "-C", "-e",
                          str(build / "firmware.elf")] + [hex(pc) for pc in pcs],
                         capture_output=True, text=True, check=True).stdout.splitlines()
    function = {pc: out[2 * i] for i, pc in enumerate(pcs)}

    def owner(chain):
        for pc in chain:
            if pc and not GENERIC.match(function.get(pc, "?")):
                return archive(pc), function[pc]
        pc = next((pc for pc in chain if pc), 0)
        return (archive(pc), function.get(pc, "?")) if pc else ("?", "?")

    def tally(items):
        by_lib, by_fn = collections.Counter(), collections.Counter()
        count_fn = collections.Counter()
        for size, count, chain in items:
            lib, fn = owner(chain)
            by_lib[lib] += size
            by_fn[(lib, fn)] += size
            count_fn[(lib, fn)] += count
        return by_lib, by_fn, count_fn

    if args.detail:
        for size, count, chain in sorted(sites, reverse=True):
            if args.detail in owner(chain)[1] or args.detail in owner(chain)[0]:
                names = " <- ".join(function.get(pc, "?") for pc in chain if pc)
                print(f"{size:8d}  x{count:<4d} {names}")
        return
    by_lib, by_fn, count_fn = tally(sites)
    title = f"live heap at '{label}'"
    if args.diff:
        base_lib, base_fn, base_count = tally(found[args.diff])
        by_lib = collections.Counter({k: by_lib[k] - base_lib[k] for k in set(by_lib) | set(base_lib)})
        by_fn = collections.Counter({k: by_fn[k] - base_fn[k] for k in set(by_fn) | set(base_fn)})
        count_fn = collections.Counter({k: count_fn[k] - base_count[k] for k in set(count_fn) | set(base_count)})
        title = f"heap growth from '{args.diff}' to '{label}'"
    total = sum(by_lib.values())
    print(f"== {title}: {total} bytes tracked (sections: {', '.join(found)})")
    print("-- by library")
    for lib, size in sorted(by_lib.items(), key=lambda item: -abs(item[1])):
        if size:
            print(f"{size:8d}  {lib}")
    print(f"-- by function (top {args.top})")
    for (lib, fn), size in sorted(by_fn.items(), key=lambda item: -abs(item[1]))[:args.top]:
        if size:
            print(f"{size:8d}  x{count_fn[(lib, fn)]:<4d} {lib:28s} {fn}")


if __name__ == "__main__":
    main()
