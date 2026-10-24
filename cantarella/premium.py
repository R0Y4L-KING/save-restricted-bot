from pyrogram import Client, filters, enums
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from database.db import db
from config import ADMINS
from datetime import date, datetime, timedelta
from logger import LOGGER

logger = LOGGER(__name__)

# ======================================================
# USER COMMANDS - Professional & Informative
# ======================================================

# /myplan - Detailed Plan & Quota Overview
@Client.on_message(filters.command("myplan") & filters.private)
async def my_plan(client: Client, message: Message):
    user_id = message.from_user.id
    
    # 1. Ensure User Exists (Fixing the 'ensure_user' error manually)
    if not await db.is_user_exist(user_id):
        await db.add_user(user_id, message.from_user.first_name)

    # 2. Fetch User Data Directly from DB
    user_data = await db.col.find_one({'id': user_id})
    
    # Defaults
    is_premium = user_data.get('is_premium', False)
    expiry = user_data.get('premium_expiry')
    daily_usage = user_data.get('daily_usage', 0)
    # Note: total_saves needs to be tracked in your traffic logic to show up here
    total_saves = user_data.get('total_saves', 0) 

    # 3. Generate Status Text
    if is_premium:
        # Premium Logic
        if expiry:
            try:
                # Handle both date objects and ISO strings
                if isinstance(expiry, (date, datetime)):
                    exp_date = expiry
                else:
                    exp_date = date.fromisoformat(str(expiry))
                
                # Calculate days left
                days_left = (exp_date - date.today()).days if isinstance(exp_date, date) else 999
                expiry_text = f"<code>{expiry}</code> ({days_left} days left)"
            except Exception:
                expiry_text = "<code>Active</code>"
        else:
            expiry_text = "<code>Permanent</code>"

        plan_text = (
            f"<b>👑 Premium Status: Active</b>\n\n"
            f"<b>📅 Expiry:</b> {expiry_text}\n\n"
            f"<b>♾️ Daily Tokens:</b> Unlimited\n"
            f"<b>♾️ Batch Limit:</b> Unlimited\n"
            f"<b>📊 Total Lifetime Saves:</b> <code>{total_saves}</code>\n\n"
            "<i>Thank you for supporting the bot! 🎉</i>"
        )
    else:
        # Free Logic
        daily_limit = 10
        tokens_left = max(0, daily_limit - daily_usage)
        
        plan_text = (
            f"<b>👤 Plan: Free Tier</b>\n\n"
            f"<b>🎫 Daily Tokens:</b> <code>{tokens_left} / {daily_limit}</code>\n"
            f"<b>📦 File Size Limit:</b> <code>2 GB</code>\n"
            f"<b>📊 Total Lifetime Saves:</b> <code>{total_saves}</code>\n\n"
            "<i>Upgrade to Premium for unlimited access! 🚀</i>"
        )

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 View Premium Plans", callback_data="premium_plans_btn")],
        [InlineKeyboardButton("📞 Contact Admin", url="https://t.me/about_zani")]
    ])

    await message.reply_text(
        plan_text,
        reply_markup=buttons,
        parse_mode=enums.ParseMode.HTML
    )

# /premium - Premium Plans Information
@Client.on_message(filters.command("premium") & filters.private)
async def premium_info(client: Client, message: Message):
    await show_premium_plans(message)

# ======================================================
# PREMIUM PLANS VIEW (Reusable)
# ======================================================

async def show_premium_plans(message_or_query):
    text = (
        "<b>💎Premium Plans</b>\n\n"
        "<blockquote>\n"
        "<b>Why Go Premium?</b>\n"
        "• ♾️ <b>Unlimited</b> Daily Saves\n"
        "• 📂 <b>4GB+</b> File Support\n"
        "• ⚡ <b>Zero</b> Processing Delay\n"
        "• 🖼 <b>Custom</b> Thumbnails & Captions\n"
        "• 👑 <b>Premium</b> Badge\n"
        "</blockquote>\n\n"
        "<b>💲 Pricing:</b>\n"
        "• <b>1 Month:</b> ₹50 / $1\n"
        "• <b>Lifetime:</b> ₹200 / $4\n\n"
        "<i>Tap the button below to buy instantly.</i>"
    )

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 Buy Premium Now", url="https://t.me/DmOwner")],
        [InlineKeyboardButton("⬅️ Back to My Plan", callback_data="myplan_back_btn")]
    ])

    if isinstance(message_or_query, Message):
        await message_or_query.reply_text(
            text,
            reply_markup=buttons,
            parse_mode=enums.ParseMode.HTML,
            disable_web_page_preview=True
        )
    else:
        await message_or_query.edit_message_text(
            text,
            reply_markup=buttons,
            parse_mode=enums.ParseMode.HTML,
            disable_web_page_preview=True
        )

# ======================================================
# ADMIN COMMANDS - Secure & Detailed
# ======================================================

@Client.on_message(filters.command("add_premium") & filters.user(ADMINS) & filters.private)
async def add_premium_admin(client: Client, message: Message):
    if len(message.command) < 3:
        return await message.reply_text(
            "<b>⚠️ Admin Usage:</b>\n"
            "<code>/add_premium &lt;user_id&gt; &lt;days&gt;</code>\n\n"
            "<i>Use 0 for permanent premium.</i>",
            parse_mode=enums.ParseMode.HTML
        )

    try:
        user_id = int(message.command[1])
        days = int(message.command[2])

        if days == 0:
            expiry_date = None
            duration_text = "Permanent"
        else:
            expiry_date = (date.today() + timedelta(days=days)).isoformat()
            duration_text = f"{days} days (until {expiry_date})"

        # Update DB
        await db.add_premium(user_id, expiry_date)

        await message.reply_text(
            f"<b>✅ Premium Added Successfully</b>\n\n"
            f"<b>User ID:</b> <code>{user_id}</code>\n"
            f"<b>Duration:</b> {duration_text}",
            parse_mode=enums.ParseMode.HTML
        )

    except ValueError:
        await message.reply_text("❌ <b>Error:</b> User ID and Days must be numbers.", parse_mode=enums.ParseMode.HTML)
    except Exception as e:
        await message.reply_text(f"❌ <b>Error:</b> {e}", parse_mode=enums.ParseMode.HTML)

@Client.on_message(filters.command("remove_premium") & filters.user(ADMINS) & filters.private)
async def remove_premium_admin(client: Client, message: Message):
    if len(message.command) < 2:
        return await message.reply_text(
            "<b>⚠️ Usage:</b> <code>/remove_premium &lt;user_id&gt;</code>",
            parse_mode=enums.ParseMode.HTML
        )
    try:
        user_id = int(message.command[1])
        await db.remove_premium(user_id)
        await message.reply_text(f"✅ Premium removed from <code>{user_id}</code>.")
    except Exception as e:
        await message.reply_text(f"Error: {e}")

# ======================================================
# CALLBACK QUERIES
# ======================================================

@Client.on_callback_query(filters.regex("^premium_plans_btn$"))
async def premium_plans_callback(client: Client, callback_query: CallbackQuery):
    await show_premium_plans(callback_query)

@Client.on_callback_query(filters.regex("^myplan_back_btn$"))
async def myplan_back_callback(client: Client, callback_query: CallbackQuery):
    # Pass the message object to reuse logic
    await my_plan(client, callback_query.message)
