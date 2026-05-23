# Rev A Cost Estimate

This is a planning estimate for a tiny run of 3-5 boards. It is not a quote. PCB
assembly prices move with stock, shipping, coupons, board options, and exact part
selection, so the real number comes from uploading Gerbers, BOM, and CPL files.

## Current Pricing Anchors

JLCPCB's published PCBA pricing page lists setup, stencil, solder-joint, feeder,
and X-ray costs. As of the currently published page, standard PCBA has a setup fee
of 25 USD for one assembly side, and double-sided placement doubles that setup fee.
The same page explains that X-ray inspection is required for hidden-joint packages
such as BGA and QFN, which is one reason Rev A avoids them. The localized JLCPCB
pricing page currently shows economic PCBA at 8 USD setup and 1.50 USD stencil for
single-sided assembly. JLCPCB's low-volume assembly guide also describes prototype
ordering as the sum of bare PCB cost, stencil/setup cost, components, and assembly
labor, with a minimum order path for small assembled batches.

Sources:

[JLCPCB PCBA price details](https://jlcpcb.com/help/article/pcb-assembly-price)

[JLCPCB PCBA price details, localized page with economic pricing](https://jlcpcb.com/fr/help/article/pcb-assembly-price)

[JLCPCB low-volume PCB assembly guide](https://jlcpcb.com/blog/low-volume-pcb-assembly)

## Expected Order Cost

| Scenario | What It Includes | Rough Cost Before VAT/Import |
|---|---|---:|
| Bare PCB only | 5 boards, no assembly | 20-50 USD plus shipping |
| Partial assembly | Top-side SMT basics, hand-solder headers/terminals/audio module | 70-130 USD plus shipping |
| More complete assembly | ESP32 module, USB-UART, regulator, USB-C, SD socket, passives assembled | 100-180 USD plus shipping |

For Israel delivery, assume shipping and taxes can be a meaningful part of the bill.
The safest mental budget for the first useful order is around 120-220 USD landed,
depending on how many parts JLC can assemble cheaply and how many connectors/modules
we hand-solder ourselves.

## Cost-Saving Choices In Rev A

The board is top-side SMT only, so we avoid double-side assembly fees. Passives are
0805 so they are easy to inspect and rework. Bulky parts like headers, screw terminals,
and possibly the MAX98357A module are hand-soldered. QFN/BGA parts are avoided, which
also avoids X-ray line items and painful inspection.

Panelizing two copies into a 100 mm x 100 mm panel may or may not help. It can reduce
handling cost in some cases, but for only 3-5 boards it may also add panelization work
without saving much. We should first price a single 80 mm x 60 mm board design, then
try a panelized quote only if the upload tool makes it look cheaper.

