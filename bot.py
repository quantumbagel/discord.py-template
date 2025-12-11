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

def setup_logging(config: Box):
    """
    Configures the logging for the bot.
    """
    logging_level_conversion = {
        "critical": logging.CRITICAL,
        "error": logging.ERROR,
        "warning": logging.WARNING,
        "info": logging.INFO,
        "debug": logging.DEBUG,
    }

    console_level_str = config.logging.console_level.lower() if config.logging else None
    output_level_str = config.logging.output_level.lower() if config.logging else None

    console_logging_level = logging_level_conversion.get(console_level_str, logging.INFO)
    output_logging_level = logging_level_conversion.get(output_level_str, logging.INFO)

    if console_level_str not in logging_level_conversion:
        console_logging_level = output_logging_level
    if output_level_str not in logging_level_conversion:
        output_logging_level = console_logging_level

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

    if config.logging and config.logging.output_folder:
        log_file_path = f"{config.logging.output_folder}/run_{initialization_runtime}.log"
        root_logger.info(f"Logging session will be saved to {log_file_path!r}")
        log_file = Path(log_file_path)

        # Create the parent directories if they don't exist
        log_file.parent.mkdir(parents=True, exist_ok=True)

        fh = logging.FileHandler(log_file_path)
        fh.setLevel(output_logging_level)
        fh.setFormatter(FileFormatter())
        root_logger.handlers.append(fh)


configuration = get_config()
setup_logging(configuration)

qualified_bot_name = configuration.bot.short_name if configuration.bot.short_name else "template"

log = logging.getLogger(qualified_bot_name)  # Base logger
startup_logger = log.getChild("startup")

startup_logger.info(f"This is quantumbagel's discord.py bot template!")  # credit yey

ensure_requirements.ensure_requirements()  # install dependencies


