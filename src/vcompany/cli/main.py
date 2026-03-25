"""vCompany CLI entry point."""

import click

from vcompany.cli.init_cmd import init


@click.group()
@click.version_option(package_name="vcompany")
def cli():
    """vCompany -- Autonomous Multi-Agent Development System"""
    pass


cli.add_command(init)
