"""
Database models for the Emoticon Analytics Bot.

This module defines all Tortoise ORM models for tracking emoji usage,
configuration settings, and user-defined datasets.
"""

from enum import Enum
from tortoise import fields
from tortoise.models import Model


class TrackingMode(str, Enum):
    """Emoji tracking mode for filtering which emojis to count."""
    ALL = "all"
    WHITELIST = "whitelist"
    BLACKLIST = "blacklist"


class ThreadPolicy(str, Enum):
    """Policy for how threads are handled during scanning."""
    IGNORE_ALL = "ignore_all"
    ACTIVE_ONLY = "active_only"
    ALL_THREADS = "all_threads"


class ScanScope(str, Enum):
    """Default scanning scope for the bot."""
    SERVER = "server"
    CATEGORY = "category"
    CHANNEL = "channel"


class TieGrouping(str, Enum):
    """How to display tied entries in leaderboards."""
    GROUP = "group"  # "User A, User B, and 25 others..."
    LIST_ALL = "list_all"  # List every user


class ComponentTarget(str, Enum):
    """Target for component settings."""
    GLOBAL = "global"
    LEADERBOARD = "leaderboard"
    INFO = "info"
    PROFILE = "profile"


class EmojiUsage(Model):
    """
    Tracks individual emoji usage events.

    Each record represents a single emoji used in a message or as a reaction.
    """
    id = fields.IntField(pk=True)
    guild_id = fields.BigIntField(index=True)
    channel_id = fields.BigIntField(index=True)
    user_id = fields.BigIntField(index=True)
    message_id = fields.BigIntField(index=True)

    # Emoji identification
    emoji_id = fields.BigIntField(null=True, index=True)  # NULL for unicode emojis
    emoji_name = fields.CharField(max_length=100, index=True)  # Name or unicode character
    emoji_animated = fields.BooleanField(default=False)
    is_external = fields.BooleanField(default=False)  # Nitro emoji from another server

    # Usage context
    is_reaction = fields.BooleanField(default=False, index=True)
    count = fields.IntField(default=1)  # For multiple same emoji in one message

    # Timestamps
    timestamp = fields.DatetimeField(auto_now_add=True, index=True)
    message_timestamp = fields.DatetimeField(null=True)

    class Meta:
        table = "emoji_usage"
        indexes = [
            ("guild_id", "emoji_id"),
            ("guild_id", "user_id"),
            ("guild_id", "channel_id"),
            ("guild_id", "timestamp"),
        ]


class EmoticonConfig(Model):
    """
    Server-wide configuration for the Emoticon Analytics Bot.

    Stores all settings related to scanning scope, filtering, and behavior.
    """
    id = fields.IntField(pk=True)
    guild_id = fields.BigIntField(unique=True, index=True)

    # Scan scope settings
    default_scan_scope = fields.CharEnumField(ScanScope, default=ScanScope.SERVER)
    ignored_channels = fields.JSONField(default=list)  # List of channel IDs
    ignored_categories = fields.JSONField(default=list)  # List of category IDs
    thread_policy = fields.CharEnumField(ThreadPolicy, default=ThreadPolicy.ACTIVE_ONLY)

    # Tracking mode settings
    tracking_mode = fields.CharEnumField(TrackingMode, default=TrackingMode.ALL)
    allow_external_emojis = fields.BooleanField(default=True)

    # Privacy and data integrity settings
    admin_override_roles = fields.JSONField(default=list)  # Role IDs that bypass view permission
    track_edits = fields.BooleanField(default=True)  # Update counts on message edits
    retain_deleted = fields.BooleanField(default=True)  # Keep stats of deleted messages

    # Scan tracking
    last_scan_timestamp = fields.DatetimeField(null=True)
    last_scan_message_id = fields.BigIntField(null=True)  # For incremental scanning

    class Meta:
        table = "emoticon_config"


class EmojiFilter(Model):
    """
    Whitelist/Blacklist entries for emoji filtering.

    Used when tracking_mode is set to WHITELIST or BLACKLIST.
    """
    id = fields.IntField(pk=True)
    guild_id = fields.BigIntField(index=True)
    emoji_id = fields.BigIntField(null=True)  # NULL for unicode emojis
    emoji_name = fields.CharField(max_length=100)  # Name or unicode character
    filter_type = fields.CharEnumField(TrackingMode, default=TrackingMode.WHITELIST)

    class Meta:
        table = "emoji_filter"
        unique_together = (("guild_id", "emoji_id", "emoji_name", "filter_type"),)


class Dataset(Model):
    """
    User-defined channel groupings for easy querying.

    Allows users to save sets of channels like "Staff Channels" or "Gaming".
    """
    id = fields.IntField(pk=True)
    guild_id = fields.BigIntField(index=True)
    name = fields.CharField(max_length=100)
    channel_ids = fields.JSONField(default=list)  # List of channel IDs
    created_by = fields.BigIntField()  # User ID who created it
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "emoticon_dataset"
        unique_together = (("guild_id", "name"),)


class ComponentSettings(Model):
    """
    Visual component settings for embed output.

    Supports inheritance: Runtime Flag → Command Setting → Global Default.
    NULL values mean "inherit from parent".
    """
    id = fields.IntField(pk=True)
    guild_id = fields.BigIntField(index=True)
    target = fields.CharEnumField(ComponentTarget, default=ComponentTarget.GLOBAL)

    # Visual settings (NULL = inherit)
    show_ids = fields.BooleanField(null=True)
    show_percentages = fields.BooleanField(null=True)
    tie_grouping = fields.CharEnumField(TieGrouping, null=True)
    compact_mode = fields.BooleanField(null=True)

    class Meta:
        table = "emoticon_component_settings"
        unique_together = (("guild_id", "target"),)


class ScanProgress(Model):
    """
    Tracks ongoing scan operations.

    Used to display progress and allow resumption of interrupted scans.
    """
    id = fields.IntField(pk=True)
    guild_id = fields.BigIntField(unique=True, index=True)

    # Progress tracking
    status = fields.CharField(max_length=20, default="idle")  # idle, scanning, paused, completed, failed
    total_channels = fields.IntField(default=0)
    scanned_channels = fields.IntField(default=0)
    total_messages = fields.IntField(default=0)
    scanned_messages = fields.IntField(default=0)
    emojis_found = fields.IntField(default=0)

    # Timing
    started_at = fields.DatetimeField(null=True)
    completed_at = fields.DatetimeField(null=True)
    last_error = fields.TextField(null=True)

    class Meta:
        table = "emoticon_scan_progress"

