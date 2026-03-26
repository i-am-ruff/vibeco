"""vco preflight command -- run pre-flight tests for Claude Code headless behavior."""

import sys
from pathlib import Path

import click

from vcompany.shared.paths import PROJECTS_BASE
from vcompany.orchestrator.preflight import run_preflight


@click.command()
@click.argument("project_name")
@click.option(
    "--output-dir",
    default=None,
    type=click.Path(),
    help="Directory for results JSON (default: project state dir)",
)
def preflight(project_name: str, output_dir: str | None) -> None:
    """Run pre-flight tests to validate Claude Code headless behavior.

    Runs 4 empirical tests and writes results to preflight_results.json.
    The monitor strategy (stream-json vs git-commit fallback) is determined
    by the results.
    """
    # Determine output path
    if output_dir:
        output_path = Path(output_dir) / "preflight_results.json"
    else:
        output_path = PROJECTS_BASE / project_name / "state" / "preflight_results.json"

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    click.echo(f"Running pre-flight tests for '{project_name}'...")
    click.echo()

    suite = run_preflight(output_path=output_path)

    # Print human-readable summary
    click.echo(suite.summary())
    click.echo()
    click.echo(f"Results written to: {output_path}")

    # Print monitor strategy recommendation
    click.echo()
    click.echo(f"Recommended monitor strategy: {suite.strategy.value}")

    # Exit code: 0 if all passed, 1 if any failed, 2 if any inconclusive
    if any(r.inconclusive for r in suite.results):
        sys.exit(2)
    elif not suite.all_passed:
        sys.exit(1)
    else:
        sys.exit(0)
