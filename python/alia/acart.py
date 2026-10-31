# SPDX-License-Identifier: MIT
# Copyright (c) 2026 NU Hachimi (Alia Pad cart SDK)
"""acart: carts from the command line (docs/cart.md). Talks to alia-session's
pad.alia.Apps1, on this machine or, with --board, on the board over adb.

  acart check [--pc] DIR...      validate cart directories (no device needed); --pc: a PC
                                 build for acart run (x86-64) instead of the board's (arm64)
  acart pack DIR [-o OUT] [--key KEY] [--comp zstd|gzip]   build an .acart
  acart run DIR [ARGS...] [--lang L] [--fresh] [--software] [--browser]   run it on this
                                 PC as the handheld would (the alia-runtime image; Docker or
                                 Podman): a window on a Wayland desktop, else a browser page
  acart exec DIR [--env K=V] -- COMMAND...   run a command in the runtime image, headless
                                 (tests and tools: pytest is there); DIR read-write, the cwd
  acart info FILE                read an .acart's trailer: manifest, hash, signature
  acart keygen PATH              new ed25519 signing key (PATH, PATH.pub)
  acart install FILE             install an .acart (with --board: copied over adb first)
  acart remove ID [--purge]      uninstall; --purge also deletes its saves
  acart verify ID                re-check an installed cart's hash and signature
  acart list [--json]            carts the session knows, and manifests that didn't load
  acart status                   what's in front
  acart launch [--replace] ID [ARGS...]   (--replace: stop what is in front first)
  acart stop [--force]
  acart suspend | resume         pause / continue the cart in front (SIGSTOP / SIGCONT)
  acart home                     what the Home button does: suspend it, show the Shell
  acart awake                    keep the screen from going off (idle) while this runs, for
                                 unattended runs; ends with Ctrl-C, kill, or a lost adb
  acart reload                   rescan the cart directories
  acart watch                    one line per event, for scripts and tools
                                 ("alive" every 10 s, so it ends when nobody reads it)
  acart --board push DIR [--launch]   copy an unpacked cart to the board's cart directory

Local bus: session ($ALIA_BUS=system for the system bus); the board runs acart itself
on its system bus. Watch lines: "foreground ID|- STATE", "started ID", "exited ID CODE",
"crashed ID LOG", "carts-changed", "session up|down".
"""
import argparse
import asyncio
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

BOARD_SRC = "/home/alia/alia-pad/src"
BOARD_CARTS = "/home/alia/.local/share/alia/carts"
NAME, PATH, IFACE = "pad.alia.Apps1", "/pad/alia/Apps1", "pad.alia.Apps1"
CARTS = ("pad.alia.Carts1", "/pad/alia/Carts1", "pad.alia.Carts1")


def unwrap(v):
    from dbus_fast import Variant
    if isinstance(v, Variant):
        return unwrap(v.value)
    if isinstance(v, dict):
        return {k: unwrap(x) for k, x in v.items()}
    if isinstance(v, list):
        return [unwrap(x) for x in v]
    return v


class Client:
    def __init__(self, bus_name: str):
        self.bus_name = bus_name
        self.bus = None

    async def connect(self):
        from dbus_fast import BusType
        from dbus_fast.aio import MessageBus
        self.bus = await MessageBus(bus_type=BusType.SYSTEM if self.bus_name == "system" else BusType.SESSION).connect()
        return self

    async def call(self, member, signature="", body=(), iface=IFACE, dest=(NAME, PATH)):
        from dbus_fast import Message, MessageType
        r = await self.bus.call(Message(destination=dest[0], path=dest[1], interface=iface, member=member,
                                        signature=signature, body=list(body)))
        if r.message_type == MessageType.ERROR:
            name = r.error_name.removeprefix("pad.alia.Apps1.Error.").removeprefix("pad.alia.Carts1.Error.")
            if r.error_name == "org.freedesktop.DBus.Error.ServiceUnknown":
                raise SystemExit("alia-session isn't running")
            raise SystemExit(f"{name}: {r.body[0] if r.body else ''}")
        return unwrap(r.body)

    async def props(self):
        (d,) = await self.call("GetAll", "s", [IFACE], iface="org.freedesktop.DBus.Properties")
        return d


