#!/usr/bin/env python3
"""docker-altrcode dispatcher — host unix socket → whitelisted make <op>.

Usage:
  dispatcher.py pins  --config <conf> --pins-file <file>
  dispatcher.py serve --config <conf> --socket <path> [--pins-file <file>]
"""
import argparse
import configparser
import glob
import hashlib
import json
import logging
import os
import re
import socket
import subprocess
import threading
import time

# Characters allowed in the argument passed to `make arg=...`.
# -> no shell metacharacters, no quotes, no `;`/`|`/expansion.
ARG_SAFE = re.compile(r"^[A-Za-z0-9_\-. ,:/=@%]+$")

DEFAULT_TIMEOUT = 1200  # 20 min per operation


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def is_glob(rel: str) -> bool:
    return any(c in rel for c in "*?[")


def resolve_pin(root: str, rel: str) -> str:
    """Absolute path of a [pins] entry, confined to the project root."""
    rel = rel.strip()
    if not rel or os.path.isabs(rel):
        raise SystemExit(f"dispatcher: invalid path to pin (must be relative): {rel!r}")
    p = os.path.abspath(os.path.join(root, rel))
    rootp = root.rstrip(os.sep)
    if p != rootp and not p.startswith(rootp + os.sep):
        raise SystemExit(f"dispatcher: file to pin is outside the project root: {rel!r}")
    return p


def load_pin_store(pins_file: str) -> dict:
    """Reads the pins file -> {absolute_path: hash}."""
    with open(pins_file) as f:
        store = json.load(f)
    if isinstance(store, dict) and isinstance(store.get("files"), dict):
        store = store["files"]
    if not isinstance(store, dict):
        raise ValueError("invalid pins file")
    return store


def pins_ok(store: dict) -> tuple[bool, str]:
    """Re-hashes each pinned entry. Returns (True, '') or (False, reason)."""
    for abspath, expected in store.items():
        if not isinstance(expected, str) or not expected:
            return False, f"invalid pin for {abspath} — restart the stack"
        try:
            cur = sha256_file(abspath)
        except OSError:
            return False, f"pinned file unreadable: {abspath} — restart the stack"
        if cur != expected:
            return False, (
                f"pinned file modified since startup: {abspath} "
                f"— operation refused (restart the stack on the host to re-pin)"
            )
    return True, ""


def parse_config(path: str) -> dict:
    cp = configparser.ConfigParser(interpolation=None, allow_no_value=True)
    cp.optionxform = str  # keep key case (Makefile != makefile)
    cp.read(path)
    cfg = {
        "name": cp.get("project", "name").strip(),
        "root": os.path.realpath(os.path.expanduser(cp.get("project", "root").strip())),
        "container": cp.get("project", "container", fallback="").strip(),
        "ops": {k: cp.getboolean("ops", k) for k in cp["ops"]} if cp.has_section("ops") else {},
        "pins": [k.strip() for k in cp["pins"].keys() if k.strip()] if cp.has_section("pins") else [],
    }
    return cfg


