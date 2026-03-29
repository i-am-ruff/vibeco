"""vco new-project command -- composite init + clone + daemon new_project."""

import shutil
from pathlib import Path

import click
from pydantic import ValidationError
from rich.console import Console
import yaml

from vcompany.cli.clone_cmd import _deploy_artifacts
from vcompany.cli.helpers import daemon_client
from vcompany.git import ops as git
from vcompany.models.config import load_config
from vcompany.shared.file_ops import write_atomic
from vcompany.shared.paths import PROJECTS_BASE
from vcompany.shared.templates import render_template

console = Console()


@click.command("new-project")
@click.argument("project_name")
@click.option(
    "--config",
    "-c",
    "config_path",
    type=click.Path(exists=True),
    required=True,
    help="Path to agents.yaml",
)
@click.option(
    "--blueprint",
    type=click.Path(exists=True),
    default=None,
    help="Path to PROJECT-BLUEPRINT.md",
)
@click.option(
    "--interfaces",
    type=click.Path(exists=True),
    default=None,
    help="Path to INTERFACES.md",
)
@click.option(
    "--milestone",
    type=click.Path(exists=True),
    default=None,
    help="Path to MILESTONE-SCOPE.md",
)
@click.option(
    "--persona",
    type=click.Path(exists=True),
    default=None,
    help="Path to strategist persona file",
)
def new_project(
    project_name: str,
    config_path: str,
    blueprint: str | None,
    interfaces: str | None,
    milestone: str | None,
    persona: str | None,
) -> None:
    """Bootstrap a full project: init + clone + start supervision."""
    # 1. Validate config
    try:
        config = load_config(Path(config_path))
    except (ValidationError, yaml.YAMLError) as e:
        console.print(f"[red]Error: Invalid configuration: {e}[/red]")
        raise SystemExit(1)

    # 2. Check project doesn't already exist
    project_dir = PROJECTS_BASE / project_name
    if project_dir.exists():
        console.print(f"[red]Error: Project already exists at {project_dir}[/red]")
        raise SystemExit(1)

    try:
        # ── Step 1: Init ──────────────────────────────────────────
        console.print(f"[bold]Initializing project '{project_name}'...[/bold]")

        clones_dir = project_dir / "clones"
        context_dir = project_dir / "context"
        agents_dir = context_dir / "agents"

        clones_dir.mkdir(parents=True)
        context_dir.mkdir(parents=True)
        agents_dir.mkdir(parents=True)

        shutil.copy2(config_path, project_dir / "agents.yaml")

        if blueprint:
            shutil.copy2(blueprint, context_dir / "PROJECT-BLUEPRINT.md")
        if interfaces:
            shutil.copy2(interfaces, context_dir / "INTERFACES.md")
        if milestone:
            shutil.copy2(milestone, context_dir / "MILESTONE-SCOPE.md")

        for agent in config.agents:
            prompt_content = render_template(
                "agent_prompt.md.j2",
                agent_id=agent.id,
                role=agent.role,
                project_name=config.project,
                owned_dirs=agent.owns,
                consumes=agent.consumes,
                milestone_name="TBD",
                milestone_scope="See MILESTONE-SCOPE.md",
            )
            write_atomic(agents_dir / f"{agent.id}.md", prompt_content)

        console.print("  Init complete")

        # ── Step 2: Clone ─────────────────────────────────────────
        console.print("[bold]Cloning agent repositories...[/bold]")

        for agent in config.agents:
            clone_dir = project_dir / "clones" / agent.id

            result = git.clone(config.repo, clone_dir)
            if not result.success:
                console.print(f"  [red]Clone failed for {agent.id}: {result.stderr}[/red]")
                if clone_dir.exists():
                    shutil.rmtree(clone_dir)
                continue

            branch_result = git.checkout_new_branch(
                f"agent/{agent.id.lower()}", cwd=clone_dir
            )
            if not branch_result.success:
                console.print(f"  [red]Branch failed for {agent.id}: {branch_result.stderr}[/red]")
                shutil.rmtree(clone_dir)
                continue

            _deploy_artifacts(clone_dir, agent, config, project_dir)
            console.print(f"  {agent.id} cloned")

        console.print("  Clone complete")

        # ── Step 3: Start supervision via daemon ──────────────────
        console.print("[bold]Starting supervision via daemon...[/bold]")
        try:
            with daemon_client() as client:
                params: dict = {"project_dir": str(project_dir)}
                if persona:
                    params["persona_path"] = persona
                resp = client.call("new_project", params)
                console.print(f"[green]Project '{resp.get('project', project_name)}' started[/green]")
        except SystemExit:
            # daemon_client() raises SystemExit(1) on connection errors
            console.print(
                "[yellow]Warning: Daemon not running. Project initialized and cloned "
                "but not started. Run 'vco up' to start.[/yellow]"
            )

    except SystemExit as e:
        # Re-raise exits from validation/existence checks (exit code != 0)
        # but catch daemon connection failures (already handled above)
        if e.code and e.code != 0:
            # Check if this is from the daemon_client handler (already printed warning)
            # or from an earlier validation step
            if not project_dir.exists():
                raise
            # Project was created, daemon just wasn't available -- that's OK
        # Exit 0 since init+clone succeeded even if daemon wasn't available
    except Exception:
        # Clean up on unexpected failure
        if project_dir.exists():
            shutil.rmtree(project_dir)
        raise
