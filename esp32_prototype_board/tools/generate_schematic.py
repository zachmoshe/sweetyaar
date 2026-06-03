#!/usr/bin/env python3
"""Generate the Rev A KiCad schematic.

The goal of this generator is a readable, full-sheet Rev A schematic with
project-local symbols. Exact manufacturer part numbers are still selected in the
BOM/quote pass, but all functional nets are present here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import uuid


OUT = Path(__file__).resolve().parents[1] / "esp32_prototype_board.kicad_sch"
PROJECT_DIR = OUT.parent
LOCAL_SYM_LIB = PROJECT_DIR / "sweetyaar_rev_a.kicad_sym"
SYM_LIB_TABLE = PROJECT_DIR / "sym-lib-table"
FP_LIB_TABLE = PROJECT_DIR / "fp-lib-table"


def uid() -> str:
    return str(uuid.uuid4())


def esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def snap(v: float, grid: float = 1.27) -> float:
    return round(v / grid) * grid


def effects(size: float = 1.27, hide: bool = False, justify: str | None = None) -> str:
    hidden = "\n\t\t\t(hide yes)" if hide else ""
    just = f"\n\t\t\t(justify {justify})" if justify else ""
    return (
        f"{hidden}\n\t\t\t(effects\n\t\t\t\t(font\n"
        f"\t\t\t\t\t(size {size} {size})\n\t\t\t\t)\n{just}\t\t\t)"
    )


@dataclass(frozen=True)
class Pin:
    number: str
    name: str
    side: str
    y: float
    kind: str = "passive"


@dataclass
class SymDef:
    lib_id: str
    width: float
    height: float
    pins: list[Pin]

    def endpoint(self, number: str, at_x: float, at_y: float) -> tuple[float, float, str]:
        for p in self.pins:
            # KiCad symbol-local Y is inverted relative to sheet Y.
            sheet_y = at_y - p.y
            if p.number == number:
                if p.side == "L":
                    return at_x - self.width / 2 - 2.54, sheet_y, "L"
                if p.side == "R":
                    return at_x + self.width / 2 + 2.54, sheet_y, "R"
                raise ValueError(f"unsupported side {p.side}")
        raise KeyError((self.lib_id, number))


SYMS: dict[str, SymDef] = {}


def add_symbol(lib_id: str, width: float, height: float, left: list[tuple[str, str]], right: list[tuple[str, str]]) -> None:
    width = snap(width, 2.54)
    pitch = 15.24
    height = max(snap(height, 2.54), snap((max(len(left), len(right)) - 1) * pitch + 10.16, 2.54))
    pins: list[Pin] = []

    def ys(count: int) -> list[float]:
        if count == 1:
            return [0.0]
        # Keep labels far enough apart that their text bounding boxes never
        # touch neighboring wires. KiCad labels are electrical objects.
        return [snap((i - (count - 1) / 2) * pitch, 1.27) for i in range(count)]

    for (number, name), y in zip(left, ys(len(left))):
        pins.append(Pin(number, name, "L", y))
    for (number, name), y in zip(right, ys(len(right))):
        pins.append(Pin(number, name, "R", y))
    SYMS[lib_id] = SymDef(lib_id, width, height, pins)


def lib_symbol_block(sym: SymDef, library_file: bool = False) -> str:
    lines: list[str] = []
    base = sym.lib_id.split(":")[-1]
    top_name = base if library_file else sym.lib_id
    prefix = "\t" if library_file else "\t\t"
    lines.append(f'{prefix}(symbol "{esc(top_name)}"')
    lines.append(f"{prefix}\t(pin_names\n{prefix}\t\t(offset 1.016)\n{prefix}\t)")
    lines.append(f"{prefix}\t(exclude_from_sim no)")
    lines.append(f"{prefix}\t(in_bom yes)")
    lines.append(f"{prefix}\t(on_board yes)")
    lines.append(f'{prefix}\t(property "Reference" "U"')
    lines.append(f"{prefix}\t\t(at 0 {snap(-sym.height / 2 - 3.81):.3f} 0)")
    lines.append(f"{prefix}\t\t{effects()}")
    lines.append(f"{prefix}\t)")
    lines.append(f'{prefix}\t(property "Value" "{esc(base)}"')
    lines.append(f"{prefix}\t\t(at 0 {snap(sym.height / 2 + 3.81):.3f} 0)")
    lines.append(f"{prefix}\t\t{effects()}")
    lines.append(f"{prefix}\t)")
    lines.append(f'{prefix}\t(property "Footprint" ""')
    lines.append(f"{prefix}\t\t(at 0 0 0)")
    lines.append(f"{prefix}\t\t{effects(hide=True)}")
    lines.append(f"{prefix}\t)")
    lines.append(f'{prefix}\t(property "Datasheet" "~"')
    lines.append(f"{prefix}\t\t(at 0 0 0)")
    lines.append(f"{prefix}\t\t{effects(hide=True)}")
    lines.append(f"{prefix}\t)")
    lines.append(f'{prefix}\t(property "Description" "Project-local Rev A schematic symbol"')
    lines.append(f"{prefix}\t\t(at 0 0 0)")
    lines.append(f"{prefix}\t\t{effects(hide=True)}")
    lines.append(f"{prefix}\t)")
    lines.append(f'{prefix}\t(symbol "{esc(base)}_0_1"')
    lines.append(f"{prefix}\t\t(rectangle")
    lines.append(f"{prefix}\t\t\t(start {-sym.width / 2:.3f} {-sym.height / 2:.3f})")
    lines.append(f"{prefix}\t\t\t(end {sym.width / 2:.3f} {sym.height / 2:.3f})")
    lines.append(f"{prefix}\t\t\t(stroke\n{prefix}\t\t\t\t(width 0.254)\n{prefix}\t\t\t\t(type default)\n{prefix}\t\t\t)")
    lines.append(f"{prefix}\t\t\t(fill\n{prefix}\t\t\t\t(type background)\n{prefix}\t\t\t)")
    lines.append(f"{prefix}\t\t)")
    lines.append(f"{prefix}\t)")
    lines.append(f'{prefix}\t(symbol "{esc(base)}_1_1"')
    for p in sym.pins:
        if p.side == "L":
            at_x = -sym.width / 2 - 2.54
            rot = 0
        else:
            at_x = sym.width / 2 + 2.54
            rot = 180
        lines.append(f"{prefix}\t\t(pin {p.kind} line")
        lines.append(f"{prefix}\t\t\t(at {at_x:.3f} {p.y:.3f} {rot})")
        lines.append(f"{prefix}\t\t\t(length 2.54)")
        lines.append(f'{prefix}\t\t\t(name "{esc(p.name)}"')
        lines.append(f"{prefix}\t\t\t\t(effects\n{prefix}\t\t\t\t\t(font\n{prefix}\t\t\t\t\t\t(size 1.27 1.27)\n{prefix}\t\t\t\t\t)\n{prefix}\t\t\t\t)")
        lines.append(f"{prefix}\t\t\t)")
        lines.append(f'{prefix}\t\t\t(number "{esc(p.number)}"')
        lines.append(f"{prefix}\t\t\t\t(effects\n{prefix}\t\t\t\t\t(font\n{prefix}\t\t\t\t\t\t(size 1.27 1.27)\n{prefix}\t\t\t\t\t)\n{prefix}\t\t\t\t)")
        lines.append(f"{prefix}\t\t\t)")
        lines.append(f"{prefix}\t\t)")
    lines.append(f"{prefix}\t)")
    lines.append(f"{prefix})")
    return "\n".join(lines)


def prop(name: str, value: str, x: float, y: float, hide: bool = False) -> str:
    return (
        f'\t\t(property "{esc(name)}" "{esc(value)}"\n'
        f"\t\t\t(at {x:.3f} {y:.3f} 0)\n"
        f"\t\t\t(show_name no)\n"
        f"\t\t\t(do_not_autoplace no)\n"
        f"\t\t\t{effects(hide=hide)}\n"
        f"\t\t)"
    )


def wire_label(x1: float, y1: float, side: str, net: str, span: float = 5.08) -> str:
    x1, y1 = snap(x1), snap(y1)
    if side == "L":
        x2, y2, rot, just = snap(x1 - span), y1, 0, "left bottom"
    else:
        x2, y2, rot, just = snap(x1 + span), y1, 180, "right bottom"
    return (
        "\t(wire\n"
        f"\t\t(pts\n\t\t\t(xy {x1:.3f} {y1:.3f}) (xy {x2:.3f} {y2:.3f})\n\t\t)\n"
        "\t\t(stroke\n\t\t\t(width 0)\n\t\t\t(type solid)\n\t\t)\n"
        f'\t\t(uuid "{uid()}")\n'
        "\t)\n"
        f'\t(label "{esc(net)}"\n'
        f"\t\t(at {x2:.3f} {y2:.3f} {rot})\n"
        "\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 0.5 0.5)\n\t\t\t)\n"
        f"\t\t\t(justify {just})\n\t\t)\n"
        f'\t\t(uuid "{uid()}")\n'
        "\t)"
    )


def no_connect(x: float, y: float) -> str:
    x, y = snap(x), snap(y)
    return f'\t(no_connect\n\t\t(at {x:.3f} {y:.3f})\n\t\t(uuid "{uid()}")\n\t)'


SCHEM_ITEMS: list[str] = []
SECTIONS: list[str] = []


def add_note(text: str, x: float, y: float, size: float = 1.27) -> None:
    x, y = snap(x), snap(y)
    SCHEM_ITEMS.append(
        f'\t(text "{esc(text)}"\n'
        "\t\t(exclude_from_sim no)\n"
        f"\t\t(at {x:.3f} {y:.3f} 0)\n"
        f"\t\t(effects\n\t\t\t(font\n\t\t\t\t(size {size} {size})\n\t\t\t)\n\t\t\t(justify left)\n\t\t)\n"
        f'\t\t(uuid "{uid()}")\n'
        "\t)"
    )


def add_section(title: str, x1: float, y1: float, x2: float, y2: float) -> None:
    x1, y1, x2, y2 = snap(x1), snap(y1), snap(x2), snap(y2)
    SECTIONS.append(
        "\t(polyline\n"
        f"\t\t(pts\n\t\t\t(xy {x1:.3f} {y1:.3f}) (xy {x2:.3f} {y1:.3f}) (xy {x2:.3f} {y2:.3f}) (xy {x1:.3f} {y2:.3f}) (xy {x1:.3f} {y1:.3f})\n\t\t)\n"
        "\t\t(stroke\n\t\t\t(width 0)\n\t\t\t(type dash)\n\t\t)\n"
        f'\t\t(uuid "{uid()}")\n'
        "\t)"
    )
    add_note(title, x1 + 2.0, y1 + 5.0, size=1.5)


def add_instance(
    lib_id: str,
    ref: str,
    value: str,
    footprint: str,
    x: float,
    y: float,
    conns: dict[str, str | None],
    dnp: bool = False,
) -> None:
    x, y = snap(x), snap(y)
    sym = SYMS[lib_id]
    lines: list[str] = []
    lines.append("\t(symbol")
    lines.append(f'\t\t(lib_id "{esc(lib_id)}")')
    lines.append(f"\t\t(at {x:.3f} {y:.3f} 0)")
    lines.append("\t\t(unit 1)")
    lines.append("\t\t(exclude_from_sim no)")
    lines.append("\t\t(in_bom yes)")
    lines.append("\t\t(on_board yes)")
    lines.append(f"\t\t(dnp {'yes' if dnp else 'no'})")
    lines.append(f'\t\t(uuid "{uid()}")')
    lines.append(prop("Reference", ref, x - sym.width / 2, y - sym.height / 2 - 3.0))
    lines.append(prop("Value", value, x - sym.width / 2, y + sym.height / 2 + 3.0))
    lines.append(prop("Footprint", footprint, x, y, hide=True))
    lines.append(prop("Datasheet", "~", x, y, hide=True))
    lines.append(prop("Description", "Rev A generated schematic item", x, y, hide=True))
    for p in sym.pins:
        lines.append(f'\t\t(pin "{esc(p.number)}"\n\t\t\t(uuid "{uid()}")\n\t\t)')
    lines.append("\t)")
    SCHEM_ITEMS.append("\n".join(lines))
    for p in sym.pins:
        net = conns.get(p.number, None)
        px, py, side = sym.endpoint(p.number, x, y)
        if net is None:
            SCHEM_ITEMS.append(no_connect(px, py))
        else:
            SCHEM_ITEMS.append(wire_label(px, py, side, net))


def define_symbols() -> None:
    add_symbol(
        "SweetYaar:ESP32_WROOM_32E_REVA",
        45.0,
        105.0,
        [
            ("1", "GND1"),
            ("2", "3V3"),
            ("3", "EN"),
            ("4", "GPIO36/SENSOR_VP"),
            ("5", "GPIO39/SENSOR_VN"),
            ("6", "GPIO34"),
            ("7", "GPIO35"),
            ("8", "GPIO32"),
            ("9", "GPIO33"),
            ("10", "GPIO25"),
            ("11", "GPIO26"),
            ("12", "GPIO27"),
            ("13", "GPIO14"),
            ("14", "GPIO12"),
            ("15", "GND2"),
            ("16", "GPIO13"),
            ("17", "NC/SD2"),
            ("18", "NC/SD3"),
            ("19", "NC/CMD"),
            ("20", "NC/CLK"),
        ],
        [
            ("21", "NC/SD0"),
            ("22", "NC/SD1"),
            ("23", "GPIO15"),
            ("24", "GPIO2"),
            ("25", "GPIO0"),
            ("26", "GPIO4"),
            ("27", "GPIO16"),
            ("28", "GPIO17"),
            ("29", "GPIO5"),
            ("30", "GPIO18"),
            ("31", "GPIO19"),
            ("32", "NC"),
            ("33", "GPIO21"),
            ("34", "RXD0/GPIO3"),
            ("35", "TXD0/GPIO1"),
            ("36", "GPIO22"),
            ("37", "GPIO23"),
            ("38", "GND3"),
            ("39", "P_GND"),
        ],
    )
    add_symbol(
        "SweetYaar:USB_C_USB2_14P",
        35.0,
        70.0,
        [
            ("A1", "GND"),
            ("A4", "VBUS"),
            ("A5", "CC1"),
            ("A6", "D+"),
            ("A7", "D-"),
            ("A8", "SBU1"),
            ("A9", "VBUS"),
            ("A12", "GND"),
            ("SH", "SHIELD"),
        ],
        [
            ("B1", "GND"),
            ("B4", "VBUS"),
            ("B5", "CC2"),
            ("B6", "D+"),
            ("B7", "D-"),
            ("B8", "SBU2"),
            ("B9", "VBUS"),
            ("B12", "GND"),
        ],
    )
    add_symbol(
        "SweetYaar:CH340C",
        35.0,
        65.0,
        [
            ("1", "GND"),
            ("4", "V3"),
            ("5", "UD+"),
            ("6", "UD-"),
            ("7", "NC"),
            ("8", "NC"),
            ("15", "R232"),
            ("16", "VCC"),
        ],
        [
            ("2", "TXD"),
            ("3", "RXD"),
            ("9", "CTS"),
            ("10", "DSR"),
            ("11", "RI"),
            ("12", "DCD"),
            ("13", "DTR"),
            ("14", "RTS"),
        ],
    )
    add_symbol("SweetYaar:AP2112K_3V3", 25.0, 40.0, [("1", "VIN"), ("2", "GND"), ("3", "EN")], [("4", "NC"), ("5", "VOUT")])
    add_symbol("SweetYaar:MICRO_SD_SPI", 35.0, 55.0, [("1", "DAT2"), ("2", "DAT3/CS"), ("3", "CMD/MOSI"), ("4", "VDD"), ("5", "CLK"), ("6", "VSS")], [("7", "DAT0/MISO"), ("8", "DAT1"), ("SH", "SHIELD")])
    add_symbol("SweetYaar:MAX98357A_MODULE", 38.0, 45.0, [("1", "LRC/WS"), ("2", "BCLK"), ("3", "DIN"), ("4", "GAIN")], [("5", "SD/MODE"), ("6", "GND"), ("7", "VIN")])
    add_symbol("SweetYaar:CONN_01X02", 18.0, 12.0, [("1", "1")], [("2", "2")])
    add_symbol("SweetYaar:CONN_01X03", 18.0, 18.0, [("1", "1"), ("2", "2")], [("3", "3")])
    add_symbol("SweetYaar:CONN_01X04", 22.0, 25.0, [("1", "1"), ("2", "2")], [("3", "3"), ("4", "4")])
    add_symbol("SweetYaar:CONN_01X08", 26.0, 50.0, [("1", "1"), ("2", "2"), ("3", "3"), ("4", "4")], [("5", "5"), ("6", "6"), ("7", "7"), ("8", "8")])
    add_symbol("SweetYaar:CONN_01X12", 30.0, 75.0, [("1", "1"), ("2", "2"), ("3", "3"), ("4", "4"), ("5", "5"), ("6", "6")], [("7", "7"), ("8", "8"), ("9", "9"), ("10", "10"), ("11", "11"), ("12", "12")])
    add_symbol("SweetYaar:R", 14.0, 9.0, [("1", "1")], [("2", "2")])
    add_symbol("SweetYaar:C", 14.0, 9.0, [("1", "1")], [("2", "2")])
    add_symbol("SweetYaar:LED", 14.0, 9.0, [("1", "A")], [("2", "K")])
    add_symbol("SweetYaar:SW_PUSH", 14.0, 9.0, [("1", "A")], [("2", "B")])
    add_symbol("SweetYaar:JUMPER_2", 14.0, 9.0, [("1", "A")], [("2", "B")])
    add_symbol("SweetYaar:SW_DPDT_PWR", 18.0, 18.0, [("2", "COM1"), ("1", "A1"), ("4", "A2")], [("3", "B1"), ("5", "COM2"), ("6", "B2")])
    add_symbol("SweetYaar:SW_DPDT_ONOFF", 18.0, 18.0, [("1", "A1"), ("3", "B1"), ("4", "A2")], [("2", "COM1"), ("5", "COM2"), ("6", "B2")])
    add_symbol("SweetYaar:NPN_BEC", 16.0, 18.0, [("1", "B")], [("2", "E"), ("3", "C")])
    add_symbol("SweetYaar:TESTPOINT", 12.0, 8.0, [("1", "TP")], [])


def add_parts() -> None:
    add_section("USB-C + 5V power entry", 10, 15, 145, 180)
    add_section("USB-UART + auto program/reset", 10, 195, 145, 380)
    add_section("ESP32-WROOM-32E core", 150, 15, 280, 380)
    add_section("microSD SPI", 290, 15, 418, 185)
    add_section("I2S audio amp", 290, 200, 418, 380)
    add_section("Expansion headers + test pads", 10, 395, 418, 570)

    add_note("USB-C is sink-only 5V. No USB-PD negotiation.", 18, 168, 1.1)
    add_note("Auto-reset topology follows Espressif DevKitC DTR/RTS -> EN/GPIO0 behavior.", 18, 368, 1.1)
    add_note("GPIO12 intentionally left unconnected: strap pin can break flash boot if pulled high.", 158, 368, 1.1)
    add_note("Use one common GND. USB monitor and external PSU share ground.", 18, 560, 1.1)

    # Power entry
    add_instance("SweetYaar:USB_C_USB2_14P", "J1", "USB-C USB2 sink", "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12", 36, 95, {
        "A1": "GND", "A4": "USB_VBUS", "A5": "USB_CC1", "A6": "USB_DP", "A7": "USB_DN", "A8": None, "A9": "USB_VBUS", "A12": "GND", "SH": "GND",
        "B1": "GND", "B4": "USB_VBUS", "B5": "USB_CC2", "B6": "USB_DP", "B7": "USB_DN", "B8": None, "B9": "USB_VBUS", "B12": "GND",
    })
    add_instance("SweetYaar:R", "R1", "5.1k", "Resistor_SMD:R_0805_2012Metric", 90, 42, {"1": "USB_CC1", "2": "GND"})
    add_instance("SweetYaar:R", "R2", "5.1k", "Resistor_SMD:R_0805_2012Metric", 90, 58, {"1": "USB_CC2", "2": "GND"})
    add_instance("SweetYaar:CONN_01X02", "J2", "EXT 5V IN", "TerminalBlock:TerminalBlock_MaiXu_MX126-5.0-02P_1x02_P5.00mm", 95, 86, {"1": "EXT_5V", "2": "GND"})
    add_instance("SweetYaar:SW_DPDT_PWR", "JP1", "5V source switch", "SweetYaar:SW-SMD_MS-22D28-G020", 95, 118, {"1": "USB_VBUS", "2": "5V_SYS", "3": "EXT_5V", "4": None, "5": None, "6": None})
    add_instance("SweetYaar:AP2112K_3V3", "U2", "AP2112K-3.3", "Package_TO_SOT_SMD:SOT-23-5", 122, 50, {"1": "5V_SYS", "2": "GND", "3": "5V_SYS", "4": None, "5": "3V3"})
    add_instance("SweetYaar:C", "C1", "22uF", "Capacitor_SMD:C_0805_2012Metric", 122, 82, {"1": "5V_SYS", "2": "GND"})
    add_instance("SweetYaar:C", "C14", "100nF", "Capacitor_SMD:C_0805_2012Metric", 122, 151, {"1": "5V_SYS", "2": "GND"})
    add_instance("SweetYaar:C", "C2", "22uF", "Capacitor_SMD:C_0805_2012Metric", 122, 105, {"1": "3V3", "2": "GND"})
    add_instance("SweetYaar:C", "C3", "100nF", "Capacitor_SMD:C_0805_2012Metric", 122, 128, {"1": "3V3", "2": "GND"})
    add_instance("SweetYaar:R", "R3", "2.2k", "Resistor_SMD:R_0805_2012Metric", 70, 155, {"1": "5V_SYS", "2": "LED_5V_A"})
    add_instance("SweetYaar:LED", "D1", "5V PWR", "LED_SMD:LED_0805_2012Metric", 100, 155, {"1": "LED_5V_A", "2": "GND"})

    # USB UART and reset/boot
    add_instance("SweetYaar:CH340C", "U1", "CH340C", "Package_SO:SOIC-16_3.9x9.9mm_P1.27mm", 45, 285, {
        "1": "GND", "4": "3V3", "5": "USB_DP", "6": "USB_DN", "7": None, "8": None, "15": "GND", "16": "3V3",
        "2": "UART0_RX", "3": "UART0_TX", "9": None, "10": None, "11": None, "12": None, "13": "USB_DTR", "14": "USB_RTS",
    })
    add_instance("SweetYaar:C", "C4", "100nF", "Capacitor_SMD:C_0805_2012Metric", 87, 218, {"1": "3V3", "2": "GND"})
    add_instance("SweetYaar:C", "C5", "100nF", "Capacitor_SMD:C_0805_2012Metric", 87, 240, {"1": "3V3", "2": "GND"})
    add_instance("SweetYaar:R", "R4", "10k", "Resistor_SMD:R_0805_2012Metric", 82, 275, {"1": "USB_DTR", "2": "AUTO_DTR_B"})
    add_instance("SweetYaar:R", "R5", "10k", "Resistor_SMD:R_0805_2012Metric", 82, 302, {"1": "USB_RTS", "2": "AUTO_RTS_B"})
    add_instance("SweetYaar:NPN_BEC", "Q1", "SS8050/MMBT3904", "Package_TO_SOT_SMD:SOT-23", 116, 275, {"1": "AUTO_DTR_B", "2": "AUTO_BOOT_NODE", "3": "EN"})
    add_instance("SweetYaar:NPN_BEC", "Q2", "SS8050/MMBT3904", "Package_TO_SOT_SMD:SOT-23", 116, 324, {"1": "AUTO_RTS_B", "2": "BOOT", "3": "AUTO_BOOT_NODE"})

    # ESP32 core
    add_instance("SweetYaar:ESP32_WROOM_32E_REVA", "U3", "ESP32-WROOM-32E", "RF_Module:ESP32-WROOM-32E", 205, 190, {
        "1": "GND", "2": "3V3", "3": "EN", "4": "GPIO36", "5": "GPIO39", "6": "SD_CD", "7": "GPIO35", "8": "GPIO32", "9": "GPIO33",
        "10": "I2S_WS", "11": "I2S_BCLK", "12": "SPI_CS1", "13": "SPI_CS2", "14": None, "15": "GND", "16": "GPIO13",
        "17": None, "18": None, "19": None, "20": None, "21": None, "22": None, "23": "GPIO15", "24": "GPIO2_LED",
        "25": "BOOT", "26": "GPIO4", "27": "I2C_SDA", "28": "I2C_SCL", "29": "ESP_SD_CS", "30": "ESP_SD_SCK", "31": "SD_MISO",
        "32": None, "33": "AMP_MUTE_CTL", "34": "UART0_RX", "35": "UART0_TX", "36": "I2S_DOUT", "37": "ESP_SD_MOSI", "38": "GND", "39": "GND",
    })
    add_instance("SweetYaar:R", "R6", "10k", "Resistor_SMD:R_0805_2012Metric", 162, 35, {"1": "3V3", "2": "EN"})
    add_instance("SweetYaar:C", "C6", "1uF", "Capacitor_SMD:C_0805_2012Metric", 162, 58, {"1": "EN", "2": "GND"})
    add_instance("SweetYaar:SW_PUSH", "SW1", "EN/RST", "Button_Switch_SMD:SW_SPST_TL3342", 162, 82, {"1": "EN", "2": "GND"})
    add_instance("SweetYaar:R", "R7", "10k", "Resistor_SMD:R_0805_2012Metric", 162, 108, {"1": "3V3", "2": "BOOT"})
    add_instance("SweetYaar:SW_PUSH", "SW2", "BOOT", "Button_Switch_SMD:SW_SPST_TL3342", 162, 134, {"1": "BOOT", "2": "GND"})
    add_instance("SweetYaar:C", "C7", "22uF", "Capacitor_SMD:C_0805_2012Metric", 262, 35, {"1": "3V3", "2": "GND"})
    add_instance("SweetYaar:C", "C8", "100nF", "Capacitor_SMD:C_0805_2012Metric", 262, 58, {"1": "3V3", "2": "GND"})
    add_instance("SweetYaar:SW_DPDT_ONOFF", "JP2", "GPIO2 LED SW", "SweetYaar:SW-SMD_MS-22D28-G020", 262, 250, {"1": "GPIO2_LED", "2": "LED_STATUS_IN", "3": None, "4": None, "5": None, "6": None})
    add_instance("SweetYaar:R", "R10", "1k", "Resistor_SMD:R_0805_2012Metric", 262, 276, {"1": "LED_STATUS_IN", "2": "LED_STATUS_A"})
    add_instance("SweetYaar:LED", "D2", "STATUS", "LED_SMD:LED_0805_2012Metric", 262, 302, {"1": "LED_STATUS_A", "2": "GND"})

    # microSD
    add_instance("SweetYaar:MICRO_SD_SPI", "J4", "microSD SPI", "Connector_Card:microSD_HC_Molex_104031-0811", 340, 95, {
        "1": "SD_D2_PU", "2": "SD_CS", "3": "SD_MOSI", "4": "3V3", "5": "SD_SCK", "6": "GND", "7": "SD_MISO", "8": "SD_D1_PU", "SH": "GND",
    })
    add_instance("SweetYaar:R", "R11", "22R", "Resistor_SMD:R_0805_2012Metric", 305, 42, {"1": "ESP_SD_SCK", "2": "SD_SCK"})
    add_instance("SweetYaar:R", "R12", "22R", "Resistor_SMD:R_0805_2012Metric", 305, 64, {"1": "ESP_SD_MOSI", "2": "SD_MOSI"})
    add_instance("SweetYaar:R", "R13", "22R", "Resistor_SMD:R_0805_2012Metric", 305, 86, {"1": "ESP_SD_CS", "2": "SD_CS"})
    for idx, (ref, net) in enumerate([("R14", "SD_MOSI"), ("R15", "SD_MISO"), ("R16", "SD_D1_PU"), ("R17", "SD_D2_PU"), ("R18", "SD_CS")]):
        add_instance("SweetYaar:R", ref, "10k", "Resistor_SMD:R_0805_2012Metric", 400, 40 + idx * 20, {"1": "3V3", "2": net})
    add_instance("SweetYaar:C", "C9", "10uF", "Capacitor_SMD:C_0805_2012Metric", 400, 148, {"1": "3V3", "2": "GND"})
    add_instance("SweetYaar:C", "C10", "100nF", "Capacitor_SMD:C_0805_2012Metric", 400, 168, {"1": "3V3", "2": "GND"})

    # Audio
    add_instance("SweetYaar:MAX98357A_MODULE", "U4", "MAX98357A blue module", "Connector_PinHeader_2.54mm:PinHeader_1x07_P2.54mm_Vertical", 320, 320, {
        "1": "I2S_WS", "2": "I2S_BCLK", "3": "I2S_DOUT", "4": None, "5": "AMP_SD_MODE", "6": "GND", "7": "5V_SYS",
    })
    add_instance("SweetYaar:R", "R24", "10k", "Resistor_SMD:R_0805_2012Metric", 360, 348, {"1": "AMP_MUTE_CTL", "2": "AMP_MUTE_BASE"})
    add_instance("SweetYaar:R", "R25", "100k", "Resistor_SMD:R_0805_2012Metric", 360, 370, {"1": "AMP_MUTE_BASE", "2": "GND"})
    add_instance("SweetYaar:NPN_BEC", "Q3", "MMBT3904", "Package_TO_SOT_SMD:SOT-23", 385, 365, {"1": "AMP_MUTE_BASE", "2": "GND", "3": "AMP_SD_MODE"})
    add_instance("SweetYaar:C", "C11", "470uF DNP", "Capacitor_THT:CP_Radial_D6.3mm_P2.50mm", 395, 275, {"1": "5V_SYS", "2": "GND"}, dnp=True)
    add_instance("SweetYaar:C", "C12", "10uF", "Capacitor_SMD:C_0805_2012Metric", 395, 305, {"1": "5V_SYS", "2": "GND"})
    add_instance("SweetYaar:C", "C13", "100nF", "Capacitor_SMD:C_0805_2012Metric", 395, 335, {"1": "5V_SYS", "2": "GND"})

    # Expansion headers
    add_instance("SweetYaar:CONN_01X08", "J6", "SPI EXP", "Connector_PinHeader_2.54mm:PinHeader_1x08_P2.54mm_Vertical", 55, 470, {"1": "3V3", "2": "GND", "3": "SD_SCK", "4": "SD_MOSI", "5": "SD_MISO", "6": "SPI_CS1", "7": "SPI_CS2", "8": "5V_SYS"})
    add_instance("SweetYaar:CONN_01X04", "J7", "I2C EXP", "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical", 130, 465, {"1": "GND", "2": "3V3", "3": "I2C_SDA", "4": "I2C_SCL"})
    add_instance("SweetYaar:R", "R19", "4.7k", "Resistor_SMD:R_0805_2012Metric", 130, 520, {"1": "3V3", "2": "I2C_SDA"})
    add_instance("SweetYaar:R", "R20", "4.7k", "Resistor_SMD:R_0805_2012Metric", 130, 545, {"1": "3V3", "2": "I2C_SCL"})
    add_instance("SweetYaar:CONN_01X12", "J8", "GPIO EXP", "Connector_PinHeader_2.54mm:PinHeader_1x12_P2.54mm_Vertical", 225, 465, {
        "1": "3V3", "2": "5V_SYS", "3": "GND", "4": "GPIO32", "5": "GPIO33", "6": "GPIO4",
        "7": "GPIO13", "8": "GPIO15", "9": "GPIO35", "10": "GPIO36", "11": "GPIO39", "12": "SD_CD",
    })
    test_nets = ["5V_SYS", "3V3", "GND", "EN", "BOOT", "UART0_TX", "UART0_RX", "GPIO32", "GPIO33", "SD_SCK", "SD_MOSI", "SD_MISO", "SD_CS", "I2S_BCLK", "I2S_WS", "I2S_DOUT", "AMP_MUTE_CTL", "AMP_SD_MODE"]
    for i, net in enumerate(test_nets):
        x = 320 + (i % 3) * 30
        y = 430 + (i // 3) * 24
        add_instance("SweetYaar:TESTPOINT", f"TP{i + 1}", net, "TestPoint:TestPoint_Pad_D1.5mm", x, y, {"1": net})


def write() -> None:
    define_symbols()
    add_parts()
    lib_symbols = "\n".join(lib_symbol_block(s) for s in SYMS.values())
    local_lib_symbols = "\n".join(lib_symbol_block(s, library_file=True) for s in SYMS.values())
    body = "\n".join(SECTIONS + SCHEM_ITEMS)
    text = f"""(kicad_sch
\t(version 20250114)
\t(generator "eeschema")
\t(generator_version "10.0.3")
\t(uuid "{uid()}")
\t(paper "A1")
\t(title_block
\t\t(title "ESP32 Prototype Board")
\t\t(date "2026-05-16")
\t\t(rev "A")
\t\t(company "SweetYaar")
\t\t(comment 1 "Reusable ESP32 audio/storage lab carrier")
\t\t(comment 2 "Generated full Rev A schematic")
\t)
\t(lib_symbols
{lib_symbols}
\t)
{body}
\t(sheet_instances
\t\t(path "/"
\t\t\t(page "1")
\t\t)
\t)
\t(embedded_fonts no)
)
"""
    OUT.write_text(text)
    LOCAL_SYM_LIB.write_text(
        f"""(kicad_symbol_lib
\t(version 20241209)
\t(generator "sweetyaar_rev_a_generator")
\t(generator_version "1")
{local_lib_symbols}
)
"""
    )
    SYM_LIB_TABLE.write_text(
        """(sym_lib_table
\t(version 7)
\t(lib (name "SweetYaar") (type "KiCad") (uri "${KIPRJMOD}/sweetyaar_rev_a.kicad_sym") (options "") (descr "SweetYaar Rev A local symbols"))
)
"""
    )
    fp_base = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints"
    fp_libs = [
        "Button_Switch_SMD",
        "Capacitor_SMD",
        "Capacitor_THT",
        "Connector_Card",
        "Connector_PinHeader_2.54mm",
        "Connector_USB",
        "Jumper",
        "LED_SMD",
        "Package_SO",
        "Package_TO_SOT_SMD",
        "RF_Module",
        "Resistor_SMD",
        "TerminalBlock",
        "TestPoint",
    ]
    FP_LIB_TABLE.write_text(
        "(fp_lib_table\n\t(version 7)\n"
        + "".join(
            f'\t(lib (name "{name}") (type "KiCad") (uri "{fp_base}/{name}.pretty") (options "") (descr ""))\n'
            for name in fp_libs
        )
        + '\t(lib (name "SweetYaar") (type "KiCad") (uri "${KIPRJMOD}/sweetyaar_rev_a.pretty") (options "") (descr "SweetYaar Rev A local footprints"))\n'
        + ")\n"
    )


if __name__ == "__main__":
    write()
