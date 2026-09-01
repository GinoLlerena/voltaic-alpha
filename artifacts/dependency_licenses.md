# Dependency licence inventory

Evidence for `HK-008`. The event requires submissions to be MIT-compliant, and that is a claim about the whole dependency tree rather than about this repository's own `LICENSE`.

- packages installed: **102**
- reachable at runtime: **95**
- development only: **7**

## Runtime, by licence category

| Category | Packages |
|---|---:|
| `PERMISSIVE` | 91 |
| `WEAK_COPYLEFT` | 4 |

## Findings

**None.** No runtime dependency carries a strong-copyleft licence, and every runtime licence resolved to a named licence.

## Weak copyleft at runtime, and why it is compatible

Reported rather than waved through, and not gated, because these obligations do not reach this repository's own MIT-licensed source:

- `certifi 2026.7.22` — Mozilla Public License 2.0 (MPL 2.0)
- `pathspec 1.1.1` — Mozilla Public License 2.0 (MPL 2.0)
- `psycopg 3.3.4` — LGPL-3.0-only
- `psycopg-binary 3.3.4` — LGPL-3.0-only

- **MPL-2.0** is file-level copyleft. Its obligations attach to the MPL files themselves and to modifications of them. These packages are used unmodified, so nothing propagates outward.
- **LGPL-3.0** attaches to the library. `psycopg` is imported through its ordinary Python interface and installed unmodified from PyPI by the user running `uv sync`; this repository neither modifies it nor redistributes it.

This is engineering documentation, not a legal opinion. If the organizers read MIT-compliance as excluding any copyleft in the dependency tree, `psycopg` is the one to revisit - it is the PostgreSQL driver, and swapping it is a real change rather than a note.


## Every package

