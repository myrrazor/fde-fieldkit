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
    port: int = typer.Option(8765, help="Port for the local web UI."),
) -> None:
    """Run the local Fieldkit API and web hub."""

    import uvicorn

    from fieldkit.web import create_app

    typer.echo(f"Fieldkit is running at http://127.0.0.1:{port}")
    uvicorn.run(create_app(), host="127.0.0.1", port=port, workers=1, log_level="info")


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
