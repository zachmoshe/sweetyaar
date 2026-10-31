"""Readable badges for records that store codes and bit fields.

Each decoder takes a record's arguments and returns [text, tone] pairs; tone
is "ok", "info", "warn" or "bad". The values mirror the firmware: telemetry
bits in main.cpp logTelemetry(), ChargerStatus.h, BatteryMonitor.h and the
BQ25186 register decoding in BQ25186Charger.cpp.
"""

from __future__ import annotations

BATTERY_STATES = ["battery unknown", "battery good", "battery medium", "battery low", "battery charging"]
BATTERY_TONES = ["warn", "ok", "info", "warn", "info"]
CHARGER_STATES = ["charger unknown", "no charger input", "charging disabled", "not charging", "charging",
                  "charge finished"]

# ChargerStatus::Condition, as stored in TELEMETRY.
CONDITIONS = [
    (1 << 0, "battery too hot/cold", "bad"),
    (1 << 1, "temperature: reduced charging", "warn"),
    (1 << 2, "no thermistor", "warn"),
    (1 << 3, "input current limited", "info"),
    (1 << 4, "system voltage limited", "info"),
    (1 << 5, "input voltage limited", "info"),
    (1 << 6, "thermal regulation", "warn"),
    (1 << 7, "input overvoltage", "bad"),
    (1 << 8, "battery undervoltage", "warn"),
    (1 << 9, "safety timer expired", "bad"),
    (1 << 10, "charger not readable", "bad"),
]

# logTelemetry() activity bits.
ACTIVITY = [
    (0x01, "playing a WAV"),
    (0x02, "phone connected"),
    (0x04, "Bluetooth audio"),
    (0x08, "app connected"),
    (0x10, "Quiet time"),
    (0x20, "Bedtime"),
    (0x40, "pairing open"),
]

# BQ25186 registers (TI datasheet; bit use as in BQ25186Charger.cpp).
STAT0_CHARGE = ["not charging", "charging (CC)", "charging (CV)", "done or disabled"]
STAT0_BITS = [
    (0x80, "no thermistor", "warn"),
    (0x10, "input current limit", "info"),
    (0x08, "system voltage limit", "info"),
    (0x04, "input voltage limit", "info"),
    (0x02, "thermal regulation", "warn"),
]
STAT1_TEMPERATURE = [None, ("too hot/cold", "bad"), ("cool", "warn"), ("warm", "warn")]
STAT1_BITS = [
    (0x80, "input overvoltage", "bad"),
    (0x40, "battery undervoltage", "warn"),
    (0x04, "safety timer fault", "bad"),
]
# FLAG0 bits latch events since the previous read (read to clear).
FLAG0_BITS = [
    (0x80, "event: thermistor fault", "warn"),
    (0x40, "event: input current limit", "info"),
    (0x20, "event: system voltage limit", "info"),
    (0x10, "event: input voltage limit", "info"),
    (0x08, "event: thermal regulation", "warn"),
    (0x04, "event: input overvoltage", "bad"),
    (0x02, "event: battery undervoltage", "warn"),
    (0x01, "event: battery overcurrent", "bad"),
]

# esp_sleep_wakeup_cause_t; EXT0 is the vibration switch, EXT1 the charger's
# power-good pin (main.cpp enterIdleDeepSleep()).
WAKE_CAUSES = {0: ("cold start", "info"), 2: ("woken by movement", "info"),
               3: ("woken by charger", "info"), 4: ("woken by timer", "info")}

# Bluetooth HCI disconnect reasons.
HCI_REASONS = {
    0x05: ("auth failure", "bad"), 0x08: ("timeout", "warn"),
    0x13: ("closed by phone", "ok"), 0x14: ("phone low resources", "warn"),
    0x15: ("phone powered off", "info"), 0x16: ("closed by toy", "info"),
    0x1F: ("unspecified error", "warn"), 0x22: ("link timeout", "warn"),
    0x3B: ("bad parameters", "warn"), 0x3D: ("encryption failed", "bad"),
    0x3E: ("failed to connect", "warn"),
}

# Xtensa EXCCAUSE values in a CRASH summary.
EXCEPTION_CAUSES = {
    0: "illegal instruction", 2: "instruction fetch error", 3: "load/store error",
    6: "divide by zero", 9: "unaligned access", 20: "bad instruction address",
    28: "bad read address", 29: "bad write address",
}


