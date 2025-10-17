import discord
from discord import app_commands
from discord.ext import commands

from cogs.base import CogTemplate, ImprovedCog


# All cogs are classes that inherit from ImprovedCog
class Echo(ImprovedCog):
    template = CogTemplate(description="Echo", authors=["quantumbagel"], version="1.0.0", name="echo")

    @commands.Cog.listener()
    async def on_ready(self):
        self.logger.info("Echo Cog has been loaded successfully.")

    @app_commands.command(name="echo", description="Makes the bot say something.")
    @app_commands.describe(message="The message you want the bot to repeat.")
    @app_commands.default_permissions(manage_messages=True)  # Permission check
    async def echo_slash(self, interaction: discord.Interaction, message: str):
        self.logger.info(f"Echoing message {message}")
        await interaction.response.send_message("Echoing your message...", ephemeral=True, delete_after=5.0)
        await interaction.channel.send(message)
