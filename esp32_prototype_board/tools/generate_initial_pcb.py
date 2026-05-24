#!/usr/bin/env python3
"""Generate the first Rev A PCB placement from the schematic netlist.

This is intentionally a placement script, not a router.  It imports the schematic
footprints and net assignments, then arranges the board according to the Rev A
placement decisions so routing can start from a known-good baseline.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess

import pcbnew


PROJECT_DIR = Path(__file__).resolve().parents[1]
PCB_PATH = PROJECT_DIR / "esp32_prototype_board.kicad_pcb"
SCH_PATH = PROJECT_DIR / "esp32_prototype_board.kicad_sch"
NETLIST_PATH = PROJECT_DIR / "esp32_prototype_board.net"
KICAD_CLI = Path("/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli")
KICAD_FOOTPRINTS = Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints")

BOARD_LEFT = 50.0
BOARD_TOP = 52.0
BOARD_RIGHT = 140.0
BOARD_BOTTOM = 117.0


@dataclass(frozen=True)
class Placement:
    x: float
    y: float
    rot: float = 0.0


PLACEMENTS: dict[str, Placement] = {
    # Left-edge power and USB entry
    "J1": Placement(53.65, 101.0, 90),
    "J2": Placement(56.0, 78.0, 90),
    "JP1": Placement(63.0, 89.0, 90),
    "U1": Placement(73.0, 101.0, 0),
    "U2": Placement(73.0, 83.0, 0),
    "R1": Placement(62.0, 96.0, 90),
    "R2": Placement(62.0, 99.0, 90),
    "R3": Placement(63.0, 106.0, 0),
    "D1": Placement(68.0, 106.0, 0),
    "C1": Placement(66.0, 82.0, 0),
    "C2": Placement(80.0, 83.0, 0),
    "C3": Placement(80.0, 88.0, 0),
    "C4": Placement(65.0, 103.5, 0),
    "C5": Placement(65.0, 108.0, 0),
    # ESP32 management
    "U3": Placement(95.0, 80.1, 0),
    "R4": Placement(82.0, 97.0, 0),
    "R5": Placement(82.0, 101.0, 0),
    "Q1": Placement(86.0, 97.0, 0),
    "Q2": Placement(86.0, 102.0, 0),
    "R6": Placement(83.0, 74.5, 0),
    "C6": Placement(89.0, 97.0, 0),
    "SW1": Placement(88.0, 109.0, 0),
    "R7": Placement(94.0, 97.0, 0),
    "SW2": Placement(98.0, 109.0, 0),
    "C7": Placement(106.0, 94.0, 0),
    "C8": Placement(106.0, 89.0, 0),
    "SJ1": Placement(97.0, 101.0, 0),
    "R10": Placement(101.0, 101.0, 0),
    "D2": Placement(105.0, 101.0, 0),
    # Right-edge microSD
    "J4": Placement(133.4, 72.0, 90),
    "R11": Placement(113.0, 72.0, 0),
    "R12": Placement(113.0, 75.0, 0),
    "R13": Placement(113.0, 78.0, 0),
    "R14": Placement(123.0, 62.0, 90),
    "R15": Placement(123.0, 65.0, 90),
    "R16": Placement(123.0, 68.0, 90),
    "R17": Placement(123.0, 71.0, 90),
    "R18": Placement(123.0, 74.0, 90),
    "C9": Placement(124.0, 81.5, 0),
    "C10": Placement(128.0, 81.5, 0),
    # Right/bottom audio module area
    "U4": Placement(111.0, 113.0, 90),
    "R24": Placement(105.0, 101.0, 90),
    "R25": Placement(108.0, 101.0, 90),
    "Q3": Placement(105.0, 106.0, 0),
    "C11": Placement(133.0, 100.0, 0),
    "C12": Placement(107.0, 111.0, 0),
    "C13": Placement(107.0, 114.0, 0),
    # Expansion headers
    "J6": Placement(91.0, 113.0, 90),
    "J7": Placement(61.0, 62.0, 0),
    "J8": Placement(60.5, 113.0, 90),
    "R19": Placement(66.0, 62.0, 90),
    "R20": Placement(66.0, 66.0, 90),
    # Test pads
    "TP1": Placement(67.0, 75.0, 0),
    "TP2": Placement(75.0, 75.0, 0),
    "TP3": Placement(83.0, 75.0, 0),
    "TP4": Placement(88.0, 94.0, 0),
    "TP5": Placement(96.0, 94.0, 0),
    "TP6": Placement(70.0, 110.0, 0),
    "TP7": Placement(76.0, 110.0, 0),
    "TP8": Placement(82.0, 110.0, 0),
    "TP9": Placement(102.0, 110.0, 0),
    "TP10": Placement(116.0, 84.0, 0),
    "TP11": Placement(120.0, 84.0, 0),
    "TP12": Placement(124.0, 84.0, 0),
    "TP13": Placement(128.0, 84.0, 0),
    "TP14": Placement(101.0, 94.0, 0),
    "TP15": Placement(101.0, 97.0, 0),
    "TP16": Placement(101.0, 100.0, 0),
    "TP17": Placement(101.0, 103.0, 0),
    "TP18": Placement(98.0, 104.0, 0),
}

MOUNTING_HOLES: dict[str, Placement] = {
    "H1": Placement(54.0, 56.0, 0),
    "H2": Placement(136.0, 56.0, 0),
    "H3": Placement(54.0, 113.0, 0),
    "H4": Placement(136.0, 113.0, 0),
}


def mm(value: float) -> int:
    return pcbnew.FromMM(value)


def vec(x: float, y: float) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I(mm(x), mm(y))


def export_netlist() -> None:
    subprocess.run(
        [str(KICAD_CLI), "sch", "export", "netlist", str(SCH_PATH), "-o", str(NETLIST_PATH)],
        check=True,
        cwd=PROJECT_DIR,
    )


def tokenize_sexp(text: str) -> list[str]:
    tokens: list[str] = []
    i = 0
    while i < len(text):
        c = text[i]
        if c.isspace():
            i += 1
        elif c in "()":
            tokens.append(c)
            i += 1
        elif c == '"':
            i += 1
            out: list[str] = []
            while i < len(text):
                if text[i] == "\\" and i + 1 < len(text):
                    out.append(text[i + 1])
                    i += 2
                elif text[i] == '"':
                    i += 1
                    break
                else:
                    out.append(text[i])
                    i += 1
            tokens.append("".join(out))
        else:
            start = i
            while i < len(text) and not text[i].isspace() and text[i] not in "()":
                i += 1
            tokens.append(text[start:i])
    return tokens


def parse_tokens(tokens: list[str], index: int = 0) -> tuple[list, int]:
    if tokens[index] != "(":
        raise ValueError(f"expected '(' at token {index}")
    index += 1
    out: list = []
    while index < len(tokens) and tokens[index] != ")":
        if tokens[index] == "(":
            child, index = parse_tokens(tokens, index)
            out.append(child)
        else:
            out.append(tokens[index])
            index += 1
    if index >= len(tokens):
        raise ValueError("unterminated s-expression")
    return out, index + 1


def children(node: list, tag: str) -> list[list]:
    return [item for item in node[1:] if isinstance(item, list) and item and item[0] == tag]


def child_text(node: list, tag: str) -> str | None:
    for item in children(node, tag):
        if len(item) >= 2 and isinstance(item[1], str):
            return item[1]
    return None


def parse_netlist() -> tuple[dict[str, dict[str, str]], dict[tuple[str, str], str]]:
    root, end = parse_tokens(tokenize_sexp(NETLIST_PATH.read_text()))
    if end == 0 or root[0] != "export":
        raise ValueError("unexpected netlist format")

    components_node = children(root, "components")[0]
    nets_node = children(root, "nets")[0]

    components: dict[str, dict[str, str]] = {}
    for comp in children(components_node, "comp"):
        ref = child_text(comp, "ref")
        value = child_text(comp, "value") or ""
        footprint = child_text(comp, "footprint") or ""
        if ref is None or not footprint:
            raise ValueError(f"component missing ref/footprint: {comp!r}")
        components[ref] = {"value": value, "footprint": footprint}

    pin_nets: dict[tuple[str, str], str] = {}
    for net in children(nets_node, "net"):
        name = child_text(net, "name")
        if not name:
            continue
        for node in children(net, "node"):
            ref = child_text(node, "ref")
            pin = child_text(node, "pin")
            if ref and pin:
                pin_nets[(ref, pin)] = name

    return components, pin_nets


def footprint_lib_path(lib: str) -> Path:
    path = KICAD_FOOTPRINTS / f"{lib}.pretty"
    if not path.exists():
        raise FileNotFoundError(f"footprint library not found: {path}")
    return path


def load_footprint(footprint_id: str) -> pcbnew.FOOTPRINT:
    lib, name = footprint_id.split(":", 1)
    fp = pcbnew.FootprintLoad(str(footprint_lib_path(lib)), name)
    if fp is None:
        raise FileNotFoundError(f"footprint not found: {footprint_id}")
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    return fp


def add_or_get_net(board: pcbnew.BOARD, name: str) -> pcbnew.NETINFO_ITEM:
    found = board.FindNet(name)
    if found is not None:
        return found
    net = pcbnew.NETINFO_ITEM(board, name)
    board.Add(net)
    return board.FindNet(name)


def clear_generated_items(board: pcbnew.BOARD) -> None:
    for fp in list(board.GetFootprints()):
        board.Delete(fp)
    for track in list(board.GetTracks()):
        board.Delete(track)
    for zone in list(board.Zones()):
        board.Delete(zone)
    for drawing in list(board.GetDrawings()):
        board.Delete(drawing)


def add_rect(board: pcbnew.BOARD, start: tuple[float, float], end: tuple[float, float], layer: int, width: float = 0.15) -> None:
    shape = pcbnew.PCB_SHAPE(board)
    shape.SetShape(pcbnew.SHAPE_T_RECT)
    shape.SetStart(vec(*start))
    shape.SetEnd(vec(*end))
    shape.SetLayer(layer)
    shape.SetWidth(mm(width))
    board.Add(shape)


def add_text(
    board: pcbnew.BOARD,
    text: str,
    x: float,
    y: float,
    layer: int,
    size: float = 1.0,
    rot: float = 0,
) -> None:
    item = pcbnew.PCB_TEXT(board)
    item.SetText(text)
    item.SetPosition(vec(x, y))
    item.SetTextSize(vec(size, size))
    item.SetTextThickness(mm(max(size * 0.12, 0.1)))
    item.SetLayer(layer)
    item.SetTextAngleDegrees(rot)
    board.Add(item)


def add_board_drawings(board: pcbnew.BOARD) -> None:
    add_rect(board, (BOARD_LEFT, BOARD_TOP), (BOARD_RIGHT, BOARD_BOTTOM), pcbnew.Edge_Cuts)
    add_rect(board, (70.75, BOARD_TOP), (119.25, 73.7), pcbnew.Dwgs_User, width=0.1)
    add_rect(board, (109.0, 94.0), (130.0, 114.5), pcbnew.Dwgs_User, width=0.1)

    add_text(board, "ESP32 antenna keepout: no copper, traces, parts, screws, or wires", 72.0, 56.0, pcbnew.Dwgs_User, 1.0)
    add_text(board, "MAX98357A module body clearance", 110.0, 97.0, pcbnew.Dwgs_User, 0.9)
    add_text(board, "Rev A first placement: 90mm x 65mm", 95.0, 116.0, pcbnew.Dwgs_User, 1.0)

    add_text(board, "USB-C", 57.8, 104.5, pcbnew.F_SilkS, 1.0)
    add_text(board, "EXT 5V\n+  GND", 58.5, 73.0, pcbnew.F_SilkS, 0.9)
    add_text(board, "5V SEL", 64.0, 84.0, pcbnew.F_SilkS, 0.8)
    add_text(board, "SD CARD", 127.0, 61.0, pcbnew.F_SilkS, 1.0)
    add_text(board, "AUDIO MODULE", 112.0, 94.0, pcbnew.F_SilkS, 0.9)
    add_text(board, "J6 SPI", 93.0, 108.0, pcbnew.F_SilkS, 0.8)
    add_text(board, "J7 I2C", 57.0, 70.5, pcbnew.F_SilkS, 0.8)


def add_schematic_footprints(board: pcbnew.BOARD, components: dict[str, dict[str, str]], pin_nets: dict[tuple[str, str], str]) -> None:
    net_objs = {net_name: add_or_get_net(board, net_name) for net_name in sorted(set(pin_nets.values()))}

    missing = sorted(set(components) - set(PLACEMENTS))
    if missing:
        raise ValueError(f"missing placement(s): {', '.join(missing)}")

    for ref in sorted(components, key=lambda r: (r.rstrip("0123456789"), int("".join(ch for ch in r if ch.isdigit()) or 0), r)):
        info = components[ref]
        fp = load_footprint(info["footprint"])
        fp.SetReference(ref)
        fp.SetValue(info["value"])
        placement = PLACEMENTS[ref]
        fp.SetPosition(vec(placement.x, placement.y))
        fp.SetOrientationDegrees(placement.rot)

        for pad in fp.Pads():
            net_name = pin_nets.get((ref, pad.GetNumber()))
            if net_name:
                pad.SetNet(net_objs[net_name])

        board.Add(fp)


def add_mounting_holes(board: pcbnew.BOARD) -> None:
    for ref, placement in MOUNTING_HOLES.items():
        fp = load_footprint("MountingHole:MountingHole_3.2mm_M3")
        fp.SetReference(ref)
        fp.SetValue("M3")
        fp.SetPosition(vec(placement.x, placement.y))
        fp.SetOrientationDegrees(placement.rot)
        board.Add(fp)


def main() -> int:
    if not KICAD_CLI.exists():
        raise FileNotFoundError(f"kicad-cli not found: {KICAD_CLI}")

    export_netlist()
    components, pin_nets = parse_netlist()

    board = pcbnew.LoadBoard(str(PCB_PATH))
    clear_generated_items(board)
    add_board_drawings(board)
    add_schematic_footprints(board, components, pin_nets)
    add_mounting_holes(board)
    pcbnew.SaveBoard(str(PCB_PATH), board)
    print(f"Wrote {PCB_PATH}")
    print(f"Imported {len(components)} schematic footprints plus {len(MOUNTING_HOLES)} mounting holes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
