"""Standard-library HTTP server for the local visualization backend."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

from .web_api import DEFAULT_ARCHIVE_ROOT, WebApiResponse, WebSandboxApi


def create_http_handler(api: WebSandboxApi) -> type[BaseHTTPRequestHandler]:
    """Return a request handler class bound to one ``WebSandboxApi``."""

    if not isinstance(api, WebSandboxApi):
        raise TypeError("api must be a WebSandboxApi.")

    class SandboxApiHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_OPTIONS(self) -> None:  # noqa: N802 - stdlib hook name.
            self._handle_request()

        def do_GET(self) -> None:  # noqa: N802 - stdlib hook name.
            self._handle_request()

        def do_POST(self) -> None:  # noqa: N802 - stdlib hook name.
            self._handle_request()

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            """Keep the dev server quiet unless a caller wraps stdout/stderr."""

            return

        def _handle_request(self) -> None:
            body = self._read_body()
            if body is None:
                return
            response = api.handle(
                self.command,
                self.path,
                body,
                headers={key: value for key, value in self.headers.items()},
            )
            self._send_api_response(response)

        def _read_body(self) -> bytes | None:
            raw_length = self.headers.get("Content-Length", "0")
            try:
                content_length = int(raw_length)
            except ValueError:
                self._send_api_response(
                    WebApiResponse(
                        400,
                        headers={"Content-Type": "application/json; charset=utf-8"},
                        body=b'{"ok":false,"status":"invalid_request","message":"Invalid Content-Length."}',
                    )
                )
                return None
            if content_length < 0 or content_length > api.max_body_bytes:
                self._send_api_response(
                    WebApiResponse(
                        413,
                        headers={"Content-Type": "application/json; charset=utf-8"},
                        body=b'{"ok":false,"status":"body_too_large","message":"Request body is too large."}',
                    )
                )
                return None
            return self.rfile.read(content_length) if content_length else b""

        def _send_api_response(self, response: WebApiResponse) -> None:
            self.send_response(response.status_code)
            headers = dict(response.headers)
            if response.is_streaming:
                headers.setdefault("Connection", "close")
            else:
                headers.setdefault("Content-Length", str(len(response.body)))
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            if response.is_streaming:
                try:
                    for chunk in response.chunks or ():
                        self.wfile.write(chunk)
                        self.wfile.flush()
                finally:
                    self.close_connection = True
                return
            if response.body:
                self.wfile.write(response.body)

    return SandboxApiHandler


def create_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    api: WebSandboxApi | None = None,
) -> ThreadingHTTPServer:
    """Create a threaded local HTTP server without starting it."""

    server_api = api or WebSandboxApi(
        archive_root=DEFAULT_ARCHIVE_ROOT,
        backend_defaults=backend_defaults_from_env(),
    )
    return ThreadingHTTPServer((host, port), create_http_handler(server_api))


def serve(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    archive_root: str | Path = DEFAULT_ARCHIVE_ROOT,
    backend_base_url: str = "",
    backend_api_key: str = "",
) -> None:
    """Start the local backend and block until interrupted."""

    backend_defaults = backend_defaults_from_env(
        backend_base_url=backend_base_url,
        backend_api_key=backend_api_key,
    )
    api = WebSandboxApi(archive_root=archive_root, backend_defaults=backend_defaults)
    server = create_server(host=host, port=port, api=api)
    print(f"Marketing sandbox backend listening on http://{host}:{port}")
    print(f"Archives: {Path(archive_root).resolve()}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping marketing sandbox backend.")
    finally:
        server.server_close()


def backend_defaults_from_env(
    *,
    backend_base_url: str = "",
    backend_api_key: str = "",
    getenv: Callable[[str, str], str] = os.environ.get,
) -> dict[str, str]:
    """Read optional provider defaults from arguments or environment."""

    base_url = (
        backend_base_url
        or getenv("MARKETING_SANDBOX_BASE_URL", "")
        or getenv("MARKETING_SANDBOX_API_BASE_URL", "")
    )
    api_key = backend_api_key or getenv("MARKETING_SANDBOX_API_KEY", "")
    defaults: dict[str, str] = {}
    if base_url:
        defaults["base_url"] = base_url
    if api_key:
        defaults["api_key"] = api_key
    return defaults


def main(argv: list[str] | None = None) -> None:
    """CLI entry point for ``python -m marketing_sandbox.web_server``."""

    parser = argparse.ArgumentParser(description="Run the marketing sandbox backend.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--archive-root", default=str(DEFAULT_ARCHIVE_ROOT))
    parser.add_argument("--backend-base-url", default="")
    parser.add_argument("--backend-api-key", default="")
    args = parser.parse_args(argv)
    serve(
        host=args.host,
        port=args.port,
        archive_root=args.archive_root,
        backend_base_url=args.backend_base_url,
        backend_api_key=args.backend_api_key,
    )


if __name__ == "__main__":
    main()
