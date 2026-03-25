"""vco sync-context command -- push updated context files to all agent clones."""

from pathlib import Path

import click

from vcompany.coordination.interactions import generate_interactions_md
from vcompany.coordination.sync_context import sync_context_files
from vcompany.models.config import load_config
from vcompany.shared.file_ops import write_atomic


@click.command("sync-context")
@click.argument("project_dir", type=click.Path(exists=True, path_type=Path))
def sync_context(project_dir: Path) -> None:
    """Push updated context files to all agent clones."""
    config = load_config(project_dir / "agents.yaml")

    # Generate and write INTERACTIONS.md to context/
    interactions_content = generate_interactions_md()
    write_atomic(project_dir / "context" / "INTERACTIONS.md", interactions_content)

    # Sync all context files to clones
    result = sync_context_files(project_dir, config)

    click.echo(f"Synced {result.files_synced} files to {result.clones_updated} clones")
    if result.errors:
        for error in result.errors:
            click.echo(f"  Error: {error}", err=True)
