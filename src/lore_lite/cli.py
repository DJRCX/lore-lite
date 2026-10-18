"""Command-line entry point; commands will be added with the core pipeline."""

import typer

app = typer.Typer(help="Extract and query cited project rules.")


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """Show help until the project commands are implemented."""
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


if __name__ == "__main__":
    app()
