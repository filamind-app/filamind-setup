# ======================================================================= #
#  FilaMind Setup - shared engine.                                         #
#  One engine, two front-ends: the `filamind-setup` CLI and the Setup      #
#  widget in FilaMind flow both drive it. Installs the FilaMind suite and   #
#  the wider Klipper ecosystem by delegating to each component's own        #
#  installer; nothing here is destructive without the operator's say-so.    #
#  GPL-3.0-or-later - FilaMind's own.                                       #
# ======================================================================= #
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

CATALOG = Path(__file__).with_name("catalog.json")
HOME = Path.home()

# A GitHub "owner/repo" slug. Validated before it is ever placed in a URL or a command so a
# catalog typo or hostile entry can never inject shell metacharacters or a foreign host.
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

# Component install types the engine knows how to act on.
_KNOWN_TYPES = {"git_repo", "web", "service", "tauri", "manual"}


@dataclass
class Component:
    id: str
    name: str
    kind: str
    repo: str
    type: str  # git_repo | web | service | tauri | manual
    deps: list[str] = field(default_factory=list)
    first_party: bool = False
    group: str = ""
    desc: str = ""
    manager_key: str = ""
    service: str = ""
    dir: str = ""
    install: str = ""  # install-script path within the repo clone (defaults to install.sh)

    @property
    def install_dir(self) -> Path:
        return HOME / (self.dir or self.id)

    @property
    def repo_url(self) -> str:
        return f"https://github.com/{self.repo}.git"

    @property
    def raw_installer(self) -> str:
        # First-party apps carry a one-line scripts/install.sh in their repo.
        return f"https://raw.githubusercontent.com/{self.repo}/main/scripts/install.sh"


def load_catalog(path: Path = CATALOG) -> dict[str, Component]:
    data = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, Component] = {}
    for g in data["groups"]:
        for c in g["components"]:
            # Validate up front so a malformed catalog fails loudly here, not mid-install.
            for req in ("id", "name", "kind", "repo", "type"):
                if not c.get(req):
                    raise SetupError(f"Catalog component is missing '{req}': {c!r}")
            if c["type"] not in _KNOWN_TYPES:
                raise SetupError(f"Catalog component {c['id']!r} has unknown type {c['type']!r}")
            if not _REPO_RE.match(c["repo"]):
                raise SetupError(f"Catalog component {c['id']!r} has an unsafe repo {c['repo']!r}")
            out[c["id"]] = Component(
                id=c["id"],
                name=c["name"],
                kind=c["kind"],
                repo=c["repo"],
                type=c["type"],
                deps=c.get("deps", []),
                first_party=c.get("first_party", False),
                group=g["group"],
                desc=c.get("desc", ""),
                manager_key=c.get("manager_key", ""),
                service=c.get("service", ""),
                dir=c.get("dir", ""),
                install=c.get("install", ""),
            )
    return out


def resolve_order(ids: list[str], catalog: dict[str, Component]) -> list[str]:
    """Topological install order so dependencies come first (e.g. moonraker before mainsail)."""
    seen: set[str] = set()
    order: list[str] = []

    def visit(cid: str) -> None:
        if cid in seen or cid not in catalog:
            return
        seen.add(cid)
        for dep in catalog[cid].deps:
            visit(dep)
        order.append(cid)

    for cid in ids:
        visit(cid)
    return order


def _moonraker_managed(url: str = "http://127.0.0.1:7125") -> set[str]:
    """Names the local Moonraker update manager tracks (lowercased); empty if unreachable."""
    try:
        with urllib.request.urlopen(f"{url}/machine/update/status", timeout=3) as r:
            data = json.load(r)
        info = data.get("result", {}).get("version_info", {})
        return {k.lower() for k in info}
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError):
        # Unreachable / non-JSON / unexpected shape — detection falls back to the dir/unit heuristics.
        return set()


class SetupError(RuntimeError):
    pass


