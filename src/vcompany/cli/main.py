"""vCompany CLI entry point."""

import click

from vcompany.cli.clone_cmd import clone
from vcompany.cli.dispatch_cmd import dispatch
from vcompany.cli.init_cmd import init
from vcompany.cli.kill_cmd import kill
from vcompany.cli.preflight_cmd import preflight
from vcompany.cli.relaunch_cmd import relaunch
from vcompany.cli.sync_context_cmd import sync_context


@click.group()
@click.version_option(package_name="vcompany")
def cli():
    """vCompany -- Autonomous Multi-Agent Development System"""
    pass


cli.add_command(clone)
cli.add_command(dispatch)
cli.add_command(init)
cli.add_command(kill)
cli.add_command(preflight)
cli.add_command(relaunch)
cli.add_command(sync_context)
