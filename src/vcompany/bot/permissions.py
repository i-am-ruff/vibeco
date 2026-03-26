"""Role-based permission checks for Discord bot commands.

Provides the is_owner() decorator for prefix commands and
is_owner_app_check() decorator for slash commands. Both restrict
commands to users with the vco-owner role (D-08, D-09).
"""

import discord
from discord import app_commands
from discord.ext import commands


def is_owner_app_check():
    """Check that the invoking user has the vco-owner role (slash command version).

    Returns False on failure so a polite ephemeral message can be sent.
    Usage: @is_owner_app_check() on an app_commands.command.
    """

    async def predicate(interaction: discord.Interaction) -> bool:
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return False

        has_role = any(role.name == "vco-owner" for role in interaction.user.roles)
        if not has_role:
            await interaction.response.send_message(
                "You need the `vco-owner` role to use this command.", ephemeral=True
            )
            return False

        return True

    return app_commands.check(predicate)


def is_owner():
    """Check that the invoking user has the vco-owner role.

    Returns False (not raise) on failure so a polite message can be sent.
    Usage: @is_owner() on a command.
    """

    async def predicate(ctx: commands.Context) -> bool:
        if not isinstance(ctx.author, discord.Member):
            await ctx.send("This command can only be used in a server.")
            return False

        has_role = any(role.name == "vco-owner" for role in ctx.author.roles)
        if not has_role:
            await ctx.send("You need the `vco-owner` role to use this command.")
            return False

        return True

    return commands.check(predicate)
