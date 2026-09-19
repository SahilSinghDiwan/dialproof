"""CLI entry point."""

import click

from .commands import render_command, run_command, selftest_command, verify_command


@click.group()
def main():
    """Air-gap conformance harness for LLM endpoints."""
    pass


@main.command()
@click.option("--endpoint", required=True, help="Base URL of the LLM endpoint")
@click.option("--model", required=True, help="Model name to test")
@click.option(
    "--allow",
    multiple=True,
    required=True,
    help="Allowed hosts (can be used multiple times)",
)
@click.option("--out", required=True, help="Output directory for reports")
@click.option(
    "--transport", default="raw-httpx", help="Transport layer (raw-httpx or litellm)"
)
def run(endpoint, model, allow, out, transport):
    """Run the capability probe against an endpoint."""
    exit_code = run_command(endpoint, model, list(allow), out, transport)
    raise SystemExit(exit_code)


@main.command()
@click.argument("report_path")
def verify(report_path):
    """Verify a report without re-running."""
    exit_code = verify_command(report_path)
    raise SystemExit(exit_code)


@main.command()
@click.argument("report_path")
@click.option(
    "--format",
    "fmt",
    default="md",
    type=click.Choice(["md", "json"]),
    help="Output format",
)
def render(report_path, fmt):
    """Render a report to the specified format."""
    output = render_command(report_path, fmt)
    click.echo(output)


@main.command()
def selftest():
    """Run the monitor selftest."""
    exit_code = selftest_command()
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
