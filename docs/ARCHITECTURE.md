# Architecture

FilaMind Setup is the installer and manager for the FilaMind suite and the Klipper ecosystem around it. This document covers how it is put together: the catalog, the shared engine, how it decides what is already installed, the safety rules it follows, and how the command-line tool and the FilaMind flow widget end up sharing one source of truth. For installation and day-to-day use, see the [README](../README.md).

## Design goals

- **One engine, two front-ends.** A command-line tool and the **Setup** widget in FilaMind flow drive the exact same engine and the same catalog, so behaviour is identical and there is one place to fix a bug.
- **Catalog-driven.** Adding a component is one entry in `catalog.json`; the engine code does not change. The catalog is the single source of truth for what exists and how it installs.
- **Delegating, not reimplementing.** The engine never reinvents a component's installer. It clones the repo and runs the component's own `install.sh`, or fetches a first-party app's one-line installer and runs it. This keeps the manager small and keeps each project in charge of its own install.
- **Safe by default.** Probing is always read-only. Mutations are explicit, repo slugs are validated before they touch a URL or a command, and the manager never deletes anything outside a direct child of `$HOME`.
- **No runtime dependencies.** The engine uses only the Python standard library, so it runs on a fresh printer host with nothing more than `python3` and `git`.

## File layout

| File | Role |
| ---- | ---- |
| `install.sh` | Bootstrap shell script. The `curl ... \| bash` entry point: clones the repo, puts the command on PATH, reconnects the terminal, and launches the wizard. |
| `filamind-setup` | The CLI front-end (a Python script). Parses subcommands and drives the engine; supplies the interactive prompts. |
| `engine.py` | The shared engine. Loads and validates the catalog, probes the host, and performs install / remove / bootstrap / migrate by delegating to component installers. |
| `catalog.json` | The component catalog - the single source of truth. |
| `.github/workflows/ci.yml` | CI: compile checks, catalog validation, and a dependency-order smoke test. |

## The catalog

`catalog.json` is a versioned document (`"schema": 1`) of groups, each containing components. The engine reads it on every run and validates every component before acting on anything, so a malformed catalog fails loudly at load time rather than mid-install.

### Component fields

Each component is loaded into a `Component` dataclass. Required fields are validated; the rest refine behaviour and detection.

| Field | Required | Meaning |
| ----- | -------- | ------- |
| `id` | yes | Short stable identifier used on the command line (e.g. `moonraker`). |
| `name` | yes | Human-readable name shown in menus and logs. |
| `kind` | yes | A label for the component's role (e.g. `web-ui`, `touch`, `companion`). |
| `repo` | yes | A GitHub `owner/repo` slug. Validated against a strict pattern before use. |
| `type` | yes | How it installs / updates: one of `git_repo`, `web`, `service`, `tauri`, `manual`. |
| `deps` | no | Other component ids that must install first. |
| `first_party` | no | `true` for FilaMind apps, which carry a self-cloning one-line installer. |
| `group` | - | Derived from the enclosing group; used for grouped output. |
| `desc` | no | One-line description shown in `list`. |
| `manager_key` | no | Name Moonraker's update manager uses, when it differs from `id`. |
| `service` | no | Systemd unit name, when the component runs as a service. |
| `dir` | no | Install directory name under `$HOME`, when it differs from `id`. |

### Install types

The `type` field selects the install path in the engine:

- **`git_repo` / `service`** - clone the repo into `$HOME/<dir>` (shallow), verify the clone is a real work tree, then run its `install.sh` if present. A leftover non-git directory from an interrupted clone is cleared first, but only ever a direct child of `$HOME`.
- **`web`** - not installed directly. These are detected and linked once present; the operator installs them with the project's own setup (or a tool like KIAUH).
- **`tauri`** - only installable when also marked `first_party` (via the app's own installer); a non-first-party `tauri` entry is catalog-only and fails loudly if an install is attempted.
- **`manual`** - needs hands-on steps; the engine points the operator at the component's documentation.

First-party FilaMind apps (`first_party: true`) override the type path entirely: they install through their own remote one-line installer regardless of declared type.

### Adding a component

Add one entry to the appropriate group in `catalog.json`. Pick the right `type`, list any `deps`, and set `manager_key` / `service` / `dir` if the runtime name differs from the `id`. The engine validates and picks it up on the next run; no Python changes are needed.

## The engine

`SetupEngine` is the whole brain. It is constructed with an optional `log` callback and an optional command `runner`, both overridable - which is exactly how the GUI backend reuses it (capturing log lines and command execution) without forking any logic.

### Read-only probing

`probe()` returns the OS pretty-name, a per-component installed map, and convenience `has_klipper` / `has_moonraker` flags. It never mutates anything. A component counts as installed if any of three independent signals agree:

1. **Moonraker's update manager** lists it (queried at `http://127.0.0.1:7125/machine/update/status`, with the component's `manager_key` or `id`, lowercased).
2. **A systemd unit** matching its `service` is present (`systemctl list-units`).
3. **Its install directory** (`$HOME/<dir>` or `$HOME/<id>`) exists.

Combining three signals keeps detection accurate when one is unavailable - for example when Moonraker is unreachable, or a component installs without a service. Every part of probing is wrapped so an unreachable Moonraker, a missing `systemctl`, or an unreadable `/etc/os-release` degrades gracefully to the remaining heuristics instead of erroring.

### Dependency ordering