def bits(value: int, table: list) -> list[list[str]]:
    return [[text, tone] for mask, text, tone in table if value & mask]


def telemetry(args: list) -> list[list[str]]:
    battery, battery_state, charger, conditions, activity = args[:5]
    out = []
    if not battery:
        out.append(["no battery reading", "warn"])
    elif battery_state < len(BATTERY_STATES):
        out.append([BATTERY_STATES[battery_state], BATTERY_TONES[battery_state]])
    if charger < len(CHARGER_STATES):
        out.append([CHARGER_STATES[charger], "info"])
    out += bits(conditions, CONDITIONS)
    out += [[text, "info"] for mask, text in ACTIVITY if activity & mask]
    if not activity & 0x80:
        out.append(["SD card not ready", "warn"])
    return out


def charger_registers(args: list) -> list[list[str]]:
    _, stat0, stat1, flag0 = args[:4]
    out = [[STAT0_CHARGE[(stat0 >> 5) & 0x03], "info"]]
    out += bits(stat0, STAT0_BITS)
    out.append(["input power good" if stat0 & 0x01 else "no input power", "ok" if stat0 & 0x01 else "info"])
    temperature = STAT1_TEMPERATURE[(stat1 >> 3) & 0x03]
    if temperature:
        out.append(list(temperature))
    out += bits(stat1, STAT1_BITS)
    out += bits(flag0, FLAG0_BITS)
    return out


def wake(cause: int) -> list[list[str]]:
    return [list(WAKE_CAUSES.get(cause, (f"wake cause {cause}", "info")))]


# DevLog.cpp resetName(). The EN pin (debugger, flashing, fetching) also
# reports power-on.
RESETS = {
    "power-on": ("cold start", "info"),
    "external": ("reset pin", "info"),
    "software": ("firmware restart", "info"),
    "panic": ("crash", "bad"),
    "interrupt-watchdog": ("watchdog hang", "bad"),
    "task-watchdog": ("watchdog hang", "bad"),
    "watchdog": ("watchdog hang", "bad"),
    "deep-sleep": ("deep-sleep wake", "ok"),
    "brownout": ("brownout", "bad"),
}


def boot(args: list) -> list[list[str]]:
    out = [list(RESETS[args[2]])] if len(args) > 2 and args[2] in RESETS else []
    if len(args) > 4 and isinstance(args[4], int) and args[4]:  # a cold start is in the reset badge
        out += wake(args[4])
    if len(args) > 1 and args[1]:
        out.append([f"{args[1]} bad resets in a row", "bad"])
    return out


def ble_disconnect(args: list) -> list[list[str]]:
    text, tone = HCI_REASONS.get(args[1], (f"reason 0x{args[1]:02X}", "info"))
    return [[text, tone]]


def ble_auth(args: list) -> list[list[str]]:
    return [["paired" if args[7] else "pairing failed", "ok" if args[7] else "bad"]]


def crash(args: list) -> list[list[str]]:
    cause = args[1]
    return [[EXCEPTION_CAUSES.get(cause, f"exception cause {cause}"), "bad"]]


def dropped(args: list) -> list[list[str]]:
    names = ["rate limit", "no erased sector", "boot loop", "writer busy", "flash error"]
    return [[f"{count} lost ({name})", "warn"] for name, count in zip(names, args) if count]


def repeated(args: list) -> list[list[str]]:
    return [[f"×{args[2]} more", "info"]]


DECODERS = {
    "TELEMETRY": (5, telemetry),
    "CHARGER_REGISTERS": (4, charger_registers),
    "BOOT": (5, boot),
    "SLEEP_WAKE": (1, lambda args: wake(args[0])),
    "BLE_DISCONNECT": (2, ble_disconnect),
    "BLE_AUTH": (8, ble_auth),
    "CRASH": (2, crash),
    "LOG_DROPPED": (1, dropped),
    "REPEATED": (4, repeated),
}


def badges(name: str, args: list) -> list[list[str]]:
    decoder = DECODERS.get(name)
    if not decoder or len(args) < decoder[0]:
        return []
    try:
        return decoder[1](args)
    except (TypeError, IndexError):
        return []  # a newer firmware changed something the decoder does not know
