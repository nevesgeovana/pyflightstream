"""Post a campaign normally to warn, or pass check_frozen=True to refuse doubts."""

import json
import re

import pytest

from pyflightstream import __version__
from pyflightstream.post.products import freeze_of_log, write_campaign_products
from pyflightstream.results import UnjudgeableSolve
from tests.tier1_offline.test_b01_frozen_solve import (
    _log,
    _make_one_step_unreadable,
    _post_workspace,
    _products_manifest,
)


def test_every_post_writes_and_archives_its_log(tmp_path):
    workspace = _post_workspace(tmp_path, 2411, (60, 61))
    write_campaign_products(workspace)
    manifest = _products_manifest(workspace)
    assert manifest.get("log") == "post.log", "a clean post names no log"
    log = workspace.products_dir(None) / manifest["log"]
    before = log.read_bytes()
    text = before.decode()
    # THE PACKAGE'S OWN VERSION, not a literal: the literal "0.26.0" passed on
    # the release tree and failed CI on the post-tag commit that opened
    # 0.27.0.dev0 (2026-09-23), a version macro re-dating a claim.
    assert all(
        word in text for word in (__version__, str(workspace.root), "matrix", "time", "False")
    )
    for name, reason in manifest["skipped"].items():
        assert name in text and reason in text
    write_campaign_products(workspace, overwrite=True)
    copies = list(log.parent.glob("archive/*/post.log"))
    assert len(copies) == 1 and copies[0].read_bytes() == before


def test_default_keeps_every_product_with_frozen_and_unread_steps(tmp_path):
    """Since 0.26.0 doubts warn in post.log and never withhold computable products."""
    workspace = _post_workspace(tmp_path, 2411, (58, 61))
    write_campaign_products(workspace)
    baseline = set(_products_manifest(workspace)["products"])
    path = workspace.sim_dir("7001") / "datapoints/DP-AL-020/AL-020_log.txt"
    path.write_text(_log(2413), encoding="utf-8")
    _make_one_step_unreadable(workspace, 58)
    write_campaign_products(workspace, overwrite=True)
    manifest = _products_manifest(workspace)
    assert set(manifest["products"]) == baseline
    log = workspace.products_dir(None) / "post.log"
    assert log.is_file(), "frozen and unread steps have no post log"
    lines = log.read_text(encoding="utf-8").splitlines()
    assert any(
        all(
            word in line
            for word in ("WARNING", "AL-020", "time_average", "58", "unread", "recollect")
        )
        for line in lines
    )
    assert any(
        all(word in line for word in ("WARNING", "AL-020", "time_average", "60", "frozen", "run"))
        for line in lines
    )


@pytest.mark.parametrize("asked", [False, True])
def test_partial_iteration_anchor_is_unread_at_the_product(tmp_path, asked):
    workspace = _post_workspace(tmp_path, 2413, (60, 61))
    path = workspace.sim_dir("7001") / "datapoints/DP-AL-020/AL-020_log.txt"
    text = path.read_text(encoding="utf-8")
    anchor = text.index("Iteration", text.rfind("Solving unsteady time-step iteration"))
    path.write_text(text[: anchor + len("Iterat")], encoding="utf-8")
    verdict = freeze_of_log(path)
    assert isinstance(verdict, UnjudgeableSolve), "a cut before Iteration was treated as readable"
    assert 61 in verdict.steps
    write_campaign_products(workspace, check_frozen=asked)
    manifest = _products_manifest(workspace)
    product = "probes/AL-020_time_average.csv"
    assert (product in manifest["products"]) is not asked
    assert "61" in (workspace.products_dir(None) / "post.log").read_text()


@pytest.mark.parametrize("row", [2411, 2413])
def test_repeated_markers_are_not_unread(tmp_path, row):
    """A marker immediately followed by the same step is an export block, not a cut."""
    source = _log(row)
    repeated = re.sub(
        r"(Solving unsteady time-step iteration \(\d+/\d+\))", r"\1\nExporting...\n\1", source
    )
    path = tmp_path / "repeat.txt"
    path.write_text(repeated, encoding="utf-8")
    verdict = freeze_of_log(path)
    if row == 2411:
        assert verdict is None
    else:
        assert verdict is not None and not isinstance(verdict, UnjudgeableSolve)
        assert (verdict.first_step, verdict.count) == (60, 2)