`resolve_order()` does a depth-first topological walk over `deps`, so dependencies are always installed before the things that need them (Klipper before Moonraker before a UI). `install()` resolves the order for the requested id, then installs each step, skipping anything already detected as installed.

### Mutations

- **`install(id)`** - resolve dependencies, then for each not-yet-installed component run `_do_install`, which branches on `first_party` and `type` as described above.
- **`remove(id)`** - for first-party apps, run their installer with `uninstall`; otherwise disable the systemd unit (if any) and remove the install directory, but only when it is a direct child of `$HOME`. Removal failures are surfaced, never swallowed, so the tool can never report a false "removed".

### The first-party installer trick

First-party apps are installed by `_run_remote_installer`, which is careful in two ways that are worth recording because they were learned the hard way:

1. **It runs the script's contents, not a temp-file path.** The first-party installers detect "am I a clone or a `curl | bash` pipe?" by testing `[ -f "$BASH_SOURCE" ]`. Handing them a downloaded temp file makes that test true, so they assume a clone layout that isn't there and fail. Running the *contents* via `bash -c` leaves `$BASH_SOURCE` empty - the same state as `curl | bash` - so the installer self-clones, which is correct.
2. **Arguments are passed as a list, never interpolated into a shell string.** Combined with strict repo-slug validation, a catalog typo or hostile entry can't inject shell syntax or redirect to a foreign host.

## Safety model

- **Repo slugs are validated** against `^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$` before they are ever placed in a URL or a command. This blocks shell metacharacters and foreign hosts at the source.
- **Catalog validation is up front.** Missing required fields, unknown `type` values, and unsafe `repo` slugs all raise at load time.
- **Destructive operations are bounded to `$HOME`.** The engine refuses to clear or remove any path that is not a direct child of `$HOME`.
- **No commands are run through a shell string.** Everything goes through argument lists; the one `bash -c` path (the first-party installer) still passes user-controlled values as separate list arguments.
- **Failures surface.** A failed clone, install script, pull, or removal raises a `SetupError` rather than reporting success.

## The bootstrap script

`install.sh` is the `curl | bash` entry point and is intentionally minimal:

1. Check that `git` and `python3` exist (clear message and exit if not).
2. Clone the installer into `$HOME/filamind-setup` (overridable via `FILAMIND_SETUP_DIR`; the repo via `FILAMIND_SETUP_REPO`), or fast-forward an existing checkout. A failed pull is reported and the run continues on the existing checkout rather than silently running stale code.
3. Symlink `filamind-setup` onto PATH - `/usr/local/bin` if passwordless sudo is available, otherwise `~/.local/bin`.
4. **Reconnect the controlling terminal.** Under `curl ... | bash`, the Python process would inherit the curl pipe as stdin (already at EOF, not a TTY), so the wizard's prompts would hit EOF immediately. The script reattaches `/dev/tty` when one is available, so the wizard can prompt. If there is truly no terminal, the CLI exits cleanly with guidance instead of a traceback.
5. `exec` the CLI with the requested command (defaulting to `bootstrap`).

The headless case is handled end to end: `_ask` in the CLI degrades to the safe/cancel option on `EOFError`, and `main()` catches a truly headless prompt and prints guidance (`... | bash -s -- menu`) instead of a stack trace.

## The two front-ends

Both front-ends are thin; the engine carries all the logic.

- **CLI (`filamind-setup`).** Parses subcommands (`bootstrap`, `menu`, `list`, `probe`, `install`, `remove`, `update`), supplies an interactive `_ask` for the wizard, and renders the grouped `list` and the interactive `menu`. The default subcommand is the interactive menu.
- **Setup widget (FilaMind flow).** The graphical front-end in [FilaMind flow](https://github.com/filamind-app/filamind-flow) drives the same `SetupEngine`, passing its own `log` and `runner` so it can stream progress into the UI. Same catalog, same detection, same install paths.

This is why a fix in the engine is a fix everywhere, and why the CLI and the widget can never drift apart in behaviour.

## Wizards

- **`bootstrap`** - probe the host, report the OS. If Klipper and Moonraker aren't both detected, advise installing those first and stop. If an existing UI (Mainsail / Fluidd / KlipperScreen) is found, ask whether to install alongside, migrate, or cancel; otherwise install the FilaMind suite (`filamind-flow`, then `filamind-3d`).
- **`migrate`** - install FilaMind alongside an existing setup, non-destructively. Settings stay in Moonraker's database and are picked up automatically; nothing is deleted, and the previous UI keeps working.

## Continuous integration

`.github/workflows/ci.yml` runs on every push and pull request, on Python 3.11:

- `python -m py_compile engine.py filamind-setup` - both Python files compile.
- `json.load` on `catalog.json` - the catalog is valid JSON.
- `bash -n install.sh` - the bootstrap script parses.
- An engine smoke test that loads the catalog and asserts the resolved dependency order is sane (`klipper` before `moonraker` before `mainsail`) - all without mutating the host.

## Conventions

- **Standard library only** in the engine; keep it dependency-free so it runs on a bare printer host.
- **Catalog over code.** New components belong in `catalog.json`, not in new engine branches.
- **Validate at the boundary.** Anything from the catalog is checked before it reaches a URL, a path, or a command.
- **Read-only stays read-only.** `probe`, `list`, and `status` must never mutate the host.
- **LF line endings** for all tracked text files (enforced via `.gitattributes`).
