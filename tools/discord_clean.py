#!/usr/bin/env python3
"""Delete all vco-* categories and their channels from Discord. Clean slate."""

import asyncio
import os
import sys

import discord


async def clean():
    token = os.environ.get("DISCORD_BOT_TOKEN", "")
    guild_id = os.environ.get("DISCORD_GUILD_ID", "")

    if not token or not guild_id:
        print("Error: DISCORD_BOT_TOKEN and DISCORD_GUILD_ID must be set")
        sys.exit(1)

    client = discord.Client(intents=discord.Intents.default())

    @client.event
    async def on_ready():
        guild = client.get_guild(int(guild_id))
        if not guild:
            print(f"Error: Guild {guild_id} not found")
            await client.close()
            return

        deleted = 0
        for cat in guild.categories:
            if cat.name.startswith("vco-"):
                for ch in cat.channels:
                    await ch.delete()
                    print(f"  Deleted #{ch.name}")
                    deleted += 1
                await cat.delete()
                print(f"Deleted category {cat.name}")
                deleted += 1

        print(f"\nDone. Deleted {deleted} channels/categories.")
        await client.close()

    await client.start(token)


if __name__ == "__main__":
    asyncio.run(clean())
