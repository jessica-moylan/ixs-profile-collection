# CLAUDE.md — IXS Bluesky Profile Collection

## Project identity

NSLS-II IXS (Inelastic X-ray Scattering) beamline Bluesky profile collection.
IPython startup scripts for beamline data acquisition at BNL NSLS-II, beamline 10-ID.

## Running the environment

```bash
pixi run start        # Launch IPython session (terminal profile)
pixi run pvs          # Print PV types and exit
pixi run qs-backend   # Start queue-server backend
pixi run qs-server    # Start queue-server HTTP server
```

IPython is launched with `--profile-dir=.` (the repo root is the profile directory).

## Startup file loading

IPython automatically runs all `.py` and `.ipy` files in `startup/` in
**lexicographical order** before any user code. Numbering convention:

| Prefix | Purpose |
|--------|---------|
| `00`   | Environment setup (`nslsii.configure_base`, callbacks) |
| `01-09`| Integrations (Olog, Tiled writer, suspenders) |
| `10`   | Real motors and optics |
| `25-26`| Pseudomotors and cameras |
| `90`   | Endstation configuration |
| `94-96`| Detectors (baseline, Dexela, Lambda) |
| `97-99`| Plans, macros, and Bluesky configuration |

Files with a `.txt` extension (e.g. `startup/ixs4c.py.txt`,
`startup/ixs4c_config.py.txt`) are **not loaded** by IPython — they are
inactive/archived scripts.

## Namespace injected by `nslsii.configure_base`

After `startup/00-startup.py` runs, the following are available in the IPython
namespace:

| Name | Description |
|------|-------------|
| `RE` | `bluesky.RunEngine` |
| `db` | Databroker catalog (`ixs`) |
| `sd` | `SupplementalData` |
| `bec` | `BestEffortCallback` |
| `peaks` | `bec.peaks` |
| `plt` | `matplotlib.pyplot` |
| `np` | `numpy` |
| `bc` | `bluesky.callbacks` |
| `bp` | `bluesky.plans` |
| `bps` | `bluesky.plan_stubs` |
| `mv`, `mvr`, `mov`, `movr` | plan_stubs shortcuts |
| `bpp` | `bluesky.preprocessors` |

## Key globals available after full startup

| Name | Defined in | Description |
|------|-----------|-------------|
| `hklps` | `startup/25-pseudomotors.py` | Six-circle HKL pseudomotor device |
| `my_spec_factory` | `startup/00-startup.py` | SPEC file writer factory (RunRouter callback) |
| `spec_router` | `startup/00-startup.py` | `RunRouter` subscribed to `RE` |
| `motor_groups` | `startup/25-pseudomotors.py` | Motor group definitions for SPEC header |
| `g0_items`, `g1_items`, `q_items` | `startup/25-pseudomotors.py` | SPEC `#G` and `#Q` line items |

## Source layout

```
profile_collection/
├── startup/              # IPython startup scripts (main source)
│   ├── utils/            # Python utility package
│   │   ├── scbasic.py    # Basic scan utilities
│   │   ├── sixcircle.py  # Six-circle diffractometer geometry engine
│   │   ├── CustomSpecWriter.py  # SPEC file writer
│   │   ├── CustomLivePlot.py    # Custom live plotting
│   │   ├── DexelaCalc.py        # Dexela detector calculations
│   │   └── conf/         # Runtime configuration files
│   └── *.py              # Numbered startup scripts
├── docs/                 # Documentation (repo root)
├── tests/                # Test suite (repo root)
├── .claude/              # Claude project configuration
├── ipython_config.py     # IPython profile configuration
├── pixi.toml             # Pixi package manager config
└── azure-pipelines.yml   # CI/CD pipeline
```

## Do not edit — runtime/state paths

These paths are managed at runtime and must not be modified:

| Path | Reason |
|------|--------|
| `history.sqlite` | IPython command history (also git-ignored) |
| `log/` | Runtime log files |
| `pid/` | Process ID files |
| `security/` | IPython security files |
| `db/` | Runtime database files (also git-ignored) |
| `md/` | Metadata key/value store (also git-ignored) |
| `startup/utils/__pycache__/` | Python bytecode cache (auto-generated) |
| `startup/utils/conf/sixcircle_last_UB` | UB matrix updated live by beamline software |
| `startup/dexela_beam_settings.json` | Dexela settings updated at runtime (git-ignored) |
| `startup/utils/read_dexela.py` | Machine-specific, git-ignored |
| `.pixi/` | Pixi environment manager (auto-managed) |

## Tests

Tests live in `tests/` at the repo root. They are **not** inside `startup/`
(which would cause IPython to execute them on startup).

## Git-ignored files

Key ignores from `.gitignore`:

- `*.sqlite` (covers `history.sqlite`)
- `db` and `md/`
- `startup/utils/read_dexela.py`
- `startup/dexela_beam_settings.json`
- `__pycache__/`, `*.pyc`
- `.pixi/*` (except `.pixi/config.toml`)
- `docs/_build/`
