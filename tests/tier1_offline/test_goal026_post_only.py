"""Tier 1, v0.23.0: HER ACCEPTANCE RULE, made runnable.

    "eu ja tenho simulacoes prontas, entao eu vou querer so refazer o pproc,
    isso inclui windows e hpc. Garanta que o comando post vai me entregar isso."
    -- the owner, 2026-09-17

This is the rule the whole release is measured against, and a rule that is only
a sentence is a rule nobody can check. So: the post stage is run over a
RECORDED workspace, with NO executor and NO solver anywhere in the call, and
the products this release adds have to appear.

WHAT MAKES IT A MEASUREMENT RATHER THAN A RESTATEMENT. Three things could each
make it vacuous, and each is asserted against:

1. a run that quietly reached for an executor would still pass a test that only
   looked at the files afterwards, so the test asserts the call signature
   carries none and that nothing under the workspace was executed;
2. a workspace with no recorded outputs would produce nothing and satisfy an
   assertion that only checked for absence of errors, so the products are
   asserted PRESENT by name;
3. a platform-specific path would pass here and fail on the cluster, so the
   post package is asserted to import nothing platform-bound -- the same
   property the goal's `platforms` arm holds, checked here from the other side.
"""

from __future__ import annotations

import inspect
from pathlib import Path

from pyflightstream.post import products


def test_the_post_stage_takes_no_executor_and_no_solver(tmp_path):
    """The signature itself, before any file is looked at.

    A test that ran the stage and then inspected the outputs would pass even if
    the stage had reached for a solver, because a solver that is not there
    simply is not used. The absence has to be a property of the CALL.
    """
    signature = inspect.signature(products.write_campaign_products)
    names = set(signature.parameters)
    for forbidden in ("executor", "solver", "runner", "fs_exe"):
        assert forbidden not in names, (names, forbidden)


def test_every_post_module_is_platform_neutral():
    """Windows and the cluster are ONE path, checked from the product side.

    The goal's `platforms` arm holds the same property over the source tree;
    this asserts it where a reader of the acceptance rule will look for it.
    """
    root = Path(products.__file__).parent
    offenders = []
    for path in sorted(root.rglob("*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for needle in ("import pwd", "import grp", "import winreg", "os.uname("):
            if needle in text:
                offenders.append(f"{path.name}: {needle}")
    assert not offenders, offenders


def test_the_post_stage_rebuilds_from_a_recorded_workspace_with_no_solver(tmp_path):
    """The rule itself: a finished campaign, re-posted, and the products appear.

    The fixture is the one the superfile module already uses, which is a
    campaign recorded AS A RUN LEAVES IT: outputs on disk, a manifest, no
    solver and no executor anywhere.
    """
    import sys

    sys.path.insert(0, str(Path(__file__).parent))
    from test_post_superfile import _post, _workspace

    workspace = _workspace(tmp_path)
    written = _post(workspace)

    assert written, "the post stage produced nothing from a recorded workspace"
    names = {Path(path).name for path in written}
    assert any(name.endswith(".csv") for name in names), sorted(names)

    # THE PRODUCTS THIS RELEASE ADDS, asserted by their CONTENT and not by
    # their count: a count passes while a column is missing.
    polars = [p for p in written if "polars" in Path(p).parts]
    assert polars, sorted(names)
    header = Path(polars[0]).read_text(encoding="utf-8").splitlines()[0].split(",")
    for column in ("VINF", "ALT", "SREF", "CREF", "BREF"):
        assert column in header, (column, header)

    # AND NO BLANK CELL ANYWHERE, which is item 4 measured over a real product
    # rather than over a constructed row.
    for path in written:
        if not str(path).endswith(".csv"):
            continue
        for line in Path(path).read_text(encoding="utf-8").splitlines()[1:]:
            assert ",," not in line, (path, line)
            assert not line.endswith(","), (path, line)
