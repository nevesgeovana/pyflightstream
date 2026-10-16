"""Source-backed workspace inventory for the Understanding preview.

Paths come from AST declarations and executable path expressions. Descriptions
and conservative edit/delete advice are editorial interpretations of those
operations, not inferred permissions. No documentation prose is an input.
"""

from __future__ import annotations

import ast
import hashlib
import html


class Source:
    def __init__(self, root):
        self.root = root
        self.symbols = {}
        self.trees = {}
        self.sources = {}
        self.references = {}
        self._walk(root / "src/pyflightstream")

    def _walk(self, folder):
        for path in sorted(folder.iterdir()):
            if path.is_symlink() or path.is_junction():
                raise ValueError(f"Reparse point in workspace source inventory: {path}")
            if path.is_dir():
                self._walk(path)
            elif path.suffix == ".py":
                module = ".".join(path.relative_to(self.root / "src").with_suffix("").parts)
                module = module.removesuffix(".__init__")
                text = path.read_text(encoding="utf-8-sig")
                tree = ast.parse(text)
                self.trees[module] = tree
                self.sources[module] = (path, text)
                self._index(module, tree.body)

    def _index(self, module, body, prefix=""):
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = prefix + node.name
                self.symbols[module + ":" + name] = node
                self._index(module, node.body, name + ".")

    def evidence(self, anchor):
        node = self.symbols.get(anchor)
        if node is None:
            raise ValueError(f"Workspace ownership anchor no longer resolves: {anchor}")
        module = anchor.split(":")[0]
        path, text = self.sources[module]
        segment = ast.get_source_segment(text, node)
        return {
            "anchor": anchor,
            "path": path.relative_to(self.root).as_posix(),
            "line": node.lineno,
            "sha256": hashlib.sha256(segment.encode()).hexdigest(),
        }

    def value(self, module, name):
        for node in self.trees[module].body:
            targets = (
                node.targets
                if isinstance(node, ast.Assign)
                else ([node.target] if isinstance(node, ast.AnnAssign) else [])
            )
            if any(isinstance(t, ast.Name) and t.id == name for t in targets):
                return ast.literal_eval(node.value)
        raise ValueError(f"Missing path declaration: {module}:{name}")

    def literal_sites(self, value):
        # Comments and docstrings must not turn prose into source evidence.
        if not self.references:
            for module, tree in self.trees.items():
                docstrings = {
                    id(n.value)
                    for n in ast.walk(tree)
                    if isinstance(n, ast.Expr)
                    and isinstance(n.value, ast.Constant)
                    and isinstance(n.value.value, str)
                }
                for node in ast.walk(tree):
                    if (
                        isinstance(node, ast.Constant)
                        and id(node) not in docstrings
                        and isinstance(node.value, str)
                    ):
                        self.references.setdefault(node.value, []).append(
                            {
                                "path": self.sources[module][0].relative_to(self.root).as_posix(),
                                "line": node.lineno,
                            }
                        )
        return self.references.get(value, [])


