import errno
import sys

import typer

from fieldkit import __version__
from fieldkit.plugin_cli import app as plugin_app
from fieldkit.plugins import REGISTRY, installed_plugins

app = typer.Typer(name="fieldkit", no_args_is_help=True)
app.add_typer(plugin_app, name="plugin")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def _root(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        help="Show the Fieldkit package version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """Fieldkit: local FDE tools as plugins."""


@app.command()
def serve(
    port: int | None = typer.Option(
        None,
        "--port",
        min=1,
        max=65535,
        help="Pin a loopback port. Default prefers 8765, then any free port.",
    ),
) -> None:
    """Run the local Fieldkit API and web hub."""

    import uvicorn

    from fieldkit.web import create_app
    from fieldkit.web.bind import PREFERRED_PORT, bind_loopback

    try:
        sock, actual = bind_loopback(port=port)
    except OSError as exc:
        if port is None:
            typer.echo("error: could not bind a loopback port", err=True)
        elif exc.errno == errno.EADDRINUSE:
            typer.echo(
                f"error: port {port} is already in use — omit --port to pick a free one",
                err=True,
            )
        else:
            typer.echo(f"error: could not bind 127.0.0.1:{port} ({exc})", err=True)
        raise typer.Exit(1) from exc

    url = f"http://127.0.0.1:{actual}"
    typer.echo(f"Fieldkit is running at {url}")
    if port is None and actual != PREFERRED_PORT:
        typer.echo(f"port {PREFERRED_PORT} was in use, using {actual}")

    config = uvicorn.Config(
        create_app(),
        host="127.0.0.1",
        port=actual,
        log_level="info",
    )
    try:
        # hand uvicorn the already-bound socket so nothing can steal the port
        uvicorn.Server(config).run(sockets=[sock])
    finally:
        sock.close()


def _mount_installed() -> None:
    for name, ep in sorted(installed_plugins().items()):
        try:
            app.add_typer(ep.load(), name=name)
        except Exception as exc:  # a broken plugin must not take the toolkit down
            typer.secho(f"warning: plugin '{name}' failed to load: {exc}", fg="yellow", err=True)


_mount_installed()


def main() -> None:
    argv = sys.argv[1:]
    if argv and not argv[0].startswith("-"):
        head = argv[0]
        if head in REGISTRY and head not in installed_plugins():
            typer.secho(f"'{head}' is a Fieldkit tool that isn't installed yet.", err=True)
            typer.secho(f"  fieldkit plugin add {head}", bold=True, err=True)
            raise SystemExit(2)
    app()


if __name__ == "__main__":
    main()
