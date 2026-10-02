# Script fixtures of the grouped jobs (0.35.0.dev0)

Source: the licensed tests of 2026-10-02 on FlightStream 26.124 build 8172026.
The per-point scripts describe synthetic tier-3 cases; the measured arm scripts
record the command sequences used to compare re-initialisation and polar changes.
Sources are identified by role only.

Each SHA-256 below was computed from the fixture file itself on 2026-10-02.
Hash domain: exact-file-bytes, including the stored line endings.

| fixture | role / source in the licensed tests | fixture sha256 | bytes |
|---|---|---|---|
| `armA.txt` | Measured arm A script: two points of one polar with re-initialisation. | `c5c99780dbc27bd98eec67ec0d3ce5eb9940c48ff842b6dd65d7d2044d084153` | 6921 |
| `armD.txt` | Measured arm D script: advance-ratio points with rotor speed restated. | `6800056da586513e1e9151ebb93750c20cf08830df5f1e2710d47ef40c91f78e` | 5661 |
| `armE.txt` | Measured arm E script: a mesh change between polars and re-initialisation within the second. | `ef5e5c2e246ba73b6df0882b92c1cea8bd8a501b77e7635b1c178ae5b22e7cf6` | 13710 |
| `p9811.txt` | Per-point script of synthetic tier-3 case 9811, alpha 0. | `793b2239b8809457b9c5de166f50478a0cbbf3ca6780cf523bc2b86b4238572d` | 5614 |
| `p9812.txt` | Per-point script of synthetic tier-3 case 9812, alpha 2. | `68a9ef66d8528da1db14aaa523e9ab043be35182b167a58534d5fdef083d829f` | 5614 |
| `p9821_j150.txt` | Per-point script of synthetic tier-3 case 9821, advance ratio 1.5. | `9b105643fbf5b00c30f63d1c7810466a8c185b2926809df0a97bcced561f2c81` | 4617 |
| `p9821_j190.txt` | Per-point script of synthetic tier-3 case 9821, advance ratio 1.9. | `5c9696f9e3e5e7fd2a64939c5010fb0e874032d10fcb1b1c4afa4b26409d7dc8` | 4616 |
| `p9841_a000.txt` | Per-point script of synthetic tier-3 case 9841, alpha 0. | `f66fa9d0d788fe7c86edf318849f73784d70bf0ea63b091f52a4d3bc34efe31a` | 7286 |
| `p9841_a040.txt` | Per-point script of synthetic tier-3 case 9841, alpha 4. | `123f7c314749030e7811db912c7e967a4c7bdd99fe4bcea0cd0acc09c260ca64` | 7286 |
