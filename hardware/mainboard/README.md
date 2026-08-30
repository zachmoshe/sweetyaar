# SweetYaar mainboard

Create the production KiCad project in this directory. Keep the project,
schematic, PCB, project library tables, and board-specific design rules together:

- `sweetyaar-mainboard.kicad_pro`
- `sweetyaar-mainboard.kicad_sch`
- `sweetyaar-mainboard.kicad_pcb`

Store immutable fabrication and assembly snapshots under `releases/<revision>/`
when a board revision is actually sent for manufacturing. Generated working
outputs belong in an ignored `fab/` directory.
