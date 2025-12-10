import discord
from discord import app_commands
from discord.ext import commands
import time

from cogs.base import CogTemplate, ImprovedCog
from utilities.embeds import user_info_embed, server_info_embed, info_embed, custom_embed


class General(ImprovedCog):
    template = CogTemplate(
        name="general",
        description="General utility commands for users and servers.",
        category="Utilities",
        version="1.0.0",
        authors=["quantumbagel"],
        emoji="ℹ️"
    )

    @app_commands.command(name="ping", description="Check the bot's latency.")
    async def ping(self, interaction: discord.Interaction):
        start_time = time.time()
        # Send a temporary message to calculate round-trip time
        await interaction.response.send_message("Pinging...", ephemeral=True)
        end_time = time.time()

        api_latency = round(self.bot.latency * 1000)
        round_trip = round((end_time - start_time) * 1000)

        embed = info_embed(
            title="Pong! 🏓",
            description=f"**API Latency:** `{api_latency}ms`\n**Round Trip:** `{round_trip}ms`"
        )

        await interaction.edit_original_response(content=None, embed=embed)

    @app_commands.command(name="userinfo", description="Get information about a user.")
    @app_commands.describe(user="The user to get information for (defaults to you).")
    async def userinfo(self, interaction: discord.Interaction, user: discord.Member = None):
        target_user = user or interaction.user
        # Use the helper function from utilities.embeds
        embed = user_info_embed(target_user)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="serverinfo", description="Get information about this server.")
    async def serverinfo(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        # Use the helper function from utilities.embeds
        embed = server_info_embed(interaction.guild)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="avatar", description="Get a user's avatar.")
    @app_commands.describe(user="The user to get the avatar for.")
    async def avatar(self, interaction: discord.Interaction, user: discord.Member = None):
        target_user = user or interaction.user

        embed = custom_embed() \
            .set_title(f"Avatar for {target_user.display_name}") \
            .set_image(target_user.display_avatar.url) \
            .set_color(target_user.color) \
            .set_footer(f"Requested by {interaction.user.display_name}")

        await interaction.response.send_message(embed=embed.build())