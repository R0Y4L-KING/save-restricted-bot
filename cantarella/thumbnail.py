from pyrogram import Client, filters, enums
from pyrogram.types import Message
from database.db import db

# ======================================================
# /set_thumb - Set Custom Thumbnail (Reply to Photo)
# ======================================================
@Client.on_message(filters.command("set_thumb") & filters.private)
async def set_custom_thumbnail(client: Client, message: Message):
    user_id = message.from_user.id
    
    # 1. Ensure User Exists
    if not await db.is_user_exist(user_id):
        await db.add_user(user_id, message.from_user.first_name)

    # 2. Validate Reply
    if not message.reply_to_message or not message.reply_to_message.photo:
        return await message.reply_text(
            "<b>🖼 Set Custom Thumbnail</b>\n\n"
            "<i>Reply to any photo with /set_thumb to use it as your default thumbnail.</i>\n\n"
            "<b>Usage:</b> Reply to a photo → <code>/set_thumb</code>",
            parse_mode=enums.ParseMode.HTML
        )

    # 3. Save File ID to Database (NOT Path)
    # This ensures it works even if the bot restarts
    file_id = message.reply_to_message.photo.file_id
    await db.set_thumbnail(user_id, file_id)

    await message.reply_photo(
        photo=file_id,
        caption=(
            "<b>✅ Custom Thumbnail Set Successfully!</b>\n\n"
            "<i>This thumbnail will be used for all your future uploads.</i>\n"
            "<i>Use /view_thumb to preview • /del_thumb to remove</i>"
        ),
        parse_mode=enums.ParseMode.HTML
    )

# ======================================================
# /view_thumb - Preview Current Thumbnail
# ======================================================
@Client.on_message(filters.command(["view_thumb", "see_thumb"]) & filters.private)
async def view_custom_thumbnail(client: Client, message: Message):
    user_id = message.from_user.id
    
    if not await db.is_user_exist(user_id):
        await db.add_user(user_id, message.from_user.first_name)

    thumb_id = await db.get_thumbnail(user_id)

    if thumb_id:
        try:
            await message.reply_photo(
                photo=thumb_id,
                caption=(
                    "<b>🖼 Your Current Custom Thumbnail</b>\n\n"
                    "<i>This is applied to all uploads.</i>\n"
                    "<i>To delete, use /del_thumb</i>"
                ),
                parse_mode=enums.ParseMode.HTML
            )
        except Exception as e:
            # If file_id is invalid/old
            await message.reply_text(f"<b>❌ Error loading thumbnail:</b> {e}\n<i>Please set a new one.</i>", parse_mode=enums.ParseMode.HTML)
    else:
        await message.reply_text(
            "<b>❌ No Custom Thumbnail Found</b>\n\n"
            "<i>Reply to a photo with /set_thumb to add one.</i>",
            parse_mode=enums.ParseMode.HTML
        )

# ======================================================
# /del_thumb - Remove Custom Thumbnail
# ======================================================
@Client.on_message(filters.command(["del_thumb", "delete_thumb"]) & filters.private)
async def delete_custom_thumbnail(client: Client, message: Message):
    user_id = message.from_user.id
    
    if not await db.is_user_exist(user_id):
        await db.add_user(user_id, message.from_user.first_name)

    thumb_id = await db.get_thumbnail(user_id)

    if not thumb_id:
        return await message.reply_text(
            "<b>ℹ️ You don't have a custom thumbnail set.</b>",
            parse_mode=enums.ParseMode.HTML
        )

    # Remove from DB
    await db.del_thumbnail(user_id)

    await message.reply_text(
        "<b>🗑 Custom Thumbnail Deleted</b>\n\n"
        "<i>Your uploads will now use the default video/file thumbnail.</i>",
        parse_mode=enums.ParseMode.HTML
    )

# ======================================================
# /thumb_mode - Check Status
# ======================================================
@Client.on_message(filters.command("thumb_mode") & filters.private)
async def thumbnail_status(client: Client, message: Message):
    user_id = message.from_user.id
    if not await db.is_user_exist(user_id):
        await db.add_user(user_id, message.from_user.first_name)

    thumb_id = await db.get_thumbnail(user_id)

    if thumb_id:
        status = "<b>🟢 Custom Thumbnail Active</b>"
        extra = "<i>Use /view_thumb to preview</i>"
    else:
        status = "<b>🔴 No Custom Thumbnail</b>"
        extra = "<i>Use /set_thumb (reply to photo) to enable</i>"

    await message.reply_text(
        f"<b>🖼 Thumbnail Status</b>\n\n"
        f"{status}\n"
        f"{extra}",
        parse_mode=enums.ParseMode.HTML
    )