def workspace_data(root):
    source = Source(root)
    rows = []
    ws = "pyflightstream.workspace"
    init = ws + ":CampaignWorkspace.init"
    collect = ws + ":CampaignWorkspace.collect_outputs"
    records = ws + ":CampaignWorkspace.read_manifest"
    post = "pyflightstream.post.products:write_campaign_products"
    input_delete = (
        "Only if no retained matrix or run needs it. Deletion removes an "
        "input needed for planning, reruns or recovery."
    )
    evidence_delete = (
        "Keep as evidence. Deletion loses recorded bytes and can prevent "
        "assessment, recovery or product rebuilding; use managed storage "
        "commands."
    )
    product_delete = (
        "Yes, if reproducible from retained records and exports. Run post "
        "again to rebuild; the inventory may otherwise name missing files."
    )

    def add(
        id,
        path,
        holds,
        writers=(),
        readers=(),
        edit="No",
        delete=evidence_delete,
        created="On demand",
        step=None,
        token=None,
        area=None,
        note="",
    ):
        if isinstance(writers, str):
            writers = (writers,)
        if isinstance(readers, str):
            readers = (readers,)
        sites = source.literal_sites(token) if token else []
        if token and not sites:
            raise ValueError(f"Workspace path literal no longer exists: {token}")
        rows.append(
            dict(
                id=id,
                path=path,
                area=area or path.split("/")[0] if "/" in path else area or "root",
                holds=holds,
                written_by=list(writers) or ["not found"],
                read_by=list(readers) or ["not found"],
                edit_by_hand=edit,
                delete=delete,
                created=created,
                execution_step=step,
                note=note,
                evidence={
                    "writers": [source.evidence(a) for a in writers],
                    "readers": [source.evidence(a) for a in readers],
                    "path_literals": sites,
                },
            )
        )

    settings = ws + "._settings_file"
    for name, desc in [
        ("SETTINGS_FILE", "Shared command defaults and logging choices."),
        (
            "LOCAL_SETTINGS_FILE",
            "Machine-local overrides, including executable and local execution choices.",
        ),
    ]:
        path = source.value(settings, name)
        add(
            path.replace(".", "-"),
            path,
            desc,
            readers=settings + ":read_workspace_settings",
            edit="Yes, valid TOML",
            delete=(
                "Yes. These defaults disappear; command arguments and remaining defaults apply."
            ),
            created="On demand, user authored",
            token=path,
        )
    add(
        "runs-json",
        "runs.json",
        (
            "Authoritative run document: run identities, outcomes, hashes and "
            "shared setup, frame and geometry definitions."
        ),
        [ws + ":CampaignWorkspace._replace_manifest", ws + ".manifest:append_record"],
        [records, ws + ".record_document:read_rows"],
        token="runs.json",
        step="steps-28",
    )
    add(
        "storage-management",
        source.value(ws + ".storage", "STORAGE_FILE"),
        "History of storage operations, pruning and deleted simulations.",
        ws + ".storage:record_storage_call",
        ws + ".storage:read_storage_calls",
        token="storage_management.json",
    )
    add(
        "additional-json",
        "additional.json",
        "Additional extraction records, separate from the run manifest.",
        ws + ":CampaignWorkspace.append_additional",
        ws + ":CampaignWorkspace.read_additional",
        token="additional.json",
        step="steps-28",
    )
    add(
        "manifest-lock",
        "runs.json.lock",
        ("Temporary owner lease for a manifest update; additional.json uses its own lease."),
        ws + ".manifest:manifest_lock",
        ws + ".manifest:manifest_lock",
        delete=(
            "Do not delete during use. The lease code removes its own lock and "
            "recovers stale owners."
        ),
        step="steps-29",
    )
    add(
        "manifest-guard",
        ".runs.json.lock.guard",
        "Persistent OS lock used to arbitrate the manifest lease.",
        ws + ".manifest:manifest_lock",
        ws + ".manifest:manifest_lock",
        delete="No. Replacing the file can split lock arbitration between processes.",
        step="steps-29",
    )
    add(
        "manifest-temp",
        "runs.json.<pid>.tmp",
        "Transient complete replacement document, atomically renamed to runs.json.",
        ws + ":CampaignWorkspace._replace_manifest",
        ws + ":CampaignWorkspace._replace_manifest",
        delete=(
            "Only an abandoned temporary file after all writers have stopped; "
            "never the live replacement."
        ),
        step="steps-29",
    )
    add(
        "root-matrix",
        "<matrix>.fs",
        "Pipe-separated campaign rows; an alternative home to inputs/matrices/.",
        writers=ws + ".excel_sync:apply_preview",
        readers="pyflightstream.cases.matrix:read_matrix",
        edit="Yes, preserve the matrix schema",
        delete=input_delete,
        created="On demand, user authored",
        step="steps-5",
        token="*.fs",
    )
    add(
        "root-plan",
        "plan.json",
        (
            "Plan receipt for a campaign without a matrix name; matrix plans use "
            "post/<matrix>/plan.json."
        ),
        "pyflightstream.run._plan:plan_campaign",
        "pyflightstream.workspace.ledger:_read_plan",
        delete="Yes. Replan before running; the saved planning receipt is lost.",
        step="steps-10",
        token="plan.json",
    )

    add(
        "inputs",
        "inputs/",
        "Reusable campaign input library.",
        init,
        ws + ".matrix:resolve_matrix",
        edit="Yes, through the input files",
        delete=input_delete,
        created="Initialization",
        token="inputs",
    )
    kinds = source.value(ws + ".inputs", "INPUT_KINDS")
    descriptions = {
        "geometries": (
            "Geometry files and per-mesh folders with mesh companions.",
            ws + ".inputs:resolve_geometry",
        ),
        "references": (
            ("Reference lengths, areas, points, frames and study declarations in r<id>.toml."),
            ws + ".inputs:resolve_reference",
        ),
        "setups": ("Solver setup artifacts s<id>.toml.", ws + ".inputs:resolve_setup"),
        "pproc": (
            "Post-processing declarations p<id>.toml, groups, exports and equations.",
            ws + ".inputs:resolve_pproc",
        ),
        "profiles": (
            "Actuator radial profile files, resolved by their file stem.",
            ws + ".inputs:resolve_profile",
        ),
        "freestreams": (
            "Structured or unstructured custom velocity fields.",
            ws + ".fields:read_field",
        ),
        "calibrations": (
            "Quasi-steady correction calibration TOML files.",
            "pyflightstream.post.corrections:write_qsteady_corrections",
        ),
        "hpc": ("Scheduler and remote execution profiles.", ws + ".hpc:read_hpc_profile"),
        "fsi": (
            "Structural coupling configuration and its referenced files.",
            ws + ".fsi_setup:resolve_row_fsi",
        ),
        "matrices": (
            "Campaign matrices, an equal alternative to root-level .fs files.",
            ws + "._layout:matrix_files",
        ),
        "management": (
            "Storage recipes controlling compaction, pruning and deletion.",
            ws + ".storage:read_recipe",
        ),
    }
    if set(kinds) != set(descriptions):
        raise ValueError("Input kinds changed; review workspace file descriptions")
    for kind in kinds:
        desc, reader = descriptions[kind]
        add(
            "inputs-" + kind,
            "inputs/" + kind + "/",
            desc,
            init,
            reader,
            edit="Yes, edit the contained input files",
            delete=input_delete,
            created="Initialization",
            token=kind,
        )
    for kind, desc, reader in [
        (
            "sixdof",
            "Free-body motion files d<id>.toml and custom force inputs.",
            ws + ".sixdof_setup:resolve_row_sixdof",
        ),
        ("costs", "Per-machine cost model files c<id>.toml.", ws + ".costs:resolve_cost_file"),
    ]:
        add(
            "inputs-" + kind,
            "inputs/" + kind + "/",
            desc,
            readers=reader,
            edit="Yes",
            delete=input_delete,
            created="On demand, user supplied",
            token=kind,
        )
    for kind, pattern, writer in [
        ("geometries", "<mesh>/<mesh>.<ext>", ws + "._geometry_build:_promote"),
        ("references", "r<id>.toml", ""),
        ("setups", "s<id>.toml", ws + ".setup_standards:write_setup_library"),
        ("pproc", "p<id>.toml", ""),
        ("profiles", "<id>.csv", ws + ".actuator_profiles:write_profile"),
        ("freestreams", "<id>.txt or <id>.dat", ws + ".fields:write_freestream"),
        ("calibrations", "<id>.toml", "pyflightstream.post.corrections:sector_offset_calibration"),
        ("hpc", "<id>.toml", ""),
        ("fsi", "f<id>.toml", ""),
        ("matrices", "<matrix>.fs", ws + ".excel_sync:apply_preview"),
        ("management", "<recipe>.toml", ""),
    ]:
        desc, reader = descriptions[kind]
        add(
            "input-file-" + kind,
            "inputs/" + kind + "/" + pattern,
            desc,
            writer or (),
            reader,
            edit=("Yes, before planning; generated files should be regenerated from their inputs"),
            delete=input_delete,
            created="On demand",
            step="steps-9" if kind == "geometries" else "steps-8",
        )
    for id, file, desc, writer, reader in [
        (
            "executables",
            "executables.toml",
            ("Shared solver build registry. Initialization writes a comment-only template."),
            init,
            ws + ".builds:resolve_build",
        ),
        (
            "executables-local",
            "executables.local.toml",
            "Machine-local executable registrations and local build acceptance.",
            "",
            ws + ".builds:resolve_build",
        ),
        (
            "reference-points",
            "reference_points.toml",
            "Named campaign reference-point coordinates.",
            "",
            ws + ":CampaignWorkspace.reference_points",
        ),
        (
            "sync-workspaces",
            "sync-workspaces.toml",
            "Workspace synchronization destinations and policies.",
            "",
            ws + ".storage:read_sync_config",
        ),
    ]:
        add(
            id,
            "inputs/" + file,
            desc,
            writer or (),
            reader,
            edit="Yes, valid TOML",
            delete=input_delete,
            created="Initialization" if id == "executables" else "On demand, user authored",
            token=file,
            step="steps-7" if id.startswith("executables") else None,
        )
    for id, path, writer, reader in [
        (
            "input-glossary",
            "inputs/INPUTS.md",
            "pyflightstream.post.glossary:write_input_glossary",
            "pyflightstream.post.glossary:write_input_glossary",
        ),
        (
            "input-template",
            "inputs/input_template.md",
            "pyflightstream.post.input_template:write_input_template",
            "pyflightstream.post.glossary:write_if_different",
        ),
        ("geometry-readme", "inputs/geometries/README.md", init, ""),
        (
            "pproc-variables",
            "inputs/pproc/VARIABLES.md",
            "pyflightstream.post.guides:write_pproc_guides",
            "pyflightstream.post.glossary:write_if_different",
        ),
        (
            "pproc-equations",
            "inputs/pproc/WRITING-EQUATIONS.md",
            "pyflightstream.post.guides:write_pproc_guides",
            "pyflightstream.post.glossary:write_if_different",
        ),
    ]:
        add(
            id,
            path,
            "Generated input guidance.",
            writer,
            reader or (),
            edit="Keep custom notes outside generated sections",
            delete="Yes. Initialization or guide generation recreates it.",
            created="Initialization; refreshed on demand",
            token=path.rsplit("/", 1)[1],
        )
    add(
        "geometry-boundaries",
        "inputs/geometries/<mesh>/<mesh>.boundaries.toml",
        "Boundary inventory, aliases, import and mesh-condition declarations.",
        ws + ".sidecars:write_inventory",
        [ws + ".sidecars:read_inventory", ws + ".sidecars:read_mesh_import"],
        edit="Yes, preserve geometry identity and valid declarations",
        delete=input_delete,
        token=".boundaries.toml",
        step="steps-9",
    )
    add(
        "geometry-provenance",
        "inputs/geometries/<mesh>/<mesh>.provenance.toml",
        "Geometry preparation provenance companion.",
        readers=ws + ".sidecars:is_sidecar",
        delete=evidence_delete,
        token=".provenance.toml",
        step="steps-9",
    )
    add(
        "geometry-trailing-edges",
        "inputs/geometries/<mesh>/<mesh>.te.txt",
        "Explicit trailing-edge selection referenced by the mesh sidecar.",
        writers=ws + ".trailing_edges:write_trailing_edge_node_file",
        readers=ws + ".sidecars:read_trailing_edges",
        edit="Yes, as an input declaration",
        delete=input_delete,
        token=".te.txt",
        step="steps-9",
    )

    add(
        "sims",
        "sims/",
        "Managed simulation and grouped-job directories.",
        init,
        ws + ".storage:space_in_use",
        created="Initialization",
        token="sims",
        step="steps-10",
    )
    add(
        "batch",
        "sims/batch/",
        ("Grouped job folders, each containing shared job scripts and execution evidence."),
        "pyflightstream.run._batch_run:_prepare_job_folders",
        ws + "._batch_life:batch_files",
        token="batch",
        step="branches-1",
    )
    add(
        "batch-job",
        "sims/batch/<job>/",
        "One grouped job's working directory.",
        "pyflightstream.run._batch_run:_prepare_job_folders",
        ws + "._batch_life:batch_files",
        step="branches-1",
    )
    add(
        "batch-script",
        "sims/batch/<job>/<script>.txt",
        "Generated grouped solver script.",
        "pyflightstream.run._batch_run:_write_job_files",
        "pyflightstream.run._batch_run:launch_job",
        step="branches-1",
    )
    add(
        "batch-end",
        "sims/batch/<job>/<stem>.end.json",
        "Job completion receipt, when the generated job writes one.",
        readers=ws + "._batch_life:end_evidence",
        step="branches-1",
        token=".end.json",
        note=(
            "Writer not found as a Python file-writing function; job scripts are "
            "executed by FlightStream."
        ),
    )
    add(
        "batch-log",
        "sims/batch/<job>/<stem>.job-log.txt",
        "Solver log for the grouped job.",
        readers=ws + "._batch_life:end_evidence",
        token=".job-log.txt",
        step="branches-1",
        note="Written by the external solver.",
    )
    add(
        "sim",
        "sims/sim_<id>/",
        "One simulation's scripts, staged inputs and collected datapoints.",
        ws + ":CampaignWorkspace.create_sim",
        ws + ":CampaignWorkspace.sim_dir",
        step="steps-10",
    )
    for folder, desc, writer, reader, step in [
        (
            "inputs",
            (
                "Copies or links to staged geometry and auxiliary input files. A link"
                " can target the input library."
            ),
            ws + ":CampaignWorkspace.stage_inputs",
            "pyflightstream.run._campaign:_prepare_case",
            "steps-17",
        ),
        (
            "scripts",
            "Rendered solver scripts retained with their recorded hashes.",
            ws + ":CampaignWorkspace.write_script",
            "pyflightstream.run._executors:LocalExecutor.run_script",
            "steps-21",
        ),
        (
            "datapoints",
            "One DP-<point> folder for each collected datapoint.",
            collect,
            "pyflightstream.post.products:_campaign_products",
            "steps-25",
        ),
    ]:
        add(
            "sim-" + folder,
            "sims/sim_<id>/" + folder + "/",
            desc,
            [ws + ":CampaignWorkspace.create_sim", writer],
            reader,
            step=step,
            token=folder,
        )
    add(
        "staged-inputs",
        "sims/sim_<id>/inputs/<file>",
        "The exact input bytes used by a run, possibly linked to the library.",
        ws + ":CampaignWorkspace.stage_inputs",
        "pyflightstream.run._sweep:_prepare_sweep_script",
        step="steps-17",
    )
    add(
        "solver-script",
        "sims/sim_<id>/scripts/<stem>.txt",
        "Emitted FlightStream commands; the manifest records their hash.",
        ws + ":CampaignWorkspace.write_script",
        "pyflightstream.run._executors:LocalExecutor.run_script",
        step="steps-21",
    )
    add(
        "datapoint",
        "sims/sim_<id>/datapoints/DP-<point>/",
        "Collected files belonging to a single point.",
        collect,
        "pyflightstream.post.products:_campaign_products",
        token="DP-",
        step="steps-25",
    )
    for kind, suffix, command, _whole_run in source.value(
        "pyflightstream.cases.pproc", "EXPORT_KINDS"
    ):
        add(
            "export-" + kind,
            "sims/sim_<id>/datapoints/DP-<point>/<stem>" + suffix,
            (
                "Solver log and convergence evidence."
                if kind == "log"
                else "Raw "
                + kind.replace("_", " ")
                + " export; present only when requested and supported."
            ),
            writers="pyflightstream.results.surface:translate_vtk_surface"
            if kind == "tecplot"
            else (),
            readers=collect,
            step="steps-23" if kind == "log" else "steps-25",
            token=suffix,
            note=(
                "Translated from the VTK export by Python."
                if kind == "tecplot"
                else "External solver command: " + command + "."
            )
            + (
                " The collector moves the file here from the working directory; "
                "collection is separate from writing the source export."
            ),
        )
    add(
        "working-exports",
        "sims/sim_<id>/<declared export>",
        "Solver exports before collection moves them into datapoints/.",
        readers=collect,
        step="steps-23",
        note="External FlightStream output; no Python writer found.",
    )
    add(
        "sim-additional",
        "sims/sim_<id>/datapoints/DP-<point>/additional/<pproc>/",
        (
            "Additional extraction scripts and exports; extraction records live "
            "in additional.json at the root."
        ),
        writers="pyflightstream.run.matrix:_extract",
        readers="pyflightstream.post._additional:_additional_products",
        step="steps-32",
        token="additional",
    )

    add(
        "post",
        "post/",
        "Derived engineering products and planning receipts.",
        init,
        ws + ".ledger:read_ledger",
        created="Initialization",
        step="steps-32",
        token="post",
        delete=product_delete,
    )
    add(
        "post-matrix",
        "post/<matrix>/",
        (
            "Products and plan receipt for one named matrix. Without a matrix, "
            "products use post/products/ and sweep tables use post/."
        ),
        post,
        ws + ".ledger:read_ledger",
        step="steps-32",
        delete=product_delete,
    )
    add(
        "post-plan",
        "post/<matrix>/plan.json",
        "Planning receipt: selected points, input identities and preflight facts.",
        "pyflightstream.run._plan:plan_campaign",
        "pyflightstream.workspace.ledger:_read_plan",
        token="plan.json",
        step="steps-10",
        delete=(
            "Yes. Replan before running; the receipt and planned-point query history are lost."
        ),
    )
    add(
        "sweep",
        "post/<matrix>/campaign_sweep.csv",
        "Campaign sweep outcomes and collected metrics.",
        "pyflightstream.run._campaign:_leave_sweep_table",
        "pyflightstream.post.products:_sweep_rows",
        token="campaign_sweep.csv",
        step="steps-30",
        delete=product_delete,
    )
    add(
        "products-json",
        "post/<matrix>/products.json",
        "Product inventory, provenance links, skips, warnings and completion state.",
        "pyflightstream.post.products:_write_manifest",
        ws + ".ledger:_read_products",
        step="steps-36",
        token="products.json",
        delete=product_delete,
    )
    for name in ["post.log", "post.log.json"]:
        add(
            name.replace(".", "-"),
            "post/<matrix>/" + name,
            "Post-processing diagnostics, including skipped or refused products.",
            post,
            ws + "._query_logs:_post_rows" if name.endswith("json") else (),
            token=name,
            step="steps-32",
            delete="Yes. Diagnostics from that post are lost; another post writes new logs.",
        )
    products = [
        (
            "polars",
            "<polar>.csv",
            "Coefficient tables over the swept conditions.",
            "pyflightstream.post._sim:_group_polar",
            "pyflightstream.post._tables:read_csv_table",
            "steps-35",
        ),
        (
            "polars",
            "<polar>.dat",
            "Optional custom-format polar tables.",
            "pyflightstream.post._sim:_group_polar",
            "",
            "steps-35",
        ),
        (
            "sections",
            "<point>*.csv",
            "Section pressure and sectional-load tables.",
            "pyflightstream.post._sim:_point_products",
            "pyflightstream.workspace.actuator_profiles:read_section_loads",
            "steps-34",
        ),
        (
            "probes",
            "<point>*.csv",
            "Probe tables and sampled flow values.",
            "pyflightstream.post._sim:_point_products",
            "",
            "steps-34",
        ),
        (
            "provenance",
            "<run>.prov.json",
            "Run provenance linking inputs, script, solver identity and output hashes.",
            "pyflightstream.post.provenance:run_provenance",
            "",
            "steps-37",
        ),
        (
            "series",
            "<point>*.csv",
            "Time or step series reconstructed from stamped exports.",
            "pyflightstream.post.series:write_point_series",
            "",
            "steps-34",
        ),
        (
            "surfaces",
            "<point>*",
            "Averaged surface exports.",
            "pyflightstream.post.surfaces:write_point_surface_average",
            "",
            "steps-34",
        ),
        (
            "settings",
            "<matrix>_settings.csv",
            "Recorded solver setup values by simulation.",
            "pyflightstream.post._settings_product:write_settings_product",
            "",
            "steps-36",
        ),
        (
            "settings",
            "<matrix>_settings.codebook.json",
            "Meaning and provenance of solver-setting codes.",
            "pyflightstream.post._settings_product:write_settings_product",
            "",
            "steps-36",
        ),
    ]
    products.extend(
        [
            (
                "farfield",
                "<group>*.csv",
                "Far-field estimates and diagnostics, when configured.",
                "pyflightstream.post.farfield_products:_write",
                "",
                "steps-34",
            ),
            (
                "streamlines",
                "<point>*",
                "Streamline tables and VTK visualization products.",
                "pyflightstream.post.streamlines:write_streamline_products",
                "",
                "steps-34",
            ),
            (
                "fields",
                "<point>*",
                "Sampled velocity fields and reusable inflow companions.",
                "pyflightstream.post.probe_fields:point_field_products",
                "pyflightstream.workspace.fields:read_field",
                "steps-34",
            ),
            (
                "structure",
                "<point>_history.csv",
                "Structural response history from coupled points.",
                "pyflightstream.post._structure:structure_products",
                "",
                "steps-34",
            ),
            (
                "additional",
                "<pproc>/*",
                "Products derived from separately recorded additional extractions.",
                "pyflightstream.post._additional:_additional_products",
                "",
                "steps-34",
            ),
        ]
    )
    for i, (folder, pattern, desc, writer, reader, step) in enumerate(products):
        add(
            "product-" + str(i),
            "post/<matrix>/" + folder + "/" + pattern,
            desc,
            writer,
            reader or (),
            token=folder,
            step=step,
            delete=product_delete,
        )
    add(
        "post-archive",
        "post/<matrix>/archive/<stamp>/",
        "Previous products retained when an operation requests archiving.",
        "pyflightstream.post.provenance:refuse_an_existing_product",
        "pyflightstream.run.records:restore",
        token="archive",
        step="steps-32",
        delete=(
            "Yes only when those previous products are no longer needed; deleting"
            " them removes the restore copy."
        ),
    )
    add(
        "reports",
        "reports/",
        "Measurement reports produced by configured post-processing.",
        "pyflightstream.post.products:_finish_campaign_products",
        created="On demand",
        token="reports",
        step="steps-36",
        area="post",
        delete=product_delete,
    )

    add(
        "logs",
        "logs/",
        "Durable command activity and console diagnostics.",
        "pyflightstream._progress:activity_event",
        ws + "._query_logs:_activity",
        token="logs",
        delete=(
            "Yes when diagnostics are no longer needed. Commands recreate the directory on demand."
        ),
    )
    for filename in ["activity.log", "activity.log.jsonl"]:
        add(
            filename.replace(".", "-"),
            "logs/" + filename,
            "Append-only activity events across workspace commands.",
            "pyflightstream._progress:activity_event",
            ws + "._query_logs:_activity" if filename.endswith("jsonl") else (),
            token=filename,
            delete=(
                "Yes when diagnostic history is no longer needed. Later commands create a new log."
            ),
            step="steps-1",
        )
    add(
        "command-log",
        "logs/<command>-<stamp>.log",
        "Console transcript for a supported workspace command invocation.",
        "pyflightstream._progress:_live_log",
        delete="Yes. That invocation's console history is lost.",
        step="steps-1",
    )
    add(
        "archive",
        "archive/",
        (
            "Archived manifests and simulation or datapoint evidence retained "
            "before managed changes."
        ),
        init,
        "pyflightstream.run.records:restore",
        created="Initialization",
        token="archive",
        delete=(
            "Only when its recovery copies are no longer needed. Deletion removes"
            " restoration evidence."
        ),
    )
    add(
        "archive-runs",
        "archive/runs-<stamp>.json",
        "Prior run document saved before superseding or rewriting records.",
        ws + ".manifest:supersede_records",
        "pyflightstream.run.records:restore",
        step="steps-28",
    )
    add(
        "archive-sim",
        "archive/<simulation archive>/",
        ("Archived simulation tree or point evidence; exact name follows the naming template."),
        [ws + ":CampaignWorkspace.archive_sim", ws + ":CampaignWorkspace.archive_datapoint"],
        "pyflightstream.run.records:restore",
    )
    for row in rows:
        if row["area"] not in ("root", "inputs", "sims", "post", "logs", "archive"):
            raise ValueError(f"Unknown workspace area: {row}")
    return {
        "method": (
            "AST path declarations and source-verified ownership anchors. "
            "Semantic descriptions and edit/delete advice are curated from the "
            "code. Ownership lists are selected direct owners or orchestration "
            "boundaries, not an exhaustive call graph. not found means no "
            "supported Python owner was identified; external solver writes and "
            "user-authored files are stated separately."
        ),
        "paths": rows,
        "summary": {
            "paths": len(rows),
            "not_found": [
                {
                    "path": r["path"],
                    "writer": r["written_by"] == ["not found"],
                    "reader": r["read_by"] == ["not found"],
                }
                for r in rows
                if "not found" in r["written_by"] or "not found" in r["read_by"]
            ],
        },
    }


