#!/usr/bin/env python3
"""docker-altrcode egress_proxy — HTTP/HTTPS proxy filtered by a domain whitelist.

Runs on the host (DOMAIN_WHITELIST=1). Allowed domains = DOMAIN_GLOBAL_WHITELIST ∪ project [domains].
CONNECT: plain TCP tunnel (no MITM). Direct HTTP: raw relay. Refusal: 403.

Usage:
  egress_proxy.py --config <conf> [--host <ip>] [--port <n>] [--port-file <f>]
"""
import argparse
import configparser
import logging
import os
import socket
import sys
import threading
from urllib.parse import urlsplit

# Domains always reachable, whatever the project.
# Loaded from the DOMAIN_GLOBAL_WHITELIST environment variable (space-separated values).
GLOBAL_DOMAINS: list[str] = os.environ.get("DOMAIN_GLOBAL_WHITELIST", "").split()

def parse_domains(conf_path: str) -> list[str]:
    """Project domains ([domains] section -> allowed). [] if missing."""
    cp = configparser.ConfigParser(interpolation=None, allow_no_value=True)
    cp.optionxform = str  # keep key case
    cp.read(conf_path)
    if not cp.has_section("domains"):
        return []
    out = []
    for line in cp.get("domains", "allowed", fallback="").splitlines():
        line = line.strip().rstrip(".")
        if line and not line.startswith((";", "#")):
            out.append(line)
    return out


def allowed(host: str, allowlist: list[str]) -> bool:
    """True if host == domain or host is a subdomain (suffix match)."""
    host = host.lower().rstrip(".")
    if not host:
        return False
    for d in allowlist:
        d = d.lower().rstrip(".")
        if not d:
            continue
        if host == d or host.endswith("." + d):
            return True
    return False


def _deny(conn: socket.socket, method: str) -> None:
    reason = b"Domain whitelist (docker-altrcode): access denied"
    try:
        if method == "CONNECT":
            conn.sendall(b"HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n")
        else:
            body = b"403 Forbidden\n" + reason + b"\n"
            header = (
                b"HTTP/1.1 403 Forbidden\r\nContent-Type: text/plain\r\n"
                + b"Content-Length: " + str(len(body)).encode()
                + b"\r\nConnection: close\r\n\r\n"
            )
            conn.sendall(header + body)
    except OSError:
        pass


def _relay(a: socket.socket, b: socket.socket, first: bytes = b"") -> None:
    """Bidirectional relay between two sockets (two threads, one per direction)."""
    def pump(src, dst, head):
        try:
            if head:
                dst.sendall(head)
            while True:
                data = src.recv(65536)
                if not data:
                    break
                dst.sendall(data)
        except OSError:
            pass
        finally:
            try:
                dst.shutdown(socket.SHUT_WR)
            except OSError:
                pass

    t_ab = threading.Thread(target=pump, args=(a, b, first), daemon=True)
    t_ba = threading.Thread(target=pump, args=(b, a, b""), daemon=True)
    t_ab.start()
    t_ba.start()
    t_ab.join(timeout=180)
    t_ba.join(timeout=180)


def _handle(conn: socket.socket, allowlist: list[str], log: logging.Logger) -> None:
    conn.settimeout(20)
    upstream = None
    try:
        # Read the request head (up to \r\n\r\n), bounded.
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = conn.recv(65536)
            if not chunk:
                return
            buf += chunk
            if len(buf) > 131072:
                return
        head, _, rest = buf.partition(b"\r\n\r\n")
        parts = head.split(b"\r\n")
        if not parts or not parts[0]:
            return
        reqline = parts[0].decode("latin-1", "replace")
        tokens = reqline.split(" ")
        method = tokens[0].upper() if tokens else ""
        target = tokens[1] if len(tokens) > 1 else ""

        if method == "CONNECT":
            host, _, port = target.rpartition(":")
            port = port or "443"
        else:
            url = urlsplit(target)
            host = url.hostname or ""
            port = str(url.port or 80)
        host = host.strip("[]").lower().rstrip(".")

        if not allowed(host, allowlist):
            log.warning("BLOCKED domain=%s (method=%s)", host, method)
            _deny(conn, method)
            return

        upstream = socket.create_connection((host, int(port)), timeout=20)
        # Streaming responses (e.g. LLM) can have long inter-chunk pauses;
        # drop the timeout before entering relay so we never cut mid-response.
        conn.settimeout(None)
        upstream.settimeout(None)
        if method == "CONNECT":
            conn.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
            _relay(conn, upstream, rest)  # rest = TLS start already received
        else:
            upstream.sendall(buf)  # forward the head (+ any body) as is
            _relay(conn, upstream)
        log.info("ok method=%s domain=%s:%s", method, host, port)
    except (OSError, ValueError, IndexError):
        pass
    finally:
        try:
            conn.close()
        except OSError:
            pass
        if upstream is not None:
            try:
                upstream.close()
            except OSError:
                pass


def serve(host: str, port: int, allowlist: list[str],
          port_file: str | None, log: logging.Logger) -> None:
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, port))
    srv.listen(32)
    real = srv.getsockname()[1]
    if port_file:
        tmp = port_file + ".tmp"
        os.makedirs(os.path.dirname(port_file), exist_ok=True)
        with open(tmp, "w") as f:
            f.write(str(real) + "\n")
        os.replace(tmp, port_file)  # atomic: the wrapper always reads a complete port
    log.info("egress proxy ready on %s:%d (whitelist = %d domain(s))",
             host, real, len(allowlist))
    try:
        while True:
            conn, _ = srv.accept()
            threading.Thread(target=_handle, args=(conn, allowlist, log),
                             daemon=True).start()
    finally:
        srv.close()


def main() -> int:
    ap = argparse.ArgumentParser(description="whitelisting egress proxy (host)")
    ap.add_argument("--config", required=True,
                    help="project config (~/.config/docker-altrcode/<name>.conf)")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=0, help="0 = any free port (recommended)")
    ap.add_argument("--port-file", default=None,
                    help="file to write the actual listening port to (dispatch wrapper)")
    args = ap.parse_args()

    allowlist = sorted(set(GLOBAL_DOMAINS) | set(parse_domains(args.config)))
    if not allowlist:
        sys.stderr.write("egress_proxy: no domain list (please fix)\n")
        return 2

    log = logging.getLogger("docker-altrcode-egress")
    if not log.handlers:
        stream = logging.StreamHandler()
        stream.setFormatter(logging.Formatter("%(asctime)s egress %(message)s"))
        log.addHandler(stream)
    log.setLevel(logging.INFO)
    log.info("allowed domains: %s", ", ".join(allowlist))

    serve(args.host, args.port, allowlist, args.port_file, log)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(0)
