import discord
from discord.ext import commands
from typing import Optional, Union, Any
import logging

logger = logging.getLogger("helpers")


def _prepare_kwargs(
        content: str = None,
        embed: discord.Embed = None,
        view: discord.ui.View = None,
        file: discord.File = None,
        files: list[discord.File] = None,
        attachments: list[discord.Attachment] = None,
        delete_after: int | None = None,
        **other_kwargs
) -> dict[str, Any]:
    """Prepare a dictionary of keyword arguments for a Discord message."""
    kwargs: dict[str, Any] = {
        'content': content,
        'embed': embed,
        'view': view,
        'delete_after': delete_after,
    }
    kwargs.update(other_kwargs)

    if file:
        kwargs['file'] = file
    elif files:
        kwargs['files'] = files

    if attachments is not None:
        kwargs['attachments'] = attachments

    # Remove None values (but keep empty lists/discord.MISSING)
    return {k: v for k, v in kwargs.items() if v is not None}


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
    kwargs: dict[str, Any] = _prepare_kwargs(
        content=content,
        embed=embed,
        view=view,
        file=file,
        files=files,
        delete_after=delete_after,
        ephemeral=ephemeral
    )

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
                del kwargs['ephemeral']
                logger.debug("Ephemeral flag ignored for context-based message (not supported)")

            # Handle reply flag
            if reply and not delete_original:  # Can't reply to a deleted message
                return await interaction_or_ctx.reply(**kwargs)
            else:
                return await interaction_or_ctx.send(**kwargs)

    except Exception as e:
        logger.error(f"Failed to send response: {e}")
        return None


async def edit(
        message: discord.Message,
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
    Edit a message from a message object.

    Args:
        message: The discord.Message object to edit.
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
    kwargs: dict[str, Any] = _prepare_kwargs(
        content=content,
        embed=embed,
        view=view,
        file=file,
        files=files,
        attachments=attachments,
        delete_after=delete_after
    )

    try:
        return await message.edit(**kwargs)
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