# RPT-040: the reproduction of the author's recorded campaign, coefficient by coefficient (2026-09-03)

**PFS-2030.07.** Every number in the tables below is read from a loads table on disk by
the GOAL-011 checker of the estate that hosts this repository (its
`--write-report`, outside this tree), and its `--report` regenerates these
tables and refuses a report whose numbers it cannot reproduce. The
recorded tables are the author's campaign on FlightStream
build #7012026 (registry 26.120); the reproduced tables are pyflightstream
0.11.0 running the same build through the workflow scheme. The arbiter is
the repeatability control: her recorded script for the unsteady point run
again unchanged, whose largest difference from the recorded table is the
band a reproduction may differ by without being a regression (PFS-2030.06).

## The repeatability control

Point POLAR-3224_M20AL+000BE+000J+130, recorded against re-run as recorded.
Band: **0.0000000**; the two tables are identical, coefficient for coefficient, so the criterion the selected points meet below is identity, not a tolerance. The control was run through the solver again (its log and its exports sit beside the table), so a zero band is the solver's determinism on this build, not a cached result.

| surface | coefficient | recorded | reproduced | difference |
|---|---|---|---|---|
| W | Cx | +0.0088267 | +0.0088267 | 0.0000000 |
| W | Cy | -0.0042794 | -0.0042794 | 0.0000000 |
| W | Cz | +0.1587538 | +0.1587538 | 0.0000000 |
| W | CL | +0.1592613 | +0.1592613 | 0.0000000 |
| W | CDi | +0.0027949 | +0.0027949 | 0.0000000 |
| W | CDo | +0.0060318 | +0.0060318 | 0.0000000 |
| W | CMx | -0.3085139 | -0.3085139 | 0.0000000 |
| W | CMy | -0.0033387 | -0.0033387 | 0.0000000 |
| W | CMz | +0.0180542 | +0.0180542 | 0.0000000 |
| B | Cx | +0.0035914 | +0.0035914 | 0.0000000 |
| B | Cy | -0.0750427 | -0.0750427 | 0.0000000 |
| B | Cz | +0.0209440 | +0.0209440 | 0.0000000 |
| B | CL | +0.0209110 | +0.0209110 | 0.0000000 |
| B | CDi | -0.0000213 | -0.0000213 | 0.0000000 |
| B | CDo | +0.0036127 | +0.0036127 | 0.0000000 |
| B | CMx | +0.0328812 | +0.0328812 | 0.0000000 |
| B | CMy | -0.0298749 | -0.0298749 | 0.0000000 |
| B | CMz | +0.0026953 | +0.0026953 | 0.0000000 |
| Total | Cx | +0.0124181 | +0.0124181 | 0.0000000 |
| Total | Cy | -0.0793221 | -0.0793221 | 0.0000000 |
| Total | Cz | +0.1796978 | +0.1796978 | 0.0000000 |
| Total | CL | +0.1801724 | +0.1801724 | 0.0000000 |
| Total | CDi | +0.0027736 | +0.0027736 | 0.0000000 |
| Total | CDo | +0.0096445 | +0.0096445 | 0.0000000 |
| Total | CMx | -0.2756327 | -0.2756327 | 0.0000000 |
| Total | CMy | -0.0332135 | -0.0332135 | 0.0000000 |
| Total | CMz | +0.0207495 | +0.0207495 | 0.0000000 |

## steady row 3207: POLAR-3207_M20AL-020BE+000

Largest difference 0.0000000, no coefficient differs; within the band 0.0000000.

