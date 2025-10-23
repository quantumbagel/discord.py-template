import asyncio
import datetime
import importlib
import logging
import sys
import traceback
from pathlib import Path

import discord
from box import Box, BoxList, box
from discord import ClientException, app_commands
from discord.ext import commands
from discord.ext.commands import CommandError

from cogs.base import ImprovedCog
# REFACTOR: Import helpers for sending messages
from utilities import ensure_requirements, helpers
from utilities.config import get_config
from utilities.exception_manager import create_detailed_error_log
from utilities.formatter import ConsoleFormatter, FileFormatter
# REFACTOR: Import embed templates for error handling
from utilities.embeds import error_embed, warning_embed

configuration = get_config()

logging_level_conversion = {"critical": logging.CRITICAL,
                            "error": logging.ERROR,
                            "warning": logging.WARNING,
                            "info": logging.INFO,
                            "debug": logging.DEBUG}

# REFACTOR: Simplified logging level logic

is_there_logging_config = configuration.logging is not None
if is_there_logging_config:

    console_level_str = configuration.logging.console_level.lower()
    output_level_str = configuration.logging.output_level.lower()
else:
    console_level_str = None
    output_level_str = None



# Get the logging level, default to INFO if invalid
console_logging_level = logging_level_conversion.get(console_level_str, logging.INFO)
output_logging_level = logging_level_conversion.get(output_level_str, logging.INFO)

# If one is not set (i.e., invalid in config), default it to the other's valid level.
if console_level_str not in logging_level_conversion:
    console_logging_level = output_logging_level
if output_level_str not in logging_level_conversion:
    output_logging_level = console_logging_level

initialization_runtime = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
logging.getLogger("discord").setLevel(
    min(console_logging_level, logging.INFO))  # Discord.py logging level - INFO (don't want DEBUG)

# Configure root logger
root_logger = logging.getLogger("root")
root_logger.setLevel(console_logging_level)

# create console handler with a higher log level
ch = logging.StreamHandler(stream=sys.stdout)
ch.setLevel(logging.DEBUG)
ch.setFormatter(ConsoleFormatter())  # custom formatter
root_logger.handlers = [ch]  # Make sure to not double print

