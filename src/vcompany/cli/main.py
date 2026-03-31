"""vCompany CLI entry point."""

import click

from vcompany.cli.ask_cmd import ask
from vcompany.cli.bot_cmd import bot
from vcompany.cli.clean_cmd import clean
from vcompany.cli.build_cmd import build
from vcompany.cli.clone_cmd import clone
from vcompany.cli.init_cmd import init
from vcompany.cli.monitor_cmd import monitor
from vcompany.cli.new_milestone_cmd import new_milestone
from vcompany.cli.preflight_cmd import preflight
from vcompany.cli.report_cmd import report
from vcompany.cli.restart_cmd import restart
from vcompany.cli.sync_context_cmd import sync_context
from vcompany.cli.dismiss_cmd import dismiss
from vcompany.cli.new_project_cmd import new_project
from vcompany.cli.down_cmd import down
from vcompany.cli.give_task_cmd import give_task
from vcompany.cli.health_cmd import health
from vcompany.cli.hire_cmd import hire
from vcompany.cli.status_cmd import status
from vcompany.cli.send_file_cmd import send_file
from vcompany.cli.signal_cmd import signal
from vcompany.cli.up_cmd import up


@click.group()
@click.version_option(package_name="vcompany")
def cli():
    """vCompany -- Autonomous Multi-Agent Development System"""
    pass


cli.add_command(ask)
cli.add_command(bot)
cli.add_command(build)
cli.add_command(clone)
cli.add_command(init)
cli.add_command(monitor)
cli.add_command(new_milestone)
cli.add_command(preflight)
cli.add_command(report)
cli.add_command(restart)
cli.add_command(sync_context)
cli.add_command(up)
cli.add_command(down)
cli.add_command(hire)
cli.add_command(give_task)
cli.add_command(dismiss)
cli.add_command(status)
cli.add_command(health)
cli.add_command(new_project)
cli.add_command(send_file)
cli.add_command(signal)
cli.add_command(clean)