| surface | coefficient | recorded | reproduced | difference | within the band |
|---|---|---|---|---|---|
| W | Cx | +0.0193288 | +0.0193288 | 0.0000000 | yes |
| W | Cy | +0.0000000 | +0.0000000 | 0.0000000 | yes |
| W | Cz | +0.1620516 | +0.1620516 | 0.0000000 | yes |
| W | CL | +0.1631176 | +0.1631176 | 0.0000000 | yes |
| W | CDi | +0.0012085 | +0.0012085 | 0.0000000 | yes |
| W | CDo | +0.0124530 | +0.0124530 | 0.0000000 | yes |
| W | CMx | +0.0000000 | +0.0000000 | 0.0000000 | yes |
| W | CMy | -0.0077298 | -0.0077298 | 0.0000000 | yes |
| W | CMz | +0.0000000 | +0.0000000 | 0.0000000 | yes |
| B | Cx | +0.0081039 | +0.0081039 | 0.0000000 | yes |
| B | Cy | +0.0000000 | +0.0000000 | 0.0000000 | yes |
| B | Cz | +0.0251062 | +0.0251062 | 0.0000000 | yes |
| B | CL | +0.0251653 | +0.0251653 | 0.0000000 | yes |
| B | CDi | +0.0000333 | +0.0000333 | 0.0000000 | yes |
| B | CDo | +0.0071894 | +0.0071894 | 0.0000000 | yes |
| B | CMx | -0.0000000 | -0.0000000 | 0.0000000 | yes |
| B | CMy | -0.0892137 | -0.0892137 | 0.0000000 | yes |
| B | CMz | +0.0000000 | +0.0000000 | 0.0000000 | yes |
| Total | Cx | +0.0274326 | +0.0274326 | 0.0000000 | yes |
| Total | Cy | +0.0000000 | +0.0000000 | 0.0000000 | yes |
| Total | Cz | +0.1871579 | +0.1871579 | 0.0000000 | yes |
| Total | CL | +0.1882829 | +0.1882829 | 0.0000000 | yes |
| Total | CDi | +0.0012418 | +0.0012418 | 0.0000000 | yes |
| Total | CDo | +0.0196424 | +0.0196424 | 0.0000000 | yes |
| Total | CMx | -0.0000000 | -0.0000000 | 0.0000000 | yes |
| Total | CMy | -0.0969435 | -0.0969435 | 0.0000000 | yes |
| Total | CMz | +0.0000000 | +0.0000000 | 0.0000000 | yes |

## unsteady row 3224: POLAR-3224_M20AL+000BE+000J+130

Largest difference 0.0000000, no coefficient differs; within the band 0.0000000.

| surface | coefficient | recorded | reproduced | difference | within the band |
|---|---|---|---|---|---|
| W | Cx | +0.0088267 | +0.0088267 | 0.0000000 | yes |
| W | Cy | -0.0042794 | -0.0042794 | 0.0000000 | yes |
| W | Cz | +0.1587538 | +0.1587538 | 0.0000000 | yes |
| W | CL | +0.1592613 | +0.1592613 | 0.0000000 | yes |
| W | CDi | +0.0027949 | +0.0027949 | 0.0000000 | yes |
| W | CDo | +0.0060318 | +0.0060318 | 0.0000000 | yes |
| W | CMx | -0.3085139 | -0.3085139 | 0.0000000 | yes |
| W | CMy | -0.0033387 | -0.0033387 | 0.0000000 | yes |
| W | CMz | +0.0180542 | +0.0180542 | 0.0000000 | yes |
| B | Cx | +0.0035914 | +0.0035914 | 0.0000000 | yes |
| B | Cy | -0.0750427 | -0.0750427 | 0.0000000 | yes |
| B | Cz | +0.0209440 | +0.0209440 | 0.0000000 | yes |
| B | CL | +0.0209110 | +0.0209110 | 0.0000000 | yes |
| B | CDi | -0.0000213 | -0.0000213 | 0.0000000 | yes |
| B | CDo | +0.0036127 | +0.0036127 | 0.0000000 | yes |
| B | CMx | +0.0328812 | +0.0328812 | 0.0000000 | yes |
| B | CMy | -0.0298749 | -0.0298749 | 0.0000000 | yes |
| B | CMz | +0.0026953 | +0.0026953 | 0.0000000 | yes |
| Total | Cx | +0.0124181 | +0.0124181 | 0.0000000 | yes |
| Total | Cy | -0.0793221 | -0.0793221 | 0.0000000 | yes |
| Total | Cz | +0.1796978 | +0.1796978 | 0.0000000 | yes |
| Total | CL | +0.1801724 | +0.1801724 | 0.0000000 | yes |
| Total | CDi | +0.0027736 | +0.0027736 | 0.0000000 | yes |
| Total | CDo | +0.0096445 | +0.0096445 | 0.0000000 | yes |
| Total | CMx | -0.2756327 | -0.2756327 | 0.0000000 | yes |
| Total | CMy | -0.0332135 | -0.0332135 | 0.0000000 | yes |
| Total | CMz | +0.0207495 | +0.0207495 | 0.0000000 | yes |

