import discord
from discord.ext import commands
from typing import Optional, Union
import logging

logger = logging.getLogger("helpers")


async def send(
        interaction_or_ctx: Union[discord.Interaction, commands.Context],
        content: str = None,
        *,
        embed: discord.Embed = None,
        view: discord.ui.View = None,
        file: discord.File = None,
        files: list[discord.File] = None,
        ephemeral: bool = True,
        delete_after: int | None = None,
        reply: bool = False,
        delete_original: bool = False,
) -> Optional[discord.Message]:
    """
    Respond to an interaction or context with an ephemeral message.
    Automatically handles whether to use respond() or followup() for interactions.

    Args:
        interaction_or_ctx: Discord interaction or commands context
        content: Message content
        embed: Discord embed
        view: Discord view with components
        file: Single file attachment
        files: Multiple file attachments
        ephemeral: Whether the message should be ephemeral (default True)
        delete_after: how long to delete the message after sending it (default None)
        reply: Whether to reply to the original message (only for Context, ignored for Interactions)
        delete_original: Whether to delete the original message (only for Context, ignored for Interactions)

    Returns:
        The sent message if possible, None otherwise
    """
    kwargs = {
        'content': content,
        'embed': embed,
        'view': view,
        'ephemeral': ephemeral,
        'delete_after': delete_after,
    }

    if file:
        kwargs['file'] = file
    elif files:
        kwargs['files'] = files

    # Remove None values
    kwargs = {k: v for k, v in kwargs.items() if v is not None}

    try:
        if isinstance(interaction_or_ctx, discord.Interaction):
            # For interactions, reply and delete_original flags are ignored
            # since interactions don't have a traditional "original message" to reply to or delete
            if interaction_or_ctx.response.is_done():
                return await interaction_or_ctx.followup.send(**kwargs)
            else:
                await interaction_or_ctx.response.send_message(**kwargs)
                return await interaction_or_ctx.original_response()
        else:  # commands.Context
            # Handle delete_original flag first (before sending response)
            if delete_original:
                try:
                    await interaction_or_ctx.message.delete()
                except (discord.NotFound, discord.Forbidden, discord.HTTPException) as e:
                    logger.warning(f"Could not delete original message: {e}")

            # Remove ephemeral from kwargs since Context doesn't support it
            if 'ephemeral' in kwargs:
                logger.warning("Ephemeral flag ignored for context-based message (not supported)")

            # Handle reply flag
            if reply and not delete_original:  # Can't reply to a deleted message
                return await interaction_or_ctx.reply(**kwargs)
            else:
                return await interaction_or_ctx.send(**kwargs)

    except Exception as e:
        logger.error(f"Failed to send response: {e}")
        return None


async def edit(
        interaction_or_ctx_or_message: Union[discord.Interaction, commands.Context, discord.Message],
        content: str = None,
        *,
        embed: discord.Embed = None,
        view: discord.ui.View = None,
        file: discord.File = None,
        files: list[discord.File] = None,
        attachments: list[discord.Attachment] = None,
        delete_after: int | None = None,
) -> Optional[discord.Message]:
    """
    Edit a message from an interaction, context, or direct message object.
    Automatically handles whether to edit the original response or followup for interactions.

    Args:
        interaction_or_ctx_or_message: Discord interaction, commands context, or message object
        content: New message content
        embed: New Discord embed
        view: New Discord view with components
        file: Single file attachment
        files: Multiple file attachments
        attachments: List of attachments to keep (discord.MISSING to remove all)
        delete_after: How long to delete the message after editing it (default None)

    Returns:
        The edited message if possible, None otherwise
    """
    kwargs = {
        'content': content,
        'embed': embed,
        'view': view,
        'delete_after': delete_after,
    }

    if file:
        kwargs['file'] = file
    elif files:
        kwargs['files'] = files

    if attachments is not None:
        kwargs['attachments'] = attachments

    # Remove None values (but keep empty lists/discord.MISSING)
    kwargs = {k: v for k, v in kwargs.items() if v is not None}

    try:
        if isinstance(interaction_or_ctx_or_message, discord.Interaction):
            # For interactions, we need to edit the original response
            if interaction_or_ctx_or_message.response.is_done():
                return await interaction_or_ctx_or_message.edit_original_response(**kwargs)
            else:
                # If response hasn't been sent yet, we can't edit it
                logger.warning("Cannot edit interaction response that hasn't been sent yet")
                return None

        elif isinstance(interaction_or_ctx_or_message, commands.Context):
            # For context, we need a reference to the message to edit
            # This assumes the context has a reference to the bot's last message
            if hasattr(interaction_or_ctx_or_message, 'bot_message') and interaction_or_ctx_or_message.bot_message:
                return await interaction_or_ctx_or_message.bot_message.edit(**kwargs)
            else:
                logger.warning("Context doesn't have a bot_message reference to edit")
                return None

        elif isinstance(interaction_or_ctx_or_message, discord.Message):
            # Direct message editing
            return await interaction_or_ctx_or_message.edit(**kwargs)

        else:
            logger.error(f"Unsupported object type for editing: {type(interaction_or_ctx_or_message)}")
            return None

    except Exception as e:
        logger.error(f"Failed to edit message: {e}")
        return None


async def edit_or_send(
        interaction_or_ctx: Union[discord.Interaction, commands.Context],
        message_to_edit: Optional[discord.Message] = None,
        content: str = None,
        *,
        embed: discord.Embed = None,
        view: discord.ui.View = None,
        file: discord.File = None,
        files: list[discord.File] = None,
        ephemeral: bool = True,
        delete_after: int | None = None,
) -> Optional[discord.Message]:
    """
    Edit an existing message if provided, otherwise send a new one.
    Useful for progress updates where you might not have a message to edit initially.

    Args:
        interaction_or_ctx: Discord interaction or commands context
        message_to_edit: Existing message to edit (if None, sends new message)
        content: Message content
        embed: Discord embed
        view: Discord view with components
        file: Single file attachment
        files: Multiple file attachments
        ephemeral: Whether new messages should be ephemeral (ignored for edits)
        delete_after: How long to delete the message after sending/editing it

    Returns:
        The edited or sent message if possible, None otherwise
    """
    if message_to_edit:
        return await edit(
            message_to_edit,
            content,
            embed=embed,
            view=view,
            file=file,
            files=files,
            delete_after=delete_after
        )
    else:
        return await send(
            interaction_or_ctx,
            content,
            embed=embed,
            view=view,
            file=file,
            files=files,
            ephemeral=ephemeral,
            delete_after=delete_after
        )