def render_tables(data):
    def cell(value):
        return html.escape(str(value)).replace("|", "&#124;")

    def owners(items):
        return "<br>".join(
            "not found" if x == "not found" else "<code>" + cell(x) + "</code>" for x in items
        )

    output = []
    for area in ("root", "inputs", "sims", "post", "logs", "archive"):
        output += ["## " + area.title(), ""]
        output += [
            "| File | What it holds | Written by | Read by | Edit by hand | Delete |",
            "|---|---|---|---|---|---|",
        ]
        for row in data["paths"]:
            if row["area"] != area:
                continue
            path = "<code>" + cell(row["path"]) + "</code>"
            if row["execution_step"]:
                path = (
                    '<a href="../understanding/execution/#step='
                    + row["execution_step"]
                    + '">'
                    + path
                    + "</a>"
                )
            output.append(
                "| "
                + " | ".join(
                    [
                        '<span id="' + row["id"] + '"></span>' + path,
                        cell(row["holds"])
                        + " <strong>Created:</strong> "
                        + cell(row["created"])
                        + (" " + cell(row["note"]) if row["note"] else ""),
                        owners(row["written_by"]),
                        owners(row["read_by"]),
                        cell(row["edit_by_hand"]),
                        cell(row["delete"]),
                    ]
                )
                + " |"
            )
        output.append("")
    return "\n".join(output)


