import dataclasses
import logging
import re
from typing import Dict, Iterator, Optional, Tuple, Union

import discord
from box import Box
from discord.ext import commands
from ruamel.yaml import YAML


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
    Loads a YAML configuration file and returns it as a Box object,
    allowing attribute-style access (e.g., config.database.host).


    Returns:
        Box: The configuration as a dot-accessible object.

    Raises:
        FileNotFoundError: If the file is not found.
        yaml.YAMLError: If the file is not a valid YAML.
    """
    logger = logging.getLogger("template.configuration")
    file_path = 'configuration/config.yaml'
    yaml = YAML(typ='safe')  # typ='safe' is the default and recommended
    try:
        with open(file_path, 'r') as file:
            config_dict = yaml.load(file)
            # Convert the dictionary to a Box object
            # frozen_box=True makes the object immutable (read-only)
            # which is good practice for configs.
            if not config_dict:
                logger.critical(f"Error: The config file at '{file_path}' is empty. I don't know WHY you did that, "
                                f"but you did I guess.")
                raise ValueError("Config file is empty.")
            config_box = Box(config_dict, frozen_box=True, default_box=True, default_box_attr=None)
            return config_box
    except FileNotFoundError:
        logger.critical(f"Error: The config file at '{file_path}' was not found. You need to create one.")
        raise
    except Exception as e:
        logger.critical(f"Error parsing or converting YAML file: {e}")
        raise
