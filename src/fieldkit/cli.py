import errno
import sys
from difflib import get_close_matches

import click
import typer

# typer>=0.12 includes releases that have not vendored click. Importing this
# private module unconditionally would crash every command on those releases.
try:
    from typer._click.exceptions import UsageError as TyperUsageError
except ImportError:
    TyperUsageError = click.UsageError

from fieldkit import __version__
from fieldkit.plugin_cli import app as plugin_app
from fieldkit.plugins import REGISTRY, installed_plugins


class FieldkitGroup(typer.core.TyperGroup):
    """Load plugin commands on use so `--help` and unrelated tools skip pandas."""

    def list_commands(self, ctx: click.Context) -> list[str]:
        names = list(super().list_commands(ctx))
        for name in sorted(installed_plugins()):
            if name not in names:
                names.append(name)
        return names

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        command = self.commands.get(cmd_name)
        if command is not None:
            return command
        if cmd_name not in installed_plugins():
            return None
        return self._load_plugin(cmd_name)

    def format_help(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        # Rich help asks every command for its summary. Serve stubs so the
        # root listing does not import plugin modules.
        original = self.get_command

        def listing_get(help_ctx: click.Context, name: str) -> click.Command | None:
            existing = self.commands.get(name)
            if existing is not None:
                return existing
            if name not in installed_plugins():
                return None
            known = REGISTRY.get(name)
            summary = known.summary if known else "installed plugin"
            return click.Command(name, help=summary, callback=lambda: None)

        self.get_command = listing_get  # type: ignore[method-assign]
        try:
            return super().format_help(ctx, formatter)
        finally:
            self.get_command = original  # type: ignore[method-assign]

    def resolve_command(
        self, ctx: click.Context, args: list[str]
    ) -> tuple[str | None, click.Command | None, list[str]]:
        try:
            return self._click_resolve_command(ctx, args)
        except (click.UsageError, TyperUsageError) as exc:
            if self.suggest_commands and args:
                matches = get_close_matches(args[0], self.list_commands(ctx))
                if matches:
                    suggestions = ", ".join(repr(match) for match in matches)
                    message = (exc.message or "").rstrip(".")
                    exc.message = f"{message}. Did you mean {suggestions}?"
            raise

    def _load_plugin(self, cmd_name: str) -> click.Command | None:
        entry = installed_plugins().get(cmd_name)
        if entry is None:
            return None
        try:
            typer_app = entry.load()
        except Exception as exc:  # a broken plugin must not take the toolkit down
            typer.secho(f"warning: plugin '{cmd_name}' failed to load: {exc}", fg="yellow", err=True)
            return None
        from typer.main import get_command

        command = get_command(typer_app)
        command.name = cmd_name
        self.add_command(command, cmd_name)
        return command


class SingleCommandGroup(typer.core.TyperGroup):
    """Omit the subcommand metavar when the Typer app has no subcommands."""

    def collect_usage_pieces(self, ctx: click.Context) -> list[str]:
        pieces = click.Command.collect_usage_pieces(self, ctx)
        if self.list_commands(ctx):
            pieces.append(self.subcommand_metavar)
        return pieces


# Typer reads cls from the instance, not from a later attribute set.
app = typer.Typer(name="fieldkit", no_args_is_help=True, cls=FieldkitGroup)
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
        # A killed heavy job closes its connection within this window, so one
        # Ctrl+C finishes shutdown instead of waiting out the request.
        timeout_graceful_shutdown=3,
    )
    server = uvicorn.Server(config)
    # capture_signals binds server.handle_exit. Stop isolated jobs in that
    # handler so the open request can return and the process can exit.
    handle_exit = getattr(server, "handle_exit", None)
    if handle_exit is not None:

        def _stop_jobs_then_exit(sig: int, frame: object) -> None:
            from fieldkit.web.routes import stop_heavy_jobs

            stop_heavy_jobs()
            handle_exit(sig, frame)

        server.handle_exit = _stop_jobs_then_exit  # type: ignore[method-assign]
    try:
        # hand uvicorn the already-bound socket so nothing can steal the port
        server.run(sockets=[sock])
    finally:
        sock.close()


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
