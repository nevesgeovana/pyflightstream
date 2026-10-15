Coverage is measured by the release's frozen full suite, with the floor kept
in `pyproject.toml`. Push CI and the release workflow's wheel tests run without
coverage instrumentation. Both release runners still test the built wheel.

migration: Contributor coverage evidence comes from the `suite-full` release
receipt, run with `--cov --cov-branch`.
