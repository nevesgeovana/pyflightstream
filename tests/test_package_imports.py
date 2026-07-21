"""Tier 1: the package installs, imports, and exposes a version."""

import pyflightstream


def test_package_imports_and_has_version():
    assert isinstance(pyflightstream.__version__, str)
    assert pyflightstream.__version__


def test_all_subpackages_import():
    import pyflightstream.cases
    import pyflightstream.commands
    import pyflightstream.files
    import pyflightstream.fsi
    import pyflightstream.post
    import pyflightstream.qa
    import pyflightstream.results
    import pyflightstream.run
    import pyflightstream.script
    import pyflightstream.versions

    modules = [
        pyflightstream.versions,
        pyflightstream.commands,
        pyflightstream.script,
        pyflightstream.cases,
        pyflightstream.files,
        pyflightstream.run,
        pyflightstream.results,
        pyflightstream.post,
        pyflightstream.fsi,
        pyflightstream.qa,
    ]
    for module in modules:
        assert module.__doc__, f"{module.__name__} is missing its pipeline-role docstring"