async def cmd_list(c: Client, a):
    (carts,) = await c.call("List")
    props = await c.props()
    if a.json:
        print(json.dumps({"carts": carts, "problems": props["Problems"], "foreground": props["Foreground"]},
                         ensure_ascii=False))
        return
    for x in carts:
        mark = "*" if x["id"] == props["Foreground"] else " "
        names = [t for t in dict.fromkeys((x.get("titles") or {}).values()) if t != x["title"]]
        title = " / ".join([x["title"], *names])  # every translated title ([locale.<tag>])
        kind = {"dir": "dir", "image": "acart" + ("+sig" if x.get("signed") else "")}.get(x.get("kind"), "?")
        print(f"{mark} {x['id']:32} {x['version']:8} {x['runtime']:8} {kind:10} {title}")
    for p in props["Problems"]:
        print(f"! {p}")


async def cmd_status(c: Client, a):
    p = await c.props()
    bg = " (background)" if p["Foreground"] and p.get("Showing") == "shell" else ""
    print(f"foreground {p['Foreground'] or '-'} {p['State']}{bg}")


async def cmd_launch(c: Client, a):
    if a.replace:
        p = await c.props()
        if p["Foreground"]:
            await c.call("Terminate", "b", [False])
            for _ in range(60):
                await asyncio.sleep(0.1)
                if not (await c.props())["Foreground"]:
                    break
    await c.call("Launch", "sas", [a.id, a.args])
    print(f"launched {a.id}")


async def cmd_stop(c: Client, a):
    await c.call("Terminate", "b", [a.force])


async def cmd_suspend(c: Client, a):
    await c.call("Suspend")
    await cmd_status(c, a)


async def cmd_resume(c: Client, a):
    await c.call("Resume")
    await cmd_status(c, a)


async def cmd_home(c: Client, a):
    await c.call("Home")
    await cmd_status(c, a)


async def cmd_awake(c: Client, a):
    """Renew a 30 s HoldAwake lease every 10 s (alia-core's idle screen-off), saying "alive"
    each time: once nobody reads us (adb gone), the write fails and the lease runs out."""
    from dbus_fast import Message
    while True:
        r = await c.bus.call(Message(destination="pad.alia.System1", path="/pad/alia/System1",
                                     interface="pad.alia.System1", member="HoldAwake", signature="su",
                                     body=["acart awake", 30]))
        if r.error_name:
            print(f"HoldAwake: {r.error_name} {r.body}", file=sys.stderr)
            return 1
        try:
            print("alive", flush=True)
        except OSError:
            os._exit(0)
        await asyncio.sleep(HEARTBEAT_S)


async def cmd_reload(c: Client, a):
    await c.call("Reload")
    await cmd_list(c, argparse.Namespace(json=False))


async def cmd_install(c: Client, a):
    (cart_id,) = await c.call("Install", "s", [str(Path(a.file).resolve())], iface=CARTS[2], dest=CARTS[:2])
    print(f"installed {cart_id}")


async def cmd_remove(c: Client, a):
    await c.call("Remove", "sb", [a.id, a.purge], iface=CARTS[2], dest=CARTS[:2])
    print(f"removed {a.id}" + (" and its saves" if a.purge else ""))


async def cmd_verify(c: Client, a):
    (msg,) = await c.call("Verify", "s", [a.id], iface=CARTS[2], dest=CARTS[:2])
    print(f"{a.id}: {msg}")


HEARTBEAT_S = 10


