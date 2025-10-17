import dataclasses
import logging
from typing import List
from discord.ext import commands

@dataclasses.dataclass
class CogTemplate:
    """A standardized template for Cog metadata."""
    name: str  # The display name of the cog
    description: str = "No description provided."  # A brief description of the cog's purpose
    category: str = "Miscellaneous"  # Category for help commands (e.g., "Moderation", "Fun")
    version: str = "1.0.0"  # The cog's version
    authors: List[str] = dataclasses.field(default_factory=list)  # List of authors
    emoji: str = "⚙️"  # An emoji to represent the cog
    enabled: bool = True  # A flag to easily disable the cog's commands or loading


class ImprovedCog(commands.Cog):
    """
    A modified Cog class that requires a 'template' attribute to be set.

    The template must be an instance of the CogTemplate dataclass, providing
    standardized metadata for each cog.
    """
    # Type hint to show developers what is expected
    template: CogTemplate = None

    def __init__(self, bot: 'BotTemplate', logger: logging.Logger = None):
        self.bot = bot
        self.logger = logger

        # Ensure template used
        if not self.template or not isinstance(self.template, CogTemplate):
            raise NotImplementedError(
                f"The cog '{self.__class__.__name__}' must have a 'template' class attribute "
                f"that is an instance of CogTemplate."
            )
