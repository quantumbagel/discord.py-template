import discord
from discord import app_commands
from discord.ext import commands


# All cogs are classes that inherit from commands.Cog
class Echo(commands.Cog):
    def __init__(self, bot: commands.Bot):
        """Initializes the cog and gets the bot instance."""
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        """A listener that prints a message when the cog is ready."""
        print("📣 Echo Cog has been loaded successfully.")

    # --- PREFIX COMMAND ---
    # The '*' in the argument list gathers all text after the command into a single string.
    # We add an alias 'say' so the command can be invoked with !echo or !say.
    @commands.command(name='echo', aliases=['say'])
    @commands.has_permissions(manage_messages=True)  # Permission check
    async def echo_prefix(self, ctx: commands.Context, *, message: str):
        """
        Repeats a message you provide.
        Requires "Manage Messages" permission.

        Example: !echo Hello, world!
        """
        # Delete the user's command message to make it appear as if the bot said it.
        # This is optional and requires the "Manage Messages" permission.
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            # The bot might not have permission to delete messages in some channels.
            print(f"Could not delete message in #{ctx.channel.name}, insufficient permissions.")

        await ctx.send(message)

    # --- SLASH COMMAND ---
    # A modern slash command for the same functionality.
    @app_commands.command(name="echo", description="Makes the bot say something.")
    @app_commands.describe(message="The message you want the bot to repeat.")
    @app_commands.default_permissions(manage_messages=True)  # Permission check
    async def echo_slash(self, interaction: discord.Interaction, message: str):
        """Slash command to repeat a message."""
        # For a slash command echo, the best UX is often to send a hidden confirmation
        # and then send the actual message publicly in the channel.
        await interaction.response.send_message("Echoing your message...", ephemeral=True, delete_after=5.0)
        await interaction.channel.send(message)

    # --- ERROR HANDLING ---
    # A local error handler for this cog's commands.
    @echo_prefix.error
    async def echo_prefix_error(self, ctx: commands.Context, error):
        """Handles errors for the !echo prefix command."""
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("Sorry, you don't have the `Manage Messages` permission to use this command.",
                           delete_after=10)
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("You need to provide a message for me to echo!", delete_after=10)
        else:
            # For other errors, you might want to log them
            print(f"An error occurred in the echo command: {error}")


async def setup(bot):
    await bot.add_cog(Echo(bot))