if is_there_logging_config and configuration.logging.output_folder:
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

    def __init__(self, config):
        # All intents because cool
        intents = discord.Intents.all()
        self._logger = logging.getLogger("template.bot")
        self._has_logged_in = False
        self.configuration: box.Box = config
        super().__init__(
            command_prefix="!",
            intents=intents,
            owner_ids=set(),
            activity=None,
            status=None,
            help_command=None  # Don't want hidden commands showing up
        )

    async def setup_hook(self):
        """
        This hook is called when the bot is first setting up.
        It's the perfect place to load your cogs.
        """
        self._logger.info("Now loading cogs")

        if configuration.cogs is None:
            self._logger.warning("No cogs found in config."
                                 "Unless you have drastically modified other components of this code, "
                                 "your bot will not do anything.")
            return

        cogs_list = configuration.cogs

        # Check if 'cogs' is a list (BoxList)
        if not isinstance(cogs_list, BoxList):
            self._logger.error(f"Cog validation error: 'cogs' must be a list. Found: {type(cogs_list)}")
            return

        for i, item in enumerate(cogs_list):
            #  Check if item is a dictionary (Box)
            if not isinstance(item, Box):
                self._logger.error(f"Cog validation error: Item {i} in 'cogs' is not a dictionary. Found: {type(item)}")
                return

            # Check if item has exactly one key
            if len(item) != 1:
                self._logger.error(f"Cog validation error: Item {i} in 'cogs' must have exactly one key. Found: {list(item.keys())}")
                return

            # Get the inner config
            cog_name = list(item.keys())[0]
            cog_config = item[cog_name]

            if not isinstance(cog_config, Box):
                self._logger.error(
                    f"Cog validation error: Config for '{cog_name}' (item {i}) is not a dictionary. Found: {type(cog_config)}")
                return

            # Check for 'class' key and its type
            if 'class' not in cog_config or not isinstance(cog_config['class'], str):
                self._logger.error(
                    f"Cog validation error: Config for '{cog_name}' (item {i}) must have a 'class' key with a string value.")
                return

            #  Check for 'enabled' key and its type
            if 'enabled' not in cog_config or not isinstance(cog_config.enabled, bool):
                self._logger.error(
                    f"Cog validation error: Config for '{cog_name}' (item {i}) must have an 'enabled' key with a boolean value.")
                return


        for cog_info in configuration.cogs:
            cog_info = dict(cog_info)
            cog_module = list(cog_info.keys())[0]
            cog_data = dict(cog_info[cog_module])
            cog_classname = cog_data["class"]
            enabled = cog_data.get("enabled", True)
            if not enabled:
                self._logger.warning(f"Skipping cog '{cog_module}.{cog_classname}' because it is disabled in config.")
                continue  # REFACTOR: Added continue to ensure disabled cogs are not processed
            try:
                module = importlib.import_module(cog_module)
            except ImportError:
                self._logger.warning(f"Failed to load cog '{cog_module}': "
                                     f"The module could not be imported.")
                continue
            cog_logger = self._logger.getChild(f"cogs[{cog_module}]")
            cog_class = getattr(module, cog_classname)
            if not issubclass(cog_class, ImprovedCog):
                self._logger.warning(
                    f"Cog '{cog_module}.{cog_classname}' is not a subclass of ImprovedCog and as such cannot be loaded.")
                continue
            try:
                await self.add_cog(cog_class(self, cog_logger))
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
            if user:  # Add check in case user is not cached
                return f"@{user.name} ({user.id})"
            return f"Unknown User ({user_id})"

        manually_set = "manually" if manually_set else "automatically"
        if self.owner_id:
            self._logger.info(f"This bot is owned by ({manually_set} set): {stringify_user(self.owner_id)}")
        elif self.owner_ids:
            self._logger.info(f"This bot is owned by ({manually_set} set): "
                              f"{','.join([stringify_user(user_id) for user_id in self.owner_ids])}")
        else:
            self._logger.error("This bot has no owner. This should not happen and will break all owner-only commands.")

        self._logger.info("Bot is ready and online!")

    async def on_command_error(self, ctx, error):
        # REFACTOR: Use helpers.send and embeds for all user-facing errors.

        # Check if the error is a CheckFailure
        if isinstance(error, commands.CheckFailure):
            # Log the failed check attempt
            log.warning(f"User '{ctx.author}' ({ctx.author.id}) failed permissions check for command '{ctx.command}'.")

            # Send a silent, embedded message to the user
            await helpers.send(
                ctx,
                embed=error_embed(
                    "Permission Denied",
                    "You do not have the required permissions to run this command."
                ),
                ephemeral=True,
                delete_after=10
            )
            return

        elif isinstance(error, commands.CommandNotFound) or isinstance(error, app_commands.errors.CommandNotFound):
            log.warning(f"User '{ctx.author}' ({ctx.author.id}) requested a message command that we don't have."
                        f" We won't do anything because this could be a valid command implemented by another bot."
                        f" More information: {error}")
            return

        elif isinstance(error, commands.CommandInvokeError):
            log.error(f"The command {ctx.command} crashed while executing. We are now logging the information.")

            # Get the original exception
            original_error = error.original
            exc_type = type(original_error)
            exc_value = original_error
            tb = original_error.__traceback__

            # Call your logging function
            if configuration.logging.output_folder:
                error_saved_to = create_detailed_error_log(
                    configuration.logging.output_folder, ctx.command.name, exc_type, exc_value, tb
                )
                log.info(f"Traceback saved to {error_saved_to!r}")
                # REFACTOR: Inform user about the error and log file
                await helpers.send(
                    ctx,
                    embed=error_embed(
                        "Command Error",
                        f"An unexpected error occurred. The details have been logged.\n"
                        f"**Log File:** `{error_saved_to}`"
                    ),
                    ephemeral=True
                )
            else:
                log.warning("Nothing was saved because logging to file was not enabled."
                            " Logging the traceback to console instead.")
                traceback.print_exception(exc=error)
                # REFACTOR: Inform user about the error
                await helpers.send(
                    ctx,
                    embed=error_embed(
                        "Command Error",
                        "An unexpected error occurred. Please contact the bot owner."
                    ),
                    ephemeral=True
                )
            return

        elif isinstance(error, commands.MissingRequiredArgument):
            if ctx.command.qualified_name == "management eval":
                # A little workaround 😈
                return
            log.warning(f"User '{ctx.author}' ({ctx.author.id}) failed to provide required argument for command '{ctx.command.qualified_name}'.")
            # REFACTOR: Use a WarningEmbed for user input errors
            await helpers.send(
                ctx,
                embed=warning_embed(
                    "Missing Argument",
                    f"You are missing a required argument: `{error.param.name}`"
                ),
                ephemeral=True,
                delete_after=10
            )
            return

        # For other errors, we can fall back to the default behavior
        log.error(f"An unhandled error occurred in command '{ctx.command}': {error}")

        # REFACTOR: Send a generic error for unhandled cases
        try:
            await helpers.send(
                ctx,
                embed=error_embed(
                    "Unhandled Error",
                    "An unknown error occurred. Please contact the bot owner."
                ),
                ephemeral=True
            )
        except Exception as e:
            log.error(f"Failed to send unhandled error message to user: {e}")

        # This will print tracebacks for unexpected errors to the console
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