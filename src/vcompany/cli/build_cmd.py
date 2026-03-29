"""vco build -- Build Docker agent images (D-04)."""

from __future__ import annotations

import click
from rich.console import Console

from vcompany.docker.build import build_image_sync


@click.command()
@click.argument("image", default="vco-agent:latest")
@click.option("--force", is_flag=True, help="Rebuild even if image exists")
@click.option("--dockerfile-dir", type=click.Path(exists=True), default=None,
              help="Directory containing Dockerfile (default: docker/)")
def build(image: str, force: bool, dockerfile_dir: str | None) -> None:
    """Build a Docker agent image.

    IMAGE defaults to vco-agent:latest. Use --force to rebuild existing images.

    Examples:
        vco build                          # Build default image
        vco build vco-agent:v2 --force     # Force rebuild with custom tag
    """
    from pathlib import Path

    console = Console()
    dir_path = Path(dockerfile_dir) if dockerfile_dir else None

    try:
        built = build_image_sync(image, dockerfile_dir=dir_path, force=force)
        if built:
            console.print(f"[green]Built image: {image}[/green]")
        else:
            console.print(f"[yellow]Image {image} already exists (use --force to rebuild)[/yellow]")
    except Exception as e:
        console.print(f"[red]Build failed: {e}[/red]")
        raise SystemExit(1)
