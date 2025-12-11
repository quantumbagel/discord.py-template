"""
Emoji extraction utilities for the Emoticon Analytics Bot.

Handles parsing and extracting emojis from messages and reactions.
"""

import re
from dataclasses import dataclass
from typing import Optional
import discord


@dataclass
class ExtractedEmoji:
    """Represents an extracted emoji from a message or reaction."""
    emoji_id: Optional[int]  # None for unicode emojis
    emoji_name: str
    animated: bool = False
    is_external: bool = False
    count: int = 1


class EmojiExtractor:
    """
    Extracts emojis from Discord messages and reactions.

    Handles both custom emojis (<:name:id> or <a:name:id>) and unicode emojis.
    """

    # Regex for custom Discord emojis
    CUSTOM_EMOJI_PATTERN = re.compile(r'<(a)?:(\w+):(\d+)>')

    # Common unicode emoji ranges (simplified)
    UNICODE_EMOJI_PATTERN = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F700-\U0001F77F"  # alchemical symbols
        "\U0001F780-\U0001F7FF"  # Geometric Shapes Extended
        "\U0001F800-\U0001F8FF"  # Supplemental Arrows-C
        "\U0001F900-\U0001F9FF"  # Supplemental Symbols and Pictographs
        "\U0001FA00-\U0001FA6F"  # Chess Symbols
        "\U0001FA70-\U0001FAFF"  # Symbols and Pictographs Extended-A
        "\U00002702-\U000027B0"  # Dingbats
        "\U000024C2-\U0001F251"  # Enclosed characters
        "]+",
        flags=re.UNICODE
    )

    def __init__(self, guild: Optional[discord.Guild] = None):
        """
        Initialize the extractor.

        Args:
            guild: The guild to check for external emojis
        """
        self.guild = guild
        self._guild_emoji_ids: set[int] = set()

        if guild:
            self._guild_emoji_ids = {emoji.id for emoji in guild.emojis}

    def extract_from_message(self, content: str) -> list[ExtractedEmoji]:
        """
        Extract all emojis from a message's content.

        Args:
            content: The message content to parse

        Returns:
            List of ExtractedEmoji objects
        """
        emojis = []

        # Extract custom emojis
        for match in self.CUSTOM_EMOJI_PATTERN.finditer(content):
            animated = match.group(1) is not None
            name = match.group(2)
            emoji_id = int(match.group(3))

            # Check if external (nitro emoji from another server)
            is_external = emoji_id not in self._guild_emoji_ids

            emojis.append(ExtractedEmoji(
                emoji_id=emoji_id,
                emoji_name=name,
                animated=animated,
                is_external=is_external
            ))

        # Extract unicode emojis
        for match in self.UNICODE_EMOJI_PATTERN.finditer(content):
            emoji_char = match.group()
            # Count each unicode emoji character separately
            for char in emoji_char:
                emojis.append(ExtractedEmoji(
                    emoji_id=None,
                    emoji_name=char,
                    animated=False,
                    is_external=False
                ))

        # Consolidate duplicates and count them
        return self._consolidate_emojis(emojis)

    def extract_from_reaction(self, reaction: discord.Reaction) -> ExtractedEmoji:
        """
        Extract emoji info from a reaction.

        Args:
            reaction: The Discord reaction object

        Returns:
            ExtractedEmoji object
        """
        emoji = reaction.emoji

        if isinstance(emoji, discord.PartialEmoji) or isinstance(emoji, discord.Emoji):
            is_external = emoji.id not in self._guild_emoji_ids if emoji.id else False
            return ExtractedEmoji(
                emoji_id=emoji.id,
                emoji_name=emoji.name or "unknown",
                animated=getattr(emoji, 'animated', False),
                is_external=is_external,
                count=reaction.count
            )
        else:
            # Unicode emoji (string)
            return ExtractedEmoji(
                emoji_id=None,
                emoji_name=str(emoji),
                animated=False,
                is_external=False,
                count=reaction.count
            )

    def extract_single(self, emoji: discord.Emoji | discord.PartialEmoji | str) -> ExtractedEmoji:
        """
        Extract info from a single emoji object or string.

        Args:
            emoji: Emoji object or unicode string

        Returns:
            ExtractedEmoji object
        """
        if isinstance(emoji, (discord.Emoji, discord.PartialEmoji)):
            is_external = emoji.id not in self._guild_emoji_ids if emoji.id else False
            return ExtractedEmoji(
                emoji_id=emoji.id,
                emoji_name=emoji.name or "unknown",
                animated=getattr(emoji, 'animated', False),
                is_external=is_external
            )
        else:
            return ExtractedEmoji(
                emoji_id=None,
                emoji_name=str(emoji),
                animated=False,
                is_external=False
            )

    def _consolidate_emojis(self, emojis: list[ExtractedEmoji]) -> list[ExtractedEmoji]:
        """
        Consolidate duplicate emojis and sum their counts.

        Args:
            emojis: List of extracted emojis

        Returns:
            Consolidated list with counts
        """
        consolidated: dict[tuple, ExtractedEmoji] = {}

        for emoji in emojis:
            key = (emoji.emoji_id, emoji.emoji_name)
            if key in consolidated:
                consolidated[key].count += emoji.count
            else:
                consolidated[key] = emoji

        return list(consolidated.values())