@pytest.mark.parametrize("shape", ["totals", "fractional", "alias"])
@pytest.mark.parametrize("asked", [False, True])
@pytest.mark.parametrize("inside", [False, True])
def test_reducer_samples_control_product_warning_or_refusal(tmp_path, shape, asked, inside):
    from tests.tier1_offline.test_unread_steps_and_freezes import _log as blocks

    workspace = _post_workspace(tmp_path, 2411, (59, 61), rotor=True)
    reference = workspace.inputs_dir / "references" / "r002.toml"
    if shape == "alias":
        reference.write_text(reference.read_text() + '\n[aliases]\nB = ["Blade1", "Blade2"]\n')
    else:
        reference.write_text(
            reference.read_text().replace(
                'families_blades = ["B"]', 'families_blades = ["Blade1", "Blade2"]'
            )
        )
    records = json.loads((workspace.root / "runs.json").read_text())
    span, depth, last, first = (3.6, 4.0, 20, 6) if shape == "fractional" else (3.0, 1.0, 61, 59)
    entry = {
        "windows": [[first, last]],
        "shape": "azimuthal",
        "revolutions": depth,
        "steps_per_revolution": span,
    }
    plan = records[0]["reductions"]
    plan["phase_locked"] = entry
    plan["rotors"] = {
        "PUSHER": {
            "blades": 2,
            "blade_families": (["B"] if shape == "alias" else ["Blade1", "Blade2"]),
            "rpm": 2200.0,
            "blade1_azimuth_deg": 0.0,
            "phase_locked": entry,
        }
    }
    (workspace.root / "runs.json").write_text(json.dumps(records))
    raw = workspace.sim_dir("7001") / "datapoints/DP-AL-020"
    if shape != "alias":
        path = raw / "AL-020_plots.txt"
        lines = path.read_text().splitlines()
        path.write_text(
            "\n".join(
                line.rsplit(",", 3)[0] + ","
                if re.match(r"\d+\.0000,", line)
                else line.replace(",CL_MRP_Blade1,CL_MRP_Blade2", "")
                for line in lines
            )
            + "\n"
        )
    earliest = 58 if shape == "alias" else first
    unread = earliest if inside else earliest - 1
    (raw / "AL-020_log.txt").write_text(
        blocks(*[(step, "unread" if step == unread else "live") for step in range(1, 62)])
    )
    write_campaign_products(workspace, matrix_stem="products", check_frozen=asked)
    manifest = _products_manifest(workspace)
    product = "probes/AL-020_phase_locked_PUSHER.csv"
    assert (product in manifest["products"]) is not (inside and asked), manifest["skipped"]
    log = workspace.products_dir("products") / "post.log"
    assert log.is_file(), "the product's sample verdict was not logged"
    affected = [
        line for line in log.read_text().splitlines() if product in line and "unread" in line
    ]
    assert bool(affected) is inside, affected


@pytest.mark.parametrize(
    ("span", "depth", "last", "columns", "expected"),
    [
        (3.0, 1.0, 61, ["CL_TOTAL"], {59, 60, 61}),
        (3.6, 4.0, 20, ["CL_TOTAL"], set(range(6, 21))),
        (3.0, 1.0, 61, ["CL_Blade1", "CL_Blade2"], {58, 59, 60, 61}),
        (2.0000000001, 1.0, 61, ["CL_Blade1", "CL_Blade2"], {59, 60, 61}),
    ],
)
def test_reducer_states_exactly_the_nonzero_samples(span, depth, last, columns, expected):
    import numpy as np

    from pyflightstream.post.unsteady import TimestepSeries, phase_locked_rows

    steps = np.arange(1, last + 1)
    series = TimestepSeries(
        steps=steps,
        times_s=None,
        points=np.zeros((1, 3)),
        fields={name: steps[:, None] for name in columns},
        sources=(),
    )
    read = set()
    rows = phase_locked_rows(
        series,
        columns,
        last_step=last,
        revolutions=depth,
        steps_per_revolution=span,
        blade1_azimuth_deg=0.0,
        blades=2,
        blade_families=["Blade1", "Blade2"],
        read_steps=read,
    )
    assert read == expected
    # The reported samples belong to the numerical path: perturb every plotted
    # value independently, and compare the rows the same reducer computes.
    for step in steps:
        changed = TimestepSeries(
            steps=steps,
            times_s=None,
            points=series.points,
            fields={name: values.astype(float).copy() for name, values in series.fields.items()},
            sources=(),
        )
        for values in changed.fields.values():
            values[step - 1] += 1e10
        measured = phase_locked_rows(
            changed,
            columns,
            last_step=last,
            revolutions=depth,
            steps_per_revolution=span,
            blade1_azimuth_deg=0.0,
            blades=2,
            blade_families=["Blade1", "Blade2"],
        )
        assert (measured != rows) is (int(step) in expected)