class BotTemplate(commands.Bot):
    _logger: logging.Logger = None

    def __init__(self, config: Box):
        # All intents because cool
        intents = discord.Intents.all()
        self._logger = logging.getLogger(f"{qualified_bot_name}.bot")
        self._has_logged_in = False
        self.configuration: box.Box = config
        super().__init__(
            command_prefix="a!",
            intents=intents,
            owner_ids=set(),
            activity=None,
            status=None,
            help_command=None  # Don't want hidden commands showing up
        )

    async def setup_hook(self):
        """
        This hook is called when the bot is first setting up.
        It's where cogs are loaded and database initialized.
        """
        self.tree.on_error = self.on_app_command_error
        await self._initialize_database()
        await self._load_cogs()

    async def _initialize_database(self):
        """Initializes the database."""
        import utilities.database as database
        await database.init_database(["cogs.emoticon.models"])

    async def _load_cogs(self):
        """Loads all cogs from the configuration."""
        self._logger.info("Now loading cogs")
        for cog_info in self.configuration.cogs:
            await self._load_cog(dict(cog_info))

    async def _load_cog(self, cog_info: dict):
        """Loads a single cog."""
        cog_module = list(cog_info.keys())[0]
        cog_data = dict(cog_info[cog_module])
        cog_classname = cog_data["class"]
        enabled = cog_data.get("enabled", True)

        if not enabled:
            self._logger.warning(f"Skipping cog '{cog_module}.{cog_classname}' because it is disabled in config.")
            return

        try:
            module = importlib.import_module(cog_module)
            cog_class = getattr(module, cog_classname)
            if not issubclass(cog_class, ImprovedCog):
                self._logger.warning(f"Cog '{cog_module}.{cog_classname}' is not a subclass of ImprovedCog and cannot be loaded.")
                return

            cog_logger = self._logger.getChild(f"cogs[{cog_module}]")
            await self.add_cog(cog_class(self, cog_logger))
        except (ImportError, CommandError, ClientException) as e:
            self._logger.warning(f"Failed to load cog '{cog_module}.{cog_classname}': {e}", exc_info=True)

    async def close(self):
        """
        Called when the bot is shutting down.
        """
        import utilities.database as database
        await database.close_database()
        await super().close()

    async def on_ready(self):
        """Event that fires when the bot is fully logged in and ready."""
        self._logger.info(f"Logged in as {self.user!r}")
        if self._has_logged_in:
            self._logger.warning("Bot is relogging.")
            return
        self._has_logged_in = True

        await self._set_owner()
        self._log_owner_info()

        self._logger.info("Bot is ready and online!")

    async def _set_owner(self):
        """Sets the bot owner(s) from the application info."""
        if not self.owner_ids and not self.owner_id:
            await self.is_owner(discord.Object(id=1234))

    def _log_owner_info(self):
        """Logs the owner information."""
        manually_set = bool(self.owner_ids or self.owner_id)
        manually_set_str = "manually" if manually_set else "automatically"

        def stringify_user(user_id: int) -> str:
            user = self.get_user(user_id)
            return f"@{user.name} ({user.id})" if user else f"Unknown User ({user_id})"

        if self.owner_id:
            self._logger.info(f"This bot is owned by ({manually_set_str} set): {stringify_user(self.owner_id)}")
        elif self.owner_ids:
            owners = ', '.join([stringify_user(uid) for uid in self.owner_ids])
            self._logger.info(f"This bot is owned by ({manually_set_str} set): {owners}")
        else:
            self._logger.error("This bot has no owner. This should not happen and will break all owner-only commands.")

    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Global error handler for App Commands (Slash Commands)."""
        
        if isinstance(error, app_commands.CommandInvokeError):
            error = error.original

        if isinstance(error, app_commands.CommandOnCooldown):
            await self._handle_cooldown_error(interaction, error)
        elif isinstance(error, app_commands.MissingPermissions) or isinstance(error, app_commands.CheckFailure):
            await self._handle_permissions_error(interaction)
        else:
            await self._handle_unexpected_error(interaction, error)

    async def _handle_cooldown_error(self, interaction: discord.Interaction, error: app_commands.CommandOnCooldown):
        """Handles cooldown errors for app commands."""
        await interaction.response.send_message(
            embed=warning_embed(
                "Command on Cooldown",
                f"This command is on cooldown. Please try again in `{error.retry_after:.2f}` seconds."
            ),
            ephemeral=True,
            delete_after=10
        )

    async def _handle_permissions_error(self, interaction: discord.Interaction):
        """Handles permission errors for app commands."""
        await interaction.response.send_message(
            embed=error_embed(
                "Permission Denied",
                "You do not have the required permissions to run this command."
            ),
            ephemeral=True
        )

    async def _handle_unexpected_error(self, interaction: discord.Interaction, error: Exception):
        """Handles unexpected errors for app commands."""
        log.error(f"App Command Error: {error} in command '{interaction.command.name if interaction.command else 'Unknown'}'")
        
        exc_type = type(error)
        exc_type_name = exc_type.__name__
        tb = error.__traceback__

        if self.configuration.logging.output_folder:
            command_name = interaction.command.name if interaction.command else 'Unknown'
            error_saved_to = create_detailed_error_log(
                self.configuration.logging.output_folder, command_name, exc_type, error, tb
            )
            log.info(f"Traceback saved to {error_saved_to!r}")
            msg_content = (f"An unexpected error occurred: `{exc_type_name}`.\n"
                           f"The details have been logged.\n"
                           f"**Log File:** `{error_saved_to}`")
        else:
            log.warning("Logging to file disabled. Printing traceback to console.")
            traceback.print_exception(exc_type, error, tb)
            msg_content = f"An unexpected error occurred: `{exc_type_name}`.\nPlease contact the bot owner."

        msg_embed = error_embed("Command Error", msg_content)

        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=msg_embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=msg_embed, ephemeral=True)
        except Exception as e:
            log.error(f"Failed to send error message to user: {e}")

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        """Global error handler for message commands."""

        if isinstance(error, commands.CheckFailure):
            await self._handle_check_failure(ctx)
        elif isinstance(error, commands.CommandNotFound):
            self._handle_command_not_found(ctx, error)
        elif isinstance(error, commands.CommandInvokeError):
            await self._handle_command_invoke_error(ctx, error)
        elif isinstance(error, commands.MissingRequiredArgument):
            await self._handle_missing_argument(ctx, error)
        else:
            await self._handle_generic_command_error(ctx, error)

    async def _handle_check_failure(self, ctx: commands.Context):
        """Handles check failures for message commands."""
        log.warning(f"User '{ctx.author}' ({ctx.author.id}) failed permissions check for command '{ctx.command}'.")
        await helpers.send(
            ctx,
            embed=error_embed(
                "Permission Denied",
                "You do not have the required permissions to run this command."
            ),
            ephemeral=True,
            delete_after=10
        )

    def _handle_command_not_found(self, ctx: commands.Context, error: commands.CommandError):
        """Handles command not found errors for message commands."""
        log.warning(f"User '{ctx.author}' ({ctx.author.id}) requested a message command that we don't have: {error}")

    async def _handle_command_invoke_error(self, ctx: commands.Context, error: commands.CommandInvokeError):
        """Handles command invocation errors for message commands."""
        log.error(f"The command {ctx.command} crashed while executing.")

        original_error = error.original
        exc_type = type(original_error)
        exc_value = original_error
        tb = original_error.__traceback__

        if self.configuration.logging.output_folder:
            error_saved_to = create_detailed_error_log(
                self.configuration.logging.output_folder, ctx.command.name, exc_type, exc_value, tb
            )
            log.info(f"Traceback saved to {error_saved_to!r}")
            msg_content = (f"An unexpected error occurred. The details have been logged.\n"
                           f"**Log File:** `{error_saved_to}`")
        else:
            log.warning("Logging to file disabled. Logging traceback to console.")
            traceback.print_exception(exc=error)
            msg_content = "An unexpected error occurred. Please contact the bot owner."

        await helpers.send(
            ctx,
            embed=error_embed("Command Error", msg_content),
            ephemeral=True
        )

    async def _handle_missing_argument(self, ctx: commands.Context, error: commands.MissingRequiredArgument):
        """Handles missing argument errors for message commands."""
        if ctx.command.qualified_name == "management eval":
            return
        log.warning(f"User '{ctx.author}' ({ctx.author.id}) failed to provide required argument for command '{ctx.command.qualified_name}'.")
        await helpers.send(
            ctx,
            embed=warning_embed(
                "Missing Argument",
                f"You are missing a required argument: `{error.param.name}`"
            ),
            ephemeral=True,
            delete_after=10
        )

    async def _handle_generic_command_error(self, ctx: commands.Context, error: commands.CommandError):
        """Handles generic errors for message commands."""
        log.error(f"An unhandled error occurred in command '{ctx.command}': {error}")
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

        await super().on_command_error(ctx, error)


# Main execution block
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