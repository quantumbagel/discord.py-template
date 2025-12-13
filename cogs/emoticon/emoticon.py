"""
Emoticon Analytics Bot - Main Cog

A comprehensive emoji analytics system for Discord servers.
Tracks emoji usage, provides leaderboards, and offers detailed statistics.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Literal

import discord
from discord import app_commands
from discord.ext import commands
from tortoise.functions import Count, Sum
from tortoise.expressions import Q

from cogs.base import CogTemplate, ImprovedCog
from utilities.embeds import custom_embed, success_embed, error_embed, info_embed, loading_embed

# Local imports
from .models import (
    EmojiUsage, EmoticonConfig, EmojiFilter, Dataset, ComponentSettings, ScanProgress,
    TrackingMode, ThreadPolicy, ScanScope, ComponentTarget
)
from .query_parser import QueryParser, ParsedQuery
from .permissions import PermissionFilter
from .renderer import Renderer, RenderSettings, merge_settings
from .extractor import EmojiExtractor, ExtractedEmoji


class LeaderboardPaginatorView(discord.ui.View):
    """Pagination view for leaderboards."""

    def __init__(
        self,
        entries: list[dict],
        total: int,
        leaderboard_type: str,
        title: str,
        renderer: 'Renderer',
        footer: str = "",
        per_page: int = 10,
        timeout: float = 180.0
    ):
        super().__init__(timeout=timeout)
        self.entries = entries
        self.total = total
        self.leaderboard_type = leaderboard_type
        self.title = title
        self.renderer = renderer
        self.footer = footer
        self.per_page = per_page
        self.current_page = 0
        self.max_pages = (len(entries) + per_page - 1) // per_page

        # Disable buttons if only one page
        if self.max_pages <= 1:
            self.previous_button.disabled = True
            self.next_button.disabled = True

    def get_page_entries(self) -> list[dict]:
        """Get entries for the current page."""
        start = self.current_page * self.per_page
        end = start + self.per_page
        return self.entries[start:end]

    def get_embed(self) -> discord.Embed:
        """Build the embed for the current page."""
        page_entries = self.get_page_entries()
        start_rank = self.current_page * self.per_page + 1

        leaderboard_text = self.renderer.render_leaderboard(
            page_entries, self.total, self.leaderboard_type, start_rank
        )

        embed = custom_embed() \
            .set_title(self.title) \
            .set_description(leaderboard_text) \
            .set_timestamp()

        # Add page info and footer
        page_info = f"Page {self.current_page + 1}/{self.max_pages}"
        if self.footer:
            embed.set_footer(f"{page_info} | {self.footer}")
        else:
            embed.set_footer(page_info)

        return embed.build()

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
        else:
            self.current_page = self.max_pages - 1  # Wrap to last page

        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < self.max_pages - 1:
            self.current_page += 1
        else:
            self.current_page = 0  # Wrap to first page

        await interaction.response.edit_message(embed=self.get_embed(), view=self)


class Emoticon(ImprovedCog):
    """
    Emoticon Analytics Bot - Track and analyze emoji usage across your server.

    Features:
    - Real-time emoji tracking in messages and reactions
    - Privacy-aware data filtering based on channel permissions
    - Powerful query syntax for filtering and customization
    - Leaderboards for emojis, users, and engagement density
    - Detailed emoji profiles and comparisons
    """

    template = CogTemplate(
        name="emoticon",
        description="Track and analyze emoji usage across your server.",
        category="Analytics",
        version="1.0.0",
        authors=["quantumbagel"],
        emoji="📊"
    )

    # Command group
    emoticon_group = app_commands.Group(
        name="emoticon",
        description="Emoji analytics commands"
    )

    # Subgroups
    settings_group = app_commands.Group(
        name="settings",
        description="Configure emoji analytics settings",
        parent=emoticon_group
    )

    dataset_group = app_commands.Group(
        name="dataset",
        description="Manage saved channel datasets",
        parent=emoticon_group
    )

    def __init__(self, bot: commands.Bot, logger: logging.Logger):
        super().__init__(bot, logger)
        self._scan_lock = asyncio.Lock()
        self._scan_semaphore = asyncio.Semaphore(5)  # Rate limiting
        self._scan_cancel_flag: dict[int, bool] = {}  # guild_id -> cancel flag

    async def cog_load(self):
        """Called when the cog is loaded."""
        self.logger.info("Emoticon Analytics cog loaded successfully.")

    # ==================== Helper Methods ====================

    async def _get_config(self, guild_id: int) -> EmoticonConfig:
        """Get or create config for a guild."""
        config, _ = await EmoticonConfig.get_or_create(guild_id=guild_id)
        return config

    async def _get_render_settings(
        self,
        guild_id: int,
        target: ComponentTarget,
        runtime_flags: Optional[dict] = None
    ) -> RenderSettings:
        """Get merged render settings for a command."""
        # Get global settings
        global_settings = await ComponentSettings.get_or_none(
            guild_id=guild_id, target=ComponentTarget.GLOBAL
        )

        # Get command-specific settings
        command_settings = await ComponentSettings.get_or_none(
            guild_id=guild_id, target=target
        )

        global_dict = {
            'show_ids': global_settings.show_ids if global_settings else None,
            'show_percentages': global_settings.show_percentages if global_settings else None,
            'compact_mode': global_settings.compact_mode if global_settings else None,
            'tie_grouping': global_settings.tie_grouping if global_settings else None,
        } if global_settings else None

        command_dict = {
            'show_ids': command_settings.show_ids if command_settings else None,
            'show_percentages': command_settings.show_percentages if command_settings else None,
            'compact_mode': command_settings.compact_mode if command_settings else None,
            'tie_grouping': command_settings.tie_grouping if command_settings else None,
        } if command_settings else None

        return merge_settings(global_dict, command_dict, runtime_flags)

    async def _apply_query_filters(
        self,
        query: ParsedQuery,
        guild_id: int,
        user: discord.Member,
        config: EmoticonConfig
    ) -> Q:
        """Build database query filters from a parsed query."""
        # Base filter: guild and exclude user_id=0 (bulk reactions from scan)
        filters = Q(guild_id=guild_id) & Q(user_id__gt=0)

        # Permission-based channel filtering
        perm_filter = PermissionFilter(user.guild, config)

        if query.channels:
            # Filter to specified channels that user can view
            allowed = perm_filter.filter_channels(user, query.channels)
            if allowed:
                filters &= Q(channel_id__in=allowed)
            else:
                # No viewable channels in query, return empty result
                filters &= Q(channel_id=-1)  # Impossible condition
        else:
            # No specific channels, use all viewable
            viewable = perm_filter.get_viewable_channels(user)
            filters &= Q(channel_id__in=viewable)

        # Excluded channels
        if query.excluded_channels:
            filters &= ~Q(channel_id__in=query.excluded_channels)

        # User filters
        if query.users:
            filters &= Q(user_id__in=query.users)
        if query.excluded_users:
            filters &= ~Q(user_id__in=query.excluded_users)

        # Date filters
        if query.date_after:
            filters &= Q(message_timestamp__gte=query.date_after)
        if query.date_before:
            filters &= Q(message_timestamp__lte=query.date_before)

        # Emoji filters
        if query.emojis:
            emoji_q = Q()
            for emoji_name in query.emojis:
                emoji_q |= Q(emoji_name__icontains=emoji_name)
            filters &= emoji_q

        return filters

    async def _should_track_emoji(
        self,
        emoji: ExtractedEmoji,
        config: EmoticonConfig
    ) -> bool:
        """Check if an emoji should be tracked based on config."""
        # Check external emoji setting
        if emoji.is_external and not config.allow_external_emojis:
            return False

        # Check tracking mode
        if config.tracking_mode == TrackingMode.ALL:
            return True

        # Check whitelist/blacklist
        filter_entry = await EmojiFilter.get_or_none(
            guild_id=config.guild_id,
            emoji_name=emoji.emoji_name,
            filter_type=config.tracking_mode
        )

        if config.tracking_mode == TrackingMode.WHITELIST:
            return filter_entry is not None
        else:  # BLACKLIST
            return filter_entry is None

    async def _record_emoji_usage(
        self,
        guild_id: int,
        channel_id: int,
        user_id: int,
        message_id: int,
        emoji: ExtractedEmoji,
        is_reaction: bool = False,
        message_timestamp: Optional[datetime] = None
    ):
        """Record an emoji usage event."""
        await EmojiUsage.create(
            guild_id=guild_id,
            channel_id=channel_id,
            user_id=user_id,
            message_id=message_id,
            emoji_id=emoji.emoji_id,
            emoji_name=emoji.emoji_name,
            emoji_animated=emoji.animated,
            is_external=emoji.is_external,
            is_reaction=is_reaction,
            count=emoji.count,
            message_timestamp=message_timestamp or datetime.now(timezone.utc)
        )

    # ==================== Event Listeners ====================

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Track emoji usage in new messages."""
        if message.author.bot or not message.guild:
            return

        config = await self._get_config(message.guild.id)

        # Check if channel is ignored
        if message.channel.id in config.ignored_channels:
            return
        if message.channel.category_id and message.channel.category_id in config.ignored_categories:
            return

        extractor = EmojiExtractor(message.guild)
        emojis = extractor.extract_from_message(message.content)

        for emoji in emojis:
            if await self._should_track_emoji(emoji, config):
                await self._record_emoji_usage(
                    guild_id=message.guild.id,
                    channel_id=message.channel.id,
                    user_id=message.author.id,
                    message_id=message.id,
                    emoji=emoji,
                    is_reaction=False,
                    message_timestamp=message.created_at
                )

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        """Handle emoji tracking on message edits."""
        if after.author.bot or not after.guild:
            return

        config = await self._get_config(after.guild.id)

        if not config.track_edits:
            return

        # Check if channel is ignored
        if after.channel.id in config.ignored_channels:
            return

        extractor = EmojiExtractor(after.guild)

        before_emojis = {(e.emoji_id, e.emoji_name): e for e in extractor.extract_from_message(before.content)}
        after_emojis = {(e.emoji_id, e.emoji_name): e for e in extractor.extract_from_message(after.content)}

        # Remove old emoji records for this message
        await EmojiUsage.filter(
            guild_id=after.guild.id,
            message_id=after.id,
            is_reaction=False
        ).delete()

        # Add new emoji records
        for emoji in after_emojis.values():
            if await self._should_track_emoji(emoji, config):
                await self._record_emoji_usage(
                    guild_id=after.guild.id,
                    channel_id=after.channel.id,
                    user_id=after.author.id,
                    message_id=after.id,
                    emoji=emoji,
                    is_reaction=False,
                    message_timestamp=after.created_at
                )

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        """Handle emoji tracking on message deletion."""
        if not message.guild:
            return

        config = await self._get_config(message.guild.id)

        if not config.retain_deleted:
            # Remove records for deleted message
            await EmojiUsage.filter(
                guild_id=message.guild.id,
                message_id=message.id
            ).delete()

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        """Track emoji usage in reactions."""
        if user.bot or not reaction.message.guild:
            return

        config = await self._get_config(reaction.message.guild.id)

        # Check if channel is ignored
        if reaction.message.channel.id in config.ignored_channels:
            return

        extractor = EmojiExtractor(reaction.message.guild)
        emoji = extractor.extract_from_reaction(reaction)
        emoji.count = 1  # Single reaction add

        if await self._should_track_emoji(emoji, config):
            await self._record_emoji_usage(
                guild_id=reaction.message.guild.id,
                channel_id=reaction.message.channel.id,
                user_id=user.id,
                message_id=reaction.message.id,
                emoji=emoji,
                is_reaction=True,
                message_timestamp=reaction.message.created_at
            )

    @commands.Cog.listener()
    async def on_reaction_remove(self, reaction: discord.Reaction, user: discord.User):
        """Handle reaction removal tracking."""
        if user.bot or not reaction.message.guild:
            return

        config = await self._get_config(reaction.message.guild.id)

        if not config.retain_deleted:
            extractor = EmojiExtractor(reaction.message.guild)
            emoji = extractor.extract_from_reaction(reaction)

            # Remove one instance of this reaction
            record = await EmojiUsage.filter(
                guild_id=reaction.message.guild.id,
                message_id=reaction.message.id,
                user_id=user.id,
                emoji_name=emoji.emoji_name,
                is_reaction=True
            ).first()

            if record:
                await record.delete()

    # ==================== Scan Commands ====================

    @emoticon_group.command(name="scan", description="Scan channel history for emoji usage. Shows status if scan is running.")
    @app_commands.describe(
        scope="What to scan",
        sync_mode="How to handle existing data",
        dry_run="Simulate scan without saving data"
    )
    @app_commands.default_permissions(manage_guild=True)
    async def scan(
        self,
        interaction: discord.Interaction,
        scope: Literal["current", "server"] = "server",
        sync_mode: Literal["append", "rescan"] = "append",
        dry_run: bool = False
    ):
        """Initiate background indexing of emoji usage. Shows status if scan is already running."""
        # If scan is running, show status instead
        if self._scan_lock.locked() and interaction.guild.id in self._scan_cancel_flag:
            progress = await ScanProgress.get_or_none(guild_id=interaction.guild.id)
            if progress and progress.status == "scanning":
                pct = (progress.scanned_channels / progress.total_channels * 100) if progress.total_channels > 0 else 0
                embed = custom_embed() \
                    .set_title("📊 Scan in Progress") \
                    .set_description(f"Progress: **{pct:.1f}%**\n\nUse `/emoticon stop` to cancel the scan.") \
                    .add_field("Channels", f"{progress.scanned_channels}/{progress.total_channels}", inline=True) \
                    .add_field("Messages", f"{progress.scanned_messages:,}", inline=True) \
                    .add_field("Emojis Found", f"{progress.emojis_found:,}", inline=True) \
                    .set_timestamp()

                await interaction.response.send_message(embed=embed.build(), ephemeral=True)
                return

        await interaction.response.send_message(
            embed=loading_embed("Starting Scan", "Preparing to scan channels..."),
            ephemeral=True
        )

        # Initialize cancel flag for this guild
        self._scan_cancel_flag[interaction.guild.id] = False

        async with self._scan_lock:
            config = await self._get_config(interaction.guild.id)

            # Determine channels to scan
            if scope == "current":
                channels = [interaction.channel]
            else:
                channels = [
                    ch for ch in interaction.guild.text_channels
                    if ch.id not in config.ignored_channels
                    and (not ch.category_id or ch.category_id not in config.ignored_categories)
                ]

            # Initialize progress tracking
            progress, _ = await ScanProgress.get_or_create(guild_id=interaction.guild.id)
            progress.status = "scanning"
            progress.total_channels = len(channels)
            progress.scanned_channels = 0
            progress.total_messages = 0
            progress.scanned_messages = 0
            progress.emojis_found = 0
            progress.started_at = datetime.now(timezone.utc)
            await progress.save()

            # Clear existing data if rescan
            if sync_mode == "rescan" and not dry_run:
                await EmojiUsage.filter(guild_id=interaction.guild.id).delete()

            extractor = EmojiExtractor(interaction.guild)

            # Track last update time for progress updates
            last_update_time = datetime.now(timezone.utc)
            update_interval = 5  # seconds

            async def update_progress_message():
                """Helper to update the progress message."""
                nonlocal last_update_time
                now = datetime.now(timezone.utc)
                if (now - last_update_time).total_seconds() >= update_interval:
                    last_update_time = now
                    pct = (progress.scanned_channels / progress.total_channels * 100) if progress.total_channels > 0 else 0

                    progress_embed = custom_embed() \
                        .set_title("📊 Scanning in Progress...") \
                        .set_description(f"Progress: **{pct:.1f}%**\n\nUse `/emoticon stop` to cancel.") \
                        .add_field("Channels", f"{progress.scanned_channels}/{progress.total_channels}", inline=True) \
                        .add_field("Messages", f"{progress.scanned_messages:,}", inline=True) \
                        .add_field("Emojis Found", f"{progress.emojis_found:,}", inline=True) \
                        .set_timestamp()

                    try:
                        await interaction.edit_original_response(embed=progress_embed.build())
                    except discord.HTTPException:
                        pass  # Ignore edit failures

            try:
                for channel in channels:
                    # Check for cancellation
                    if self._scan_cancel_flag.get(interaction.guild.id, False):
                        progress.status = "cancelled"
                        progress.completed_at = datetime.now(timezone.utc)
                        await progress.save()

                        await interaction.edit_original_response(
                            embed=warning_embed(
                                "⏹️ Scan Cancelled",
                                f"**Channels scanned:** {progress.scanned_channels}/{progress.total_channels}\n"
                                f"**Messages processed:** {progress.scanned_messages:,}\n"
                                f"**Emojis found:** {progress.emojis_found:,}"
                            )
                        )
                        return

                    async with self._scan_semaphore:
                        try:
                            # Get last scanned message ID for append mode
                            after_message = None
                            if sync_mode == "append" and config.last_scan_message_id:
                                try:
                                    after_message = await channel.fetch_message(config.last_scan_message_id)
                                except discord.NotFound:
                                    pass

                            async for message in channel.history(limit=None, after=after_message):
                                # Check for cancellation
                                if self._scan_cancel_flag.get(interaction.guild.id, False):
                                    break

                                if message.author.bot:
                                    continue

                                progress.scanned_messages += 1

                                emojis = extractor.extract_from_message(message.content)

                                for emoji in emojis:
                                    if await self._should_track_emoji(emoji, config):
                                        progress.emojis_found += emoji.count

                                        if not dry_run:
                                            await self._record_emoji_usage(
                                                guild_id=interaction.guild.id,
                                                channel_id=channel.id,
                                                user_id=message.author.id,
                                                message_id=message.id,
                                                emoji=emoji,
                                                is_reaction=False,
                                                message_timestamp=message.created_at
                                            )

                                # Also scan reactions - iterate through users who reacted
                                for reaction in message.reactions:
                                    emoji = extractor.extract_from_reaction(reaction)
                                    emoji.count = 1  # Each user's reaction counts as 1

                                    if await self._should_track_emoji(emoji, config):
                                        if not dry_run:
                                            # Iterate through users who added this reaction
                                            try:
                                                async for user in reaction.users():
                                                    if user.bot:
                                                        continue
                                                    progress.emojis_found += 1
                                                    await self._record_emoji_usage(
                                                        guild_id=interaction.guild.id,
                                                        channel_id=channel.id,
                                                        user_id=user.id,
                                                        message_id=message.id,
                                                        emoji=emoji,
                                                        is_reaction=True,
                                                        message_timestamp=message.created_at
                                                    )
                                            except discord.Forbidden:
                                                # Can't access reaction users, skip
                                                pass
                                        else:
                                            # Dry run - just count
                                            progress.emojis_found += reaction.count

                                # Update progress message periodically
                                await update_progress_message()

                                # Rate limiting
                                await asyncio.sleep(0.01)

                            progress.scanned_channels += 1
                            await progress.save()

                            # Update after each channel completes
                            await update_progress_message()

                        except discord.Forbidden:
                            self.logger.warning(f"No access to channel {channel.name}")
                            continue

                # Check if cancelled during final channel
                if self._scan_cancel_flag.get(interaction.guild.id, False):
                    progress.status = "cancelled"
                    progress.completed_at = datetime.now(timezone.utc)
                    await progress.save()

                    await interaction.edit_original_response(
                        embed=warning_embed(
                            "⏹️ Scan Cancelled",
                            f"**Channels scanned:** {progress.scanned_channels}/{progress.total_channels}\n"
                            f"**Messages processed:** {progress.scanned_messages:,}\n"
                            f"**Emojis found:** {progress.emojis_found:,}"
                        )
                    )
                    return

                progress.status = "completed"
                progress.completed_at = datetime.now(timezone.utc)
                await progress.save()

                # Update config with last scan info
                if not dry_run:
                    config.last_scan_timestamp = datetime.now(timezone.utc)
                    await config.save()

                # Send completion message
                result_type = "✅ Dry Run Complete" if dry_run else "✅ Scan Complete"
                completion_embed = success_embed(
                    result_type,
                    f"**Channels scanned:** {progress.scanned_channels}/{progress.total_channels}\n"
                    f"**Messages processed:** {progress.scanned_messages:,}\n"
                    f"**Emojis found:** {progress.emojis_found:,}"
                )
                await interaction.edit_original_response(embed=completion_embed)

            except Exception as e:
                progress.status = "failed"
                progress.last_error = str(e)
                await progress.save()

                self.logger.error(f"Scan failed: {e}")
                await interaction.edit_original_response(
                    embed=error_embed("Scan Failed", f"An error occurred: {str(e)[:200]}")
                )
            finally:
                # Clean up cancel flag
                self._scan_cancel_flag.pop(interaction.guild.id, None)

    @emoticon_group.command(name="stop", description="Stop the currently running scan.")
    @app_commands.default_permissions(manage_guild=True)
    async def stop_scan(self, interaction: discord.Interaction):
        """Stop a running scan."""
        if not self._scan_lock.locked() or interaction.guild.id not in self._scan_cancel_flag:
            await interaction.response.send_message(
                embed=info_embed("No Active Scan", "There is no scan currently running to stop."),
                ephemeral=True
            )
            return

        # Set cancel flag
        self._scan_cancel_flag[interaction.guild.id] = True

        await interaction.response.send_message(
            embed=warning_embed("Stopping Scan", "The scan will stop after the current operation completes..."),
            ephemeral=True
        )

    @emoticon_group.command(name="status", description="Check the status of an ongoing scan.")
    async def scan_status(self, interaction: discord.Interaction):
        """Check scan progress."""
        progress = await ScanProgress.get_or_none(guild_id=interaction.guild.id)

        if not progress or progress.status == "idle":
            await interaction.response.send_message(
                embed=info_embed("No Active Scan", "No scan is currently in progress."),
                ephemeral=True
            )
            return

        if progress.status == "scanning":
            pct = (progress.scanned_channels / progress.total_channels * 100) if progress.total_channels > 0 else 0
            embed = custom_embed() \
                .set_title("📊 Scan in Progress") \
                .set_description(f"Progress: {pct:.1f}%") \
                .add_field("Channels", f"{progress.scanned_channels}/{progress.total_channels}", inline=True) \
                .add_field("Messages", f"{progress.scanned_messages:,}", inline=True) \
                .add_field("Emojis Found", f"{progress.emojis_found:,}", inline=True) \
                .set_timestamp()

            await interaction.response.send_message(embed=embed.build(), ephemeral=True)
        else:
            status_text = "✅ Completed" if progress.status == "completed" else f"❌ {progress.status}"
            embed = custom_embed() \
                .set_title("Scan Status") \
                .add_field("Status", status_text, inline=True) \
                .add_field("Last Run", f"<t:{int(progress.started_at.timestamp())}:R>" if progress.started_at else "Never", inline=True)

            if progress.last_error:
                embed.add_field("Last Error", progress.last_error[:200], inline=False)

            await interaction.response.send_message(embed=embed.build(), ephemeral=True)

    # ==================== Info Commands ====================

    @emoticon_group.command(name="info", description="Get detailed stats for a specific emoji.")
    @app_commands.describe(
        emoji="The emoji to analyze",
        query="Filter scope and display options"
    )
    async def info(
        self,
        interaction: discord.Interaction,
        emoji: str,
        query: Optional[str] = None
    ):
        """Get detailed 'trading card' stats for a single emoji."""
        await interaction.response.defer()

        config = await self._get_config(interaction.guild.id)
        parser = QueryParser(interaction.guild)
        parsed = parser.parse(query or "")

        # Parse the emoji argument
        extractor = EmojiExtractor(interaction.guild)

        # Try to extract emoji from the string
        extracted = extractor.extract_from_message(emoji)
        if not extracted:
            await interaction.followup.send(
                embed=error_embed("Invalid Emoji", "Could not parse the provided emoji."),
                ephemeral=True
            )
            return

        target_emoji = extracted[0]

        # Build query filters
        base_filters = await self._apply_query_filters(parsed, interaction.guild.id, interaction.user, config)

        if target_emoji.emoji_id:
            emoji_filter = Q(emoji_id=target_emoji.emoji_id)
        else:
            emoji_filter = Q(emoji_name=target_emoji.emoji_name, emoji_id__isnull=True)

        # Get usage stats
        total_uses = await EmojiUsage.filter(base_filters & emoji_filter).annotate(total=Sum('count')).values('total')
        total_count = total_uses[0]['total'] if total_uses and total_uses[0]['total'] else 0

        if total_count == 0:
            await interaction.followup.send(
                embed=info_embed("No Data", f"No usage data found for {emoji}"),
                ephemeral=True
            )
            return

        # Get top users (excluding user_id=0)
        top_users = await EmojiUsage.filter(base_filters & emoji_filter & Q(user_id__gt=0)) \
            .annotate(use_count=Sum('count')) \
            .group_by('user_id') \
            .order_by('-use_count') \
            .limit(3) \
            .values('user_id', 'use_count')

        # Get top channels
        top_channels = await EmojiUsage.filter(base_filters & emoji_filter) \
            .annotate(use_count=Count('id')) \
            .group_by('channel_id') \
            .order_by('-use_count') \
            .limit(3) \
            .values('channel_id', 'use_count')

        # Get server-wide rank
        all_emojis = await EmojiUsage.filter(base_filters) \
            .annotate(use_count=Count('id')) \
            .group_by('emoji_id', 'emoji_name') \
            .order_by('-use_count') \
            .values('emoji_id', 'emoji_name', 'use_count')

        rank = 1
        for i, e in enumerate(all_emojis, 1):
            if e['emoji_id'] == target_emoji.emoji_id and e['emoji_name'] == target_emoji.emoji_name:
                rank = i
                break

        # Build embed
        renderer = Renderer(await self._get_render_settings(interaction.guild.id, ComponentTarget.INFO, parsed.flags))
        emoji_display = renderer.render_emoji(target_emoji.emoji_id, target_emoji.emoji_name, target_emoji.animated)

        embed = custom_embed() \
            .set_title(f"📊 Emoji Info: {emoji_display}") \
            .set_color('info') \
            .add_field("Total Uses", f"**{total_count:,}**", inline=True) \
            .add_field("Server Rank", f"**#{rank}**", inline=True) \
            .set_timestamp()

        # Add top users
        if top_users:
            user_lines = []
            for i, u in enumerate(top_users, 1):
                member = interaction.guild.get_member(u['user_id'])
                name = member.display_name if member else f"User {u['user_id']}"
                user_lines.append(f"{i}. {name} ({u['use_count']:,})")
            embed.add_field("Top Users", "\n".join(user_lines), inline=False)

        # Add top channels
        if top_channels:
            channel_lines = []
            for i, c in enumerate(top_channels, 1):
                channel = interaction.guild.get_channel(c['channel_id'])
                name = f"#{channel.name}" if channel else f"Channel {c['channel_id']}"
                channel_lines.append(f"{i}. {name} ({c['use_count']:,})")
            embed.add_field("Top Channels", "\n".join(channel_lines), inline=False)

        # Add metadata for custom emojis
        if target_emoji.emoji_id:
            discord_emoji = interaction.guild.get_emoji(target_emoji.emoji_id)
            if discord_emoji:
                embed.set_thumbnail(discord_emoji.url)
                embed.add_field("Created", f"<t:{int(discord_emoji.created_at.timestamp())}:D>", inline=True)
                embed.add_field("Animated", "Yes" if discord_emoji.animated else "No", inline=True)

        await interaction.followup.send(embed=embed.build())

    # ==================== Leaderboard Commands ====================

    @emoticon_group.command(name="leaderboard", description="View emoji usage leaderboards.")
    @app_commands.describe(
        type="Type of leaderboard",
        sort="Sort order",
        dataset="Apply a saved dataset",
        query="Filter scope and display options"
    )
    async def leaderboard(
        self,
        interaction: discord.Interaction,
        type: Literal["global", "user", "density"] = "global",
        sort: Literal["most", "least"] = "most",
        dataset: Optional[str] = None,
        query: Optional[str] = None
    ):
        """View emoji usage leaderboards."""
        await interaction.response.defer()

        config = await self._get_config(interaction.guild.id)
        parser = QueryParser(interaction.guild)
        parsed = parser.parse(query or "")

        # Apply dataset if specified
        if dataset:
            saved_dataset = await Dataset.get_or_none(guild_id=interaction.guild.id, name=dataset)
            if saved_dataset:
                parsed.channels = saved_dataset.channel_ids
            else:
                await interaction.followup.send(
                    embed=error_embed("Dataset Not Found", f"No dataset named '{dataset}' exists."),
                    ephemeral=True
                )
                return

        # Build query filters
        base_filters = await self._apply_query_filters(parsed, interaction.guild.id, interaction.user, config)

        # Get render settings
        settings = await self._get_render_settings(interaction.guild.id, ComponentTarget.LEADERBOARD, parsed.flags)
        renderer = Renderer(settings)

        sort_order = '-use_count' if sort == "most" else 'use_count'

        # Get total emoji count for percentage calculation
        total_result = await EmojiUsage.filter(base_filters).annotate(total=Sum('count')).values('total')
        total = total_result[0]['total'] if total_result and total_result[0]['total'] else 0

        # Fetch more results for pagination (up to 100)
        max_results = 100

        if type == "global":
            # Emoji leaderboard
            results = await EmojiUsage.filter(base_filters) \
                .annotate(use_count=Sum('count')) \
                .group_by('emoji_id', 'emoji_name', 'emoji_animated') \
                .order_by(sort_order) \
                .limit(max_results) \
                .values('emoji_id', 'emoji_name', 'emoji_animated', 'use_count')

            entries = [
                {
                    'emoji_id': r['emoji_id'],
                    'emoji_name': r['emoji_name'],
                    'animated': r['emoji_animated'],
                    'count': r['use_count']
                }
                for r in results
            ]

            title = "🏆 Emoji Leaderboard"
            if sort == "least":
                title = "📉 Least Used Emojis"

            leaderboard_type = "emoji"

        elif type == "user":
            # User leaderboard
            results = await EmojiUsage.filter(base_filters) \
                .annotate(use_count=Sum('count')) \
                .group_by('user_id') \
                .order_by(sort_order) \
                .limit(max_results) \
                .values('user_id', 'use_count')

            entries = []
            for r in results:
                member = interaction.guild.get_member(r['user_id'])
                entries.append({
                    'user_id': r['user_id'],
                    'user_name': member.display_name if member else f"User {r['user_id']}",
                    'count': r['use_count']
                })

            title = "👥 User Emoji Leaderboard"
            leaderboard_type = "user"

        else:  # density
            # Emoji count / unique messages ratio
            results = await EmojiUsage.filter(base_filters) \
                .annotate(
                    emoji_count=Sum('count'),
                    message_count=Count('message_id', distinct=True)
                ) \
                .group_by('user_id') \
                .order_by('-emoji_count') \
                .limit(max_results) \
                .values('user_id', 'emoji_count', 'message_count')

            entries = []
            for r in results:
                member = interaction.guild.get_member(r['user_id'])
                density = (r['emoji_count'] / r['message_count']) if r['message_count'] > 0 else 0
                entries.append({
                    'user_id': r['user_id'],
                    'user_name': member.display_name if member else f"User {r['user_id']}",
                    'count': round(density, 2)
                })

            # Sort by density
            entries.sort(key=lambda x: x['count'], reverse=(sort == "most"))

            title = "📈 Emoji Density Leaderboard"
            leaderboard_type = "user"
            # For density, total doesn't apply in the same way
            total = 100

        # Build footer with query info
        footer_parts = []
        if parsed.raw_query:
            footer_parts.append(f"Query: {parsed.raw_query}")
        if parsed.channels:
            footer_parts.append(f"Channels: {len(parsed.channels)}")
        if parsed.users:
            footer_parts.append(f"Users: {len(parsed.users)}")
        if parsed.date_after:
            footer_parts.append(f"After: {parsed.date_after.strftime('%Y-%m-%d')}")
        if parsed.date_before:
            footer_parts.append(f"Before: {parsed.date_before.strftime('%Y-%m-%d')}")

        footer = " | ".join(footer_parts) if footer_parts else ""

        # Create pagination view
        view = LeaderboardPaginatorView(
            entries=entries,
            total=total,
            leaderboard_type=leaderboard_type,
            title=title,
            renderer=renderer,
            footer=footer,
            per_page=settings.max_entries
        )

        await interaction.followup.send(embed=view.get_embed(), view=view)

    # ==================== Profile Command ====================

    @emoticon_group.command(name="profile", description="View a user's emoji profile.")
    @app_commands.describe(
        user="The user to view (defaults to you)",
        query="Filter scope and display options"
    )
    async def profile(
        self,
        interaction: discord.Interaction,
        user: Optional[discord.Member] = None,
        query: Optional[str] = None
    ):
        """View a user's emoji usage profile."""
        await interaction.response.defer()

        target_user = user or interaction.user
        config = await self._get_config(interaction.guild.id)
        parser = QueryParser(interaction.guild)
        parsed = parser.parse(query or "")

        # Build query filters
        base_filters = await self._apply_query_filters(parsed, interaction.guild.id, interaction.user, config)
        user_filters = base_filters & Q(user_id=target_user.id)

        # Get user stats
        total_uses = await EmojiUsage.filter(user_filters).annotate(total=Sum('count')).values('total')
        total = total_uses[0]['total'] if total_uses and total_uses[0]['total'] else 0

        if total == 0:
            await interaction.followup.send(
                embed=info_embed("No Data", f"No emoji usage data found for {target_user.display_name}"),
                ephemeral=True
            )
            return

        # Get signature emoji (most used)
        top_emoji = await EmojiUsage.filter(user_filters) \
            .annotate(use_count=Sum('count')) \
            .group_by('emoji_id', 'emoji_name', 'emoji_animated') \
            .order_by('-use_count') \
            .first() \
            .values('emoji_id', 'emoji_name', 'emoji_animated', 'use_count')

        # Get unique emoji count
        unique_emojis = await EmojiUsage.filter(user_filters) \
            .distinct() \
            .values('emoji_id', 'emoji_name')

        # Get reaction vs text ratio
        reaction_count = await EmojiUsage.filter(user_filters & Q(is_reaction=True)).annotate(total=Sum('count')).values('total')
        text_count = await EmojiUsage.filter(user_filters & Q(is_reaction=False)).annotate(total=Sum('count')).values('total')

        reactions = reaction_count[0]['total'] if reaction_count and reaction_count[0]['total'] else 0
        texts = text_count[0]['total'] if text_count and text_count[0]['total'] else 0

        reaction_ratio = (reactions / total * 100) if total > 0 else 0

        # Build embed
        settings = await self._get_render_settings(interaction.guild.id, ComponentTarget.PROFILE, parsed.flags)
        renderer = Renderer(settings)

        signature = ""
        if top_emoji:
            signature = renderer.render_emoji(top_emoji['emoji_id'], top_emoji['emoji_name'], top_emoji['emoji_animated'])

        embed = custom_embed() \
            .set_title(f"📊 Emoji Profile: {target_user.display_name}") \
            .set_thumbnail(target_user.display_avatar.url) \
            .add_field("Signature Emoji", signature or "None", inline=True) \
            .add_field("Total Uses", f"**{total:,}**", inline=True) \
            .add_field("Vocabulary", f"**{len(unique_emojis)}** unique emojis", inline=True) \
            .add_field("Reaction Ratio", f"**{reaction_ratio:.1f}%** reactions vs text", inline=True) \
            .set_timestamp()

        # Add top 5 emojis
        top_5 = await EmojiUsage.filter(user_filters) \
            .annotate(use_count=Sum('count')) \
            .group_by('emoji_id', 'emoji_name', 'emoji_animated') \
            .order_by('-use_count') \
            .limit(5) \
            .values('emoji_id', 'emoji_name', 'emoji_animated', 'use_count')

        if top_5:
            top_lines = []
            for i, e in enumerate(top_5, 1):
                emoji_str = renderer.render_emoji(e['emoji_id'], e['emoji_name'], e['emoji_animated'])
                top_lines.append(f"{i}. {emoji_str} ({e['use_count']:,})")
            embed.add_field("Top Emojis", "\n".join(top_lines), inline=False)

        await interaction.followup.send(embed=embed.build())

    # ==================== Compare Command ====================

    @emoticon_group.command(name="compare", description="Compare two emojis or users.")
    @app_commands.describe(
        entity_a="First emoji or @user",
        entity_b="Second emoji or @user",
        query="Filter scope"
    )
    async def compare(
        self,
        interaction: discord.Interaction,
        entity_a: str,
        entity_b: str,
        query: Optional[str] = None
    ):
        """Compare two entities side-by-side."""
        await interaction.response.defer()

        config = await self._get_config(interaction.guild.id)
        parser = QueryParser(interaction.guild)
        parsed = parser.parse(query or "")

        base_filters = await self._apply_query_filters(parsed, interaction.guild.id, interaction.user, config)

        # Determine entity types and get counts
        extractor = EmojiExtractor(interaction.guild)

        async def get_entity_data(entity_str: str) -> dict:
            # Check if it's a user mention
            if entity_str.startswith('<@') or entity_str.startswith('@'):
                user_id = int(''.join(filter(str.isdigit, entity_str)))
                member = interaction.guild.get_member(user_id)

                result = await EmojiUsage.filter(base_filters & Q(user_id=user_id)) \
                    .annotate(total=Sum('count')) \
                    .values('total')

                count = result[0]['total'] if result and result[0]['total'] else 0

                return {
                    'type': 'user',
                    'name': member.display_name if member else f"User {user_id}",
                    'count': count
                }
            else:
                # It's an emoji
                extracted = extractor.extract_from_message(entity_str)
                if not extracted:
                    return {'type': 'unknown', 'name': entity_str, 'count': 0}

                emoji = extracted[0]

                if emoji.emoji_id:
                    emoji_filter = Q(emoji_id=emoji.emoji_id)
                else:
                    emoji_filter = Q(emoji_name=emoji.emoji_name, emoji_id__isnull=True)

                result = await EmojiUsage.filter(base_filters & emoji_filter) \
                    .annotate(total=Sum('count')) \
                    .values('total')

                count = result[0]['total'] if result and result[0]['total'] else 0

                settings = await self._get_render_settings(interaction.guild.id, ComponentTarget.INFO, {})
                renderer = Renderer(settings)

                return {
                    'type': 'emoji',
                    'name': renderer.render_emoji(emoji.emoji_id, emoji.emoji_name, emoji.animated),
                    'count': count
                }

        data_a = await get_entity_data(entity_a)
        data_b = await get_entity_data(entity_b)

        settings = await self._get_render_settings(interaction.guild.id, ComponentTarget.INFO, parsed.flags)
        renderer = Renderer(settings)

        comparison_text = renderer.render_comparison(data_a, data_b)

        embed = custom_embed() \
            .set_title("⚔️ Comparison") \
            .set_description(comparison_text) \
            .set_timestamp()

        await interaction.followup.send(embed=embed.build())

    # ==================== Settings Commands ====================

    @settings_group.command(name="scope", description="Configure scanning scope.")
    @app_commands.describe(
        default_scope="Default scan breadth",
        thread_policy="How to handle threads"
    )
    @app_commands.default_permissions(manage_guild=True)
    async def settings_scope(
        self,
        interaction: discord.Interaction,
        default_scope: Optional[Literal["server", "category", "channel"]] = None,
        thread_policy: Optional[Literal["ignore", "active", "all"]] = None
    ):
        """Configure the bot's scanning scope."""
        config = await self._get_config(interaction.guild.id)

        changes = []

        if default_scope:
            scope_map = {"server": ScanScope.SERVER, "category": ScanScope.CATEGORY, "channel": ScanScope.CHANNEL}
            config.default_scan_scope = scope_map[default_scope]
            changes.append(f"Default scope: **{default_scope}**")

        if thread_policy:
            policy_map = {"ignore": ThreadPolicy.IGNORE_ALL, "active": ThreadPolicy.ACTIVE_ONLY, "all": ThreadPolicy.ALL_THREADS}
            config.thread_policy = policy_map[thread_policy]
            changes.append(f"Thread policy: **{thread_policy}**")

        await config.save()

        if changes:
            await interaction.response.send_message(
                embed=success_embed("Settings Updated", "\n".join(changes)),
                ephemeral=True
            )
        else:
            embed = custom_embed() \
                .set_title("Current Scope Settings") \
                .add_field("Default Scope", config.default_scan_scope.value, inline=True) \
                .add_field("Thread Policy", config.thread_policy.value, inline=True) \
                .add_field("Ignored Channels", str(len(config.ignored_channels)), inline=True) \
                .add_field("Ignored Categories", str(len(config.ignored_categories)), inline=True)

            await interaction.response.send_message(embed=embed.build(), ephemeral=True)

    @settings_group.command(name="filters", description="Configure emoji tracking filters.")
    @app_commands.describe(
        tracking_mode="What emojis to track",
        allow_external="Track nitro emojis from other servers"
    )
    @app_commands.default_permissions(manage_guild=True)
    async def settings_filters(
        self,
        interaction: discord.Interaction,
        tracking_mode: Optional[Literal["all", "whitelist", "blacklist"]] = None,
        allow_external: Optional[bool] = None
    ):
        """Configure emoji tracking filters."""
        config = await self._get_config(interaction.guild.id)

        changes = []

        if tracking_mode:
            mode_map = {"all": TrackingMode.ALL, "whitelist": TrackingMode.WHITELIST, "blacklist": TrackingMode.BLACKLIST}
            config.tracking_mode = mode_map[tracking_mode]
            changes.append(f"Tracking mode: **{tracking_mode}**")

        if allow_external is not None:
            config.allow_external_emojis = allow_external
            changes.append(f"External emojis: **{'Allowed' if allow_external else 'Blocked'}**")

        await config.save()

        if changes:
            await interaction.response.send_message(
                embed=success_embed("Filter Settings Updated", "\n".join(changes)),
                ephemeral=True
            )
        else:
            filter_count = await EmojiFilter.filter(guild_id=interaction.guild.id).count()

            embed = custom_embed() \
                .set_title("Current Filter Settings") \
                .add_field("Tracking Mode", config.tracking_mode.value, inline=True) \
                .add_field("External Emojis", "Allowed" if config.allow_external_emojis else "Blocked", inline=True) \
                .add_field("Filter List Entries", str(filter_count), inline=True)

            await interaction.response.send_message(embed=embed.build(), ephemeral=True)

    @settings_group.command(name="display", description="Configure visual display options.")
    @app_commands.describe(
        target="Which command to configure",
        show_ids="Show emoji IDs",
        show_percentages="Show percentages",
        compact_mode="Use compact display mode"
    )
    @app_commands.default_permissions(manage_guild=True)
    async def settings_display(
        self,
        interaction: discord.Interaction,
        target: Literal["global", "leaderboard", "info", "profile"] = "global",
        show_ids: Optional[bool] = None,
        show_percentages: Optional[bool] = None,
        compact_mode: Optional[bool] = None
    ):
        """Configure visual display options."""
        target_map = {
            "global": ComponentTarget.GLOBAL,
            "leaderboard": ComponentTarget.LEADERBOARD,
            "info": ComponentTarget.INFO,
            "profile": ComponentTarget.PROFILE
        }

        settings, _ = await ComponentSettings.get_or_create(
            guild_id=interaction.guild.id,
            target=target_map[target]
        )

        changes = []

        if show_ids is not None:
            settings.show_ids = show_ids
            changes.append(f"Show IDs: **{show_ids}**")

        if show_percentages is not None:
            settings.show_percentages = show_percentages
            changes.append(f"Show percentages: **{show_percentages}**")

        if compact_mode is not None:
            settings.compact_mode = compact_mode
            changes.append(f"Compact mode: **{compact_mode}**")

        await settings.save()

        if changes:
            await interaction.response.send_message(
                embed=success_embed(f"Display Settings Updated ({target})", "\n".join(changes)),
                ephemeral=True
            )
        else:
            embed = custom_embed() \
                .set_title(f"Display Settings: {target}") \
                .add_field("Show IDs", str(settings.show_ids) if settings.show_ids is not None else "Inherit", inline=True) \
                .add_field("Show %", str(settings.show_percentages) if settings.show_percentages is not None else "Inherit", inline=True) \
                .add_field("Compact", str(settings.compact_mode) if settings.compact_mode is not None else "Inherit", inline=True)

            await interaction.response.send_message(embed=embed.build(), ephemeral=True)

    @settings_group.command(name="privacy", description="Configure privacy and data integrity settings.")
    @app_commands.describe(
        track_edits="Update counts when messages are edited",
        retain_deleted="Keep stats from deleted messages"
    )
    @app_commands.default_permissions(manage_guild=True)
    async def settings_privacy(
        self,
        interaction: discord.Interaction,
        track_edits: Optional[bool] = None,
        retain_deleted: Optional[bool] = None
    ):
        """Configure privacy and data integrity settings."""
        config = await self._get_config(interaction.guild.id)

        changes = []

        if track_edits is not None:
            config.track_edits = track_edits
            changes.append(f"Track edits: **{track_edits}**")

        if retain_deleted is not None:
            config.retain_deleted = retain_deleted
            changes.append(f"Retain deleted: **{retain_deleted}**")

        await config.save()

        if changes:
            await interaction.response.send_message(
                embed=success_embed("Privacy Settings Updated", "\n".join(changes)),
                ephemeral=True
            )
        else:
            embed = custom_embed() \
                .set_title("Privacy Settings") \
                .add_field("Track Edits", "Yes" if config.track_edits else "No", inline=True) \
                .add_field("Retain Deleted", "Yes" if config.retain_deleted else "No", inline=True) \
                .add_field("Admin Override Roles", str(len(config.admin_override_roles)), inline=True)

            await interaction.response.send_message(embed=embed.build(), ephemeral=True)

    @settings_group.command(name="ignore", description="Add or remove channels/categories from ignore list.")
    @app_commands.describe(
        action="Add or remove from ignore list",
        channel="Channel to ignore/unignore",
        category="Category to ignore/unignore"
    )
    @app_commands.default_permissions(manage_guild=True)
    async def settings_ignore(
        self,
        interaction: discord.Interaction,
        action: Literal["add", "remove", "list"],
        channel: Optional[discord.TextChannel] = None,
        category: Optional[discord.CategoryChannel] = None
    ):
        """Manage ignored channels and categories."""
        config = await self._get_config(interaction.guild.id)

        if action == "list":
            ignored_channels = [f"<#{cid}>" for cid in config.ignored_channels]
            ignored_categories = [f"Category {cid}" for cid in config.ignored_categories]

            embed = custom_embed() \
                .set_title("Ignored Channels & Categories") \
                .add_field("Channels", "\n".join(ignored_channels) or "None", inline=False) \
                .add_field("Categories", "\n".join(ignored_categories) or "None", inline=False)

            await interaction.response.send_message(embed=embed.build(), ephemeral=True)
            return

        changes = []

        if channel:
            if action == "add":
                if channel.id not in config.ignored_channels:
                    config.ignored_channels.append(channel.id)
                    changes.append(f"Added {channel.mention} to ignore list")
            else:
                if channel.id in config.ignored_channels:
                    config.ignored_channels.remove(channel.id)
                    changes.append(f"Removed {channel.mention} from ignore list")

        if category:
            if action == "add":
                if category.id not in config.ignored_categories:
                    config.ignored_categories.append(category.id)
                    changes.append(f"Added category **{category.name}** to ignore list")
            else:
                if category.id in config.ignored_categories:
                    config.ignored_categories.remove(category.id)
                    changes.append(f"Removed category **{category.name}** from ignore list")

        await config.save()

        if changes:
            await interaction.response.send_message(
                embed=success_embed("Ignore List Updated", "\n".join(changes)),
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                embed=info_embed("No Changes", "Please specify a channel or category to add/remove."),
                ephemeral=True
            )

    # ==================== Dataset Commands ====================

    @dataset_group.command(name="create", description="Create a saved dataset of channels.")
    @app_commands.describe(
        name="Name for the dataset",
        channels="Channels to include (mention multiple)"
    )
    async def dataset_create(
        self,
        interaction: discord.Interaction,
        name: str,
        channels: str
    ):
        """Create a reusable channel dataset."""
        # Parse channel mentions
        channel_ids = []
        for word in channels.split():
            if word.startswith('<#') and word.endswith('>'):
                try:
                    channel_id = int(word[2:-1])
                    channel_ids.append(channel_id)
                except ValueError:
                    pass

        if not channel_ids:
            await interaction.response.send_message(
                embed=error_embed("No Channels", "Please mention at least one channel (e.g., #general #chat)"),
                ephemeral=True
            )
            return

        # Check if dataset already exists
        existing = await Dataset.get_or_none(guild_id=interaction.guild.id, name=name)
        if existing:
            await interaction.response.send_message(
                embed=error_embed("Dataset Exists", f"A dataset named '{name}' already exists. Delete it first or use a different name."),
                ephemeral=True
            )
            return

        await Dataset.create(
            guild_id=interaction.guild.id,
            name=name,
            channel_ids=channel_ids,
            created_by=interaction.user.id
        )

        channel_mentions = " ".join(f"<#{cid}>" for cid in channel_ids)
        await interaction.response.send_message(
            embed=success_embed("Dataset Created", f"Created dataset **{name}** with channels:\n{channel_mentions}"),
            ephemeral=True
        )

    @dataset_group.command(name="delete", description="Delete a saved dataset.")
    @app_commands.describe(name="Name of the dataset to delete")
    async def dataset_delete(
        self,
        interaction: discord.Interaction,
        name: str
    ):
        """Delete a saved dataset."""
        deleted = await Dataset.filter(guild_id=interaction.guild.id, name=name).delete()

        if deleted:
            await interaction.response.send_message(
                embed=success_embed("Dataset Deleted", f"Deleted dataset **{name}**"),
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                embed=error_embed("Not Found", f"No dataset named '{name}' exists."),
                ephemeral=True
            )

    @dataset_group.command(name="list", description="List all saved datasets.")
    async def dataset_list(self, interaction: discord.Interaction):
        """List all saved datasets."""
        datasets = await Dataset.filter(guild_id=interaction.guild.id).all()

        if not datasets:
            await interaction.response.send_message(
                embed=info_embed("No Datasets", "No datasets have been created yet."),
                ephemeral=True
            )
            return

        embed = custom_embed() \
            .set_title("📁 Saved Datasets") \
            .set_timestamp()

        for ds in datasets:
            channel_count = len(ds.channel_ids)
            embed.add_field(
                name=ds.name,
                value=f"{channel_count} channel(s) | Created <t:{int(ds.created_at.timestamp())}:R>",
                inline=False
            )

        await interaction.response.send_message(embed=embed.build(), ephemeral=True)

    # ==================== Help Command ====================

    @emoticon_group.command(name="help", description="Get help with query syntax and commands.")
    async def help_command(self, interaction: discord.Interaction):
        """Display help information."""
        parser = QueryParser()

        embed = custom_embed() \
            .set_title("📊 Emoticon Analytics Help") \
            .set_description(parser.get_help_text()) \
            .add_field(
                "Commands",
                "• `/emoticon scan` - Index emoji history\n"
                "• `/emoticon leaderboard` - View rankings\n"
                "• `/emoticon info <emoji>` - Emoji details\n"
                "• `/emoticon profile [@user]` - User profile\n"
                "• `/emoticon compare` - Compare entities\n"
                "• `/emoticon settings` - Configure bot\n"
                "• `/emoticon dataset` - Manage datasets",
                inline=False
            ) \
            .set_timestamp()

        await interaction.response.send_message(embed=embed.build(), ephemeral=True)

