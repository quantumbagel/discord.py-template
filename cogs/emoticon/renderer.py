"""
Visual rendering utilities for the Emoticon Analytics Bot.

Handles the rendering of leaderboards and other visual elements.
"""

from dataclasses import dataclass
from typing import Optional

from .models import TieGrouping


@dataclass
class RenderSettings:
    """Settings for rendering output."""
    show_ids: bool = False
    show_percentages: bool = True
    compact_mode: bool = False
    tie_grouping: TieGrouping = TieGrouping.GROUP
    max_entries: int = 10


class Renderer:
    """
    Renders visual elements for emoji analytics output.

    Supports multiple output formats and styles, with settings inheritance
    from global defaults through command-specific to runtime flags.
    """

    def __init__(self, settings: Optional[RenderSettings] = None):
        """
        Initialize the renderer.

        Args:
            settings: Render settings to use (defaults to RenderSettings())
        """
        self.settings = settings or RenderSettings()

    def render_emoji(self, emoji_id: Optional[int], emoji_name: str, animated: bool = False) -> str:
        """
        Render an emoji for display.

        Args:
            emoji_id: The emoji ID (None for unicode)
            emoji_name: The emoji name or unicode character
            animated: Whether the emoji is animated

        Returns:
            Formatted emoji string
        """
        if emoji_id:
            # Custom emoji
            prefix = 'a' if animated else ''
            emoji_str = f"<{prefix}:{emoji_name}:{emoji_id}>"

            if self.settings.show_ids:
                return f"{emoji_str} (`{emoji_id}`)"
            return emoji_str
        else:
            # Unicode emoji
            return emoji_name

    def render_tie_group(self, users: list[tuple[int, str]], max_display: int = 3) -> str:
        """
        Render a group of tied users.

        Args:
            users: List of (user_id, display_name) tuples
            max_display: Maximum users to show before "and X others"

        Returns:
            Formatted string for tied users
        """
        if self.settings.tie_grouping == TieGrouping.LIST_ALL:
            return ", ".join(name for _, name in users)

        # GROUP mode
        if len(users) <= max_display:
            return ", ".join(name for _, name in users)

        shown = [name for _, name in users[:max_display]]
        remaining = len(users) - max_display

        if len(shown) == 1:
            return f"{shown[0]} and {remaining} others"
        else:
            return f"{', '.join(shown[:-1])}, {shown[-1]}, and {remaining} others"

    def render_leaderboard_entry(
        self,
        rank: int,
        emoji_id: Optional[int],
        emoji_name: str,
        count: int,
        total: int,
        animated: bool = False,
        tied_users: Optional[list[tuple[int, str]]] = None
    ) -> str:
        """Render a single leaderboard entry."""
        emoji_str = self.render_emoji(emoji_id, emoji_name, animated)
        percentage = (count / total * 100) if total > 0 else 0

        if self.settings.compact_mode:
            result = f"{rank}. {emoji_str} ({count:,})"
            if self.settings.show_percentages:
                result += f" {percentage:.1f}%"
            return result

        # Standard format
        line = f"**{rank}.** {emoji_str} — **{count:,}** uses"
        if self.settings.show_percentages:
            line += f" ({percentage:.1f}%)"

        if tied_users:
            tie_str = self.render_tie_group(tied_users)
            line += f"\n    *(Tie: {tie_str})*"

        return line

    def render_user_leaderboard_entry(
        self,
        rank: int,
        user_id: int,
        user_name: str,
        count: int,
        total: int,
        signature_emoji: Optional[str] = None
    ) -> str:
        """Render a user leaderboard entry."""
        percentage = (count / total * 100) if total > 0 else 0

        if self.settings.compact_mode:
            result = f"{rank}. {user_name} ({count:,})"
            if signature_emoji:
                result = f"{rank}. {signature_emoji} {user_name} ({count:,})"
            return result

        # Standard format
        header = f"**{rank}.** {user_name}"
        if signature_emoji:
            header = f"**{rank}.** {signature_emoji} {user_name}"

        line = f"{header} — **{count:,}** uses"
        if self.settings.show_percentages:
            line += f" ({percentage:.1f}%)"

        return line

    def render_leaderboard(
        self,
        entries: list[dict],
        total: int,
        leaderboard_type: str = "emoji",
        start_rank: int = 1
    ) -> str:
        """Render a full leaderboard."""
        if not entries:
            return "*No data found for the specified filters.*"

        lines = []

        for i, entry in enumerate(entries, start_rank):
            if leaderboard_type == "emoji":
                line = self.render_leaderboard_entry(
                    rank=i,
                    emoji_id=entry.get('emoji_id'),
                    emoji_name=entry.get('emoji_name', '?'),
                    count=entry.get('count', 0),
                    total=total,
                    animated=entry.get('animated', False),
                    tied_users=entry.get('tied_users')
                )
            else:  # user leaderboard
                line = self.render_user_leaderboard_entry(
                    rank=i,
                    user_id=entry.get('user_id', 0),
                    user_name=entry.get('user_name', 'Unknown'),
                    count=entry.get('count', 0),
                    total=total,
                    signature_emoji=entry.get('signature_emoji')
                )

            lines.append(line)

        if self.settings.compact_mode:
            return " | ".join(lines)

        return "\n".join(lines)

    def render_comparison(
        self,
        entity_a: dict,
        entity_b: dict,
        comparison_type: str = "emoji"
    ) -> str:
        """Render a side-by-side comparison."""
        count_a = entity_a.get('count', 0)
        count_b = entity_b.get('count', 0)
        name_a = entity_a.get('name', 'Entity A')
        name_b = entity_b.get('name', 'Entity B')

        total = count_a + count_b
        pct_a = (count_a / total * 100) if total > 0 else 50
        pct_b = (count_b / total * 100) if total > 0 else 50

        # Determine winner
        if count_a > count_b:
            diff = ((count_a - count_b) / count_b * 100) if count_b > 0 else 100
            victory = f"**{name_a}** leads by **{diff:.1f}%**"
        elif count_b > count_a:
            diff = ((count_b - count_a) / count_a * 100) if count_a > 0 else 100
            victory = f"**{name_b}** leads by **{diff:.1f}%**"
        else:
            victory = "**It's a tie!**"

        lines = [
            f"**{name_a}**: {count_a:,} ({pct_a:.1f}%)",
            f"**{name_b}**: {count_b:,} ({pct_b:.1f}%)",
            "",
            victory
        ]

        return "\n".join(lines)


def merge_settings(
    global_settings: Optional[dict],
    command_settings: Optional[dict],
    runtime_flags: Optional[dict]
) -> RenderSettings:
    """Merge settings with inheritance: Runtime → Command → Global → Defaults."""
    defaults = RenderSettings()
    result = {}

    # Start with defaults
    for field_name in ['show_ids', 'show_percentages', 'compact_mode', 'tie_grouping']:
        result[field_name] = getattr(defaults, field_name)

    # Apply global settings
    if global_settings:
        for key, value in global_settings.items():
            if value is not None and key in result:
                result[key] = value

    # Apply command settings
    if command_settings:
        for key, value in command_settings.items():
            if value is not None and key in result:
                result[key] = value

    # Apply runtime flags (highest priority)
    if runtime_flags:
        for key, value in runtime_flags.items():
            if value is not None and key in result:
                result[key] = value

    return RenderSettings(**result)