def test_every_stage_warning_is_logged_even_if_the_caller_filters_it(tmp_path, monkeypatch):
    import warnings

    from pyflightstream._errors import PyflightstreamWarning, warn
    from pyflightstream.post import products

    original = products._write_the_products

    def stage(*args, **kwargs):
        # THROUGH THE PACKAGE'S ROUTE since 0.27.0 (RPT-058): a stage warns with
        # `_errors.warn`, which the post's own sink collects, and a bare
        # `warnings.warn` is outside the package and is not logged.
        warn(
            "point=AL-020 product=probes: restore the missing probe coordinates",
            PyflightstreamWarning,
            stacklevel=2,
        )
        return original(*args, **kwargs)

    monkeypatch.setattr(products, "_write_the_products", stage)
    workspace = _post_workspace(tmp_path, 2411, (60, 61))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        write_campaign_products(workspace)
    assert (
        "restore the missing probe coordinates"
        in (workspace.products_dir(None) / "post.log").read_text()
    )


def test_a_clean_empty_campaign_also_has_a_log(tmp_path):
    from pyflightstream.workspace import CampaignWorkspace

    workspace = CampaignWorkspace.init(tmp_path / "empty")
    assert write_campaign_products(workspace) == []
    manifest = _products_manifest(workspace)
    assert manifest["log"] == "post.log"
    assert "WARNING" not in (workspace.products_dir(None) / "post.log").read_text()
    # R02: a clean post writes its machine-readable twin too, with no record.
    assert manifest.get("log_json") == "post.log.json", sorted(manifest)
    document = json.loads((workspace.products_dir(None) / "post.log.json").read_text())
    assert document["records"] == [], document


def test_failed_incomplete_point_keeps_computable_products_by_default(tmp_path):
    """Since 0.26.0 an unread block is a warning even on a failed record."""
    from pyflightstream.workspace import RunStatus

    workspace = _post_workspace(tmp_path, 2411, (58, 61), status=RunStatus.FAILED_INCOMPLETE_OUTPUT)
    _make_one_step_unreadable(workspace, 58)
    write_campaign_products(workspace)
    manifest = _products_manifest(workspace)
    assert "probes/AL-020_time_average.csv" in manifest["products"]
    assert "unread" in (workspace.products_dir(None) / "post.log").read_text()


def test_guard_judges_the_sample_set_not_its_envelope():
    import numpy as np

    from pyflightstream.post.products import _frozen_window_reason, _window_the_reduction_reads
    from pyflightstream.post.unsteady import TimestepSeries

    steps = np.array([1, 59, 60, 61])
    series = TimestepSeries(
        steps=steps,
        times_s=None,
        points=np.zeros((1, 3)),
        fields={"CL_Blade2": steps[:, None]},
        sources=(),
    )
    reads = _window_the_reduction_reads(
        "phase_locked",
        {"shape": "azimuthal", "revolutions": 1, "steps_per_revolution": 3},
        (59, 61),
        series,
        ["CL_Blade2"],
        2,
        {"families": ["Blade1", "Blade2"], "rpm": 1},
    )
    assert reads == {1, 59, 60, 61}
    assert _frozen_window_reason(UnjudgeableSolve(58, 1, steps=(58,)), reads) is None
    assert _frozen_window_reason(UnjudgeableSolve(1, 1, steps=(1,)), reads) is not None


