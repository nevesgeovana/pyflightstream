# RPT-086 - The windows FlightStream 26.124 shows when launched with its GUI (2026-09-28)

A no-solve probe on **FlightStream 26.124, build 8172026**, executable SHA-256
withheld from the public tree per NFR-31 (the
executable of [RPT-085](RPT-085_native-workspace-evidence_2026-09-27.md)). It
establishes which top-level windows that build opens in the first 40 s after a
launch WITHOUT `-hidden` and without a script, which is how a matrix row
stating `HIDDEN 0` launches it. It does not establish the behaviour of any
other build, nor of a launch that runs a script.

## Why it was run

A row stating `HIDDEN 0` ran under 0.29.0 and was killed within 2 s as
`FAILED_EXECUTION`, "solver dialog contains no readable text": the local
executor's window watcher (`run/_solver_windows.py`) selected a window of the
solver and found no text in it. That message is produced only for a window
with no title and no readable control text, so the window killed was not the
titled main window. The probe asks which window it was.

## Method

The executable was started with no argument (no `-hidden`, no script). Every
0.5 s for 40 s, every top-level window of that exact process id was read:
class, title, visibility, enabled state, owner, whether its owner was disabled
(the package's own `modal` test), window style, size, and the class and text of
up to twelve child controls. Nothing was clicked. The process tree was then
terminated and `tasklist` confirmed that no process of that id remained. The
record is [RPT-086_gui-launch-windows_2026-09-28.json](RPT-086_gui-launch-windows_2026-09-28.json).

## Result

| t (s) | class | title | visible | modal (package test) | size (px) | children |
|---|---|---|---|---|---|---|
| 0.5 | `ChimeraMain` | `FlightStream` | no | no | 960 x 475 | MDIClient, Chimera, RICHEDIT, ... |
| 1.0 | `#32770` | (empty) | **yes** | **yes** | 700 x 525 | one `Static`, empty text |
| 3.0 | `ChimeraMain` | `FlightStream (simulation: ~/Default.fsm)` | yes | no | 1296 x 688 | MDIClient, Chimera, RICHEDIT, ... |

- The main window is class `ChimeraMain` and titled; the 0.29.0 watcher never
  selects it (it is not `#32770`, not modal, and its title names no error).
- For about two seconds after launch, a startup splash of class `#32770` is
  visible, modal over the main window (its owner is disabled), with no title,
  one image control with no text and NO button. It closes by itself.
- That splash matches every condition of the 0.29.0 selection and yields
  exactly "solver dialog contains no readable text": it is the window killed.

## An independent reading on the tier-3 GUI matrix

The same day, the licensed tier-3 workspace at the v0.29.0 tag ran
`tests/tier3_licensed/matriz_gui.fs` through `pyfs-matrix run`: its seven rows
(5007, 5008, 5009, 5010, 5012, 5013, 5014) all state `HIDDEN 0`, and all nine
points failed. Every one of the 64 failure lines in that workspace's
`logs/activity.log` carries the same text, "solver modal/error detected ...
solver dialog contains no readable text", about 2 s after each launch. There is
no other failure text. The same machine launched the solver directly (hidden,
with a script) 88 times in the same session without a failure. That is the
defect this report measures, on the path it predicts.

## What 0.30.0 does with it

A window of the solver with no title, no readable text and no button control
asks nothing of anyone and is spared (`asks_nothing`,
`run/_solver_windows.py`); it is written once to the point's
`pyfs-solver-windows.log`. A window with a title, any readable text or any
button is still a dialog and still ends the point. The tier-1 test
`tests/tier1_offline/test_goal035_splash_window.py` uses the window this
report measured.

## What is not established

- A complete `HIDDEN 0` run on 26.124 with the 0.30.0 watcher (the solve that
  survives the splash) has not been run; it is owed, and `matriz_gui.fs` is
  the natural run for it.
- Other builds are not measured; their splash may differ.
