"""Role-based permission checks for Discord bot commands.

Provides the is_owner() decorator that restricts commands to users
with the vco-owner role (D-08, D-09).
"""

import discord
from discord.ext import commands


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