def test_interrupted_post_keeps_its_log_and_warning(tmp_path, monkeypatch):
    from pyflightstream._errors import PyflightstreamWarning, warn
    from pyflightstream.post import products

    def interrupt(*args, **kwargs):
        warn(
            "point=AL-020 product=probe: restore the missing data",
            PyflightstreamWarning,
            stacklevel=2,
        )
        raise RuntimeError("interrupted by the test")

    monkeypatch.setattr(products, "_write_the_products", interrupt)
    workspace = _post_workspace(tmp_path, 2411, (60, 61))
    with pytest.raises(RuntimeError, match="interrupted by the test"):
        write_campaign_products(workspace)
    manifest = _products_manifest(workspace)
    assert manifest["log"] == "post.log" and manifest["complete"] is False
    log = (workspace.products_dir(None) / "post.log").read_text()
    assert "restore the missing data" in log and "interrupted by the test" in log
    # R02: the interrupted post writes its machine-readable twin too, and the
    # interrupted manifest names it.
    assert manifest.get("log_json") == "post.log.json", sorted(manifest)
    records = json.loads(
        (workspace.products_dir(None) / "post.log.json").read_text(encoding="utf-8")
    )["records"]
    assert {
        "point": "AL-020",
        "product": "probe",
        "message": "restore the missing data",
        "remedy": None,
    } in records, records
    assert any(
        (record["point"], record["product"], record["remedy"])
        == ("campaign", "stage", "correct the stated input and post again.")
        and "interrupted by the test" in record["message"]
        for record in records
    ), records


def _rendered(record):
    """The WARNING line of one record, spelled as the page states it (R02)."""
    remedy = f" Remedy: {record['remedy']}" if record["remedy"] else ""
    named = f"point={record['point']} product={record['product']}"
    return f"WARNING {named}: {record['message']}{remedy}"


def test_post_log_json_is_the_same_records_as_post_log(tmp_path):
    """post.log.json holds the records post.log renders, one per WARNING line, in order (R02).

    One lifted warning (the failed point's available exports) and one named
    skip with its remedy, so the comparison is never of two empty lists. The
    header lines are rendered from the document's own values, so the two files
    have one source for the header as well as for the records.
    """
    from pyflightstream.workspace import RunStatus

    workspace = _post_workspace(tmp_path, 2411, (58, 61), status=RunStatus.FAILED_INCOMPLETE_OUTPUT)
    _make_one_step_unreadable(workspace, 58)
    write_campaign_products(workspace, check_frozen=True)
    manifest = _products_manifest(workspace)
    assert manifest.get("log_json") == "post.log.json", sorted(manifest)
    out = workspace.products_dir(None)
    before = (out / manifest["log_json"]).read_bytes()
    document = json.loads(before)
    header = {key: document.get(key) for key in ("version", "workspace", "matrix", "check_frozen")}
    assert header == {
        "version": __version__,
        "workspace": str(workspace.root),
        "matrix": None,
        "check_frozen": True,
    }, header
    lines = (out / manifest["log"]).read_text(encoding="utf-8").splitlines()
    assert lines[:5] == [
        f"pyflightstream {document['version']} post",
        f"workspace={document['workspace']}",
        f"matrix={document['matrix']}",
        f"time={document['time']}",
        f"check_frozen={document['check_frozen']} (refuse instead of warn)",
    ], lines[:5]
    records = document["records"]
    assert all(set(record) == {"point", "product", "message", "remedy"} for record in records)
    # SAME RECORDS, SAME COUNT, SAME ORDER: every WARNING line is one record.
    assert [_rendered(record) for record in records] == [
        line for line in lines if line.startswith("WARNING ")
    ]
    skip = next(iter(manifest["skipped"]))
    assert any(record["point"] == skip and record["remedy"] for record in records), records
    # THE LIFT: the warning names its own point and product, and the record
    # carries them rather than `point=campaign product=stage` in front of them.
    assert any(
        record["product"] == "available-exports" and record["point"] != "campaign"
        for record in records
    ), records
    write_campaign_products(workspace, overwrite=True, check_frozen=True)
    copies = list(out.glob("archive/*/post.log.json"))
    assert len(copies) == 1 and copies[0].read_bytes() == before, copies


# RPT-058. Every wait below has a timeout and every join one longer than any
# wait, so a regression that deadlocks a post fails here instead of hanging CI.
_WAIT_S = 10
_JOIN_S = 30