async def cmd_watch(c: Client, a):
    from dbus_fast import Message, MessageType
    rules = [f"type='signal',sender='{NAME}',path='{PATH}'",
             f"type='signal',sender='{CARTS[0]}',path='{CARTS[1]}'",
             f"type='signal',sender='org.freedesktop.DBus',member='NameOwnerChanged',arg0='{NAME}'"]
    for r in rules:
        await c.bus.call(Message(destination="org.freedesktop.DBus", path="/org/freedesktop/DBus",
                                 interface="org.freedesktop.DBus", member="AddMatch", signature="s", body=[r]))
    state = {"fg": None, "st": None}

    def emit(line):
        try:
            print(line, flush=True)
        except OSError:  # the reader is gone (BrokenPipeError): nobody is watching
            os._exit(0)

    async def heartbeat():
        # Over adb (--board), killing the local adb leaves this process running on the board
        # (no hangup reaches it), and it only writes when something changes: the panel left
        # one behind per connection. A line every 10 s fails once the reader is gone.
        while True:
            await asyncio.sleep(HEARTBEAT_S)
            emit("alive")

    def foreground(fg, st):
        if (fg, st) != (state["fg"], state["st"]):
            state.update(fg=fg, st=st)
            emit(f"foreground {fg or '-'} {st}")

    def handler(m):
        if m.message_type != MessageType.SIGNAL:
            return
        if m.member == "NameOwnerChanged":
            emit("session up" if m.body[2] else "session down")
            if m.body[2]:  # appeared after we started watching: say what's in front
                asyncio.get_running_loop().create_task(current())
            else:
                foreground("", "idle")
        elif m.member == "PropertiesChanged":
            ch = unwrap(m.body[1])
            foreground(ch.get("Foreground", state["fg"]), ch.get("State", state["st"]))
        elif m.member == "Started":
            emit(f"started {m.body[0]}")
        elif m.member == "Exited":
            emit(f"exited {m.body[0]} {m.body[1]}")
        elif m.member == "Crashed":
            emit(f"crashed {m.body[0]} {m.body[1]}")
        elif m.member == "CartsChanged":
            emit("carts-changed")
        elif m.member in ("Installed", "Removed"):
            emit(f"{m.member.lower()} {m.body[0]}")

    async def current():
        try:
            p = await c.props()
        except SystemExit:  # gone again already
            return
        state.update(fg=None, st=None)
        foreground(p["Foreground"], p["State"])

    c.bus.add_message_handler(handler)
    asyncio.get_running_loop().create_task(heartbeat())
    try:
        p = await c.props()
        emit("session up")
        foreground(p["Foreground"], p["State"])
    except SystemExit:
        emit("session down")
    await c.bus.wait_for_disconnect()


def cmd_check(a) -> int:
    from alia import cart as cartlib
    from alia import platform
    bad = 0
    for d in a.dirs:
        try:
            c = cartlib.load(d)
        except cartlib.CartError as e:
            print(f"✗ {e}")
            bad += 1
            continue
        problems, notes = platform.check(c, "pc" if a.pc else "board")
        art = ", ".join(c.art) or "no art"
        shots = f", {len(c.screenshots)} screenshots" if c.screenshots else ""
        mark = "✗" if problems else "✓"
        print(f"{mark} {c.id} {c.version} ({c.runtime}{', dev' if c.dev else ''}, platform {c.platform}): {art}{shots}")
        for p in problems:
            print(f"  ✗ {p}")
        for n in c.notes + notes:
            print(f"  note: {n}")
        bad += bool(problems)
    return 1 if bad else 0


RUNTIME_IMAGE = "ghcr.io/nu-hachimi/alia-runtime"


def runtime_dirs() -> tuple[Path, Path]:
    """Where acart run keeps saves and settings, and caches: the platform's own places."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "alia-runtime"
        return base, base / "cache"
    if sys.platform == "darwin":
        return (Path.home() / "Library/Application Support/alia-runtime",
                Path.home() / "Library/Caches/alia-runtime")
    return (Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "alia-runtime",
            Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "alia-runtime")


# Docker's own errors (before the cart starts) -> what they mean here
DOCKER_HINTS = [
    ("Cannot connect to the Docker daemon", "Docker isn't running: start Docker Desktop (or the docker service)"),
    ("failed to connect to the docker API", "Docker isn't running: start Docker Desktop (or the docker service)"),
    ("port is already allocated", "the page's port is taken (another acart run?): pick one with --port"),
    ("address already in use", "the page's port is taken (another acart run?): pick one with --port"),
]


def _page_up(url: str, proc, timeout: float) -> bool:
    """Wait for the simulator's page to answer (the first run pulls the image first)."""
    import time
    import urllib.request
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and proc.poll() is None:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return True
        except OSError:
            pass
        time.sleep(0.5)
    return False


def runtime_size():
    from alia import runtime
    return runtime.display()["size"]


