# Python stack — bootstrap reference

Procedures first; dated observations at the bottom. When an observation's date is old,
re-verify before relying on it — that is the rot-check skill's job, but don't wait for it.

## Creator

- **uv (default):** `uv init --lib` for packages, `uv init` for apps. It is maintained by
  Astral and kept current — it already emits `.python-version`, `py.typed`, and a src
  layout; do not re-create what it wrote, and do not overwrite it.
- **pip (only when the user insists):** `python -m venv .venv`, then installs into it.
  Read the pip caveats below before declaring tasks.

## Baseline quality setup (assumed, still stated in the interview)

- **ruff** as linter AND formatter. Start from `select = ["E","F","I","B","UP","SIM","N","RUF"]`
  and adjust to the user's taste. Leave `target-version` out — ruff infers it from
  `requires-python`, and a hardcoded one silently pins yesterday.
- **mypy** with `strict = true`. If the user prefers a different type checker, that is an
  interview answer and an `evolve` event, not a deviation.
- **pytest**, tests in `tests/` mirroring `src/`.
- Declare dev tools as a PEP 735 `[dependency-groups]` `dev` group, not extras.

## Version constraints

Floors (`>=`), not pins, for libraries; the lockfile is the pin. Before writing any
floor, check the current release on PyPI (`https://pypi.org/pypi/<pkg>/json`) and
`requires-python` compatibility. Record the check date in a comment when it matters.

## Tasks to declare in project.yaml

```yaml
tasks:
  install: uv sync            # or the pip equivalent
  test: uv run pytest
  lint: uv run ruff check src tests
  typecheck: uv run mypy src
```

## pip caveats (verified 2026-07)

- `pip install -e .` does NOT install PEP 735 dependency-groups — a pip project can
  declare ruff/mypy/pytest and end up with a venv that has none of them, while looking
  healthy. Installing a group needs `pip install --group dev`, available only in
  pip >= 25.1, and a fresh venv bundles an older pip: upgrade pip inside the venv first.
- Only run `pip install --group dev` against a pyproject that actually declares the
  group — pip exits non-zero on a missing group.

## Line endings (verified 2026-07, the bug that keeps returning)

`Path.write_text` translates `\n` to `os.linesep` — on Windows every file you generate
gets CRLF, and formatters (ruff format, biome) then fail on files nobody edited. Write
generated files with `newline="\n"` explicitly, and put `* text=auto eol=lf` in
`.gitattributes` so git cannot undo it on checkout.
