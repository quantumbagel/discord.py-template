import discord
from typing import Optional, Union, List, Dict, Any
from datetime import datetime
from utilities.config import get_config

class BaseEmbedTemplate:
    """Base class for all embed templates with common configuration handling."""
    
    def __init__(self, config=None):
        self.config = config or get_config()
        self._embed = discord.Embed()
    
    def _get_color(self, color_type: str) -> int:
        """Get a color from the configuration or return a default."""
        try:
            return self.config.style.embed_colors.get(color_type, 0x5865F2)
        except (AttributeError, KeyError):
            # Fallback colors if config is not available
            fallback_colors = {
                'default': 0x5865F2,
                'success': 0x57F287,
                'error': 0xED4245,
                'warning': 0xFEE75C,
                'info': 0x539bf5
            }
            return fallback_colors.get(color_type, 0x5865F2)
    
    def _get_emoji(self, emoji_name: str) -> str:
        """Get an emoji from the configuration or return a default."""
        try:
            return self.config.style.emojis.get(emoji_name, "")
        except (AttributeError, KeyError):
            # Fallback emojis if config is not available
            fallback_emojis = {
                'loading': '⏳',
                'success': '✅',
                'error': '❌',
                'info': 'ℹ️'
            }
            return fallback_emojis.get(emoji_name, "")
    
    def set_color(self, color: Union[str, int, discord.Color]) -> 'BaseEmbedTemplate':
        """Set the embed color. Can be a color type string, hex int, or discord.Color."""
        if isinstance(color, str):
            self._embed.color = self._get_color(color)
        elif isinstance(color, int):
            self._embed.color = color
        elif isinstance(color, discord.Color):
            self._embed.color = color.value
        return self
    
    def set_title(self, title: str, url: Optional[str] = None) -> 'BaseEmbedTemplate':
        """Set the embed title and optional URL."""
        self._embed.title = title
        if url:
            self._embed.url = url
        return self
    
    def set_description(self, description: str) -> 'BaseEmbedTemplate':
        """Set the embed description."""
        self._embed.description = description
        return self
    
    def add_field(self, name: str, value: str, inline: bool = False) -> 'BaseEmbedTemplate':
        """Add a field to the embed."""
        self._embed.add_field(name=name, value=value, inline=inline)
        return self
    
    def set_author(self, name: str, icon_url: Optional[str] = None, url: Optional[str] = None) -> 'BaseEmbedTemplate':
        """Set the embed author."""
        self._embed.set_author(name=name, icon_url=icon_url, url=url)
        return self
    
    def set_footer(self, text: str, icon_url: Optional[str] = None) -> 'BaseEmbedTemplate':
        """Set the embed footer."""
        self._embed.set_footer(text=text, icon_url=icon_url)
        return self
    
    def set_thumbnail(self, url: str) -> 'BaseEmbedTemplate':
        """Set the embed thumbnail."""
        self._embed.set_thumbnail(url=url)
        return self
    
    def set_image(self, url: str) -> 'BaseEmbedTemplate':
        """Set the embed image."""
        self._embed.set_image(url=url)
        return self
    
    def set_timestamp(self, timestamp: Optional[datetime] = None) -> 'BaseEmbedTemplate':
        """Set the embed timestamp. Defaults to current time if None."""
        self._embed.timestamp = timestamp or datetime.utcnow()
        return self
    
    def _apply_kwargs(self, kwargs: Dict[str, Any]) -> 'BaseEmbedTemplate':
        """Apply additional keyword arguments to the embed."""
        for key, value in kwargs.items():
            if key == 'fields' and isinstance(value, list):
                for field in value:
                    if isinstance(field, dict):
                        self.add_field(
                            name=field.get('name', 'Field'),
                            value=field.get('value', 'Value'),
                            inline=field.get('inline', False)
                        )
            elif key == 'footer':
                if isinstance(value, dict):
                    self.set_footer(text=value.get('text', ''), icon_url=value.get('icon_url'))
                else:
                    self.set_footer(text=str(value))
            elif key == 'author':
                if isinstance(value, dict):
                    self.set_author(
                        name=value.get('name', ''),
                        icon_url=value.get('icon_url'),
                        url=value.get('url')
                    )
                else:
                    self.set_author(name=str(value))
            elif key == 'thumbnail':
                self.set_thumbnail(url=str(value))
            elif key == 'image':
                self.set_image(url=str(value))
        
        return self
    
    def build(self) -> discord.Embed:
        """Build and return the final embed."""
        return self._embed


class SuccessEmbed(BaseEmbedTemplate):
    """Template for success embeds with green color and success emoji."""
    
    def __init__(self, title: str = "Success", description: str = None, config=None, **kwargs):
        super().__init__(config)
        emoji = self._get_emoji('success')
        formatted_title = f"{emoji} {title}" if emoji else title
        
        self.set_color('success')
        self.set_title(formatted_title)
        self.set_timestamp()
        
        if description:
            self.set_description(description)
        
        self._apply_kwargs(kwargs)


class ErrorEmbed(BaseEmbedTemplate):
    """Template for error embeds with red color and error emoji."""
    
    def __init__(self, title: str = "Error", description: str = None, config=None, **kwargs):
        super().__init__(config)
        emoji = self._get_emoji('error')
        formatted_title = f"{emoji} {title}" if emoji else title
        
        self.set_color('error')
        self.set_title(formatted_title)
        self.set_timestamp()
        
        if description:
            self.set_description(description)
        
        self._apply_kwargs(kwargs)


