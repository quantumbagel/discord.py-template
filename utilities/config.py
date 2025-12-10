import dataclasses
import logging
import re
from typing import Dict, Iterator, Optional, Tuple, Union, List, Literal

import discord
from box import Box
from discord.ext import commands
from pydantic import BaseModel, Field, ValidationError
from ruamel.yaml import YAML


# --- Configuration Models ---

class BotConfig(BaseModel):
    """Defines the 'bot' section of the config."""
    short_name: str
    full_name: str
    prefix: str
    # Supports a list of IDs, Nones, or a mix.
    owner_ids: List[Optional[int]]
    testing_guild: Optional[int] = None


class LoggingConfig(BaseModel):
    """Defines the 'logging' section."""
    console_level: Literal["debug", "info", "warning", "error", "critical"]
    output_level: Literal["debug", "info", "warning", "error", "critical"]
    output_folder: str


class DatabaseConfig(BaseModel):
    """Defines the 'database' section."""
    url: str


class EmbedColors(BaseModel):
    """Defines the 'embed_colors' sub-section."""
    default: int
    success: int
    error: int
    warning: int
    info: int


class Emojis(BaseModel):
    """Defines the 'emojis' sub-section."""
    loading: str
    success: str
    error: str
    info: str


class StyleConfig(BaseModel):
    """Defines the 'style' section."""
    embed_colors: EmbedColors
    emojis: Emojis


class LinksConfig(BaseModel):
    """Defines the 'links' section."""
    invite_url: Optional[str] = None
    support_server: Optional[str] = None
    github_repo: Optional[str] = None


class CogDetails(BaseModel):
    """Defines the structure for a single cog entry."""
    # We use 'alias' because 'class' is a reserved keyword in Python
    class_name: str = Field(..., alias="class")
    enabled: bool


class Config(BaseModel):
    """
    The main Pydantic model for validating the entire config.yml file.
    """
    bot: BotConfig
    auth: str
    logging: LoggingConfig
    database: DatabaseConfig
    style: StyleConfig
    links: LinksConfig
    # A list where each item is a dictionary, e.g., {"cogs.echo": {...}}
    cogs: List[Dict[str, CogDetails]]


@dataclasses.dataclass
class EmojiMap:
    """
    Manages a map of string aliases to emojis, using a private internal dictionary.
    """
    _aliases: Dict[str, str] = dataclasses.field(default_factory=dict)
    bot: commands.Bot = dataclasses.field(init=False, repr=False)

    def _convert_to_object(self, emoji_str: str) -> Union[discord.Emoji, str]:
        """
        Converts an emoji string to a discord.Emoji object if it's a custom emoji.
        """
        if not hasattr(self, 'bot'):
            return emoji_str

        match = re.search(r'<a?:[a-zA-Z0-9_]+:([0-9]+)>$', emoji_str)
        if match:
            emoji_id = int(match.group(1))
            emoji_obj = self.bot.get_emoji(emoji_id)
            return emoji_obj if emoji_obj else emoji_str

        return emoji_str

    def __getattr__(self, name: str) -> Union[discord.Emoji, str]:
        """Allows accessing emojis as attributes (e.g., emojis.success)."""
        alias = self._aliases.get(name.lower())
        if alias is not None:
            return self._convert_to_object(alias)
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute or emoji alias '{name}'")

    def get(self, alias: str, default: Optional[str] = None) -> Union[discord.Emoji, str, None]:
        """Retrieves an emoji by its alias."""
        emoji_str = self._aliases.get(alias.lower())
        if emoji_str is not None:
            return self._convert_to_object(emoji_str)
        return default

    def __len__(self) -> int:
        return len(self._aliases)

    def __iter__(self) -> Iterator[Tuple[str, Union[discord.Emoji, str]]]:
        for alias, emoji_str in self._aliases.items():
            yield alias, self._convert_to_object(emoji_str)

    def __contains__(self, alias: str) -> bool:
        return alias.lower() in self._aliases


def get_config() -> Box:
    """
    Loads a YAML configuration file, validates it using Pydantic, and returns it as a Box object.

    Returns:
        Box: The configuration as a dot-accessible object.

    Raises:
        FileNotFoundError: If the file is not found.
        ValidationError: If the config does not match the schema.
    """
    logger = logging.getLogger("template.configuration")
    file_path = 'configuration/config.yaml'
    yaml = YAML(typ='safe')
    
    try:
        with open(file_path, 'r', encoding="utf-8") as file:
            raw_config = yaml.load(file)
            
        if not raw_config:
            logger.critical(f"Error: The config file at '{file_path}' is empty.")
            raise ValueError("Config file is empty.")

        # Validate with Pydantic
        try:
            validated_config = Config(**raw_config)
        except ValidationError as e:
            logger.critical(f"❌ ERROR: Config validation failed:\n{e}")
            raise

        # Convert back to dict (using aliases to keep 'class' key) and then to Box
        # This ensures the rest of the bot continues to work with Box features
        config_dict = validated_config.model_dump(by_alias=True)
        config_box = Box(config_dict, frozen_box=True, default_box=True, default_box_attr=None)
        
        return config_box

    except FileNotFoundError:
        logger.critical(f"Error: The config file at '{file_path}' was not found.")
        raise
    except Exception as e:
        logger.critical(f"Error loading config: {e}")
        raise