| Package | Version | Licence | Category | Scope |
|---|---|---|---|---|
| `alembic` | 1.19.1 | MIT | `PERMISSIVE` | runtime |
| `alpaca-py` | 0.44.0 | Apache Software License | `PERMISSIVE` | runtime |
| `altair` | 6.2.2 | BSD License | `PERMISSIVE` | runtime |
| `annotated-doc` | 0.0.5 | MIT | `PERMISSIVE` | runtime |
| `annotated-types` | 0.8.0 | MIT | `PERMISSIVE` | runtime |
| `anyio` | 4.14.2 | MIT | `PERMISSIVE` | runtime |
| `APScheduler` | 3.11.3 | MIT License | `PERMISSIVE` | runtime |
| `ast_serialize` | 0.8.0 | MIT | `PERMISSIVE` | runtime |
| `attrs` | 26.1.0 | MIT | `PERMISSIVE` | runtime |
| `blinker` | 1.9.0 | MIT License | `PERMISSIVE` | runtime |
| `boolean.py` | 5.0 | BSD-2-Clause | `PERMISSIVE` | runtime |
| `CacheControl` | 0.14.4 | Apache-2.0 | `PERMISSIVE` | runtime |
| `certifi` | 2026.7.22 | Mozilla Public License 2.0 (MPL 2.0) | `WEAK_COPYLEFT` | runtime |
| `charset-normalizer` | 3.5.1 | MIT | `PERMISSIVE` | runtime |
| `click` | 8.5.0 | BSD-3-Clause | `PERMISSIVE` | runtime |
| `coverage` | 7.15.4 | Apache-2.0 | `PERMISSIVE` | dev |
| `cyclonedx-python-lib` | 11.12.0 | Apache Software License | `PERMISSIVE` | runtime |
| `defusedxml` | 0.7.1 | Python Software Foundation License | `PERMISSIVE` | runtime |
| `detect-secrets` | 1.5.0 | Apache Software License | `PERMISSIVE` | dev |
| `fastapi` | 0.141.1 | MIT | `PERMISSIVE` | runtime |
| `filelock` | 3.32.4 | MIT | `PERMISSIVE` | runtime |
| `greenlet` | 3.5.5 | MIT AND PSF-2.0 | `PERMISSIVE` | runtime |
| `h11` | 0.16.0 | MIT License | `PERMISSIVE` | runtime |
| `httpcore` | 1.0.9 | BSD-3-Clause | `PERMISSIVE` | runtime |
| `httpcore2` | 2.12.0 | BSD-3-Clause | `PERMISSIVE` | runtime |
| `httptools` | 0.8.0 | MIT | `PERMISSIVE` | runtime |
| `httpx` | 0.28.1 | BSD License | `PERMISSIVE` | runtime |
| `httpx2` | 2.12.0 | BSD-3-Clause | `PERMISSIVE` | runtime |
| `idna` | 3.19 | BSD-3-Clause | `PERMISSIVE` | runtime |
| `iniconfig` | 2.3.0 | MIT | `PERMISSIVE` | runtime |
| `itsdangerous` | 2.2.0 | BSD License | `PERMISSIVE` | runtime |
| `Jinja2` | 3.1.6 | BSD License | `PERMISSIVE` | runtime |
| `jiter` | 0.16.0 | MIT | `PERMISSIVE` | runtime |
| `jsonschema` | 4.26.0 | MIT | `PERMISSIVE` | runtime |
| `jsonschema-specifications` | 2025.9.1 | MIT | `PERMISSIVE` | runtime |
| `librt` | 0.15.0 | MIT | `PERMISSIVE` | runtime |
| `license-expression` | 30.4.4 | Apache-2.0 | `PERMISSIVE` | runtime |
| `Mako` | 1.4.1 | MIT | `PERMISSIVE` | runtime |
| `markdown-it-py` | 4.2.0 | MIT License | `PERMISSIVE` | runtime |
| `MarkupSafe` | 3.0.3 | BSD-3-Clause | `PERMISSIVE` | runtime |
| `mdurl` | 0.1.2 | MIT License | `PERMISSIVE` | runtime |
| `msgpack` | 1.2.2 | Apache-2.0 | `PERMISSIVE` | runtime |
| `mypy` | 2.3.1 | MIT | `PERMISSIVE` | dev |
| `mypy_extensions` | 1.1.0 | MIT | `PERMISSIVE` | runtime |
| `narwhals` | 2.25.0 | MIT | `PERMISSIVE` | runtime |
| `numpy` | 2.5.2 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | `PERMISSIVE` | runtime |
| `openai` | 3.5.0 | Apache-2.0 | `PERMISSIVE` | runtime |
| `options-alpha-agent-lab` | 0.1.0 | MIT | `PERMISSIVE` | runtime |
| `packageurl-python` | 0.17.6 | MIT License | `PERMISSIVE` | runtime |
| `packaging` | 26.3 | Apache-2.0 OR BSD-2-Clause | `PERMISSIVE` | runtime |
| `pandas` | 3.0.5 | BSD License | `PERMISSIVE` | runtime |
| `pathspec` | 1.1.1 | Mozilla Public License 2.0 (MPL 2.0) | `WEAK_COPYLEFT` | runtime |
| `pillow` | 12.3.0 | MIT-CMU | `PERMISSIVE` | runtime |
| `pip` | 26.2.1 | MIT | `PERMISSIVE` | runtime |
| `pip-api` | 0.0.34 | Apache Software License | `PERMISSIVE` | runtime |
| `pip-requirements-parser` | 32.0.1 | MIT | `PERMISSIVE` | runtime |
| `pip_audit` | 2.10.1 | Apache Software License | `PERMISSIVE` | dev |
| `platformdirs` | 4.11.5 | MIT | `PERMISSIVE` | runtime |
| `plotly` | 7.0.0 | MIT | `PERMISSIVE` | runtime |
| `pluggy` | 1.6.0 | MIT License | `PERMISSIVE` | runtime |
| `protobuf` | 7.36.0 | 3-Clause BSD License | `PERMISSIVE` | runtime |
| `psycopg` | 3.3.4 | LGPL-3.0-only | `WEAK_COPYLEFT` | runtime |
| `psycopg-binary` | 3.3.4 | LGPL-3.0-only | `WEAK_COPYLEFT` | runtime |
| `py-serializable` | 2.1.0 | Apache Software License | `PERMISSIVE` | runtime |
| `pyarrow` | 25.0.1 | Apache-2.0 | `PERMISSIVE` | runtime |
| `pydantic` | 2.13.4 | MIT | `PERMISSIVE` | runtime |
| `pydantic_core` | 2.46.4 | MIT | `PERMISSIVE` | runtime |
| `pydeck` | 0.9.3 | Apache License 2.0 | `PERMISSIVE` | runtime |
| `Pygments` | 2.21.0 | BSD-2-Clause | `PERMISSIVE` | runtime |
| `pyparsing` | 3.3.2 | MIT | `PERMISSIVE` | runtime |
| `pytest` | 9.1.1 | MIT | `PERMISSIVE` | dev |
| `pytest-asyncio` | 1.4.0 | Apache-2.0 | `PERMISSIVE` | dev |
| `python-dateutil` | 2.9.0.post0 | Apache Software License; BSD License | `PERMISSIVE` | runtime |
| `python-dotenv` | 1.2.3 | BSD-3-Clause | `PERMISSIVE` | runtime |
| `python-json-logger` | 4.2.0 | BSD-2-Clause | `PERMISSIVE` | runtime |
| `python-multipart` | 0.0.32 | Apache-2.0 | `PERMISSIVE` | runtime |
| `pytz` | 2026.3.post1 | MIT License | `PERMISSIVE` | runtime |
| `PyYAML` | 6.0.3 | MIT License | `PERMISSIVE` | runtime |
| `referencing` | 0.37.0 | MIT | `PERMISSIVE` | runtime |
| `requests` | 2.34.2 | Apache Software License | `PERMISSIVE` | runtime |
| `rich` | 15.0.0 | MIT License | `PERMISSIVE` | runtime |
| `rpds-py` | 2026.6.3 | MIT | `PERMISSIVE` | runtime |
| `ruff` | 0.16.5 | MIT | `PERMISSIVE` | dev |
| `six` | 1.17.0 | MIT License | `PERMISSIVE` | runtime |
| `sniffio` | 1.3.1 | Apache Software License; MIT License | `PERMISSIVE` | runtime |
| `sortedcontainers` | 2.4.0 | Apache Software License | `PERMISSIVE` | runtime |
| `SQLAlchemy` | 2.0.52 | MIT | `PERMISSIVE` | runtime |
| `sseclient-py` | 1.9.0 | Apache Software License v2 | `PERMISSIVE` | runtime |
| `starlette` | 1.6.0 | BSD-3-Clause | `PERMISSIVE` | runtime |
| `streamlit` | 1.62.0 | Apache-2.0 | `PERMISSIVE` | runtime |
| `toml` | 0.10.2 | MIT License | `PERMISSIVE` | runtime |
| `tomli` | 2.4.1 | MIT | `PERMISSIVE` | runtime |
| `tomli_w` | 1.2.0 | MIT License | `PERMISSIVE` | runtime |
| `truststore` | 0.10.4 | MIT | `PERMISSIVE` | runtime |
| `typing-inspection` | 0.4.4 | MIT | `PERMISSIVE` | runtime |
| `typing_extensions` | 4.16.0 | PSF-2.0 | `PERMISSIVE` | runtime |
| `tzlocal` | 5.4.4 | MIT | `PERMISSIVE` | runtime |
| `urllib3` | 2.7.0 | MIT | `PERMISSIVE` | runtime |
| `uvicorn` | 0.52.4 | BSD-3-Clause | `PERMISSIVE` | runtime |
| `uvloop` | 0.22.1 | Apache Software License; MIT License | `PERMISSIVE` | runtime |
| `watchfiles` | 1.2.0 | MIT License | `PERMISSIVE` | runtime |
| `websockets` | 16.1.1 | BSD-3-Clause | `PERMISSIVE` | runtime |
