<div align="center">

# FilaMind Setup

One installer for the whole Klipper printing stack, driven by a single catalog you can read in a minute.

**Built by Egyptian makers, for world makers. Happy printing.** 🇪🇬

A small-team hobby project, built and tested on real printers. The code is all here to read.

[![Support on Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/I2I119XEIV)

[![CI](https://github.com/filamind-app/filamind-setup/actions/workflows/ci.yml/badge.svg)](https://github.com/filamind-app/filamind-setup/actions/workflows/ci.yml)
[![License: GPLv3](https://img.shields.io/badge/License-GPLv3-111111.svg)](LICENSE)
[![Klipper](https://img.shields.io/badge/Klipper-compatible-111111)](https://www.klipper3d.org)
[![Moonraker](https://img.shields.io/badge/Moonraker-API-111111)](https://moonraker.readthedocs.io)

[Install](#install) · [Uninstall](#uninstall) · [What it manages](#what-it-manages) · [Wizards](#wizards) · [How its built](#how-its-built) · [Develop](#develop) · [Docs](#documentation) · [Support](#support)

</div>

FilaMind Setup is the installer and manager for the FilaMind suite and the wider Klipper ecosystem around it. One engine, two front-ends: a command-line tool (`filamind-setup`) and the **Setup** widget inside [FilaMind flow](https://github.com/filamind-app/filamind-flow) both drive the same engine and the same catalog, so the behaviour is identical and there is one source of truth. It never installs anything itself by guesswork; it delegates to each component's own installer, and read-only probing is always safe.

## Install

Run on the printer host, as your normal printer user:

```bash
curl -fsSL https://raw.githubusercontent.com/filamind-app/filamind-setup/main/install.sh | bash
```

This clones the installer, puts the `filamind-setup` command on your PATH (system-wide if it can, otherwise in `~/.local/bin`), and runs the **first-run wizard**. The wizard detects your printer, then either installs the FilaMind suite or adopts an existing Mainsail/Fluidd setup alongside it, without touching what you already have. It needs only `git` and `python3` to start, and you can re-run it any time to update or repair.

To skip the wizard and go straight to something specific, pass a command through:

```bash
curl -fsSL https://raw.githubusercontent.com/filamind-app/filamind-setup/main/install.sh | bash -s -- menu
```

### Prefer a browser?

You can finish in a graphical wizard instead of the terminal:

```bash
filamind-setup serve
```

It prints a one-time link — `http://<printer-ip>:8077/?t=<token>` — to open on any device on your network. The token is shown only in the terminal that launched it, so only you can drive the install. No extra dependencies: it's Python's standard library, over the same engine as the CLI.

## Ongoing use

Once the command is on your PATH:

```bash
filamind-setup              # interactive menu (default)
filamind-setup list         # the catalog + what's installed
filamind-setup install <id> # install a component, and its dependencies
filamind-setup remove  <id> # remove a component
filamind-setup probe        # show what was detected
filamind-setup serve        # finish setup from a browser (one-time link)
filamind-setup bootstrap    # re-run the first-run wizard
```

The `<id>` is the short id shown by `filamind-setup list` (for example `moonraker`, `filamind-flow`, `spoolman`).

## Uninstall

`filamind-setup` is just a clone and a symlink, so removing it is removing those two things. To remove a single component you installed through it, use `filamind-setup remove <id>`, which calls that component's own uninstaller (for FilaMind apps) or stops its service and clears its directory. To remove the manager itself:

```bash
rm -f ~/.local/bin/filamind-setup        # or: sudo rm -f /usr/local/bin/filamind-setup
rm -rf ~/filamind-setup
```

This leaves every component you installed, and your Klipper config and Moonraker database, exactly where they are.

## What it manages

A curated catalog (`catalog.json`) spanning the whole stack: core (Klipper, Moonraker), web UIs, touchscreens, webcam, filament tracking, mobile companions, remote monitoring, Klipper add-ons, and firmware tools. **Adding a component is one entry in the catalog** — the engine itself never changes.

| Group | Examples |
| ----- | -------- |
| Core | Klipper, Moonraker |
| Web UIs | FilaMind 3d, Mainsail, Fluidd |
| Touchscreens | FilaMind screen, KlipperScreen, Guppyscreen |
| Host widgets | FilaMind flow |
| Webcam | Crowsnest |
| Filament | Spoolman |
| Companions | Mobileraker, OctoApp |
| Monitoring / remote | Obico, OctoEverywhere, SimplyPrint |
| Klipper add-ons | KAMP, TMC Autotune, Shake&Tune, LED Effect, Timelapse, and more |
| Firmware tools | Katapult, CAN-bus tools |

How a component installs depends on its catalog `type`:

- **FilaMind apps** (flow, 3d, screen) install through their own one-line installers.
- **Git-based components** are cloned and handed to their own `install.sh`.
- **Web UIs** are detected and linked once present — install them with their own setup or a tool like KIAUH, and the manager picks them up.
- **Dependencies install first** (for example Moonraker before a UI). Install detection combines Moonraker's update manager, managed systemd services, and on-disk checks, so it stays accurate even when one signal is missing.

## Wizards

- **Setup wizard** (`bootstrap`) — the first install. It probes the host, then installs the FilaMind suite. If Klipper or Moonraker aren't present yet, it tells you to install those first and stops, rather than guessing.
- **Migration** — adopt an existing Klipper / Moonraker / UI setup by installing FilaMind **alongside** it. This is non-destructive: your Klipper config, macros, and Moonraker database are left untouched, and your previous UI keeps working.

## How it's built

FilaMind Setup is deliberately small and dependency-free: a Python 3 engine (`engine.py`), a thin CLI front-end (`filamind-setup`), a bootstrap shell script (`install.sh`), and the catalog (`catalog.json`). The engine uses only the Python standard library, so it runs on a fresh printer host with nothing extra installed. Every catalog entry is validated on load, every repo slug is checked before it ever reaches a URL or a command, and the manager never clears anything outside a direct child of `$HOME`. For the full design — the catalog schema, install detection, the safety rules, and how the CLI and the flow widget share one engine — see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## How it relates to the suite

`filamind-setup` is the shared engine. The **Setup** widget in [FilaMind flow](https://github.com/filamind-app/filamind-flow) is the graphical front-end of the same catalog and the same engine. Either way, you get the same one-command install of the FilaMind suite, and the same catalog for everything around it.

## Develop

You only need Python 3.11+ and `git`.

```bash
git clone https://github.com/filamind-app/filamind-setup.git
cd filamind-setup

python -m py_compile engine.py filamind-setup    # compiles cleanly
python -c "import json; json.load(open('catalog.json'))"   # catalog is valid JSON
bash -n install.sh                                # bootstrap script parses
```

Probing is always read-only, so you can run it anywhere:

```bash
python ./filamind-setup probe
python ./filamind-setup list
```

To add a component, add one entry to `catalog.json` (the schema and `type` values are documented in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)) — no engine change needed. CI runs the same checks above plus a dependency-order smoke test on every push and pull request.

## Documentation

| Document | What's inside |
| -------- | ------------- |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Catalog schema, the shared engine, install detection, the safety model, and the two front-ends |
| [catalog.json](catalog.json) | The component catalog itself — the single source of truth |

## Support

FilaMind Setup is free and open source, built and maintained in spare time. If it saved you an afternoon of setup, or you just want to see it grow, a coffee helps keep the work going. Code, catalog entries, and ideas are just as welcome.

<div align="center">

[![Support on Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/I2I119XEIV)

</div>

## Credits

Built and maintained by the DeltaFabs team. Built by Egyptian makers, for world makers.

## License

[GPL-3.0-or-later](LICENSE) © 2026 DeltaFabs team.