## unsteady_rotor row 9001: POLAR-9001_M14AL+000BE+000J+170

Largest difference 0.0000000, no coefficient differs; within the band 0.0000000.

| surface | coefficient | recorded | reproduced | difference | within the band |
|---|---|---|---|---|---|
| Blade1 | Cx | -0.0091985 | -0.0091985 | 0.0000000 | yes |
| Blade1 | Cy | -0.0092181 | -0.0092181 | 0.0000000 | yes |
| Blade1 | Cz | -0.0002462 | -0.0002462 | 0.0000000 | yes |
| Blade1 | CL | -0.0002457 | -0.0002457 | 0.0000000 | yes |
| Blade1 | CDi | -0.0094041 | -0.0094041 | 0.0000000 | yes |
| Blade1 | CDo | +0.0002056 | +0.0002056 | 0.0000000 | yes |
| Blade1 | CMx | -0.0044168 | -0.0044168 | 0.0000000 | yes |
| Blade1 | CMy | +0.0047622 | +0.0047622 | 0.0000000 | yes |
| Blade1 | CMz | +0.0000289 | +0.0000289 | 0.0000000 | yes |
| S | Cx | -0.0000531 | -0.0000531 | 0.0000000 | yes |
| S | Cy | -0.0000506 | -0.0000506 | 0.0000000 | yes |
| S | Cz | -0.0015687 | -0.0015687 | 0.0000000 | yes |
| S | CL | -0.0015660 | -0.0015660 | 0.0000000 | yes |
| S | CDi | -0.0000866 | -0.0000866 | 0.0000000 | yes |
| S | CDo | +0.0000335 | +0.0000335 | 0.0000000 | yes |
| S | CMx | -0.0000013 | -0.0000013 | 0.0000000 | yes |
| S | CMy | -0.0001318 | -0.0001318 | 0.0000000 | yes |
| S | CMz | +0.0000043 | +0.0000043 | 0.0000000 | yes |
| N | Cx | +0.0002328 | +0.0002328 | 0.0000000 | yes |
| N | Cy | +0.0000027 | +0.0000027 | 0.0000000 | yes |
| N | Cz | +0.0035167 | +0.0035167 | 0.0000000 | yes |
| N | CL | +0.0035624 | +0.0035624 | 0.0000000 | yes |
| N | CDi | +0.0001140 | +0.0001140 | 0.0000000 | yes |
| N | CDo | +0.0001188 | +0.0001188 | 0.0000000 | yes |
| N | CMx | +0.0000000 | +0.0000000 | 0.0000000 | yes |
| N | CMy | -0.0042820 | -0.0042820 | 0.0000000 | yes |
| N | CMz | +0.0000013 | +0.0000013 | 0.0000000 | yes |
| Total | Cx | -0.0090188 | -0.0090188 | 0.0000000 | yes |
| Total | Cy | -0.0092660 | -0.0092660 | 0.0000000 | yes |
| Total | Cz | +0.0017018 | +0.0017018 | 0.0000000 | yes |
| Total | CL | +0.0017507 | +0.0017507 | 0.0000000 | yes |
| Total | CDi | -0.0093767 | -0.0093767 | 0.0000000 | yes |
| Total | CDo | +0.0003579 | +0.0003579 | 0.0000000 | yes |
| Total | CMx | -0.0044181 | -0.0044181 | 0.0000000 | yes |
| Total | CMy | +0.0003484 | +0.0003484 | 0.0000000 | yes |
| Total | CMz | +0.0000344 | +0.0000344 | 0.0000000 | yes |

## The cold-run control: POLAR-3207_M20AL+000BE+000

Her recorded point was warm-started from the previous angle; the reproduction
runs it cold through the workflow. The difference is reported, not bound by
the band: largest 0.0025969 at Total.Cz.