def _witness(point):
    """Warn through a REAL package site, the one a frozen or unread window reaches.

    Not a warning written in the test: the route under test is the one the
    package's own sites take, so the witness takes it too, on either tree.
    """
    from pyflightstream.post import products

    products._judge_average(UnjudgeableSolve(1, 1, steps=(1,)), {1}, point=point, product="probe")


def _post_in_threads(workspaces, first, second, entered, ended=None):
    """Post two campaigns in two threads; ``second`` starts once ``entered`` is set.

    Each thread sets its event in ``ended``, if it has one, when its post has
    returned or raised. Returns each thread's exception by name, so an
    assertion inside a stage surfaces here; a thread still alive after the
    join is a failure of the test, never a hang.
    """
    import threading

    failures = {}

    def post(name):
        try:
            write_campaign_products(workspaces[name])
        except BaseException as error:
            failures[name] = error
        finally:
            if ended and name in ended:
                ended[name].set()

    threads = {
        name: threading.Thread(target=post, args=(name,), name=name, daemon=True)
        for name in (first, second)
    }
    threads[first].start()
    assert entered.wait(_WAIT_S), f"{first} never entered its post"
    threads[second].start()
    for thread in threads.values():
        thread.join(_JOIN_S)
    assert not any(thread.is_alive() for thread in threads.values()), "a post never ended"
    return failures


def _logs(workspaces):
    return {
        name: (workspace.products_dir(None) / "post.log").read_text(encoding="utf-8")
        for name, workspace in workspaces.items()
    }


@pytest.mark.parametrize("interrupt_b", [False, True])
def test_two_posts_in_two_threads_keep_their_own_warnings(tmp_path, monkeypatch, interrupt_b):
    """Each campaign's post.log holds its own warnings, and each thread re-emits its own.

    The ordering is RPT-058's: A enters its post, B enters its post, A warns
    while B collects, B warns, B ends first. On 0.26.0 both logs held both
    warnings and each warning was re-emitted by both threads.
    """
    import threading
    import warnings

    from pyflightstream.post import products
    from pyflightstream.workspace import CampaignWorkspace

    workspaces = {name: CampaignWorkspace.init(tmp_path / name.lower()) for name in "AB"}
    a_in, b_in, a_warned, b_done = (threading.Event() for _ in range(4))
    original_write = products._write_the_products
    original_replay = warnings.warn_explicit
    replayed = []

    def replay(message, *args, **kwargs):
        replayed.append((threading.current_thread().name, str(message)))
        return original_replay(message, *args, **kwargs)

    def stage(workspace, *args, **kwargs):
        if workspace.root == workspaces["A"].root:
            a_in.set()
            assert b_in.wait(_WAIT_S), "B never entered its post"
            _witness("campaign-A")
            a_warned.set()
            assert b_done.wait(_WAIT_S), "B's post never ended"
        else:
            b_in.set()
            assert a_warned.wait(_WAIT_S), "A never warned"
            _witness("campaign-B")
            if interrupt_b:
                raise RuntimeError("B interrupted by the test")
        return original_write(workspace, *args, **kwargs)

    monkeypatch.setattr(warnings, "warn_explicit", replay)
    monkeypatch.setattr(products, "_write_the_products", stage)
    failures = _post_in_threads(workspaces, "A", "B", a_in, ended={"B": b_done})
    assert "A" not in failures, failures.get("A")
    assert ("B" in failures) is interrupt_b, failures.get("B")

    logs = _logs(workspaces)
    # B FIRST: B's is the log RPT-058 measured holding A's warning.
    assert "campaign-A" not in logs["B"], logs["B"]
    assert logs["B"].count("campaign-B") == 1, logs["B"]
    assert "campaign-B" not in logs["A"], logs["A"]
    assert logs["A"].count("campaign-A") == 1, logs["A"]
    if interrupt_b:
        assert "B interrupted by the test" in logs["B"], logs["B"]
    ours = sorted(
        (thread, point)
        for thread, message in replayed
        for point in ("campaign-A", "campaign-B")
        if point in message
    )
    assert ours == [("A", "campaign-A"), ("B", "campaign-B")], ours