class SetupEngine:
    """Drives catalog-based install / update / remove by delegating to each component's own
    installer. Read-only probing is always safe; mutations shell out to git and the components'
    install scripts (which use sudo where needed)."""

    def __init__(
        self,
        log: Callable[[str], None] = print,
        runner: Callable[[list[str]], int] | None = None,
    ) -> None:
        self.catalog = load_catalog()
        self.log = log
        self._run = runner or self._default_run

    # ---- command runner (overridable for tests / the GUI backend) ----
    def _default_run(self, cmd: list[str]) -> int:
        self.log("    $ " + " ".join(cmd))
        return subprocess.run(cmd, check=False).returncode

    def _run_remote_installer(self, c: Component, *args: str) -> int:
        """Download a first-party component's installer (no shell), then run its CONTENTS via
        ``bash -c`` with list arguments - so a repo/path can never inject shell syntax.

        We run the script's *contents*, not the temp-file path: the first-party installers decide
        "am I a clone or a curl|bash pipe?" by testing ``[ -f "$BASH_SOURCE" ]``. Handing them a temp
        file makes that test true, so they assume a clone layout (deploy/install.sh as a sibling)
        that isn't there and fail (APP resolves to ``/``). Running the contents leaves BASH_SOURCE
        empty - the same state as ``curl | bash`` - so the installer self-clones, which is correct.
        """
        if not _REPO_RE.match(c.repo):
            raise SetupError(f"Unsafe repo for {c.name}: {c.repo!r}")
        fd, tmp = tempfile.mkstemp(suffix=".sh")
        os.close(fd)
        try:
            if self._run(["curl", "-fsSL", c.raw_installer, "-o", tmp]) != 0:
                raise SetupError(f"Could not download the {c.name} installer")
            with open(tmp, encoding="utf-8") as fh:
                script = fh.read()
            # $0 is a label; real args become $1.. (passed as a list, never shell-interpolated).
            return self._run(["bash", "-c", script, "filamind-setup", *args])
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass

    # ---- read-only ----
    def list_components(self) -> list[Component]:
        return list(self.catalog.values())

    def probe(self, moonraker_url: str = "http://127.0.0.1:7125") -> dict:
        """OS facts + which catalog components look installed. Pure reads, never mutates."""
        managed = _moonraker_managed(moonraker_url)
        services = self._systemd_units()
        installed = {cid: self._is_installed(c, managed, services) for cid, c in self.catalog.items()}
        return {
            "os": self._os_release(),
            "installed": installed,
            "has_klipper": installed.get("klipper", False),
            "has_moonraker": installed.get("moonraker", False),
        }

    def status(self, cid: str, probe: dict | None = None) -> str:
        p = probe or self.probe()
        return "installed" if p["installed"].get(cid) else "not-installed"

    def _is_installed(self, c: Component, managed: set[str], services: set[str]) -> bool:
        key = (c.manager_key or c.id).lower()
        if key in managed:
            return True
        if c.service and c.service.lower() in services:
            return True
        return c.install_dir.is_dir()

    def _systemd_units(self) -> set[str]:
        try:
            out = subprocess.run(
                ["systemctl", "list-units", "--type=service", "--all", "--plain", "--no-legend"],
                capture_output=True,
                text=True,
                check=False,
            ).stdout
        except FileNotFoundError:
            return set()
        return {line.split(".service")[0].strip().lower() for line in out.splitlines() if ".service" in line}

    def _os_release(self) -> str:
        try:
            for line in Path("/etc/os-release").read_text().splitlines():
                if line.startswith("PRETTY_NAME="):
                    return line.split("=", 1)[1].strip().strip('"')
        except OSError:
            pass
        return os.uname().sysname if hasattr(os, "uname") else "unknown"

    # ---- mutations ----
    def install(self, cid: str, probe: dict | None = None) -> None:
        if cid not in self.catalog:
            raise SetupError(f"Unknown component: {cid}")
        self.install_all([cid], probe=probe)

    def install_all(self, ids: list[str], probe: dict | None = None) -> None:
        """Install several targets in ONE dependency-resolved pass, so a shared dependency (e.g.
        Moonraker) installs once, not once per target. On an empty host this naturally installs
        Klipper -> Moonraker first, then the targets - a true from-scratch install."""
        p = probe or self.probe()
        for dep in resolve_order(ids, self.catalog):
            c = self.catalog.get(dep)
            if c is None:
                continue
            if p["installed"].get(dep):
                self.log(f"[skip] {c.name} already installed")
                continue
            self.log(f"[install] {c.name} ({c.type})")
            self._do_install(c)
            p["installed"][dep] = True  # mark done so a later target won't reinstall it this run

    def remove(self, cid: str) -> None:
        if cid not in self.catalog:
            raise SetupError(f"Unknown component: {cid}")
        c = self.catalog[cid]
        self.log(f"[remove] {c.name}")
        self._do_remove(c)

    def _do_install(self, c: Component) -> None:
        if c.first_party:
            # FilaMind apps carry a self-cloning one-line installer (fetched + run without a shell).
            if self._run_remote_installer(c) != 0:
                raise SetupError(f"{c.name} installer failed")
            return
        if c.type in ("git_repo", "service"):
            dest = c.install_dir
            # A leftover non-git directory (e.g. an interrupted clone) would corrupt the install -
            # clear it first, but only ever a direct $HOME child.
            if dest.exists() and not (dest / ".git").is_dir():
                if dest.parent != HOME:
                    raise SetupError(f"Refusing to clear {dest} (not a direct $HOME child)")
                shutil.rmtree(dest)
            if not (dest / ".git").is_dir():
                if self._run(["git", "clone", "--depth", "1", c.repo_url, str(dest)]) != 0:
                    raise SetupError(f"git clone of {c.name} failed")
            # Never trust a half-finished clone before running its installer.
            if self._run(["git", "-C", str(dest), "rev-parse", "--is-inside-work-tree"]) != 0:
                raise SetupError(f"{c.name} clone is incomplete/corrupt at {dest}")
            # Run the component's own installer. Most carry install.sh at the root; some - Klipper
            # (scripts/install-debian.sh), Moonraker (scripts/install-moonraker.sh), KlipperScreen -
            # ship it elsewhere, declared as `install` in the catalog. Those official installers set
            # up the OS deps, the venv and the systemd service, i.e. a real from-scratch install.
            installer = dest / (c.install or "install.sh")
            if installer.is_file():
                if self._run(["bash", str(installer)]) != 0:
                    raise SetupError(f"{c.name} installer ({installer.name}) failed")
            else:
                self.log(f"    cloned {c.name}; no installer at {installer.name} - finish per its docs")
            return
        if c.type == "web":
            self.log(
                f"    {c.name} is a web UI - install it with its own setup (or KIAUH); "
                "this manager links it once present."
            )
            return
        if c.type == "manual":
            self.log(f"    {c.name} needs manual steps - see its documentation.")
            return
        # Any other type (e.g. a non-first-party tauri) is not installable here - fail loudly
        # instead of silently claiming success.
        raise SetupError(f"Don't know how to install {c.name} (type {c.type!r})")

    def _do_remove(self, c: Component) -> None:
        if c.first_party:
            self._run_remote_installer(c, "uninstall")
            return
        if c.service:
            self._run(["sudo", "-n", "systemctl", "disable", "--now", c.service])
        dest = c.install_dir
        if dest.parent == HOME and dest.is_dir():
            # No silent ignore_errors: a failed removal must surface, never report a false "removed".
            try:
                shutil.rmtree(dest)
            except OSError as exc:
                raise SetupError(f"Could not remove {dest}: {exc}") from exc
            self.log(f"    removed {dest}")
        else:
            self.log(f"    left {dest} in place (not a direct $HOME child)")

    # ---- wizards (front-ends supply `ask`) ----
    def bootstrap(self, ask: Callable[[str, list[str]], str] | None = None) -> None:
        """First-run wizard covering every scenario from one command: an EMPTY host gets the full
        stack from scratch (Klipper + Moonraker + the FilaMind suite); an EXISTING Mainsail/Fluidd
        host is installed alongside or migrated; an already-FilaMind host just tops up what's missing."""
        p = self.probe()
        self.log(f"Detected: {p['os']}")
        empty = not (p["has_klipper"] and p["has_moonraker"])
        existing = [u for u in ("mainsail", "fluidd", "klipperscreen") if p["installed"].get(u)]
        if existing and ask:
            choice = ask(
                f"Found an existing setup ({', '.join(existing)}). How do you want to proceed?",
                ["install FilaMind alongside", "migrate to FilaMind", "cancel"],
            )
            if choice == "cancel":
                return
            if choice == "migrate to FilaMind":
                self.migrate(p)
                return
        if empty:
            self.log("No Klipper/Moonraker detected - installing the whole stack from scratch:")
            self.log("  Klipper + Moonraker + the FilaMind suite (flow + 3d).")
        else:
            self.log("Installing the FilaMind suite (flow + 3d); any missing dependency is added too.")
        # Dependency resolution installs Klipper -> Moonraker first on an empty host, then the suite.
        self.install_all(["filamind-flow", "filamind-3d"], probe=p)
        self.log("Done.")

    def migrate(self, probe: dict | None = None) -> None:
        """Adopt an existing Klipper/Moonraker setup: install FilaMind alongside, non-destructively.
        Settings stay in Moonraker's DB and are picked up automatically; nothing is deleted."""
        p = probe or self.probe()
        self.log("Migrating non-destructively: installing FilaMind alongside your current UI.")
        self.log("Your Klipper config, macros and Moonraker database are left untouched.")
        self.install_all(["filamind-flow", "filamind-3d"], probe=p)
        self.log("Done. Your previous UI still works; open FilaMind to use the suite.")