def cmd_run(a) -> int:
    """Run a cart directory on this PC the way the handheld runs it, in the alia-runtime
    image (Docker or Podman): the same libraries, rules, gamepad and pause behaviour."""
    import glob
    import shutil
    import tempfile
    from alia import cart as cartlib
    try:
        c = cartlib.load(a.dir)
    except cartlib.CartError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1
    engine = os.environ.get("ALIA_RT_ENGINE") or shutil.which("docker") or shutil.which("podman")
    if not engine:
        print("✗ acart run needs Docker or Podman", file=sys.stderr)
        return 1
    xdg = os.environ.get("XDG_RUNTIME_DIR", "")
    wl = os.environ.get("WAYLAND_DISPLAY", "")
    wl_sock = wl if wl.startswith("/") else os.path.join(xdg, wl)
    # a window on a Wayland desktop, or else the browser (macOS, Windows, X11): the picture,
    # sound and gamepads go through a page on this machine
    browser = a.browser or not (wl and os.path.exists(wl_sock))
    home, caches = runtime_dirs()
    state = home / "settings.json"
    save = Path(tempfile.mkdtemp(prefix="alia-save-")) if a.fresh else home / "saves" / c.id
    cache = caches / c.id
    for d in (save, cache, home):
        d.mkdir(parents=True, exist_ok=True)
    lang = a.lang
    if not lang:
        try:
            lang = json.loads(state.read_text())["lang"]
        except (OSError, ValueError, KeyError):
            lang = "zh-CN" if os.environ.get("LANG", "").startswith("zh") else "en"
    from alia import platform
    import platform as host
    target = "board" if host.machine() in ("aarch64", "arm64") else "pc"  # the image runs this machine's arch
    problems, _ = platform.check(c, target)
    for p in problems:
        print(f"warning: {p}", file=sys.stderr)
    image = a.image or os.environ.get("ALIA_RT_IMAGE") or f"{RUNTIME_IMAGE}:{c.platform}"
    uid, gid = (os.getuid(), os.getgid()) if hasattr(os, "getuid") else (1000, 1000)  # Windows: any
    cmd = [engine, "run", "--rm", "--init", "--security-opt", "label=disable",
           "-v", f"{Path(a.dir).resolve()}:/cart:ro", "-v", f"{save}:/save", "-v", f"{cache}:/cache",
           "-v", f"{home}:/state",
           "-e", f"ALIA_RT_UID={uid}", "-e", f"ALIA_RT_GID={gid}",
           "-e", f"ALIA_RT_LANG={lang}", "-e", f"ALIA_RT_SIZE={a.size or 'x'.join(map(str, runtime_size()))}",
           "-e", f"ALIA_RT_ARGS={json.dumps(a.args)}", "-e", "ALIA_RT_STATE=/state/settings.json"]
    # the cart's gamepad: uinput where this machine has it; else (Docker Desktop on Windows and
    # macOS) the image simulates the same gamepad in user space by itself
    if os.path.exists("/dev/uinput"):
        cmd += ["--device", "/dev/uinput", "--device-cgroup-rule", "c 13:* rmw"]
    if os.path.isdir("/dev/dri") and not a.software:
        cmd += ["--device", "/dev/dri"]
    if a.software:
        cmd += ["-e", "LIBGL_ALWAYS_SOFTWARE=1"]
    if browser:  # the container's own PipeWire and a page on this machine only
        cmd += ["-p", f"127.0.0.1:{a.port}:7300", "-e", "ALIA_RT_BROWSER=1", "-e", f"ALIA_RT_HOST_PORT={a.port}",
                "--cap-add", "NET_ADMIN"]  # the supervisor closes the network for the cart (iptables)
    else:
        cmd += ["-v", f"{wl_sock}:/run/host-wayland"]
    pw = os.path.join(xdg, "pipewire-0")
    if a.debug:
        cmd += ["-e", "ALIA_RT_DEBUG=1"]
    if a.no_audio:
        cmd += ["-e", "ALIA_RT_NO_AUDIO=1"]
    elif browser:
        pass
    elif os.path.exists(pw):
        cmd += ["-v", f"{pw}:/run/alia/pipewire-0"]
    else:
        print("note: no PipeWire here: the cart runs without sound", file=sys.stderr)
    # the PC's gamepads (in the browser mode the page reads them, any system)
    pads = [] if browser else sorted({os.path.realpath(p) for p in glob.glob("/dev/input/by-id/*-event-joystick")})
    for i, p in enumerate(pads):
        cmd += ["--device", f"{p}:/run/host-input/pad{i}:r"]
    if pads:
        cmd += ["-e", "ALIA_RT_PADS=" + ":".join(f"/run/host-input/pad{i}" for i in range(len(pads)))]
    if not c.permissions.get("network") and not browser:
        cmd += ["--network", "none"]
    cmd.append(image)
    print(f"{c.id} {c.version} in {image} (language {lang}, saves in {save})", file=sys.stderr)
    import threading
    proc = subprocess.Popen(cmd, stderr=subprocess.PIPE, text=True, errors="replace")
    said = []

    def relay():  # the container's messages as they come, and an explanation for Docker's own errors
        for line in proc.stderr:
            sys.stderr.write(line)
            sys.stderr.flush()
            for pattern, hint in DOCKER_HINTS:
                if pattern in line and hint not in said:
                    said.append(hint)
    relayer = threading.Thread(target=relay, daemon=True)
    relayer.start()
    if browser:
        url = f"http://localhost:{a.port}"

        def when_up():
            if _page_up(f"http://127.0.0.1:{a.port}/", proc, 180):
                print(f"open {url} (the simulator's screen, sound and gamepads)", file=sys.stderr)
                if not a.no_open:
                    import webbrowser
                    webbrowser.open(url)
        threading.Thread(target=when_up, daemon=True).start()
    while True:
        try:
            code = proc.wait()
            break
        except KeyboardInterrupt:  # Docker passes it on: the cart quits as on the handheld
            continue
    relayer.join(timeout=2)
    for hint in said:
        print(f"✗ {hint}", file=sys.stderr)
    if code in (125, 126, 127) and not said:  # docker run's own failures, not the cart's exit
        print(f"✗ the simulator didn't start (docker exit {code}): see the message above", file=sys.stderr)
    return code


