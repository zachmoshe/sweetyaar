# SweetYaar — Project Overview

This document explains what SweetYaar is, why the project was redesigned, and
how its major pieces came together. It is intentionally not a technical
specification or a task tracker. Detailed and current decisions belong in the
engineering documents linked below.

## What SweetYaar Is

SweetYaar is a battery-powered audio toy designed to be installed inside a
doll. Its child-facing interaction stays deliberately simple: physical buttons
play songs and animal sounds stored on removable media.

The same toy can also act as a conventional Bluetooth speaker. A separate
parent remote provides access to controls and settings that should not be part
of the child's physical interface, including content selection, volume,
temporary quiet time, sleep behavior, and Bedtime mode.

The complete product combines four areas:

- Embedded firmware for playback, Bluetooth, controls, and power behavior.
- A small parent-facing web app that communicates directly with the toy.
- Custom electronics designed for safe battery operation and low standby
  power.
- An enclosure and harness system that make the electronics suitable for use
  inside a doll.

## How the Project Got Here

The first SweetYaar implementation was a MicroPython-based local audio toy. It
proved the basic idea, but the next version needed to appear as a normal
Bluetooth audio device to phones and computers. That requirement led to a new
firmware implementation using the ESP32's Classic Bluetooth capabilities and a
C++/Arduino development environment.

Once Bluetooth speaker support was added, the project grew beyond a firmware
rewrite. Local playback and streamed audio needed to share the same speaker
cleanly, parents needed a convenient way to control the toy, and the device
needed predictable behavior when switching between child controls, parent
controls, and external Bluetooth audio.

The parent experience became a lightweight Web Bluetooth app rather than a
native application or cloud service. This keeps the system private and local,
avoids accounts and installation requirements, and still allows richer settings
than the physical toy should expose.

The software work also exposed the limits of the original development-board
prototype. Reliable sleep, battery charging, peripheral power control,
programming access, and physical safety all require a purpose-built board and
enclosure. The current direction is therefore a complete product design rather
than a collection of connected modules.

## Product Principles

- Keep the child's controls small, immediate, and predictable.
- Put configuration and supervision in the parent remote.
- Keep audio content replaceable without rebuilding firmware.
- Work locally without an account, application server, or Wi-Fi setup flow.
- Treat local playback and Bluetooth streaming as distinct uses of one speaker.
- Prefer safe, understandable behavior over maximum charging speed, output
  power, or battery capacity.
- Make deep sleep the normal inactive state while retaining a physical service
  and safety control.
- Design the electronics, enclosure, connectors, and wiring as one product.

## Evolution of the Design

The project has progressed through several broad stages:

1. Rebuild the original toy behavior in the new firmware environment.
2. Add Bluetooth speaker support while preserving local audio playback.
3. Add a parent remote for live control and persistent settings.
4. Add content management, Bedtime behavior, battery state, and reliable sleep
   and wake behavior.
5. Move from a modular prototype to a production-oriented custom PCB.
6. Integrate the board, battery, speaker, controls, and service access into a
   safe enclosure.

These stages explain the history of the repository; they are not a current
completion checklist. Open work and verification requirements are maintained
in the relevant engineering guide rather than duplicated here.

## Authoritative Engineering Documents

- [Hardware](engineering/hardware.md) is the source of truth for the
  electrical architecture, component connections, PCB requirements, power and
  charging design, safety constraints, enclosure interfaces, and hardware
  validation.
- [Firmware](engineering/firmware.md) is the source of truth for device
  behavior, playback rules, Bluetooth behavior, content handling, sleep and
  wake behavior, firmware organization, building, flashing, and testing.
- [Mobile App](engineering/mobile-app.md) is the source of truth for the
  parent experience, controls and settings, Bluetooth connection flow, Bedtime
  presentation, offline operation, deployment, and app testing.
- [README](../README.md) covers repository history, development setup, common
  commands, and the repository layout.

When this overview and an engineering guide disagree, the engineering guide is
authoritative. New technical decisions should be recorded in the appropriate
guide instead of expanding this overview into a second specification.
