# Trimmed cue previews

All files are 44.1 kHz, 16-bit mono PCM. Only all-zero leading/trailing samples
were removed, with one zero frame retained at each endpoint. Audible PCM,
pitch and gain are unchanged. `manifest.json` records original/trimmed hashes,
sample counts and exact removed lengths.

| File | Use | Duration |
| --- | --- | --- |
| `ready.wav` | Ready | 0.723333 s |
| `pairing.wav` | Bluetooth pairing | 0.629524 s |
| `error.wav` | Error | 0.631088 s |
| `battery.wav` | MEDIUM/LOW warning | 0.763605 s |
| `charger.wav` | Historical charger diagnostic; exact Ready copy | 0.723333 s |
| `charger-sunrise.wav` | Selected Sunrise sound, embedded as charger.wav | 0.494490 s |

Ready, pairing, error and battery match their embedded assets; the embedded
charger asset matches `charger-sunrise.wav`. The diagnostic `charger.wav` and
its manifest entry are retained as historical comparison evidence.
The original auditions remain in their existing directories. Their
generators use `../reference/pairing-original.wav`, preserving the original
sample extraction offsets after the embedded pairing WAV is trimmed.