# Explicit associations preserve the existing static trace, including steps that
# work only in memory. Every identifier is checked against the generated rows.
STEP_FILES = {
    1: ["root-matrix", "command-log"],
    2: ["root-matrix", "input-file-matrices"],
    3: ["inputs"],
    4: ["root-matrix", "inputs", "runs-json", "input-glossary"],
    5: ["root-matrix"],
    6: ["inputs", "executables"],
    7: ["executables", "executables-local"],
    8: ["input-file-references", "input-file-setups", "input-file-pproc"],
    9: ["input-file-geometries", "geometry-boundaries"],
    10: ["runs-json", "sim", "post-plan"],
    11: ["input-file-geometries"],
    12: ["input-file-geometries", "input-file-setups"],
    13: ["root-matrix", "post-plan", "runs-json", "sweep"],
    14: ["root-matrix", "inputs", "runs-json"],
    15: ["executables", "inputs-hpc"],
    16: ["runs-json"],
    17: ["input-file-geometries", "staged-inputs"],
    18: ["solver-script"],
    19: ["staged-inputs"],
    20: [],
    21: ["solver-script"],
    22: ["solver-script", "working-exports"],
    23: ["solver-script", "working-exports", "export-log"],
    24: ["working-exports", "datapoint"],
    25: ["datapoint", "export-loads", "export-log"],
    26: ["export-loads", "export-log"],
    27: ["datapoint", "runs-json"],
    28: ["runs-json", "manifest-lock"],
    29: ["runs-json", "manifest-temp", "manifest-guard"],
    30: ["runs-json", "sweep", "products-json"],
    31: ["runs-json", "products-json"],
    32: ["runs-json", "post-log", "post-log-json", "products-json"],
    33: ["runs-json", "datapoint", "root-matrix", "products-json", "sweep"],
    34: ["export-loads", "input-file-pproc", "product-0", "product-2", "product-3"],
    35: ["export-loads", "product-0", "product-1"],
    36: ["runs-json", "products-json", "reports"],
    37: ["runs-json", "product-4"],
}


