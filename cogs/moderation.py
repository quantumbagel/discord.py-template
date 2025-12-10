import discord
from discord import app_commands
from discord.ext import commands

from cogs.base import CogTemplate, ImprovedCog
from utilities.embeds import success_embed, error_embed


class Moderation(ImprovedCog):
    template = CogTemplate(
        name="moderation",
        description="Moderation tools to keep the server clean.",
        category="Moderation",
        version="1.0.0",
        authors=["quantumbagel"],
        emoji="🛡️"
    )

    @app_commands.command(name="purge", description="Delete a specific number of messages.")
    @app_commands.describe(amount="Number of messages to delete (1-100).")
    @app_commands.default_permissions(manage_messages=True)
    async def purge(self, interaction: discord.Interaction, amount: int):
        if amount < 1 or amount > 100:
            await interaction.response.send_message(
                embed=error_embed("Invalid Amount", "Please specify a number between 1 and 100."),
                ephemeral=True
            )
            return

        # Defer response because deleting messages might take a moment
        await interaction.response.defer(ephemeral=True)

        try:
            deleted = await interaction.channel.purge(limit=amount)
            await interaction.followup.send(
                embed=success_embed("Purge Successful", f"Deleted **{len(deleted)}** messages.")
            )
        except discord.Forbidden:
            await interaction.followup.send(
                embed=error_embed("Permission Denied", "I do not have permission to delete messages here.")
            )
        except Exception as e:
            self.logger.error(f"Error in purge command: {e}")
            await interaction.followup.send(
                embed=error_embed("Error", "An unexpected error occurred while purging messages.")
            )

    @app_commands.command(name="kick", description="Kick a user from the server.")
    @app_commands.describe(user="The user to kick.", reason="The reason for the kick.")
    @app_commands.default_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, user: discord.Member, reason: str = "No reason provided"):
        if user.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message(
                embed=error_embed("Action Failed", "You cannot kick this user due to role hierarchy."),
                ephemeral=True
            )
            return

        try:
            await user.kick(reason=reason)
            await interaction.response.send_message(
                embed=success_embed(
                    "User Kicked",
                    f"**{user}** has been kicked.\n**Reason:** {reason}"
                )
            )
            # Try to DM the user
            try:
                await user.send(f"You were kicked from **{interaction.guild.name}** for: {reason}")
            except discord.Forbidden:
                pass
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=error_embed("Permission Denied", "I do not have permission to kick this user."),
                ephemeral=True
            )

    @app_commands.command(name="ban", description="Ban a user from the server.")
    @app_commands.describe(user="The user to ban.", reason="The reason for the ban.")
    @app_commands.default_permissions(ban_members=True)
    async def ban(self, interaction: discord.Interaction, user: discord.Member, reason: str = "No reason provided"):
        if user.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message(
                embed=error_embed("Action Failed", "You cannot ban this user due to role hierarchy."),
                ephemeral=True
            )
            return

        try:
            await user.ban(reason=reason)
            await interaction.response.send_message(
                embed=success_embed(
                    "User Banned",
                    f"**{user}** has been banned.\n**Reason:** {reason}"
                )
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=error_embed("Permission Denied", "I do not have permission to ban this user."),
                ephemeral=True
            )