class Dispatcher:
    def __init__(self, cfg: dict, sock_path: str, log: logging.Logger,
                 pins_file: str | None = None):
        self.cfg = cfg
        self.sock_path = sock_path
        self.pins_file = pins_file
        self.log = log
        self._lock = threading.Lock()

    def _check_pins(self) -> tuple[bool, str]:
        """Checks the pins. Not configured -> ok. Missing/unreadable -> fail closed."""
        if not self.pins_file:
            return True, ""
        try:
            store = load_pin_store(self.pins_file)
        except FileNotFoundError:
            return False, "pins file missing — restart the stack (pins are regenerated on every start)"
        except (ValueError, OSError) as exc:
            return False, f"pins file unreadable ({exc}) — restart the stack"
        return pins_ok(store)

    def _authorized(self, op: str, arg) -> tuple[bool, str, list, dict]:
        """(ok, error, argv, env)."""
        allow_arg = self.cfg["ops"].get(op)
        if allow_arg is None:
            return False, f"unknown or unauthorized operation: {op}", [], {}
        if arg:
            if not allow_arg:
                return False, f"operation does not accept an argument: {op}", [], {}
            if not ARG_SAFE.match(arg):
                return False, "argument rejected (disallowed characters)", [], {}
        argv = ["make", op]
        if arg:
            argv.append(f"arg={arg}")
        return True, "", argv, self._env()

    @staticmethod
    def _env() -> dict:
        # Minimal env: the dispatcher's secrets are not exported.
        return {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": os.path.expanduser("~"),
            "USER": os.environ.get("USER", ""),
            "SHELL": "/bin/bash",
            "TERM": os.environ.get("TERM", "xterm-256color"),
        }

    def _transaction(self, op: str, arg) -> dict:
        ok_pins, pins_err = self._check_pins()
        if not ok_pins:
            with self._lock:
                self.log.warning("BLOCKED pins (%s) op=%s arg=%r", pins_err, op, arg)
            return {"ok": False, "error": pins_err, "exit": 1, "out": ""}
        # 2) Whitelist + safe argument.
        ok, err, argv, env = self._authorized(op, arg)
        if not ok:
            with self._lock:
                self.log.warning("REFUSED op=%s arg=%r (%s)", op, arg, err)
            return {"ok": False, "error": err, "exit": 1, "out": ""}
        t0 = time.time()
        try:
            proc = subprocess.run(
                argv,
                cwd=self.cfg["root"],
                env=env,
                capture_output=True,
                text=True,
                timeout=DEFAULT_TIMEOUT,
            )
            out = proc.stdout + proc.stderr
            with self._lock:
                self.log.info(
                    "op=%s arg=%r exit=%d dt=%.1fs",
                    op, arg, proc.returncode, time.time() - t0,
                )
            return {"ok": True, "exit": proc.returncode, "out": out}
        except subprocess.TimeoutExpired as exc:
            out = (exc.stdout or "") + (exc.stderr or "")
            return {"ok": True, "exit": 124, "out": out + "\n[timeout]\n"}
        except FileNotFoundError:
            return {"ok": False, "error": f"command not found: {argv[0]} (host)", "exit": 1, "out": ""}
        except Exception as exc:
            with self._lock:
                self.log.error("internal ERROR op=%s arg=%r: %r", op, arg, exc)
            return {"ok": False, "error": f"dispatcher internal error: {exc}", "exit": 1, "out": ""}

    # ---- socket server ----
    def run_server(self):
        os.makedirs(os.path.dirname(self.sock_path), exist_ok=True)
        try:
            os.unlink(self.sock_path)
        except FileNotFoundError:
            pass
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(self.sock_path)
        os.chmod(self.sock_path, 0o600)
        srv.listen(8)
        self.log.info("dispatcher ready on %s (project=%s)", self.sock_path, self.cfg["name"])
        while True:
            conn, _ = srv.accept()
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn: socket.socket):
        with conn:
            try:
                data = conn.recv(65536).decode("utf-8")
            except OSError:
                return
            try:
                req = json.loads(data.split("\n")[0] or "{}")
                op = str(req.get("op", ""))
                arg = req.get("arg")
            except ValueError:
                return
            resp = self._transaction(op, arg)
            try:
                conn.sendall((json.dumps(resp) + "\n").encode("utf-8"))
            except OSError:
                pass


def cmd_pins(conf_path: str, pins_path: str) -> None:
    """Generates the hashes of the [pins] files (host side, before the stack starts)."""
    cfg = parse_config(conf_path)
    pins = {}
    for rel in cfg["pins"]:
        pat = resolve_pin(cfg["root"], rel)
        if is_glob(rel):
            for m in sorted(glob.glob(pat)):
                if os.path.isfile(m):
                    pins[m] = sha256_file(m)
            continue
        if not os.path.isfile(pat):
            raise SystemExit(
                f"dispatcher: file to pin not found: {pat} "
                f"(declared in [pins] of {conf_path})"
            )
        pins[pat] = sha256_file(pat)
    os.makedirs(os.path.dirname(pins_path), exist_ok=True)
    tmp = pins_path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(pins, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, pins_path)  # atomic: never a half-written file
    print(f"dispatcher: pins regenerated ({len(pins)} file(s)) -> {pins_path}")


def main():
    ap = argparse.ArgumentParser(description="dispatcher docker-altrcode")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_serve = sub.add_parser("serve", help="start the socket server")
    p_serve.add_argument("--config", required=True)
    p_serve.add_argument("--socket", required=True)
    p_serve.add_argument(
        "--pins-file", default=None,
        help="pinned hashes file (checked before each operation)",
    )

    p_pins = sub.add_parser(
        "pins", help="regenerate the pinned files hashes (host side, at startup)"
    )
    p_pins.add_argument("--config", required=True)
    p_pins.add_argument("--pins-file", required=True)

    args = ap.parse_args()

    if args.cmd == "pins":
        cmd_pins(args.config, args.pins_file)
        return

    cfg = parse_config(args.config)

    log = logging.getLogger("docker-altrcode")
    if not log.handlers:
        log.addHandler(logging.StreamHandler())
    log.setLevel(logging.INFO)

    Dispatcher(cfg, args.socket, log, pins_file=args.pins_file).run_server()


if __name__ == "__main__":
    main()
