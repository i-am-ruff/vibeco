"""vCompany CLI entry point."""

import click

from vcompany.cli.bot_cmd import bot
from vcompany.cli.clone_cmd import clone
from vcompany.cli.init_cmd import init
from vcompany.cli.monitor_cmd import monitor
from vcompany.cli.new_milestone_cmd import new_milestone
from vcompany.cli.preflight_cmd import preflight
from vcompany.cli.report_cmd import report
from vcompany.cli.restart_cmd import restart
from vcompany.cli.sync_context_cmd import sync_context
from vcompany.cli.up_cmd import up


@click.group()
@click.version_option(package_name="vcompany")
def cli():
    """vCompany -- Autonomous Multi-Agent Development System"""
    pass


cli.add_command(bot)
cli.add_command(clone)
cli.add_command(init)
cli.add_command(monitor)
cli.add_command(new_milestone)
cli.add_command(preflight)
cli.add_command(report)
cli.add_command(restart)
cli.add_command(sync_context)
cli.add_command(up)