def cmd_exec(a) -> int:
    """Run any command in the alia-runtime image, headless: tests and tools (`alia test`),
    not carts. The directory is mounted read-write as the working directory; the command
    runs as this user; no window, gamepad, sound, sandbox or network rules. pytest and
    pyflakes are on PATH (their own environment, which carts never see)."""
    import glob
    import shutil
    engine = os.environ.get("ALIA_RT_ENGINE") or shutil.which("docker") or shutil.which("podman")
    if not engine:
        print("✗ acart exec needs Docker or Podman", file=sys.stderr)
        return 1
    if not a.command:
        print("✗ acart exec DIR -- COMMAND...", file=sys.stderr)
        return 2
    from alia import platform
    work = Path(a.dir).resolve()
    uid, gid = (os.getuid(), os.getgid()) if hasattr(os, "getuid") else (1000, 1000)
    image = a.image or os.environ.get("ALIA_RT_IMAGE") or f"{RUNTIME_IMAGE}:{platform.version()}"
    cmd = [engine, "run", "--rm", "--init", "--security-opt", "label=disable", "--entrypoint", "",
           "--user", f"{uid}:{gid}", "-v", f"{work}:/work", "-w", "/work",
           "-e", "HOME=/tmp", "-e", "PATH=/opt/alia-tools/bin:/usr/local/bin:/usr/bin:/bin",
           "-e", "PYTHONDONTWRITEBYTECODE=1", "-e", "XDG_CACHE_HOME=/tmp/.cache"]
    if os.path.isdir("/dev/dri"):
        cmd += ["--device", "/dev/dri"]
        gids = sorted({os.stat(p).st_gid for p in glob.glob("/dev/dri/*")})
        for g in gids:
            cmd += ["--group-add", str(g)]
    else:
        cmd += ["-e", "LIBGL_ALWAYS_SOFTWARE=1"]
    for kv in a.env or []:
        cmd += ["-e", kv]
    if sys.stdin.isatty() and sys.stdout.isatty():
        cmd += ["-it"]
    cmd += [image, *a.command]
    proc = subprocess.Popen(cmd)
    while True:
        try:
            return proc.wait()
        except KeyboardInterrupt:  # Docker passes it on
            continue


def cmd_pack(a) -> int:
    from alia import acart_file as af
    from alia import cart as cartlib
    from alia import platform
    try:
        c = cartlib.load(a.dir)
        problems, _ = platform.check(c)
        if problems:  # a cart that wouldn't run on the board isn't packed
            for p in problems:
                print(f"✗ {p}", file=sys.stderr)
            print("✗ not packed: fix the above (acart check shows the same)", file=sys.stderr)
            return 1
        out = Path(a.output or f"{c.id}-{c.version}.acart")
        try:
            af.find_mksquashfs()
        except af.AcartError:  # no squashfs-tools here (Windows, macOS): pack in the runtime image
            return pack_in_image(a, out)
        t = af.pack(a.dir, out, key=a.key, comp=a.comp)
    except (af.AcartError, cartlib.CartError) as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1
    print(f"{out}: {c.id} {c.version}, {out.stat().st_size / 1024:.0f} KiB, sha256 {t.sha256.hex()[:16]}…, "
          + (f"signed by {t.key_id.hex()[:16]}…" if t.signed else "unsigned"))
    return 0