| surface | coefficient | recorded | reproduced | difference |
|---|---|---|---|---|
| W | Cx | +0.0173192 | +0.0176176 | 0.0002984 |
| W | Cy | +0.0000000 | +0.0000000 | 0.0000000 |
| W | Cz | +0.3207254 | +0.3229156 | 0.0021902 |
| W | CL | +0.3217189 | +0.3238804 | 0.0021615 |
| W | CDi | +0.0047076 | +0.0047691 | 0.0000615 |
| W | CDo | +0.0126116 | +0.0128485 | 0.0002369 |
| W | CMx | -0.0000000 | +0.0000000 | 0.0000000 |
| W | CMy | -0.0077468 | -0.0082302 | 0.0004834 |
| W | CMz | +0.0000000 | +0.0000000 | 0.0000000 |
| B | Cx | +0.0072467 | +0.0072475 | 0.0000008 |
| B | Cy | +0.0000000 | +0.0000000 | 0.0000000 |
| B | Cz | +0.0427982 | +0.0432049 | 0.0004067 |
| B | CL | +0.0427389 | +0.0431470 | 0.0004081 |
| B | CDi | +0.0000212 | +0.0000212 | 0.0000000 |
| B | CDo | +0.0072256 | +0.0072262 | 0.0000006 |
| B | CMx | -0.0000000 | -0.0000000 | 0.0000000 |
| B | CMy | -0.0600705 | -0.0603177 | 0.0002472 |
| B | CMz | +0.0000000 | +0.0000000 | 0.0000000 |
| Total | Cx | +0.0245659 | +0.0248651 | 0.0002992 |
| Total | Cy | +0.0000000 | +0.0000000 | 0.0000000 |
| Total | Cz | +0.3635236 | +0.3661205 | 0.0025969 |
| Total | CL | +0.3644578 | +0.3670274 | 0.0025696 |
| Total | CDi | +0.0047287 | +0.0047903 | 0.0000616 |
| Total | CDo | +0.0198372 | +0.0200748 | 0.0002376 |
| Total | CMx | -0.0000000 | -0.0000000 | 0.0000000 |
| Total | CMy | -0.0678172 | -0.0685478 | 0.0007306 |
| Total | CMz | +0.0000000 | +0.0000000 | 0.0000000 |

## The scripts, verb for verb

- scripts 3 of 3 within the allow-list: the three rendered scripts against her recorded ones, outside an enumerated allow-list nothing differs.
- her recorded unsteady 3224 script states `DELTA_TIME 0.00388`; the package derives the step from the azimuthal pair [^rounding]
- her recorded unsteady_rotor 9001 script states `SET_MOTION_ROTOR_RPM 1 473.1723 0.0 0.0`; the package derives the speed from the advance ratio and emits it at four decimals, her tool's precision
- her recorded unsteady_rotor 9001 script states `DELTA_TIME 0.00352`; the package derives the step from the azimuthal pair [^rounding]

[^rounding]: CORRECTED 2026-09-04, and the correction is the author's own.
    Both lines said the package emits the derived step at five decimals, her
    tool's precision. It does not and should not: her word that day was that
    the rounding belongs to the file she typed rather than to what a run
    emits, and rounding would end a run at an azimuth nobody chose, which is
    what stating the revolutions exists to prevent. The package emits the
    derivation whole, 0.0038813952731 and 0.0035223250952, and the difference
    against her two recorded values is an allow-list entry of the scripts arm
    rather than an emission that matches them. The measurement this report
    carries, 3 of 3 within the allow-list, is unaffected; what was wrong was
    the sentence explaining WHY. Found by a technical-writing review of the
    v0.12.0 release.

## The products and the export set

- products 32 of 32 equal
- exports 3 of 3 complete on 26.120

## Reproduction

Measured on: 2026-09-03, on the licensed seat that holds build #7012026, by the estate's GOAL-011 checker. To re-take: run the
reproduction workspace's matrix through `pyfs-matrix run`, run the
repeatability control beside it, and regenerate this report with the
checker's `--write-report`; `--report` then refuses any number that moved.
The recorded tables live in the author's own campaign folder, which is
machine-local and named in no versioned file.
