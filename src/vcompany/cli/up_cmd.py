"""vco up -- Start the vCompany system (bot + tmux session).

Starts the Discord bot with optional project loading. Creates a tmux
session 'vco-system' with windows for strategist and monitor. The bot
works without a project -- Strategist is always available in #strategist.
"""

import logging
import subprocess
from pathlib import Path

import click

logger = logging.getLogger("vcompany.cli.up")

WORKTREE_PATH = Path.home() / "vco-workflow-master-worktree"
WORKTREE_BRANCH = "worktree/workflow-master"


def _ensure_worktree(repo_root: Path) -> Path:
    """Create workflow-master git worktree if it doesn't exist. Idempotent."""
    if WORKTREE_PATH.exists():
        return WORKTREE_PATH

    # Check if branch already exists (leftover branch without worktree dir)
    branch_check = subprocess.run(
        ["git", "-C", str(repo_root), "branch", "--list", WORKTREE_BRANCH],
        capture_output=True,
        text=True,
    )
    has_branch = bool(branch_check.stdout.strip())

    cmd = ["git", "-C", str(repo_root), "worktree", "add"]
    if not has_branch:
        cmd += ["-b", WORKTREE_BRANCH]
    cmd.append(str(WORKTREE_PATH))
    if has_branch:
        cmd.append(WORKTREE_BRANCH)

    subprocess.run(cmd, check=True)
    logger.info("Created workflow-master worktree at %s", WORKTREE_PATH)
    return WORKTREE_PATH


@click.command()
@click.option(
    "--project-dir",
    type=click.Path(file_okay=False, dir_okay=True),
    default=None,
    help="Project directory containing agents.yaml (optional)",
)
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]),
    default="INFO",
    help="Logging level",
)
def up(project_dir: str | None, log_level: str) -> None:
    """Start the vCompany system.

    Launches the Discord bot + Strategist tmux pane + monitor tmux pane.
    Works without a project -- Strategist is always available in #strategist.
    """
    log_file = Path.home() / "vco.log"
    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(str(log_file), mode="w"),
        ],
    )
    logging.getLogger().info("Logging to %s", log_file)

    from vcompany.bot.client import VcoBot
    from vcompany.bot.config import BotConfig
    from vcompany.tmux.session import TmuxManager

    # Set up tmux session for monitor and agents (Strategist runs via subprocess, not tmux)
    tmux = TmuxManager()
    session = tmux.get_or_create_session("vco-system")

    # First window: monitor (placeholder until project loads)
    active_window = session.active_window
    active_window.rename_window("monitor")
    active_pane = active_window.active_pane
    tmux.send_command(active_pane, "echo 'vCompany monitor: waiting for project...'")

    # Create workflow-master worktree (idempotent, non-blocking on failure)
    repo_root = Path(__file__).resolve().parents[3]
    try:
        _ensure_worktree(repo_root)
    except Exception:
        logger.warning("Failed to create workflow-master worktree -- continuing without it", exc_info=True)

    # Load bot config from environment
    bot_config = BotConfig()

    # Optionally load project config
    project_path = None
    project_config = None

    if project_dir:
        project_path = Path(project_dir)
        agents_yaml = project_path / "agents.yaml"
        if agents_yaml.exists():
            from vcompany.models.config import load_config

            project_config = load_config(agents_yaml)
            logger.info("Loaded project config from %s", agents_yaml)
        else:
            logger.info("No agents.yaml found at %s, starting without project", project_path)
            project_path = None

    # Create and run bot
    if project_path and project_config:
        logger.info("Starting VcoBot with project at %s", project_path)
        bot_instance = VcoBot(
            guild_id=bot_config.discord_guild_id,
            project_dir=project_path,
            config=project_config,
        )
    else:
        logger.info("Starting VcoBot without project (Strategist-only mode)")
        bot_instance = VcoBot(guild_id=bot_config.discord_guild_id)

    from vcompany.daemon.daemon import Daemon

    daemon = Daemon(
        bot=bot_instance,
        bot_token=bot_config.discord_bot_token,
    )
    daemon.run()  # Blocks until shutdown