def pack_in_image(a, out: Path) -> int:
    """acart pack inside the alia-runtime image, which has mksquashfs (and, for --key, the
    signing library): the cart read-only, the output's directory writable, run as this user."""
    import shutil
    from alia import platform
    engine = os.environ.get("ALIA_RT_ENGINE") or shutil.which("docker") or shutil.which("podman")
    if not engine:
        print("✗ packing needs mksquashfs (squashfs-tools), or Docker to pack in the runtime image",
              file=sys.stderr)
        return 1
    out = out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    uid, gid = (os.getuid(), os.getgid()) if hasattr(os, "getuid") else (1000, 1000)
    image = os.environ.get("ALIA_RT_IMAGE") or f"{RUNTIME_IMAGE}:{platform.version()}"
    cmd = [engine, "run", "--rm", "--security-opt", "label=disable", "--entrypoint", "",
           "--user", f"{uid}:{gid}", "--network", "none", "-e", "HOME=/tmp",
           "-v", f"{Path(a.dir).resolve()}:/cart:ro", "-v", f"{out.parent}:/out"]
    inner = ["/opt/alia-tools/bin/python", "-m", "alia.acart", "pack", "/cart", "-o", f"/out/{out.name}",
             "--comp", a.comp]
    if a.key:
        cmd += ["-v", f"{Path(a.key).resolve()}:/key:ro"]
        inner += ["--key", "/key"]
    print(f"(no mksquashfs here: packing in {image})", file=sys.stderr)
    code = subprocess.run(cmd + [image] + inner).returncode
    if code == 0:
        print(f"-> {out}")  # the line above names it as the image sees it (/out/...)
    return code


def cmd_info(a) -> int:
    from alia import acart_file as af
    try:
        t = af.read_trailer(a.file)
        ok = af.image_sha256(a.file, t.image_size) == t.sha256
    except af.AcartError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1
    print(f"image {t.image_size} bytes, sha256 {t.sha256.hex()} ({'ok' if ok else 'MISMATCH'})")
    print(f"signed by key {t.key_id.hex()}" if t.signed else "unsigned")
    print(t.manifest.rstrip())
    return 0 if ok else 1


def cmd_keygen(a) -> int:
    from alia import acart_file as af
    pub = af.keygen(a.path)
    print(f"private key {a.path} (keep it out of git), public key {pub}")
    print("trust it on the device: copy the .pub into ~/.local/share/alia/keys/ (or /etc/alia/keys/)")
    return 0


def cmd_push(a) -> int:
    from alia import cart as cartlib
    try:
        c = cartlib.load(a.dir)
    except cartlib.CartError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1
    dest = f"{BOARD_CARTS}/{c.id}"
    subprocess.run(["adb", "-d", "shell", f"rm -rf {shlex.quote(dest)} && mkdir -p {BOARD_CARTS}"], check=True)
    subprocess.run(["adb", "-d", "push", str(a.dir), dest], check=True, stdout=subprocess.DEVNULL)
    print(f"pushed {c.id} -> {dest}")
    remote(["reload"])
    return remote(["launch", "--replace", c.id]) if a.launch else 0


def board_install(a) -> int:
    tmp = f"/tmp/acart-install-{Path(a.file).name}"
    subprocess.run(["adb", "-d", "push", a.file, tmp], check=True, stdout=subprocess.DEVNULL)
    try:
        return remote(["install", tmp])
    finally:
        subprocess.run(["adb", "-d", "shell", f"rm -f {shlex.quote(tmp)}"])


def remote(args: list[str]) -> int:
    """Run acart on the board (its system bus), streaming its output: the board's own
    (python3-alia), or a development copy in BOARD_SRC while one runs from there."""
    rest = "python3 -m alia.acart --bus system " + " ".join(shlex.quote(x) for x in args)
    cmd = (f"if [ -e /run/alia-dev-stack ] || ! python3 -c 'import alia.acart' 2>/dev/null; then "
           f"cd {BOARD_SRC} && PYTHONPATH=sdk/python exec {rest}; else exec {rest}; fi")
    return subprocess.run(["adb", "-d", "shell", cmd]).returncode


