from discord.ext import commands

from cogs.base import CogTemplate, ImprovedCog


class Management(ImprovedCog):
    """
    A cog for bot management, now nested under a single group command.
    """
    all_cogs = []
    template = CogTemplate(description="Management", authors=["quantumbagel"], version="1.0.0", name="management")

    async def cog_load(self):
        all_cogs = self.bot.configuration.cogs
        # for cog_info in all_cogs:
        #     cog_data = cog_info.get()
        self.logger.info(f"Management cog is now loaded.")

    # This check ensures that only the bot owner can use these commands.
    async def cog_check(self, ctx: commands.Context) -> bool:
        return await self.bot.is_owner(ctx.author)

    @commands.group(name="management", description="Commands for managing the bot.", aliases=["m"])
    async def management(self, ctx: commands.Context):
        """Commands for managing the bot."""
        raise TypeError("this is a bug that happens randomly for no reason")
        if ctx.invoked_subcommand is None:
            await ctx.send("Invalid management command.")

    @management.group(name='cog', aliases=['c'])
    async def cog(self, ctx: commands.Context):
        """Commands for managing cogs."""
        if ctx.invoked_subcommand is None:
            await ctx.send("Invalid management cog command.")

    @management.command(name='list', aliases=['status'])
    async def list_cogs(self, ctx: commands.Context):
        self.bot.cogs_loaded = list(self.bot.cogs.keys())
