# 3D model sources and coverage

Checked 2026-09-20. New model assignments use manufacturer-supplied files, manufacturer-linked CAD
portals, or existing models from KiCad's official libraries, with two explicitly
approved exceptions: the Murata inductors use a generated rectangular body
placeholder, and the USB connector uses an existing EasyEDA model for the exact
part. No published model was stretched to fit a different component.

## Installed models

| Footprint / component | Source and current assignment | Coverage |
| --- | --- | --- |
| `DLA0010A` / TPS63802DLAR | [TI engineer's STEP attachment](https://e2e.ti.com/support/power-management-group/power-management/f/power-management-forum/899809/tps63802-step-file-request), stored unchanged as `SweetYaar.3dshapes/TI_DLA0010A.step` | SweetYaar footprint, imported Ultra Librarian footprint, and mainboard `U_3V3` / `U_5V1` |
| `WSON10_DLH_TEX`, `-L`, `-M` / BQ25185DLHR | [Official KiCad DLH0010A model](https://gitlab.com/kicad/libraries/kicad-packages3D/-/blob/master/Package_DFN_QFN.3dshapes/Texas_DLH0010A_WSON-10-1EP_2.2x2mm_P0.4mm_EP0.9x1.5mm.step) | All three SweetYaar variants and all three imported Ultra Librarian variants |
| `Texas_DLH0010A_WSON-10-1EP_2.2x2mm_P0.4mm_EP0.9x1.5mm` / BQ25185DLHR | Same official KiCad model | Existing model reference retained in the library and mainboard `U_CHG1`; file existence and geometry checked |
| `WS2812B-V6` | [Official KiCad WS2812B PLCC4 model](https://gitlab.com/kicad/libraries/kicad-packages3D/-/blob/master/LED_SMD.3dshapes/LED_WS2812B_PLCC4_5.0x5.0mm_P3.2mm.step) | Added to personal LCSC library and new project-owned SweetYaar footprint; mainboard `D_LED1` and its schematic footprint field now use `SweetYaar:WS2812B-V6` |
| `RP2040` in personal LCSC library | [Official KiCad QFN56 model](https://gitlab.com/kicad/libraries/kicad-packages3D/-/blob/master/Package_DFN_QFN.3dshapes/QFN-56-1EP_7x7mm_P0.4mm_EP3.2x3.2mm.step) | Replaced the reference to the personal EasyEDA-derived WRL file with the official package model; original WRL/STEP files retained |
| `microSD_HC_Molex_104031-0811` / `J_SD1` | [Official Molex STEP archive](https://www.molex.com/content/dam/molex/molex-dot-com/products/automated/en-us/3dcadmodels/104/104031/1040310811_stp.zip), stored unchanged as `SweetYaar.3dshapes/Molex_1040310811.step` | SweetYaar footprint and embedded mainboard footprint; all 14 pad locations checked against model contacts |
| `Texas_DPY0002A_0.6x1mm_P0.65mm` / ESD441, `D1`, `D2` | Original `DPY0002A.stp` extracted unchanged from [TI TIDA-010932 CAD archive](https://www.ti.com/lit/zip/tidmbo7), stored as `SweetYaar.3dshapes/TI_DPY0002A.step` | New project-owned copy of the official KiCad footprint; both schematic instances and embedded PCB footprints use the SweetYaar library; both contacts checked |
| `TQFN-16-1EP_3x3mm_P0.5mm_EP1.23x1.23mm` / MAX98357AETE+T, `U_AMP1` | User download from the SamacSys option on [ADI's component resources](https://www.analog.com/en/products/max98357a.html), stored unchanged as `SweetYaar.3dshapes/SamacSys_MAX98357AETE_T.step` | Project-owned copy of the existing KiCad footprint, embedded mainboard footprint, schematic assignment, and SweetYaar symbol default |
| `L_Murata_DFE201612E` / `L_3V3`, `L_5V1` | User-approved **rough placeholder**, `SweetYaar.3dshapes/Placeholder_DFE201612E_2.0x1.6x1.2mm.step` | SweetYaar footprint and both embedded mainboard footprints; 2.0 x 1.6 x 1.2 mm rectangular body, centered over the existing footprint |
| `USB_C_Receptacle_HRO_TYPE-C-31-M-12` / `J_USB1` | User-approved [EasyEDA model for C165948](https://pcbpartpicker.app/part/lcsc-c165948), stored unchanged as `SweetYaar.3dshapes/EasyEDA_HRO_TYPE-C-31-M-12.step`; manufacturer authorship unverified | Project-owned copy of the existing KiCad footprint, embedded PCB footprint, and schematic footprint assignment |

The LED model is KiCad's published **WS2812B package model**, not a
Worldsemi-authored V6-specific model. Its body is 5 x 5 mm, terminals extend to
5.4 mm overall, and height is 1.6 mm. The [V6 manufacturer drawing](https://datasheet.lcsc.com/datasheet/pdf/0689d8fd6dabfc7959e82552d4ffad8b.pdf?productCode=C52917433)
specifies 1.57 +/- 0.05 mm height. Pad orientation and the pin-3 corner mark
agree. This is a nominal visualization, not a worst-case tolerance envelope.

All added assignments use scale `(1, 1, 1)`. Except for the Molex SD and HRO USB
connectors, their offsets and rotations are zero. The original Molex file has a displaced
origin: its assignment uses offset `(44.470057, -1.712511, 0.61)` mm and rotation
`(0, 0, 180)` degrees. USB uses offset `(0, -1.05, 0)` mm and rotation
`(0, 0, 180)` degrees. These are model transforms only. They do not modify the
footprint's placement rotation or `FT Rotation Offset` used by assembly exports.

## Model file paths and provenance

The TI file uses
`${KIPRJMOD}/../libraries/SweetYaar.3dshapes/TI_DLA0010A.step`.
This resolves from both `hardware/mainboard` and `hardware/debugger`. When using
these libraries in another project, retain that directory structure or adjust
the model path for that project.

KiCad models use `${KICAD10_3DMODEL_DIR}` and require the KiCad 10 3D-model
libraries. The global LCSC footprints also use this variable, so they no longer
depend on an absolute personal model-file path.

TI source file:

- Download: <https://e2e.ti.com/cfs-file/__key/communityserver-discussions-components-files/196/DLA0010A.stp>
- Original filename: `DLA0010A.stp`.
- Stored file: `SweetYaar.3dshapes/TI_DLA0010A.step` (identical bytes).
- SHA-256: `942b488b136c91e882509a8ebd21184f8212fc6341e41e40325a65ef70613e59`.
- Supplied by a TI engineer for TPS63802. Original STEP header and geometry
  preserved; no new license is asserted for this manufacturer asset.

Molex source file:

- Download: <https://www.molex.com/content/dam/molex/molex-dot-com/products/automated/en-us/3dcadmodels/104/104031/1040310811_stp.zip>.
- Original filename inside the archive: `1040310811.stp`.
- Stored file: `SweetYaar.3dshapes/Molex_1040310811.step` (identical bytes).
- SHA-256: `1c7d98004a40dd2a13273773959a46755e246b3bbbc2739e21018cd8ddbf0cb3`.
- Manufacturer STEP header dated 2015-03-27 retained. No new license is asserted.
- Model path uses `${KIPRJMOD}/../libraries/SweetYaar.3dshapes/` as above.
- Transformed bounds are X -6.34 to 6.34, Y -6.05 to 6.00, Z 0 to 1.45 mm.
  The eight signal contacts sit at Z=0; shell/detect contacts are 0.01 mm above
  that plane. All 14 footprint pads overlap the corresponding model contacts.
  This model includes the connector, not an inserted microSD card.

The personal library files updated on this machine are
`/Users/zmoshe/KiCad/LCSC.pretty/WS2812B-V6.kicad_mod` and
`/Users/zmoshe/KiCad/LCSC.pretty/RP2040.kicad_mod`.
The separate global `EasyEDA.pretty` library was inspected but is outside the
requested SweetYaar/LCSC/repository libraries and was not edited.

TI DPY0002A source file:

- Official reference design: <https://www.ti.com/tool/TIDA-010932>.
- Download: <https://www.ti.com/lit/zip/tidmbo7>.
- Extracted from `TIDMBO7/Copy of 24Vac to 3V3_PCB.PcbDoc`, embedded
  `Models/17` stream; the corresponding model record names `DPY0002A.stp`.
- Stored file: `SweetYaar.3dshapes/TI_DPY0002A.step` (original decompressed bytes).
- SHA-256: `433c2b3b548dd88a169421ac038e60bbd21d03a5e83fd682c0e3ef3dca75bbaf`.
- The identical file is also embedded in [TI TIDA-010247 CAD archive](https://www.ti.com/lit/zip/tidmb62),
  in `32S BMU_BQ76972_CAN Stacking_V2.PcbDoc`, `Models/76` and `Models/77`.
- TI package model, with the original Creo STEP header dated 2018-09-20;
  no generated geometry and no new license asserted. Its bounds are
  1.0 x 0.6 x 0.45 mm; both underside contacts align with the existing pads
  using zero offset/rotation and unit scale. This is package geometry and
  does not reproduce an ESD441-specific top marking.
- Model path: `${KIPRJMOD}/../libraries/SweetYaar.3dshapes/TI_DPY0002A.step`.
- Obtained from TI directly after the Ultra Librarian export failed.

MAX98357AETE+T source file:

- Downloaded by the user through the SamacSys dialog linked from
  <https://www.analog.com/en/products/max98357a.html>.
- Archive: `LIB_MAX98357AETE+T.zip`; original member:
  `MAX98357AETE+T/3D/MAX98357AETE+T.stp`.
- Stored file: `SweetYaar.3dshapes/SamacSys_MAX98357AETE_T.step` (identical bytes).
- SHA-256: `2e2efe87a0bd929411a6c8e9176d24d3e32cbe253592f87725342c204d70acf6`.
- Published SamacSys model supplied through ADI's CAD resources; its original
  FreeCAD/OpenCascade header dated 2020-08-27 is retained. No geometry was generated.
- Original archive metadata and license are retained beside the STEP as
  `SamacSys_MAX98357AETE_T.part_info.txt` and
  `SamacSys_MAX98357AETE_T.LICENSE.txt`. The supplied license permits board
  designs but restricts redistribution of models as reusable PCB library components.
- Body measures 3.0 x 3.0 mm; overall bounds including terminals are
  3.1 x 3.1 x 0.8 mm. Exposed contact is 1.1 x 1.1 mm and sits within the
  existing 1.23 x 1.23 mm copper land. All 17 contacts overlap the existing pads,
  and the top pin-1 mark matches the footprint, using zero offset/rotation
  and unit scale.
- The existing KiCad land pattern was retained; the archive's alternate footprint
  was not imported. Model alignment does not certify a land pattern.
- Model path: `${KIPRJMOD}/../libraries/SweetYaar.3dshapes/SamacSys_MAX98357AETE_T.step`.

Inductor placeholder:

- No matching manufacturer or official KiCad model was obtained. KiCad's
  DFE201610P has a different height. The user explicitly approved a rough-size
  dummy for the inductors on 2026-09-20.
- Generated as a single OpenCascade rectangular solid, 2.0 x 1.6 x 1.2 mm,
  using the dimensions recorded in the existing DFE201612E footprint and
  [Murata's package specification](https://datasheet.lcsc.com/datasheet/pdf/9a2227c0960d033e774a76ebdabff58d.pdf?productCode=C337892).
- Bounds: X -1 to 1, Y -0.8 to 0.8, Z 0 to 1.2 mm. Unit scale, zero offset
  and rotation. OpenCascade re-import verified these bounds.
- This is explicitly **not manufacturer CAD**. It omits terminal geometry,
  edge details, manufacturing tolerances, and solder standoff. Use it for rough
  body visualization, not a certified maximum clearance envelope or pad check.
- The schematic already selects the same footprint; no schematic edit is needed.

USB source file:

- The [C165948 registry entry](https://pcbpartpicker.app/part/lcsc-c165948)
  publishes an existing EasyEDA STEP for the exact TYPE-C-31-M-12, available
  from its [STEP asset link](https://api.pcbpartpicker.app/api/assets/f69c03da-2874-4e90-9b88-dd8424af37a8).
  Its header names `USB-C_SMD-TYPE-C-31-M-12.step`, SolidWorks 2020,
  export date 2022-07-15; the body carries EasyEDA/LCEDA markings.
- SHA-256: `b083e67ce4d06850a2c3835a6366f4012b2def64f8f2781636381ebcaa33e9a0`.
- Manufacturer authorship is unverified. The user explicitly approved this
  checked EasyEDA model on 2026-09-20 as an exception to the earlier
  manufacturer/official-KiCad-only requirement. HRO's own product page directs
  its 3D request to customer support; no message was sent.
- Stored unchanged as `SweetYaar.3dshapes/EasyEDA_HRO_TYPE-C-31-M-12.step`.
- Model transform for the existing native KiCad footprint: offset
  `(0, -1.05, 0)` mm, rotation `(0, 0, 180)` degrees, unit scale. This is a
  model-coordinate correction, not a footprint placement or assembly offset.
- With that transform, all 12 SMD solder faces at Z=0 overlap the current pads.
  The locating pegs center on X +/-2.89, Y +2.60 mm in model coordinates.
  Shell tabs align with the four mounting holes (rear tab centers differ by
  approximately 0.005 mm). The mouth is at model Y=-3.65 mm, matching the
  footprint's front at KiCad Y=+3.65 mm.
- Outer shell width is 8.94 mm, height about 3.25 mm above the PCB, versus
  8.94 mm and 3.26 mm in the [HRO drawing distributed by LCSC](https://datasheet.lcsc.com/datasheet/pdf/9e56b777c022540fcce7c7f67825f55e.pdf?productCode=C165948),
  dated 2020-12-08. Geometry includes the receptacle opening and tongue.
  Model alignment does not verify plug overmold clearance or enclosure tolerances.
- A separate [AI03 community model](https://github.com/ai03-2725/Type-C.pretty)
  was also inspected. The EasyEDA model above was selected and installed.

## Remaining library gap

| Footprint / component | Status and next source |
| --- | --- |
| `SW-SMD_MS-22D28-G020` | No matching manufacturer or official KiCad model obtained. The [G-Switch product page](https://dg-switch.com/smdwdkg/1494.html) offers a drawing; a verified STEP file is still needed. This library-only part is not fitted to the current mainboard. |

All current mainboard model references resolve to existing files. A model
filename alone is not evidence of verified enclosure clearance.

`DebuggerPad_1x06_P2.54mm` is bare PCB copper; it correctly has no connector
body model. The same applies to the board's bare test pads, solder jumpers, and
mounting holes. These are not missing purchased components.

The vibration-switch footprint's pre-existing resistor-shaped model is retained
as an estimate, explicitly accepted by the user on 2026-09-20. It is not an
accurate mechanical model of the fitted switch; its clearance remains unverified.

## Verification performed

- KiCad loaded the edited footprints and the mainboard successfully.
- OpenCascade imported the initial four assigned model families. Measured overall model
  bounds were 2 x 3 x 1 mm (TI DLA0010A), 2.2 x 1.975 x 0.8 mm
  (KiCad DLH0010A), 5.4 x 5 x 1.6 mm including terminals (LED), and
  7 x 7 x 0.9 mm (RP2040 package).
- With zero transforms, model contact faces overlap all numbered footprint
  pads: 10, 11, 4, and 57 respectively. Top-view overlays were inspected for
  orientation. This checks model placement; it is not a new land-pattern review.
- Parsed before/after comparison confirmed no changes to pads, nets, board
  placement, board outline, test-pad exclusions, or assembly-rotation fields.
  Schematic edits are the LED, two ESD diode, amplifier, and USB footprint-library
  references. The amplifier symbol's default footprint in SweetYaar was updated too.
- The debugger PCB currently contains no footprints.
- After adding the two inductor placeholders, KiCad loaded all 102 footprints.
  Exact text comparison against the pre-amplifier snapshot, reversing only the
  amplifier model references and the two new inductor model blocks, matched.
- After installing USB, all 76 model references across the 102 mainboard
  footprints resolve. KiCad loaded the USB library footprint and confirmed
  its model path, offset, and rotation. Exact before/after comparison verified
  that the only USB-related board/schematic changes were the library reference
  and model assignment; pads, nets, and placement stayed unchanged.

No routing/ERC/DRC pass or complete enclosure fit approval is implied by this
3D-model update.
