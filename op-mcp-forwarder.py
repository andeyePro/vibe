#!/usr/bin/env python3
"""Host-side TCP passthrough for the tailnet-only OpenProject MCP.

A vibe container is *not* on the tailnet, so it cannot reach the OP MCP sidecar
(`openproject-mcp.<tailnet>.ts.net:443`, tailnet-only) directly. The Mac running
vibe *is* on the tailnet, so this tiny relay bridges the gap:

    container --(--add-host hostname:host-gateway)--> Mac:LISTEN_PORT --> tailnet:443

It is a pure Layer-4 byte shuttle: the TLS session is end-to-end between the
container's MCP client and the sidecar, so the Tailscale (publicly-trusted) cert
validates, SNI is preserved, and the bearer is never decrypted here. The
container registers the MCP with an explicit bare `Host:` header so the sidecar's
DNS-rebinding guard accepts it despite the non-443 port (see register-op-mcp.sh).

Bound to 127.0.0.1 only — Docker Desktop / OrbStack route the container's
`host-gateway` to host loopback, so no wider exposure is needed. The listener is
a singleton: if the port is already taken (another vibe already started one), we
exit 0 rather than error, which makes the launcher's spawn idempotent.

Usage: op-mcp-forwarder.py <listen_port> <target_host> <target_port>
"""

import socket
import sys
import threading


def _pipe(src: socket.socket, dst: socket.socket) -> None:
    try:
        while True:
            chunk = src.recv(65536)
            if not chunk:
                break
            dst.sendall(chunk)
    except OSError:
        pass
    finally:
        for s in (src, dst):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def _handle(client: socket.socket, target: tuple) -> None:
    try:
        upstream = socket.create_connection(target, timeout=10)
    except OSError:
        client.close()
        return
    threading.Thread(target=_pipe, args=(client, upstream), daemon=True).start()
    _pipe(upstream, client)


def main() -> int:
    if len(sys.argv) != 4:
        sys.stderr.write(
            "usage: op-mcp-forwarder.py <listen_port> <target_host> <target_port>\n"
        )
        return 2
    listen_port = int(sys.argv[1])
    target = (sys.argv[2], int(sys.argv[3]))

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind(("127.0.0.1", listen_port))
    except OSError:
        # Port already taken -> a forwarder is presumably already up. Idempotent.
        sys.stderr.write(
            "op-mcp-forwarder: 127.0.0.1:%d already bound; assuming already "
            "running, exiting.\n" % listen_port
        )
        return 0
    srv.listen(64)
    sys.stderr.write(
        "op-mcp-forwarder: 127.0.0.1:%d -> %s:%d\n"
        % (listen_port, target[0], target[1])
    )
    while True:
        try:
            client, _ = srv.accept()
        except OSError:
            continue
        threading.Thread(target=_handle, args=(client, target), daemon=True).start()


if __name__ == "__main__":
    sys.exit(main())