class WarningEmbed(BaseEmbedTemplate):
    """Template for warning embeds with yellow color."""
    
    def __init__(self, title: str = "Warning", description: str = None, config=None, **kwargs):
        super().__init__(config)
        
        self.set_color('warning')
        self.set_title(f"⚠️ {title}")
        self.set_timestamp()
        
        if description:
            self.set_description(description)
        
        self._apply_kwargs(kwargs)


class InfoEmbed(BaseEmbedTemplate):
    """Template for info embeds with blue color and info emoji."""
    
    def __init__(self, title: str = "Information", description: str = None, config=None, **kwargs):
        super().__init__(config)
        emoji = self._get_emoji('info')
        formatted_title = f"{emoji} {title}" if emoji else title
        
        self.set_color('info')
        self.set_title(formatted_title)
        self.set_timestamp()
        
        if description:
            self.set_description(description)
        
        self._apply_kwargs(kwargs)


class LoadingEmbed(BaseEmbedTemplate):
    """Template for loading embeds with default color and loading emoji."""
    
    def __init__(self, title: str = "Loading...", description: str = None, config=None, **kwargs):
        super().__init__(config)
        emoji = self._get_emoji('loading')
        formatted_title = f"{emoji} {title}" if emoji else title
        
        self.set_color('default')
        self.set_title(formatted_title)
        
        if description:
            self.set_description(description)
        
        self._apply_kwargs(kwargs)


class CommandHelpEmbed(BaseEmbedTemplate):
    """Template for command help embeds."""
    
    def __init__(self, command_name: str, description: str, usage: str = None, 
                 aliases: List[str] = None, config=None, **kwargs):
        super().__init__(config)
        
        self.set_color('info')
        self.set_title(f"Command: {command_name}")
        self.set_description(description)
        self.set_timestamp()
        
        if usage:
            self.add_field(name="Usage", value=f"`{usage}`", inline=False)
        
        if aliases:
            self.add_field(name="Aliases", value=", ".join([f"`{alias}`" for alias in aliases]), inline=False)
        
        self._apply_kwargs(kwargs)


class UserInfoEmbed(BaseEmbedTemplate):
    """Template for user information embeds."""
    
    def __init__(self, user: discord.Member, config=None, **kwargs):
        super().__init__(config)
        
        self.set_color('default')
        self.set_title("User Information")
        self.set_thumbnail(user.display_avatar.url)
        self.set_timestamp()
        
        self.add_field(name="Username", value=str(user), inline=True)
        self.add_field(name="ID", value=str(user.id), inline=True)
        self.add_field(name="Created", value=f"<t:{int(user.created_at.timestamp())}:F>", inline=False)
        self.add_field(name="Joined", value=f"<t:{int(user.joined_at.timestamp())}:F>", inline=False)
        
        if user.premium_since:
            self.add_field(name="Nitro Booster Since", value=f"<t:{int(user.premium_since.timestamp())}:F>", inline=False)
        
        self._apply_kwargs(kwargs)


class ServerInfoEmbed(BaseEmbedTemplate):
    """Template for server information embeds."""
    
    def __init__(self, guild: discord.Guild, config=None, **kwargs):
        super().__init__(config)
        
        self.set_color('default')
        self.set_title(f"Server Information: {guild.name}")
        self.set_timestamp()
        
        self.add_field(name="Owner", value=str(guild.owner), inline=True)
        self.add_field(name="Members", value=str(guild.member_count), inline=True)
        self.add_field(name="Created", value=f"<t:{int(guild.created_at.timestamp())}:F>", inline=False)
        self.add_field(name="Boost Level", value=str(guild.premium_tier), inline=True)
        self.add_field(name="Boost Count", value=str(guild.premium_subscription_count), inline=True)
        
        if guild.icon:
            self.set_thumbnail(guild.icon.url)
        
        self._apply_kwargs(kwargs)


class CustomEmbed(BaseEmbedTemplate):
    """Template for fully customizable embeds."""
    
    def __init__(self, config=None):
        super().__init__(config)
        self.set_color('default')


# Convenience functions for quick access
def success_embed(title: str = "Success", description: str = None, config=None, **kwargs) -> discord.Embed:
    """Quick function to create a success embed."""
    return SuccessEmbed(title, description, config, **kwargs).build()

def error_embed(title: str = "Error", description: str = None, config=None, **kwargs) -> discord.Embed:
    """Quick function to create an error embed."""
    return ErrorEmbed(title, description, config, **kwargs).build()

def warning_embed(title: str = "Warning", description: str = None, config=None, **kwargs) -> discord.Embed:
    """Quick function to create a warning embed."""
    return WarningEmbed(title, description, config, **kwargs).build()

def info_embed(title: str = "Information", description: str = None, config=None, **kwargs) -> discord.Embed:
    """Quick function to create an info embed."""
    return InfoEmbed(title, description, config, **kwargs).build()

def loading_embed(title: str = "Loading...", description: str = None, config=None, **kwargs) -> discord.Embed:
    """Quick function to create a loading embed."""
    return LoadingEmbed(title, description, config, **kwargs).build()

def command_help_embed(command_name: str, description: str, usage: str = None, 
                      aliases: List[str] = None, config=None, **kwargs) -> discord.Embed:
    """Quick function to create a command help embed."""
    return CommandHelpEmbed(command_name, description, usage, aliases, config, **kwargs).build()

def user_info_embed(user: discord.Member, config=None, **kwargs) -> discord.Embed:
    """Quick function to create a user info embed."""
    return UserInfoEmbed(user, config, **kwargs).build()

def server_info_embed(guild: discord.Guild, config=None, **kwargs) -> discord.Embed:
    """Quick function to create a server info embed."""
    return ServerInfoEmbed(guild, config, **kwargs).build()

def custom_embed(config=None) -> CustomEmbed:
    """Create a new custom embed instance."""
    return CustomEmbed(config)