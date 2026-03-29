"""Docker image build utilities (D-03, D-04).

Auto-build logic wraps docker-py SDK calls in asyncio.to_thread() to avoid
blocking the event loop (Pitfall 2 from RESEARCH.md).
"""

import asyncio
import logging
from pathlib import Path

import docker
import docker.errors

logger = logging.getLogger(__name__)

# Default Dockerfile location relative to repo root
_DEFAULT_DOCKERFILE_DIR = Path(__file__).parent.parent.parent.parent / "docker"


async def ensure_docker_image(
    image: str,
    dockerfile_dir: Path | None = None,
) -> bool:
    """Build Docker image if it doesn't exist locally (D-03).

    Called automatically during Docker agent hire. Uses asyncio.to_thread()
    to avoid blocking the event loop during potentially long builds.

    Args:
        image: Docker image name with tag (e.g., "vco-agent:latest").
        dockerfile_dir: Directory containing Dockerfile. Defaults to docker/ in repo root.

    Returns:
        True if image was built, False if it already existed.
    """
    build_dir = dockerfile_dir or _DEFAULT_DOCKERFILE_DIR
    client = docker.from_env()

    try:
        await asyncio.to_thread(client.images.get, image)
        logger.info("Docker image %s found locally", image)
        return False
    except docker.errors.ImageNotFound:
        logger.info("Docker image %s not found, building from %s...", image, build_dir)
        await asyncio.to_thread(
            client.images.build,
            path=str(build_dir),
            tag=image,
            rm=True,
        )
        logger.info("Successfully built Docker image %s", image)
        return True


def build_image_sync(
    image: str,
    dockerfile_dir: Path | None = None,
    force: bool = False,
) -> bool:
    """Synchronous image build for CLI usage (D-04).

    Args:
        image: Docker image name with tag.
        dockerfile_dir: Directory containing Dockerfile.
        force: If True, rebuild even if image exists.

    Returns:
        True if image was built, False if skipped (already exists and not forced).
    """
    build_dir = dockerfile_dir or _DEFAULT_DOCKERFILE_DIR
    client = docker.from_env()

    if not force:
        try:
            client.images.get(image)
            logger.info("Docker image %s already exists (use --force to rebuild)", image)
            return False
        except docker.errors.ImageNotFound:
            pass

    logger.info("Building Docker image %s from %s...", image, build_dir)
    client.images.build(
        path=str(build_dir),
        tag=image,
        rm=True,
    )
    logger.info("Successfully built Docker image %s", image)
    return True
