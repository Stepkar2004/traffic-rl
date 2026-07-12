"""Phase-0 smoke test: the package imports and the venv is wired."""

import traffic_rl


def test_package_imports() -> None:
    assert traffic_rl.__doc__ is not None