def link_execution(execution, data):
    by_id = {row["id"]: row for row in data["paths"]}
    valid_steps = {s["id"] for s in execution["steps"] + execution["branches"]}
    for row in data["paths"]:
        if row["execution_step"] and row["execution_step"] not in valid_steps:
            raise ValueError(f"Unknown execution step: {row['execution_step']}")
    for step in execution["steps"] + execution["branches"]:
        ids = (
            STEP_FILES.get(step["order"], [])
            if step["id"].startswith("steps-")
            else ["batch", "batch-script", "batch-log", "batch-end", "runs-json"]
        )
        # Include every file linked to this step so all row links are reciprocal.
        ids = list(
            dict.fromkeys(
                ids + [r["id"] for r in data["paths"] if r["execution_step"] == step["id"]]
            )
        )
        step["workspace_files"] = [{"id": id, "path": by_id[id]["path"]} for id in ids]
        for field in ("inputs", "outputs"):
            step[field] = [value.replace("W/sim_", "W/sims/sim_") for value in step[field]]


def render_execution_files(execution):
    lines = [
        "## Files by execution step",
        "",
        (
            "File links lead to the workspace reference. Optional products are "
            "associated with the stage that creates them; their presence depends "
            "on configuration."
        ),
        "",
        "| Step | Workspace files |",
        "|---|---|",
    ]
    for step in execution["steps"] + execution["branches"]:
        links = [
            "[" + html.escape(row["path"]) + "](../workspace-files.md#" + row["id"] + ")"
            for row in step["workspace_files"]
        ]
        lines.append(
            '| <span id="step='
            + step["id"]
            + '"></span>['
            + str(step["order"])
            + ". "
            + step["function"]
            + "](#step="
            + step["id"]
            + ") | "
            + ("<br>".join(links) or "In-memory values only in this step.")
            + " |"
        )
    return "\n".join(lines) + "\n"
