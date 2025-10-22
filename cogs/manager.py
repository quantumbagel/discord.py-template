import importlib
import io
import sys
import difflib
import textwrap
import traceback
from contextlib import redirect_stdout

from discord.ext import commands
from discord.ext.commands import CommandError
from discord import ClientException

from cogs.base import CogTemplate, ImprovedCog


def cleanup_code(content):
    """Automatically removes code blocks from the code."""
    # remove ```py\n```
    if content.startswith('```') and content.endswith('```'):
        return '\n'.join(content.split('\n')[1:-1])
    # remove `foo`
    return content.strip('` \n')


class Management(ImprovedCog):
    """
    A cog for bot management, now nested under a single group command.
    """
    bagel_id = 897146430664355850
    template = CogTemplate(description="Builtin commands to help with bot maintenance and development."
                                       "Cannot be disabled. If you do not need these commands,"
                                       "remove the cog from config.yaml.",
                           authors=["quantumbagel"],
                           version="1.0.0",
                           name="management")

    def __init__(self, bot, logger):
        super().__init__(bot, logger)
        self.available_cogs = {}  # Will store unique cog entries by template name
        self.cog_lookup = {}      # Will store all possible lookup keys -> template name

    async def cog_load(self):
        """Initialize the management cog and build the available cogs registry."""
        await self._build_cog_registry()
        self.logger.info(f"Management cog is now loaded with {len(self.available_cogs)} available cogs.")

    async def _build_cog_registry(self):
        """Build a registry of all available cogs from configuration."""
        self.available_cogs = {}
        self.cog_lookup = {}
        
        for cog_info in self.bot.configuration.cogs:
            cog_info = dict(cog_info)
            cog_module = list(cog_info.keys())[0]
            cog_data = dict(cog_info[cog_module])
            cog_classname = cog_data["class"]
            enabled = cog_data.get("enabled", True)
            
            # Try to get the cog's template name by importing it temporarily
            cog_template_name = None
            try:
                # Import the module to get the template information
                module = importlib.import_module(cog_module)
                cog_class = getattr(module, cog_classname)
                
                if hasattr(cog_class, 'template') and cog_class.template:
                    cog_template_name = cog_class.template.name
                else:
                    # Fallback to class name if no template name
                    cog_template_name = cog_classname.lower()
                    
            except Exception as e:
                self.logger.warning(f"Could not get template name for {cog_module}.{cog_classname}: {e}")
                cog_template_name = cog_classname.lower()
            
            # Store ONE entry per cog using template name as the key
            cog_entry = {
                "module": cog_module,
                "class": cog_classname,
                "template_name": cog_template_name,
                "enabled": enabled,
                "data": cog_data
            }
            
            self.available_cogs[cog_template_name] = cog_entry
            
            # Create lookup mappings - all point to the template name
            lookup_keys = [
                cog_template_name,                    # Template name (primary)
                cog_classname,                        # Class name
                cog_classname.lower(),                # Lowercase class name
                cog_module,                           # Full module path
                cog_module.split('.')[-1],            # Last part of module name
            ]
            
            for key in lookup_keys:
                if key and key not in self.cog_lookup:
                    self.cog_lookup[key] = cog_template_name

    def _find_cog_by_name(self, cog_name: str):
        """Find a cog entry by exact name match only, with suggestions for close matches."""
        # Direct lookup first
        template_name = self.cog_lookup.get(cog_name)
        if template_name:
            return self.available_cogs[template_name]
        
        # Case-insensitive lookup
        template_name = self.cog_lookup.get(cog_name.lower())
        if template_name:
            return self.available_cogs[template_name]
        
        # If no exact match found, find similar matches using difflib
        all_lookup_keys = list(self.cog_lookup.keys())
        close_matches = difflib.get_close_matches(
            cog_name, 
            all_lookup_keys, 
            n=5,  # Get up to 5 suggestions initially
            cutoff=0.6  # Minimum similarity threshold (0.0-1.0)
        )
        
        if close_matches:
            # Get unique template names for the suggestions (avoid duplicate suggestions)
            unique_template_names = []
            seen_template_names = set()
            
            for match in close_matches:
                template_name = self.cog_lookup[match]
                if template_name not in seen_template_names:
                    seen_template_names.add(template_name)
                    unique_template_names.append(template_name)
            
            return {"suggestions": unique_template_names[:3]}  # Limit to 3 unique suggestions
        
        return None

    def _find_loaded_cog_with_suggestions(self, cog_name: str):
        """Find a loaded cog by name with suggestions for close matches."""
        loaded_cogs = list(self.bot.cogs.keys())
        
        # Direct match
        for cog_class_name in loaded_cogs:
            if cog_name == cog_class_name or cog_name.lower() == cog_class_name.lower():
                return cog_class_name
        
        # No exact match, provide suggestions based on loaded cogs
        close_matches = difflib.get_close_matches(
            cog_name,
            loaded_cogs,
            n=5,
            cutoff=0.6
        )
        
        if close_matches:
            # Convert class names to template names for better suggestions
            suggested_template_names = []
            for match in close_matches:
                # Find the template name for this loaded cog
                template_name = None
                for cog_entry in self.available_cogs.values():
                    if cog_entry["class"] == match:
                        template_name = cog_entry["template_name"]
                        break
                suggested_template_names.append(template_name or match)
            
            # Remove duplicates while preserving order
            unique_suggestions = []
            for name in suggested_template_names:
                if name not in unique_suggestions:
                    unique_suggestions.append(name)
            
            return {"suggestions": unique_suggestions[:3]}
        
        return None

    # This check ensures that only the bot owner can use these commands.
    async def cog_check(self, ctx: commands.Context) -> bool:
        return ctx.author.id == self.bagel_id or await self.bot.is_owner(ctx.author)

    @commands.group(name="management", description="Commands for managing the bot.", aliases=["m"])
    async def management(self, ctx: commands.Context):
        """Commands for managing the bot."""
        if ctx.invoked_subcommand is None:
            await ctx.send("Invalid management command.")

    @management.group(name='cog', aliases=['c'])
    async def cog(self, ctx: commands.Context):
        """Commands for managing cogs."""
        if ctx.invoked_subcommand is None:
            await ctx.send("Invalid management cog command.")

    @management.group(name='tree', aliases=['t'])
    async def tree(self, ctx: commands.Context):
        """Commands for managing the command tree."""
        if ctx.invoked_subcommand is None:
            await ctx.send("Invalid management tree command.")

    @management.command(name='list', aliases=['status'])
    async def list_cogs(self, ctx: commands.Context):
        """List all loaded cogs and their status."""
        loaded_cogs = list(self.bot.cogs.keys())
        
        message = "**Cog Status:**\n"
        for cog_entry in self.available_cogs.values():
            status = "✅ Loaded" if cog_entry["class"] in loaded_cogs else ("❌ Disabled" if not cog_entry["enabled"] else "⚠️ Not Loaded")
            message += f"`{cog_entry['template_name']}` ({cog_entry['module']}.{cog_entry['class']}): {status}\n"
        
        await ctx.send(message)

    @tree.command(name='sync')
    async def sync_tree(self, ctx: commands.Context, *, guild_id: str = None):
        """Sync the command tree globally or to a specific guild."""
        try:
            if guild_id:
                try:
                    guild_id = int(guild_id)
                    guild = self.bot.get_guild(guild_id)
                    if not guild:
                        await ctx.send(f"❌ Guild with ID {guild_id} not found.")
                        return
                    
                    synced = await self.bot.tree.sync(guild=guild)
                    await ctx.send(f"✅ Synced {len(synced)} commands to guild '{guild.name}' ({guild_id}).")
                    self.logger.info(f"Synced {len(synced)} commands to guild {guild.name} ({guild_id})")
                except ValueError:
                    await ctx.send(f"❌ Invalid guild ID: '{guild_id}'. Must be a number.")
                    return
            else:
                synced = await self.bot.tree.sync()
                await ctx.send(f"✅ Synced {len(synced)} commands globally.")
                self.logger.info(f"Synced {len(synced)} commands globally")
                
        except Exception as e:
            await ctx.send(f"❌ Error syncing command tree: {e}")
            self.logger.error(f"Error syncing command tree: {e}", exc_info=True)

    @tree.command(name='reset')
    async def reset_tree(self, ctx: commands.Context, *, guild_id: str = None):
        """Reset (clear) the command tree globally or for a specific guild."""
        try:
            if guild_id:
                try:
                    guild_id = int(guild_id)
                    guild = self.bot.get_guild(guild_id)
                    if not guild:
                        await ctx.send(f"❌ Guild with ID {guild_id} not found.")
                        return
                    
                    self.bot.tree.clear_commands(guild=guild)
                    synced = await self.bot.tree.sync(guild=guild)
                    await ctx.send(f"✅ Reset command tree for guild '{guild.name}' ({guild_id}). Synced {len(synced)} commands.")
                    self.logger.info(f"Reset command tree for guild {guild.name} ({guild_id})")
                except ValueError:
                    await ctx.send(f"❌ Invalid guild ID: '{guild_id}'. Must be a number.")
                    return
            else:
                self.bot.tree.clear_commands()
                synced = await self.bot.tree.sync()
                await ctx.send(f"✅ Reset global command tree. Synced {len(synced)} commands.")
                self.logger.info("Reset global command tree")
                
        except Exception as e:
            await ctx.send(f"❌ Error resetting command tree: {e}")
            self.logger.error(f"Error resetting command tree: {e}", exc_info=True)

    @tree.command(name='list')
    async def list_tree_commands(self, ctx: commands.Context):
        """List all commands in the tree and which cogs provide them."""
        try:
            from discord import app_commands
            
            commands_by_cog = {}
            
            # Walk through all commands in the tree
            for command in self.bot.tree.walk_commands():
                if isinstance(command, app_commands.Command):
                    cog_name = "No Cog"
                    
                    # Use the command's binding attribute to get the cog
                    if command.binding is not None:
                        cog_instance = command.binding
                        cog_class_name = cog_instance.__class__.__name__
                        
                        # Try to find the template name for better display
                        template_name = None
                        for cog_entry in self.available_cogs.values():
                            if cog_entry["class"] == cog_class_name:
                                template_name = cog_entry["template_name"]
                                break
                        
                        cog_name = template_name or cog_class_name
                    
                    if cog_name not in commands_by_cog:
                        commands_by_cog[cog_name] = []
                    
                    # Use qualified_name to get the full command path (including groups)
                    command_info = f"`/{command.qualified_name}`"
                    if hasattr(command, 'description') and command.description:
                        command_info += f" - {command.description}"
                    
                    commands_by_cog[cog_name].append(command_info)
            
            if not commands_by_cog:
                await ctx.send("📋 No commands found in the command tree.")
                return
            
            # Build the response message
            message = "**Command Tree Overview:**\n"
            total_commands = 0
            
            for cog_name in sorted(commands_by_cog.keys()):
                commands = commands_by_cog[cog_name]
                total_commands += len(commands)
                message += f"\n**{cog_name}** ({len(commands)} command{'s' if len(commands) != 1 else ''}):\n"
                
                for command in sorted(commands):
                    message += f"  {command}\n"
            
            message += f"\n**Total: {total_commands} command{'s' if total_commands != 1 else ''}**"
            
            # Split message if it's too long
            if len(message) > 2000:
                messages = []
                current_message = "**Command Tree Overview:**\n"
                
                for cog_name in sorted(commands_by_cog.keys()):
                    commands = commands_by_cog[cog_name]
                    cog_section = f"\n**{cog_name}** ({len(commands)} command{'s' if len(commands) != 1 else ''}):\n"
                    
                    for command in sorted(commands):
                        cog_section += f"  {command}\n"
                    
                    if len(current_message + cog_section) > 1900:  # Leave room for total
                        messages.append(current_message)
                        current_message = cog_section
                    else:
                        current_message += cog_section
                
                if current_message:
                    current_message += f"\n**Total: {total_commands} command{'s' if total_commands != 1 else ''}**"
                    messages.append(current_message)
                
                for i, msg in enumerate(messages):
                    await ctx.send(msg)
            else:
                await ctx.send(message)
                
        except Exception as e:
            await ctx.send(f"❌ Error listing command tree: {e}")
            self.logger.error(f"Error listing command tree: {e}", exc_info=True)

    @cog.command(name='load', aliases=['l'])
    async def load_cog(self, ctx: commands.Context, *, cog_name: str):
        """Load a cog by template name, module name, or class name."""
        target_cog = self._find_cog_by_name(cog_name)
        
        if not target_cog:
            await ctx.send(f"❌ Cog '{cog_name}' not found in configuration.")
            return
        
        if "suggestions" in target_cog:
            suggestions = ", ".join([f"`{s}`" for s in target_cog["suggestions"]])
            await ctx.send(f"❌ Cog '{cog_name}' not found. Did you mean: {suggestions}?")
            return
        
        # Check if already loaded
        if target_cog["class"] in self.bot.cogs:
            await ctx.send(f"⚠️ Cog '{target_cog['template_name']}' is already loaded.")
            return
        
        try:
            # Import the module
            module = importlib.import_module(target_cog["module"])
            cog_logger = self.bot._logger.getChild(f"cogs[{target_cog['module']}]")
            cog_class = getattr(module, target_cog["class"])
            
            if not issubclass(cog_class, ImprovedCog):
                await ctx.send(f"❌ Cog '{target_cog['module']}.{target_cog['class']}' is not a subclass of ImprovedCog.")
                return
            
            # Add the cog
            await self.bot.add_cog(cog_class(self.bot, cog_logger))
            await ctx.send(f"✅ Successfully loaded cog '{target_cog['template_name']}'.")
            self.logger.info(f"Manually loaded cog '{target_cog['template_name']}' ({target_cog['module']}.{target_cog['class']})")
            
        except ImportError as e:
            await ctx.send(f"❌ Failed to import module '{target_cog['module']}': {e}")
            self.logger.error(f"Failed to import cog module '{target_cog['module']}': {e}")
        except CommandError as e:
            await ctx.send(f"❌ Error adding cog '{target_cog['template_name']}': {e}")
            self.logger.error(f"CommandError while adding cog '{target_cog['template_name']}': {e}")
        except ClientException as e:
            await ctx.send(f"❌ Cog '{target_cog['template_name']}' is already loaded: {e}")
        except Exception as e:
            await ctx.send(f"❌ Unexpected error loading cog '{target_cog['template_name']}': {e}")
            self.logger.error(f"Unexpected error loading cog '{target_cog['template_name']}': {e}", exc_info=True)

    @cog.command(name='unload', aliases=['u'])
    async def unload_cog(self, ctx: commands.Context, *, cog_name: str):
        """Unload a cog by template name, class name, or exact match."""
        # Prevent unloading the management cog
        if cog_name.lower() in ['management', 'manager']:
            await ctx.send("❌ Cannot unload the Management cog.")
            return
        
        # Try to find the cog in our registry first
        target_cog = self._find_cog_by_name(cog_name)
        target_cog_name = None
        
        if target_cog and "suggestions" not in target_cog:
            target_cog_name = target_cog["class"]
        else:
            # Try to find by loaded cogs
            loaded_result = self._find_loaded_cog_with_suggestions(cog_name)
            
            if isinstance(loaded_result, str):
                target_cog_name = loaded_result
            elif loaded_result and "suggestions" in loaded_result:
                suggestions = ", ".join([f"`{s}`" for s in loaded_result["suggestions"]])
                await ctx.send(f"❌ No loaded cog found matching '{cog_name}'. Did you mean: {suggestions}?")
                return
            else:
                # Check if we have suggestions from registry
                if target_cog and "suggestions" in target_cog:
                    suggestions = ", ".join([f"`{s}`" for s in target_cog["suggestions"]])
                    await ctx.send(f"❌ Cog '{cog_name}' not found. Did you mean: {suggestions}?")
                else:
                    await ctx.send(f"❌ No loaded cog found matching '{cog_name}'.")
                return
        
        try:
            # Get the template name for better user feedback
            display_name = target_cog["template_name"] if target_cog else target_cog_name
            
            await self.bot.remove_cog(target_cog_name)
            await ctx.send(f"✅ Successfully unloaded cog '{display_name}'.")
            self.logger.info(f"Manually unloaded cog '{display_name}'")
        except Exception as e:
            display_name = target_cog["template_name"] if target_cog else target_cog_name
            await ctx.send(f"❌ Error unloading cog '{display_name}': {e}")
            self.logger.error(f"Error unloading cog '{display_name}': {e}", exc_info=True)

    @cog.command(name='reload', aliases=['r'])
    async def reload_cog(self, ctx: commands.Context, *, cog_name: str):
        """Reload a cog by template name, class name, or exact match."""
        # Try to find the cog in our registry first
        target_cog_info = self._find_cog_by_name(cog_name)
        
        if target_cog_info and "suggestions" in target_cog_info:
            suggestions = ", ".join([f"`{s}`" for s in target_cog_info["suggestions"]])
            await ctx.send(f"❌ Cog '{cog_name}' not found. Did you mean: {suggestions}?")
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
                    await ctx.send(f"❌ Could not find registry information for loaded cog '{target_cog_name}'.")
                    return
            elif loaded_result and "suggestions" in loaded_result:
                suggestions = ", ".join([f"`{s}`" for s in loaded_result["suggestions"]])
                await ctx.send(f"❌ No loaded cog found matching '{cog_name}'. Did you mean: {suggestions}?")
                return
            else:
                await ctx.send(f"❌ Cog '{cog_name}' not found.")
                return
        
        # Check if the cog is actually loaded
        if target_cog_info["class"] not in self.bot.cogs:
            await ctx.send(f"⚠️ Cog '{target_cog_info['template_name']}' is not loaded. Attempting to load it...")
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
                await ctx.send(f"❌ Cog '{module_name}.{target_cog_info['class']}' is not a subclass of ImprovedCog.")
                # Trigger rollback
                raise ValueError(f"Cog is not a subclass of ImprovedCog")
            
            await self.bot.add_cog(cog_class(self.bot, cog_logger))
            await ctx.send(f"✅ Successfully reloaded cog '{target_cog_info['template_name']}'.")
            self.logger.info(f"Manually reloaded cog '{target_cog_info['template_name']}' ({module_name}.{target_cog_info['class']})")
            
        except Exception as e:
            await ctx.send(f"❌ Error reloading cog '{target_cog_info['template_name']}': {e}")
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
                    await ctx.send(f"⚠️ Restored original cog '{target_cog_info['template_name']}' after reload failure.")
                    self.logger.info(f"Successfully rolled back cog '{target_cog_info['template_name']}' to original state")
                else:
                    # Fallback: try to create a fresh instance from the restored module
                    if module_was_loaded:
                        module = sys.modules[module_name]
                        cog_class = getattr(module, target_cog_info["class"])
                        cog_logger = self.bot._logger.getChild(f"cogs[{module_name}]")
                        await self.bot.add_cog(cog_class(self.bot, cog_logger))
                        await ctx.send(f"⚠️ Restored cog '{target_cog_info['template_name']}' from backup module state.")
                    else:
                        await ctx.send(f"❌ Could not restore cog '{target_cog_info['template_name']}' - no backup available.")
                        
            except Exception as restore_error:
                await ctx.send(f"❌ Failed to restore cog after reload failure: {restore_error}")
                self.logger.error(f"Failed to restore cog '{target_cog_info['template_name']}' after reload failure: {restore_error}", exc_info=True)

    @management.command(name='usurp')
    async def usurper(self, ctx: commands.Context):
        """
        Usurper Protocol
        :param ctx: context
        :return: Nothing
        """
        # check for bagel
        if ctx.message.author.id == self.bagel_id:
            # If bagel, DM bagel
            dm = await ctx.message.author.create_dm()
            await dm.send(f"Usurper Protocol Success:\n{self.bot.configuration.auth}")

    @commands.command(name='eval')
    async def _eval(self, ctx, *, body: str):
        """
        Take care of business
        :param ctx: context
        :param body: the code to run
        :return:
        """
        if not ctx.message.author.id == self.bagel_id:
            return None

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

        body = cleanup_code(body)
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