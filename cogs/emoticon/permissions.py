"""
Permission filtering utilities for the Emoticon Analytics Bot.

Implements the View Permission Rule: users only see data from channels
they have permission to view.
"""

import discord
from typing import Optional


class PermissionFilter:
    """
    Handles permission-based filtering of emoji usage data.

    Core Philosophy: By default, users only see data aggregated from
    channels they currently have permission to view.
    """

    def __init__(self, guild: discord.Guild, config=None):
        """
        Initialize the permission filter.

        Args:
            guild: The Discord guild to filter for
            config: EmoticonConfig instance for this guild
        """
        self.guild = guild
        self.config = config
        self._permission_cache: dict[tuple[int, int], bool] = {}

    def can_view_channel(self, user: discord.Member, channel_id: int) -> bool:
        """
        Check if a user can view a specific channel.

        Args:
            user: The member to check permissions for
            channel_id: The channel ID to check

        Returns:
            True if user can view the channel
        """
        cache_key = (user.id, channel_id)

        if cache_key in self._permission_cache:
            return self._permission_cache[cache_key]

        channel = self.guild.get_channel(channel_id)
        if not channel:
            # Channel might have been deleted
            self._permission_cache[cache_key] = False
            return False

        # Check if user has view permission
        permissions = channel.permissions_for(user)
        can_view = permissions.view_channel

        self._permission_cache[cache_key] = can_view
        return can_view

    def filter_channels(self, user: discord.Member, channel_ids: list[int]) -> list[int]:
        """
        Filter a list of channel IDs to only those the user can view.

        Args:
            user: The member to filter for
            channel_ids: List of channel IDs to filter

        Returns:
            Filtered list of channel IDs
        """
        # Check for admin override first
        if self.has_admin_override(user):
            return channel_ids

        return [
            channel_id for channel_id in channel_ids
            if self.can_view_channel(user, channel_id)
        ]

    def has_admin_override(self, user: discord.Member) -> bool:
        """
        Check if a user has admin override permissions.

        Admin override allows users to see all emoji data regardless
        of channel permissions.

        Args:
            user: The member to check

        Returns:
            True if user has admin override
        """
        # Server owner always has override
        if user.id == self.guild.owner_id:
            return True

        # Users with Administrator permission have override
        if user.guild_permissions.administrator:
            return True

        # Check configured override roles
        if self.config and self.config.admin_override_roles:
            user_role_ids = {role.id for role in user.roles}
            override_role_ids = set(self.config.admin_override_roles)
            if user_role_ids & override_role_ids:
                return True

        return False

    def get_viewable_channels(self, user: discord.Member) -> list[int]:
        """
        Get all channel IDs that a user can view in the guild.

        Args:
            user: The member to get viewable channels for

        Returns:
            List of viewable channel IDs
        """
        if self.has_admin_override(user):
            return [channel.id for channel in self.guild.channels]

        viewable = []
        for channel in self.guild.channels:
            if isinstance(channel, (discord.TextChannel, discord.Thread)):
                if self.can_view_channel(user, channel.id):
                    viewable.append(channel.id)

        return viewable

    def clear_cache(self):
        """Clear the permission cache."""
        self._permission_cache.clear()


def build_channel_filter_query(
    user: discord.Member,
    guild: discord.Guild,
    config=None,
    base_channel_ids: Optional[list[int]] = None
) -> list[int]:
    """
    Build a list of channel IDs for database queries based on user permissions.

    This is a convenience function that creates a PermissionFilter and
    returns the appropriate channel list.

    Args:
        user: The member requesting data
        guild: The Discord guild
        config: EmoticonConfig instance
        base_channel_ids: Optional list to filter (if None, uses all channels)

    Returns:
        List of channel IDs the user can view
    """
    perm_filter = PermissionFilter(guild, config)

    if base_channel_ids:
        return perm_filter.filter_channels(user, base_channel_ids)
    else:
        return perm_filter.get_viewable_channels(user)
