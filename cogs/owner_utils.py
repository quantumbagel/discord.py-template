import discord
from discord.ext import commands
from typing import Literal, Optional
import math

from cogs.base import BagelCog, CogTemplate


class Management(BagelCog):
    """
    A cog for bot management, including listing guilds, emojis,
    managing other cogs, and syncing application commands.
    """

    template = CogTemplate(description="Management", authors=["quantumbagel"], version="1.0.0", name="management")

    # This check ensures that only the bot owner can use these commands.
    async def cog_check(self, ctx: commands.Context) -> bool:
        return await self.bot.is_owner(ctx.author)

    @commands.command(name='emojis', aliases=['listemojis'])
    @commands.guild_only()
    async def list_emojis(self, ctx: commands.Context):
        """Lists all custom emojis the bot has access to."""
        emojis = sorted(await self.bot.fetch_application_emojis(), key=lambda e: e.name)
        if not emojis:
            await ctx.send("I don't have access to any custom emojis.")
            return

        items_per_page = 20
        pages = math.ceil(len(emojis) / items_per_page)
        current_page = 1

        def get_embed(page_num):
            start_index = (page_num - 1) * items_per_page
            end_index = start_index + items_per_page
            emoji_slice = emojis[start_index:end_index]

            description = "\n".join([f"{e} `:{e.name}:` (ID: {e.id})" for e in emoji_slice])

            embed = discord.Embed(
                title="Custom Emojis",
                description=description,
                color=discord.Color.blue()
            )
            embed.set_footer(text=f"Page {page_num}/{pages}")
            return embed

        message = await ctx.send(embed=get_embed(current_page))

        if pages <= 1:
            return

        await message.add_reaction("◀️")
        await message.add_reaction("▶️")

        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ["◀️", "▶️"] and reaction.message.id == message.id

        while True:
            try:
                reaction, user = await self.bot.wait_for("reaction_add", timeout=60.0, check=check)

                if str(reaction.emoji) == "▶️" and current_page < pages:
                    current_page += 1
                elif str(reaction.emoji) == "◀️" and current_page > 1:
                    current_page -= 1

                await message.edit(embed=get_embed(current_page))
                await message.remove_reaction(reaction, user)

            except TimeoutError:
                await message.clear_reactions()
                break

    @commands.command(name='guilds', aliases=['servers'])
    async def list_guilds(self, ctx: commands.Context):
        """Lists all guilds the bot is a member of."""
        guilds = sorted(self.bot.guilds, key=lambda g: g.member_count, reverse=True)

        if not guilds:
            await ctx.send("I am not in any guilds.")
            return

        description_lines = [f"**{g.name}** (ID: {g.id}) - {g.member_count} members" for g in guilds]

        items_per_page = 10
        pages = math.ceil(len(description_lines) / items_per_page)

        for i in range(pages):
            start = i * items_per_page
            end = start + items_per_page
            page_content = "\n".join(description_lines[start:end])

            embed = discord.Embed(
                title=f"Guilds ({len(guilds)} total)",
                description=page_content,
                color=discord.Color.green()
            )
            embed.set_footer(text=f"Page {i + 1}/{pages}")
            await ctx.send(embed=embed)

    # --- CORRECTED COG MANAGEMENT COMMANDS ---
    @commands.group(name='cog', invoke_without_command=True)
    async def cog(self, ctx: commands.Context):
        """Base command for managing cogs."""
        await ctx.send_help(ctx.command)

    @cog.command(name='load')
    async def load_cog(self, ctx: commands.Context, *, cog_name: str):
        """Loads a cog."""
        try:
            await self.bot.load_extension(f"cogs.{cog_name}")
            await ctx.send(f"✅ Successfully loaded the `{cog_name}` cog.")
        except commands.ExtensionAlreadyLoaded:
            await ctx.send(f"⚠️ The `{cog_name}` cog is already loaded.")
        except commands.ExtensionNotFound:
            await ctx.send(f"❌ Could not find the `{cog_name}` cog.")
        except Exception as e:
            await ctx.send(f"An error occurred while loading `{cog_name}`: ```py\n{e}\n```")

    @cog.command(name='unload')
    async def unload_cog(self, ctx: commands.Context, *, cog_name: str):
        """Unloads a cog."""
        if cog_name.lower() == 'management':
            await ctx.send("❌ You cannot unload the management cog.")
            return
        try:
            await self.bot.unload_extension(f"cogs.{cog_name}")
            await ctx.send(f"✅ Successfully unloaded the `{cog_name}` cog.")
        except commands.ExtensionNotLoaded:
            await ctx.send(f"⚠️ The `{cog_name}` cog is not loaded.")
        except Exception as e:
            await ctx.send(f"An error occurred while unloading `{cog_name}`: ```py\n{e}\n```")

    @cog.command(name='reload')
    async def reload_cog(self, ctx: commands.Context, *, cog_name: str):
        """Reloads a cog."""
        try:
            await self.bot.reload_extension(f"cogs.{cog_name}")
            await ctx.send(f"✅ Successfully reloaded the `{cog_name}` cog.")
        except commands.ExtensionNotLoaded:
            await ctx.send(f"⚠️ The `{cog_name}` cog is not loaded. Use `!cog load {cog_name}` first.")
        except commands.ExtensionNotFound:
            await ctx.send(f"❌ Could not find the `{cog_name}` cog.")
        except Exception as e:
            await ctx.send(f"An error occurred while reloading `{cog_name}`: ```py\n{e}\n```")

    # --- END OF COG MANAGEMENT COMMANDS ---

    @commands.command()
    @commands.guild_only()
    async def sync(self, ctx: commands.Context, guilds: commands.Greedy[discord.Object],
                   spec: Optional[Literal["~", "*", "clear"]] = None) -> None:
        """
        Syncs application (slash) commands to Discord.

        Usage:
        `!sync` -> Syncs to the current guild.
        `!sync ~` -> Syncs to the current guild.
        `!sync *` -> Syncs globally to all guilds.
        `!sync <guild_id>` -> Syncs to a specific guild.
        `!sync clear` -> Clears commands from the current guild.
        `!sync * clear` -> Clears all global commands.
        """
        if not guilds:
            if spec == "~":
                synced = await self.bot.tree.sync(guild=ctx.guild)
            elif spec == "*":
                synced = await self.bot.tree.sync()
            elif spec == "clear":
                self.bot.tree.clear_commands(guild=ctx.guild)
                await self.bot.tree.sync(guild=ctx.guild)
                synced = []
            else:
                synced = await self.bot.tree.sync(guild=ctx.guild)

            scope = "to the current guild" if spec == "~" or spec is None else "globally"
            status = "Cleared" if spec == "clear" else "Synced"
            await ctx.send(f"{status} {len(synced)} commands {scope}.")
            return

        ret = 0
        for guild in guilds:
            try:
                await self.bot.tree.sync(guild=guild)
            except discord.HTTPException:
                pass
            else:
                ret += 1

        await ctx.send(f"Synced the tree to {ret}/{len(guilds)} guilds.")