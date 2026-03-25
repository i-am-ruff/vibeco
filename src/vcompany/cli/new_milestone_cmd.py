"""vco new-milestone command -- transition to a new milestone scope.

Updates MILESTONE-SCOPE.md, generates PM-CONTEXT.md, syncs context to clones,
and optionally resets agent states and re-dispatches.

Implements MILE-01, D-19, D-20.
"""

import json
import shutil
import subprocess
from pathlib import Path

import click

from vcompany.coordination.sync_context import sync_context_files
from vcompany.models.config import load_config
from vcompany.strategist.context_builder import write_pm_context


@click.command("new-milestone")
@click.option(
    "--project-dir",
    "-p",
    required=True,
    type=click.Path(exists=True),
    help="Path to the project directory",
)
@click.option(
    "--scope-file",
    "-s",
    required=True,
    type=click.Path(exists=True),
    help="New MILESTONE-SCOPE.md file",
)
@click.option(
    "--reset/--no-reset",
    default=False,
    help="Reset agent states to idle/phase 1",
)
@click.option(
    "--dispatch/--no-dispatch",
    default=False,
    help="Re-dispatch all agents after update",
)
def new_milestone(
    project_dir: str,
    scope_file: str,
    reset: bool,
    dispatch: bool,
) -> None:
    """Transition to a new milestone scope.

    Copies the scope file, generates PM-CONTEXT.md, syncs context to all
    agent clones, and optionally resets agent states and re-dispatches.
    """
    project_path = Path(project_dir)
    scope_path = Path(scope_file)

    # Load project config
    config_path = project_path / "agents.yaml"
    try:
        config = load_config(config_path)
    except Exception as e:
        click.echo(f"Error loading config: {e}", err=True)
        raise SystemExit(1)

    # Step 1: Copy scope file to project context
    context_dir = project_path / "context"
    context_dir.mkdir(parents=True, exist_ok=True)
    dest_scope = context_dir / "MILESTONE-SCOPE.md"
    shutil.copy2(str(scope_path), str(dest_scope))
    click.echo(f"Copied scope file to {dest_scope}")

    # Step 2: Generate PM-CONTEXT.md
    pm_context_path = write_pm_context(project_path)
    click.echo(f"Generated {pm_context_path}")

    # Step 3: Sync context files to all clones
    result = sync_context_files(project_path, config)
    click.echo(
        f"Synced {result.files_synced} files to {result.clones_updated} clones"
    )
    if result.errors:
        for err in result.errors:
            click.echo(f"  Warning: {err}", err=True)

    # Step 4: Reset agent states if requested
    if reset:
        agents_json_path = project_path / "state" / "agents.json"
        if agents_json_path.exists():
            data = json.loads(agents_json_path.read_text())
            for agent_id, agent_state in data.get("agents", {}).items():
                agent_state["phase"] = 1
                agent_state["status"] = "idle"
            agents_json_path.write_text(json.dumps(data, indent=2))
            click.echo("Reset all agent states to idle/phase 1")
        else:
            click.echo("No agents.json found, skipping reset")

    # Step 5: Re-dispatch if requested
    if dispatch:
        project_name = config.project
        subprocess.run(
            ["vco", "dispatch", project_name, "--all"],
            check=False,
        )
        click.echo("Re-dispatched all agents")

    click.echo("Milestone transition complete.")
