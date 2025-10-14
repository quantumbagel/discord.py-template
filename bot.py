import os

import discord
from discord.ext import commands

from utilities import ensure_requirements
import asyncio
import importlib
import logging
import sys
from utilities.formatter import Formatter

logging.getLogger("discord").setLevel(logging.INFO)  # Discord.py logging level - INFO (don't want DEBUG)

logging.basicConfig(level=logging.DEBUG)

# Configure root logger
root_logger = logging.getLogger("root")
root_logger.setLevel(logging.DEBUG)

# create console handler with a higher log level
ch = logging.StreamHandler(stream=sys.stdout)
ch.setLevel(logging.DEBUG)

ch.setFormatter(Formatter())  # custom formatter
root_logger.handlers = [ch]  # Make sure to not double print

log = logging.getLogger("template")  # Base logger
startup_logger = log.getChild("startup")

startup_logger.info(f"QuantumBagel's Discord.py Bot Template")  # credit yey

ensure_requirements.ensure_requirements()  # install dependencies

from cogs import echo

TOKEN = ""

class MyBot(commands.Bot):
    def __init__(self):
        # All intents because cool
        intents = discord.Intents.all()

        # Startup
        activity_type = discord.ActivityType.playing
        activity = discord.Activity(type=activity_type, name="Bot is starting...")
        print('init')
        super().__init__(
            command_prefix=None,
            intents=intents,
            owner_ids=set(),
            activity=activity
        )

    async def setup_hook(self):
        """
        This hook is called when the bot is first setting up.
        It's the perfect place to load your cogs.
        """
        startup_logger.info("now loading cogs")
        cogs_folder = "./cogs"

        for filename in os.listdir(cogs_folder):
            if filename.endswith(".py"):
                cog_name = f"{cogs_folder.replace('./', '')}.{filename[:-3]}"
                try:
                    await self.load_extension(cog_name)
                    startup_logger.info(f"Loaded cog: {cog_name}")
                except Exception as e:
                    startup_logger.error(f"Failed to load cog: {cog_name}", exc_info=e)

        # Optional: Sync slash commands with a specific guild for faster testing.
        # To sync globally, remove the `guild` argument.
        # guild_id = 1188476885420740740
        # if guild_id:
        #     startup_logger.info(f"Syncing slash commands to guild {guild_id}...")
        #     self.tree.copy_global_to(guild=discord.Object(id=guild_id))
        #     await self.tree.sync(guild=discord.Object(id=guild_id))

        startup_logger.info("cogs loaded")

    async def on_ready(self):
        """Event that fires when the bot is fully logged in and ready."""
        startup_logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
        startup_logger.info("Bot is ready and online!")
        print('removing presence')
        await self.change_presence()


# 5. Main execution block
async def main():
    if TOKEN is None:
        startup_logger.critical("TOKEN not found in .env file. Please set it.")
        return

    bot = MyBot()
    async with bot:
        await bot.start(TOKEN)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot shutdown requested. Exiting...")

if __name__ != "__main__":
    startup_logger.critical("Don't import from this file!")
    sys.exit(1)
