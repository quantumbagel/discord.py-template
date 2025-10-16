import datetime
import os
from pathlib import Path

import discord
from discord import ClientException
from discord.ext import commands
from discord.ext.commands import CommandError

from cogs.base import ImprovedCog
from utilities import ensure_requirements
import asyncio
import importlib
import logging
import sys
from utilities.formatter import ConsoleFormatter, FileFormatter
from utilities.config import get_config

configuration = get_config()

logging_level_conversion = {"critical": logging.CRITICAL,
                            "error": logging.ERROR,
                            "warning": logging.WARNING,
                            "info": logging.INFO,
                            "debug": logging.DEBUG}



console_level = configuration.logging.console_level.lower()
output_level = configuration.logging.output_level.lower()
console_logging_level = None
output_logging_level = None

if console_level in logging_level_conversion.keys():
    console_logging_level = logging_level_conversion[console_level]

if output_level in logging_level_conversion.keys():
    output_logging_level = logging_level_conversion[output_level]

if console_logging_level is None and output_logging_level is not None:
    console_logging_level = output_logging_level
elif output_logging_level is None and console_logging_level is not None:
    output_logging_level = console_logging_level
elif console_logging_level is None and output_logging_level is None:
    console_logging_level = logging.INFO
    output_logging_level = logging.INFO



initialization_runtime = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
logging.getLogger("discord").setLevel(min(console_logging_level, logging.INFO))  # Discord.py logging level - INFO (don't want DEBUG)


# Configure root logger
root_logger = logging.getLogger("root")
root_logger.setLevel(console_logging_level)

# create console handler with a higher log level
ch = logging.StreamHandler(stream=sys.stdout)
ch.setLevel(logging.DEBUG)
ch.setFormatter(ConsoleFormatter())  # custom formatter
root_logger.handlers = [ch]  # Make sure to not double print

if configuration.logging.output_folder:
    log_file_path = f"{configuration.logging.output_folder}/run_{initialization_runtime}.log"
    root_logger.info(f"logging prep: this session will be saved to {log_file_path!r}")
    log_file = Path(log_file_path)

    # Create the parent directories if they don't exist
    log_file.parent.mkdir(parents=True, exist_ok=True)

    fh = logging.FileHandler(log_file_path)
    fh.setLevel(output_logging_level)
    fh.setFormatter(FileFormatter())
    root_logger.handlers.append(fh)

log = logging.getLogger("template")  # Base logger
startup_logger = log.getChild("startup")

startup_logger.info(f"This is quantumbagel's discord.py bot template!")  # credit yey

ensure_requirements.ensure_requirements()  # install dependencies


class BotTemplate(commands.Bot):
    _logger: logging.Logger = None
    def __init__(self, configuration):
        # All intents because cool
        intents = discord.Intents.all()
        self._logger = logging.getLogger("template.bot")
        self._has_logged_in = False
        self.configuration = configuration

        self._logger.info("Setting initial presence...")
        activity_type = discord.ActivityType.playing
        activity = discord.Activity(type=activity_type, name="Bot is starting...")
        super().__init__(
            command_prefix="!",
            intents=intents,
            owner_ids=set(),
            activity=activity
        )

    async def setup_hook(self):
        """
        This hook is called when the bot is first setting up.
        It's the perfect place to load your cogs.
        """
        self._logger.info("Now loading cogs")

        for cog_info in configuration.cogs:
            cog_info = dict(cog_info)
            cog_module = list(cog_info.keys())[0]
            cog_data = dict(cog_info[cog_module])
            cog_classname = cog_data["class"]
            enabled = cog_data.get("enabled", True)
            if not enabled:
                self._logger.warning(f"Skipping cog '{cog_module}.{cog_classname}' because it is disabled.")
            try:
                module = importlib.import_module(cog_module)
            except ImportError:
                self._logger.warning(f"Failed to load cog '{cog_module}': "
                                     f"The module could not be imported.")
                continue
            cog_logger = self._logger.getChild(f"cogs[{cog_module}]")
            cog_class = getattr(module, cog_classname)
            if not issubclass(cog_class, ImprovedCog):
                self._logger.warning(f"Cog '{cog_module}.{cog_classname}' is not a subclass of ImprovedCog and as such cannot be loaded.")
                continue
            try:
                await self.add_cog(cog_class(self, cog_logger))
            except TypeError:
                self._logger.warning(f"Failed to load cog '{cog_module}.{cog_classname}': "
                                     f"The cog does not inherit from class Cog")
            except CommandError:
                self._logger.warning(f"Failed to load cog '{cog_module}.{cog_classname}': "
                                     f"There was an error while adding the Cog!", exc_info=True)
            except ClientException:
                self._logger.warning(f"Failed to load cog '{cog_module}.{cog_classname}': "
                                     f"A cog with this name is already loaded!")




    async def on_ready(self):
        """Event that fires when the bot is fully logged in and ready."""
        self._logger.info(f"Logged in as {self.user!r}")
        if self._has_logged_in:
            self._logger.warning("Bot is relogging.")
            return
        self._has_logged_in = True
        manually_set = True
        if not self.owner_ids and not self.owner_id:
            manually_set = False
            # This is a hack that will populate either self.owner_id or self.owner_ids
            # depending on the number of owners from the application portal
            await self.is_owner(discord.Object(id=1234))


        def stringify_user(user_id):
            user = self.get_user(user_id)
            return f"@{user.name} ({user.id})"
        manually_set = "manually" if manually_set else "automatically"
        if self.owner_id:
            self._logger.info(f"This bot is owned by ({manually_set} set): {stringify_user(self.owner_id)}")
        elif self.owner_ids:
            self._logger.info(f"This bot is owned by ({manually_set} set): "
                              f"{','.join([stringify_user(user_id) for user_id in self.owner_ids])}")
        else:
            self._logger.error("This bot has no owner. This should not happen and will break all owner-only commands.")

        self._logger.info("Bot is ready and online!")
        await self.change_presence()
        self._logger.debug("Removed startup presence before cogs load.")

    async def on_command_error(self, ctx, error):
        # Check if the error is a CheckFailure
        if isinstance(error, commands.CheckFailure):
            # Log the failed check attempt
            log.warning(f"User '{ctx.author}' ({ctx.author.id}) failed check for command '{ctx.command}'.")

            # Optionally, send a silent message to the user
            await ctx.send("You do not have the required permissions to run this command.", ephemeral=True,
                           delete_after=10)

            # The error is handled, so we can just return
            return

        # For other errors, we can fall back to the default behavior
        # This will print tracebacks for unexpected errors to the console
        log.error(f"An unhandled error occurred in command '{ctx.command}': {error}")
        await super().on_command_error(ctx, error)


# 5. Main execution block
async def main():
    if configuration.auth is None:
        startup_logger.critical("Authentication token not found in configuration. Exiting...")
        return

    bot = BotTemplate(configuration)
    async with bot:
        await bot.start(configuration.auth)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        startup_logger.critical("Bot shutdown requested. Exiting...")

if __name__ != "__main__":
    startup_logger.critical("Don't import from this file!")
    sys.exit(1)
