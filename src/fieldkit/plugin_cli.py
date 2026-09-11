"""The `fieldkit plugin` command group: list, add, remove, update."""

from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.table import Table

from fieldkit.plugins import (
    REGISTRY,
    installed_plugins,
    package_requirement,
    resolve_requirement,
    run_installer,
    run_uninstaller,
)

app = typer.Typer(name="plugin", no_args_is_help=True, help="Add, remove, and list Fieldkit tools.")

console = Console()


def _statuses() -> list[dict[str, str]]:
    installed = installed_plugins()
    rows = []
    for name, known in REGISTRY.items():
        rows.append(
            {
                "name": name,
                "package": known.package,
                "summary": known.summary,
                "status": "installed" if name in installed else "available",
            }
        )
    # plugins from outside the registry still deserve a listing
    for name in sorted(set(installed) - set(REGISTRY)):
        rows.append(
            {
                "name": name,
                "package": installed[name].dist.name if installed[name].dist else "?",
                "summary": "(third-party plugin)",
                "status": "installed",
            }
        )
    return rows


@app.command("list")
def list_(json_output: bool = typer.Option(False, "--json", help="Machine-readable output.")) -> None:
    """Show installed tools and what else is available."""

    rows = _statuses()
    if json_output:
        typer.echo(json.dumps({"plugins": rows}, indent=2))
        return
    table = Table(title="Fieldkit tools")
    table.add_column("tool", style="bold")
    table.add_column("status")
    table.add_column("what it does")
    for row in rows:
        style = "green" if row["status"] == "installed" else "dim"
        table.add_row(row["name"], f"[{style}]{row['status']}[/{style}]", row["summary"])
    console.print(table)
    missing = [r["name"] for r in rows if r["status"] == "available"]
    if missing:
        console.print(f"[dim]add one with:[/dim] fieldkit plugin add {missing[0]}")


@app.command()
def add(
    names: list[str] = typer.Argument(..., help="Tool names, e.g. xray scrub"),
    source: str = typer.Option(
        None,
        help="Force a source: local or git. PyPI is not available yet.",
    ),
    extra: list[str] = typer.Option(None, "--extra", help="Optional extras, e.g. --extra ml for tell."),
    wheelhouse: str = typer.Option(
        None,
        help=(
            "Directory of pre-built fieldkit wheels. Resolves Fieldkit packages locally; "
            "other dependencies may still contact a package index (not a full offline install)."
        ),
    ),
) -> None:
    """Install one or more tools into this Fieldkit."""

    requirements = []
    for name in names:
        if name not in REGISTRY:
            known = ", ".join(REGISTRY)
            typer.secho(f"unknown tool '{name}' — known tools: {known}", fg="red", err=True)
            raise typer.Exit(2)
        try:
            if wheelhouse:
                requirements.append(package_requirement(name, extras=extra))
            else:
                requirements.append(resolve_requirement(name, source=source, extras=extra))
        except (FileNotFoundError, ValueError) as exc:
            typer.secho(f"error: {exc}", fg="red", err=True)
            raise typer.Exit(2) from exc
    code = run_installer(requirements, find_links=wheelhouse)
    if code != 0:
        typer.secho("install failed — see output above", fg="red", err=True)
        raise typer.Exit(code)
    for name in names:
        typer.secho(f"✓ {name} installed — try: fieldkit {name} --help", fg="green")


@app.command()
def remove(names: list[str] = typer.Argument(..., help="Tool names to uninstall.")) -> None:
    """Uninstall tools (the core and your data stay put)."""

    packages = []
    for name in names:
        if name not in REGISTRY:
            typer.secho(f"unknown tool '{name}'", fg="red", err=True)
            raise typer.Exit(2)
        packages.append(REGISTRY[name].package)
    code = run_uninstaller(packages)
    if code != 0:
        raise typer.Exit(code)
    for name in names:
        typer.secho(f"✓ {name} removed", fg="green")


@app.command()
def update(
    names: list[str] = typer.Argument(None, help="Tools to update; default is everything installed."),
    source: str = typer.Option(
        None,
        help="Force a source: local or git. PyPI is not available yet.",
    ),
    wheelhouse: str = typer.Option(
        None,
        help=(
            "Directory of pre-built fieldkit wheels. Resolves Fieldkit packages locally; "
            "other dependencies may still contact a package index (not a full offline install)."
        ),
    ),
) -> None:
    """Reinstall tools at their newest version."""

    targets = names or [n for n in REGISTRY if n in installed_plugins()]
    if not targets:
        typer.echo("nothing installed to update")
        return
    try:
        if wheelhouse:
            requirements = [package_requirement(name) for name in targets]
        else:
            requirements = [resolve_requirement(name, source=source) for name in targets]
    except (FileNotFoundError, ValueError) as exc:
        typer.secho(f"error: {exc}", fg="red", err=True)
        raise typer.Exit(2) from exc
    code = run_installer(requirements, upgrade=True, find_links=wheelhouse)
    if code != 0:
        raise typer.Exit(code)
    typer.secho(f"✓ updated: {', '.join(targets)}", fg="green")
