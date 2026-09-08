@echo off
rem The shell command the action re-read probe registers as a COMMAND_LINE
rem action (GOAL-012 item 7b, PFS-2031.08). The solver runs it after every
rem unsteady time step; it runs actions_probe.py beside it with the Python
rem named by PYFS_PYTHON when that is set, and the python on the PATH the
rem solver inherited otherwise. Nothing documented says which directory an
rem action runs from, so the script is addressed by this file's own folder.
if defined PYFS_PYTHON (
  "%PYFS_PYTHON%" "%~dp0actions_probe.py" %*
) else (
  python "%~dp0actions_probe.py" %*
)
