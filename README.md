# FilaMind Setup

FilaMind's own installer/manager for the Klipper 3D-printing stack. **One engine, two front-ends:**
a command-line tool (`filamind-setup`) and the **Setup** widget inside FilaMind flow both drive the
same engine, so behaviour is identical and there is one source of truth.

## Install (one line)

Run on the printer host as your normal printer user:

```bash
curl -fsSL https://raw.githubusercontent.com/filamind-app/filamind-setup/main/install.sh | bash
```

This clones the installer, puts the `filamind-setup` command on your PATH, and runs the **first-run
wizard**: it detects your printer, then either installs the FilaMind suite or adopts an existing
Mainsail/Fluidd setup alongside it (non-destructively).

## Ongoing use

```bash
filamind-setup              # interactive menu
filamind-setup list         # the catalog + what's installed
filamind-setup install <id> # install a component (and its dependencies)
filamind-setup remove  <id> # remove a component
filamind-setup probe        # show what was detected
```

## What it manages

A curated catalog (`catalog.json`) spanning the stack: core (Klipper, Moonraker), web UIs,
touchscreens, webcam, filament, companions, monitoring/remote, Klipper add-ons and firmware tools.
**Adding a component is one catalog entry** - the engine needs no change.

- **FilaMind apps** (flow, 3d, screen) install through their own one-line installers.
- **Git-based components** are cloned and handed to their own `install.sh`.
- **Web UIs** are detected and linked once present (install them with their own setup or KIAUH).
- Dependencies install first (e.g. Moonraker before a UI). Install detection combines Moonraker's
  update manager, managed services and on-disk checks.

## Wizards

- **Setup wizard** (`bootstrap`) - first install: probe the host, then install the suite. If Klipper
  or Moonraker aren't present, it tells you to install them first.
- **Migration** - adopt an existing Klipper/Moonraker/UI setup by installing FilaMind **alongside**
  it. Non-destructive: your Klipper config, macros and Moonraker database are left untouched.

## How it relates to the suite

`filamind-setup` is the shared engine; the **Setup** widget in
[FilaMind flow](https://github.com/filamind-app/filamind-flow) is the GUI front-end of the same
catalog. Either way you get the same one-command install of the FilaMind suite.

GPL-3.0-or-later.
