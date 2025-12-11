"""
Query parser for the Emoticon Analytics Bot.

Parses the unified query string syntax for filtering and runtime overrides.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class ParsedQuery:
    """Result of parsing a query string."""
    # Channel filters
    channels: list[int] = field(default_factory=list)
    excluded_channels: list[int] = field(default_factory=list)

    # User filters
    users: list[int] = field(default_factory=list)
    excluded_users: list[int] = field(default_factory=list)

    # Role filters
    roles: list[str] = field(default_factory=list)

    # Emoji filters
    emojis: list[str] = field(default_factory=list)

    # Date filters
    date_after: Optional[datetime] = None
    date_before: Optional[datetime] = None

    # Component flags (runtime overrides)
    flags: dict = field(default_factory=dict)

    # Raw query for debugging
    raw_query: str = ""

    # Parse errors/warnings
    errors: list[str] = field(default_factory=list)


class QueryParser:
    """
    Parses the power-user query string syntax.

    Supported syntax:
        #channel         - Include a specific channel
        -#channel        - Exclude a specific channel
        @user            - Include specific user data
        -@user           - Exclude specific user data
        role:Name        - Include users with a specific role
        emoji:name       - Filter by specific emoji
        after:YYYY-MM-DD - Only count usage after this date
        before:YYYY-MM-DD - Only count usage before this date

    Component flags:
        --no-ids / --ids         - Toggle emoji ID display
        --compact                - Force compact format
        --expanded               - Force detailed view
        --no-percentages / --percentages - Toggle percentage display
    """

    # Regex patterns for parsing
    CHANNEL_PATTERN = re.compile(r'(-?)#(\w+|\d+)')
    USER_PATTERN = re.compile(r'(-?)@(\w+|\d+)')
    ROLE_PATTERN = re.compile(r'role:(\w+)')
    EMOJI_PATTERN = re.compile(r'emoji:(\w+)')
    DATE_AFTER_PATTERN = re.compile(r'after:(\d{4}-\d{2}-\d{2})')
    DATE_BEFORE_PATTERN = re.compile(r'before:(\d{4}-\d{2}-\d{2})')

    # Component flag patterns
    FLAG_PATTERNS = {
        '--no-ids': ('show_ids', False),
        '--ids': ('show_ids', True),
        '--compact': ('compact_mode', True),
        '--expanded': ('compact_mode', False),
        '--no-percentages': ('show_percentages', False),
        '--percentages': ('show_percentages', True),
    }

    def __init__(self, guild=None):
        """
        Initialize the query parser.

        Args:
            guild: The Discord guild for resolving names to IDs
        """
        self.guild = guild

    def parse(self, query: str) -> ParsedQuery:
        """
        Parse a query string into structured filters and flags.

        Args:
            query: The raw query string from the user

        Returns:
            ParsedQuery object with all parsed components
        """
        result = ParsedQuery(raw_query=query)

        if not query:
            return result

        # Parse component flags first (they're at the end)
        for flag, (key, value) in self.FLAG_PATTERNS.items():
            if flag in query:
                result.flags[key] = value
                query = query.replace(flag, '')

        # Parse channel filters
        for match in self.CHANNEL_PATTERN.finditer(query):
            excluded = match.group(1) == '-'
            channel_ref = match.group(2)
            channel_id = self._resolve_channel(channel_ref)

            if channel_id:
                if excluded:
                    result.excluded_channels.append(channel_id)
                else:
                    result.channels.append(channel_id)
            else:
                result.errors.append(f"Could not resolve channel: {channel_ref}")

        # Parse user filters
        for match in self.USER_PATTERN.finditer(query):
            excluded = match.group(1) == '-'
            user_ref = match.group(2)
            user_id = self._resolve_user(user_ref)

            if user_id:
                if excluded:
                    result.excluded_users.append(user_id)
                else:
                    result.users.append(user_id)
            else:
                result.errors.append(f"Could not resolve user: {user_ref}")

        # Parse role filters
        for match in self.ROLE_PATTERN.finditer(query):
            role_name = match.group(1)
            result.roles.append(role_name)

        # Parse emoji filters
        for match in self.EMOJI_PATTERN.finditer(query):
            emoji_name = match.group(1)
            result.emojis.append(emoji_name)

        # Parse date filters
        after_match = self.DATE_AFTER_PATTERN.search(query)
        if after_match:
            try:
                result.date_after = datetime.strptime(after_match.group(1), '%Y-%m-%d')
            except ValueError:
                result.errors.append(f"Invalid date format: {after_match.group(1)}")

        before_match = self.DATE_BEFORE_PATTERN.search(query)
        if before_match:
            try:
                result.date_before = datetime.strptime(before_match.group(1), '%Y-%m-%d')
            except ValueError:
                result.errors.append(f"Invalid date format: {before_match.group(1)}")

        return result

    def _resolve_channel(self, ref: str) -> Optional[int]:
        """Resolve a channel reference to an ID."""
        # If it's already a numeric ID
        if ref.isdigit():
            return int(ref)

        # Try to find by name in guild
        if self.guild:
            for channel in self.guild.channels:
                if channel.name.lower() == ref.lower():
                    return channel.id

        return None

    def _resolve_user(self, ref: str) -> Optional[int]:
        """Resolve a user reference to an ID."""
        # If it's already a numeric ID
        if ref.isdigit():
            return int(ref)

        # Try to find by name/display name in guild
        if self.guild:
            for member in self.guild.members:
                if (member.name.lower() == ref.lower() or
                    member.display_name.lower() == ref.lower()):
                    return member.id

        return None

    def get_help_text(self) -> str:
        """Return help text explaining the query syntax."""
        return """
**Query Syntax Help**

**Filters:**
• `#channel` - Include a specific channel
• `-#channel` - Exclude a specific channel
• `@user` - Include specific user data
• `-@user` - Exclude specific user data
• `role:Name` - Include users with a specific role
• `emoji:name` - Filter by specific emoji
• `after:YYYY-MM-DD` - Only count usage after this date
• `before:YYYY-MM-DD` - Only count usage before this date

**Display Flags:**
• `--ids` / `--no-ids` - Toggle emoji ID display
• `--percentages` / `--no-percentages` - Toggle percentages
• `--compact` - Condensed single-line format
• `--expanded` - Detailed multi-line format

**Example:**
`#general #chat -@Bots after:2024-01-01 --compact`
"""