def test_one_posts_silenced_sweep_does_not_silence_another_post(tmp_path, monkeypatch):
    """A warning is never LOST to another post's sweep table (RPT-058's second form).

    The products stage reads the sweep table with that table's own warning
    silenced. On 0.26.0 the silencing was a process-wide filter, so a warning B
    raised while A was inside it reached neither campaign's log.
    """
    import threading

    from pyflightstream.post import products
    from pyflightstream.results import tables
    from pyflightstream.workspace import CampaignWorkspace

    workspaces = {name: CampaignWorkspace.init(tmp_path / name.lower()) for name in "AB"}
    a_in_sweep, b_in, b_warned = (threading.Event() for _ in range(3))
    original_sweep = tables.sweep_table
    original_write = products._write_the_products

    def sweep(workspace, *args, **kwargs):
        if workspace.root == workspaces["A"].root:
            a_in_sweep.set()
            assert b_warned.wait(_WAIT_S), "B never warned"
        return original_sweep(workspace, *args, **kwargs)

    def stage(workspace, *args, **kwargs):
        if workspace.root == workspaces["B"].root:
            b_in.set()
            assert a_in_sweep.wait(_WAIT_S), "A never reached its sweep table"
            _witness("campaign-B")
            b_warned.set()
        return original_write(workspace, *args, **kwargs)

    # `_sweep_rows` imports `sweep_table` when it is called, so the module
    # attribute is what it reads.
    monkeypatch.setattr(tables, "sweep_table", sweep)
    monkeypatch.setattr(products, "_write_the_products", stage)
    failures = _post_in_threads(workspaces, "B", "A", b_in)
    assert not failures, failures
    logs = _logs(workspaces)
    assert logs["B"].count("campaign-B") == 1, logs["B"]
    assert "campaign-B" not in logs["A"], logs["A"]


def test_the_sweep_tables_own_warning_stays_out_of_the_post_log(tmp_path, monkeypatch):
    """The sweep table's warning belongs to whoever asked for the table, not to the post.

    With its control: the same route from the stage itself IS logged, so a
    route that logged nothing could not pass the first assertion.
    """
    import pandas

    from pyflightstream._errors import PyflightstreamWarning, warn
    from pyflightstream.post import products
    from pyflightstream.results import tables

    original_write = products._write_the_products

    def sweep(*args, **kwargs):
        warn(
            "point=campaign product=sweep: sweep-table witness", PyflightstreamWarning, stacklevel=2
        )
        return pandas.DataFrame()

    def stage(*args, **kwargs):
        warn("point=campaign product=stage: stage witness", PyflightstreamWarning, stacklevel=2)
        return original_write(*args, **kwargs)

    monkeypatch.setattr(tables, "sweep_table", sweep)
    monkeypatch.setattr(products, "_write_the_products", stage)
    workspace = _post_workspace(tmp_path, 2411, (60, 61))
    write_campaign_products(workspace)
    log = (workspace.products_dir(None) / "post.log").read_text(encoding="utf-8")
    assert "stage witness" in log, log
    assert "sweep-table witness" not in log, log


def test_no_bare_warnings_warn_where_a_post_reaches():
    """Every warning under post/, results/ and cases/ goes through `_errors.warn`.

    A bare `warnings.warn` there would bypass the post's sink and be missing
    from post.log. The walk reads the package the test IMPORTED, and its
    floor keeps it from passing having found nothing.
    """
    import ast
    from pathlib import Path

    import pyflightstream

    package = Path(pyflightstream.__file__).parent
    bare = []
    routed = 0
    for folder in ("post", "results", "cases"):
        for path in sorted((package / folder).rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if not isinstance(node, ast.Call):
                    continue
                function = node.func
                if (
                    isinstance(function, ast.Attribute)
                    and function.attr == "warn"
                    and isinstance(function.value, ast.Name)
                    and function.value.id == "warnings"
                ):
                    bare.append((path.relative_to(package).as_posix(), node.lineno))
                elif isinstance(function, ast.Name) and function.id == "warn":
                    routed += 1
    sites = [f"{relative}:{line}" for relative, line in sorted(bare)]
    assert not sites, f"warn through pyflightstream._errors.warn instead: {sites}"
    assert routed >= 38, f"the walk found {routed} `warn(` calls, below the floor of 38"
