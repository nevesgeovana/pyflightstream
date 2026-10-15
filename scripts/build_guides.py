"""Build downloadable guides from source into an artifact directory.

Run ``python scripts/build_guides.py`` with pdflatex and the plot extra installed.
Sources and figure generation run in a temporary copy; no tracked file is written.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def print_failure_log(log_path: Path) -> None:
    """Show bounded TeX diagnostics without replacing the build failure."""
    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as error:
        print(f"Guide log unavailable: {log_path}: {error}", file=sys.stderr)
        return
    print(f"Last 80 lines of {log_path}:", file=sys.stderr)
    print("\n".join(lines[-80:]), file=sys.stderr)
    for index, line in enumerate(lines):
        if line.startswith("!"):
            print("First TeX error and 10 following lines:", file=sys.stderr)
            print("\n".join(lines[index : index + 11]), file=sys.stderr)
            break


def build(output: Path) -> None:
    """Compile the nine decks and user guide, preserving logs and source hashes."""
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    compiler = shutil.which("pdflatex")
    if compiler is None:
        raise RuntimeError("Install TeX Live or MiKTeX with pdflatex to build the guides")
    version = subprocess.check_output(
        [compiler, "--version"], text=True, env=os.environ.copy()
    ).splitlines()[0]
    inputs = {}
    receipts = []
    with tempfile.TemporaryDirectory(prefix="guide-sources-", dir=output.parent) as temporary:
        source = Path(temporary) / "guide"
        tracked = subprocess.check_output(
            ["git", "-C", str(ROOT), "ls-files", "--", "guide"],
            text=True,
            env=os.environ.copy(),
        )
        for name in tracked.splitlines():
            path = ROOT / name
            if any(p.is_symlink() or p.is_junction() for p in (path, *path.parents)):
                raise ValueError(f"Guide source must not traverse a link: {path}")
            if path.suffix not in {".tex", ".py", ".md"} or "build" in path.parts:
                continue
            relative = path.relative_to(ROOT / "guide")
            target = source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            data = path.read_bytes()
            target.write_bytes(data)
            inputs[path.relative_to(ROOT).as_posix()] = hashlib.sha256(data).hexdigest()
        latex = source / "latex-sources"
        figure = latex / "02-workspaces/figures/qsteady_reduced_frequency.py"
        subprocess.run([sys.executable, str(figure)], check=True, env=os.environ.copy())
        jobs = [(p, f"pyfts-guide-{p.parent.name}") for p in sorted(latex.glob("0*/main.tex"))]
        jobs.append((source / "pyflightstream_user_guide.tex", "pyflightstream_user_guide"))
        for tex, name in jobs:
            working = latex / "shared" if tex.name == "main.tex" else source
            env = os.environ.copy()
            env["TEXINPUTS"] = os.pathsep.join(
                [str(tex.parent) + "//", str(latex / "shared") + "//", ""]
            )
            command = [compiler, "-interaction=nonstopmode", "-halt-on-error"]
            if "MiKTeX" in version:
                command += [
                    f"-include-directory={tex.parent}",
                    f"-include-directory={latex / 'shared'}",
                ]
            command += [f"-output-directory={output}", f"-jobname={name}", str(tex)]
            for _ in range(3):
                done = subprocess.run(
                    command, cwd=working, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
                )
                if done.returncode:
                    print_failure_log(output / (name + ".log"))
                    raise RuntimeError(f"Guide build failed: see {output / (name + '.log')}")
            pdf = output / f"{name}.pdf"
            log_path = output / f"{name}.log"
            log = log_path.read_text(encoding="utf-8", errors="replace")
            if re.search(r"(?m)^Overfull|^!", log):
                print_failure_log(log_path)
                raise RuntimeError(f"Guide has a layout or TeX error: {log_path}")
            for local in (str(ROOT), str(Path(temporary)), str(output)):
                log = log.replace(local, "<build>").replace(local.replace("\\", "/"), "<build>")
            log = re.sub(r"[A-Za-z]:[\\/][^\s()]+", "<local-path>", log)
            log_path.write_text(log, encoding="utf-8")
            receipts.append(
                {
                    "name": pdf.name,
                    "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
                    "log_sha256": hashlib.sha256(log_path.read_bytes()).hexdigest(),
                    "exit_status": 0,
                }
            )
            print(f"Built {pdf.name}", flush=True)
    record = {"typesetter": version, "source_sha256": inputs, "pdfs": receipts}
    (output / "build-record.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    shutil.copyfile(ROOT / "guide/LICENSE-AND-AUTHORSHIP.md", output / "LICENSE-AND-AUTHORSHIP.md")


def main() -> None:
    """Build guides at the requested output location."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "build/guides")
    build(parser.parse_args().output)


if __name__ == "__main__":
    main()
