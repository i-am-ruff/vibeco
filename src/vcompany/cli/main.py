"""vCompany CLI entry point."""

import click


@click.group()
@click.version_option(package_name="vcompany")
def cli():
    """vCompany -- Autonomous Multi-Agent Development System"""
    pass