def main(argv=None) -> int:
    # Output redirected on Windows gets the old code page (cp1252, GBK), which has no ✓ and
    # crashed acart check: write UTF-8 there instead (a log file reads it), never fail on a sign
    for stream in (sys.stdout, sys.stderr):
        try:
            "✓✗".encode(stream.encoding or "ascii")
        except (UnicodeEncodeError, LookupError):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, ValueError):
                pass
    ap = argparse.ArgumentParser(prog="acart", description=__doc__.split("\n\n")[0])
    ap.add_argument("--board", action="store_true", help="the board, over adb")
    ap.add_argument("--bus", choices=["system", "session"], default=os.environ.get("ALIA_BUS", "session"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check")
    p.add_argument("--pc", action="store_true", help="a PC build (x86-64, for acart run), not the board's")
    p.add_argument("dirs", nargs="+")
    p = sub.add_parser("list")
    p.add_argument("--json", action="store_true")
    sub.add_parser("status")
    p = sub.add_parser("launch")
    p.add_argument("--replace", action="store_true", help="stop whatever is in front first")
    p.add_argument("id")
    p.add_argument("args", nargs=argparse.REMAINDER)
    p = sub.add_parser("stop")
    p.add_argument("--force", action="store_true")
    sub.add_parser("reload")
    sub.add_parser("suspend")
    sub.add_parser("resume")
    sub.add_parser("home")
    sub.add_parser("awake")
    sub.add_parser("watch")
    p = sub.add_parser("push")
    p.add_argument("dir")
    p.add_argument("--launch", action="store_true")
    p = sub.add_parser("run", help="run a cart directory on this PC as the handheld would")
    p.add_argument("--lang", help="the system language (zh-CN, en); default: as last time, or $LANG")
    p.add_argument("--size", help="the screen (default: the handheld's, runtime.toml [display])")
    p.add_argument("--fresh", action="store_true", help="an empty save directory, thrown away after")
    p.add_argument("--software", action="store_true", help="software rendering (no GPU)")
    p.add_argument("--no-audio", action="store_true", help="no sound (when this PC's audio misbehaves)")
    p.add_argument("--debug", action="store_true", help="print every key the simulator receives")
    p.add_argument("--browser", action="store_true",
                   help="screen, sound and gamepads in a browser page (the default without a Wayland desktop)")
    p.add_argument("--port", type=int, default=7300, help="the browser page's port on this machine")
    p.add_argument("--no-open", action="store_true", help="don't open the browser by itself")
    p.add_argument("--image", help=f"the runtime image (default {RUNTIME_IMAGE}:<the cart's platform>)")
    p.add_argument("dir")
    p.add_argument("args", nargs=argparse.REMAINDER)
    p = sub.add_parser("exec", help="run a command in the runtime image, headless (tests, tools)")
    p.add_argument("--image", help=f"the runtime image (default {RUNTIME_IMAGE}:<the platform baseline>)")
    p.add_argument("--env", action="append", metavar="K=V", help="an environment variable for the command")
    p.add_argument("dir", help="mounted read-write as the working directory")
    p.add_argument("command", nargs=argparse.REMAINDER, help="-- COMMAND...")
    p = sub.add_parser("pack")
    p.add_argument("dir")
    p.add_argument("-o", "--output")
    p.add_argument("--key", help="ed25519 private key (acart keygen)")
    p.add_argument("--comp", default="zstd", choices=["zstd", "gzip"])
    p = sub.add_parser("info")
    p.add_argument("file")
    p = sub.add_parser("keygen")
    p.add_argument("path")
    p = sub.add_parser("install")
    p.add_argument("file")
    p = sub.add_parser("remove")
    p.add_argument("id")
    p.add_argument("--purge", action="store_true", help="also delete its saves")
    p = sub.add_parser("verify")
    p.add_argument("id")
    raw = list(sys.argv[1:] if argv is None else argv)
    a = ap.parse_args(raw)

    if a.cmd == "exec" and a.command[:1] == ["--"]:
        a.command = a.command[1:]
    if a.cmd in ("check", "pack", "info", "keygen", "run", "exec"):
        return globals()[f"cmd_{a.cmd}"](a)
    if a.cmd == "install" and a.board:
        return board_install(a)
    if a.cmd == "push":
        if not a.board:
            ap.error("push is for the board (--board); locally, put the cart in a --carts directory")
        return cmd_push(a)
    if a.board:
        return remote([x for x in raw if x != "--board"])

    async def run():
        c = await Client(a.bus).connect()
        await globals()[f"cmd_{a.cmd}"](c, a)

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
