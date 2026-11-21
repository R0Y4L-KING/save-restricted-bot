import asyncio
import time
from datetime import datetime

from pyrogram import Client, filters, enums
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from config import ADMINS
from database.db import db
from logger import LOGGER

logger = LOGGER(__name__)

# admin_id -> "broadcast" | "addpremium" | "removepremium"
ADMIN_STATE = {}

PANEL_TEXT = (
    "<b>🛠 Admin Panel</b>\n\n"
    "<blockquote>Neeche se option chuno 👇</blockquote>"
)


def panel_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Stats", callback_data="adm:stats")],
        [InlineKeyboardButton("🧾 Pending Orders", callback_data="adm:pending")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="adm:bc")],
        [InlineKeyboardButton("➕ Add Premium", callback_data="adm:add")],
        [InlineKeyboardButton("➖ Remove Premium", callback_data="adm:rem")],
    ])


async def _stats_text():
    try:
        s = await db.bot_stats()
    except Exception as e:
        return f"❌ Stats failed: <code>{e}</code>"
    return (
        "<b>📊 Bot Stats</b>\n\n"
        f"👥 <b>Total users:</b> <code>{s['total']}</code>\n"
        f"🆕 <b>New today:</b> <code>{s['new_today']}</code>\n"
        f"✅ <b>Verified now:</b> <code>{s['verified']}</code>\n"
        f"💎 <b>Premium active:</b> <code>{s['premium']}</code>\n\n"
        f"🧾 <b>Orders:</b> <code>{s['orders']}</code> "
        f"(pending <code>{s['pending']}</code>, approved <code>{s['approved']}</code>)\n"
        f"💰 <b>Revenue:</b> <code>₹{s['revenue']}</code>\n\n"
        f"🗄 <b>DB:</b> MongoDB"
    )


# ======================================================
# /admin panel
# ======================================================
@Client.on_message(filters.command(["admin", "panel"]) & filters.user(ADMINS) & filters.private)
async def admin_panel(client: Client, message: Message):
    await message.reply_text(PANEL_TEXT, reply_markup=panel_markup(),
                             parse_mode=enums.ParseMode.HTML)


@Client.on_message(filters.command(["stats", "users"]) & filters.user(ADMINS) & filters.private)
async def admin_stats(client: Client, message: Message):
    await message.reply_text(await _stats_text(), parse_mode=enums.ParseMode.HTML)


@Client.on_message(filters.command("canceladmin") & filters.user(ADMINS) & filters.private)
async def admin_cancel(client: Client, message: Message):
    ADMIN_STATE.pop(message.from_user.id, None)
    await message.reply_text("✅ Admin action cancel ho gaya.")


@Client.on_callback_query(filters.regex(r"^adm:"))
async def admin_callbacks(client: Client, cq: CallbackQuery):
    if cq.from_user.id not in ADMINS:
        return await cq.answer("Sirf admin.", show_alert=True)

    action = cq.data.split(":", 1)[1]
    chat_id = cq.message.chat.id

    if action == "stats":
        await cq.answer()
        return await client.send_message(chat_id, await _stats_text(),
                                         parse_mode=enums.ParseMode.HTML)

    if action == "pending":
        await cq.answer()
        orders = await db.pending_orders(10)
        if not orders:
            return await client.send_message(
                chat_id, "✅ Koi pending order nahi hai.")
        lines = ["<b>🧾 Pending orders</b>\n"]
        for o in orders:
            lines.append(
                f"• <code>{o['_id']}</code> — ₹{o.get('price')} — "
                f"user <code>{o.get('user_id')}</code> — UTR "
                f"<code>{o.get('utr', '')}</code>")
        return await client.send_message(chat_id, "\n".join(lines),
                                         parse_mode=enums.ParseMode.HTML)

    if action == "bc":
        ADMIN_STATE[cq.from_user.id] = "broadcast"
        await cq.answer()
        return await client.send_message(
            chat_id,
            "📢 Jo message broadcast karna hai wo ab bhejo (text / photo / video / document).\n\n"
            "<i>Cancel karne ke liye /canceladmin</i>",
            parse_mode=enums.ParseMode.HTML)

    if action == "add":
        ADMIN_STATE[cq.from_user.id] = "addpremium"
        await cq.answer()
        return await client.send_message(
            chat_id,
            "➕ Format: <code>user_id days</code>\n\n"
            "Jaise: <code>123456789 30</code>  (0 = lifetime)",
            parse_mode=enums.ParseMode.HTML)

    if action == "rem":
        ADMIN_STATE[cq.from_user.id] = "removepremium"
        await cq.answer()
        return await client.send_message(
            chat_id, "➖ Jis user ka premium hatana hai uska <code>user_id</code> bhejo.",
            parse_mode=enums.ParseMode.HTML)

    await cq.answer()


# ======================================================
# Admin input router (called from start.py's save())
# ======================================================
async def _broadcast(client: Client, admin_chat_id, from_chat_id, message_id):
    ids = await db.all_user_ids()
    ok = fail = 0
    for uid in ids:
        try:
            await client.copy_message(uid, from_chat_id, message_id)
            ok += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)
    await client.send_message(
        admin_chat_id,
        f"<b>📢 Broadcast done</b>\n\n"
        f"✅ Sent: <code>{ok}</code>\n"
        f"❌ Failed: <code>{fail}</code>\n"
        f"👥 Total: <code>{len(ids)}</code>",
        parse_mode=enums.ParseMode.HTML)


async def handle_admin_input(client: Client, message: Message):
    action = ADMIN_STATE.pop(message.from_user.id, None)
    if not action:
        return False

    chat_id = message.chat.id

    if action == "broadcast":
        await message.reply_text("📢 Broadcast shuru ho gaya... result baad me bhejta hoon.")
        asyncio.create_task(
            _broadcast(client, chat_id, message.chat.id, message.id))
        return True

    text = (message.text or "").strip()

    if action == "addpremium":
        parts = text.split()
        if len(parts) != 2:
            await message.reply_text("❌ Format: <code>user_id days</code>",
                                     parse_mode=enums.ParseMode.HTML)
            return True
        try:
            uid, days = int(parts[0]), int(parts[1])
        except ValueError:
            await message.reply_text("❌ Numbers hone chahiye. Jaise <code>123456789 30</code>",
                                     parse_mode=enums.ParseMode.HTML)
            return True
        expiry = await db.grant_premium_days(uid, days)
        when = "Lifetime" if expiry is None else expiry
        await message.reply_text(
            f"✅ <code>{uid}</code> ko {days if days else 'lifetime'} din ka premium diya.\n"
            f"Expiry: <code>{when}</code>",
            parse_mode=enums.ParseMode.HTML)
        try:
            await client.send_message(
                uid,
                "<b>🎉 Premium Activated!</b>\n\n"
                f"<blockquote>Your plan is {when}.</blockquote>",
                parse_mode=enums.ParseMode.HTML)
        except Exception:
            pass
        return True

    if action == "removepremium":
        try:
            uid = int(text)
        except ValueError:
            await message.reply_text("❌ user_id number hona chahiye.")
            return True
        await db.remove_premium(uid)
        await message.reply_text(f"✅ <code>{uid}</code> ka premium hata diya.")
        try:
            await client.send_message(
                uid, "<b>ℹ️ Premium Removed</b>\n\n<i>Renew anytime with /premium.</i>",
                parse_mode=enums.ParseMode.HTML)
        except Exception:
            pass
        return True

    return True


# ======================================================
# Quick commands (/grant, /revoke)
# ======================================================
@Client.on_message(filters.command("grant") & filters.user(ADMINS) & filters.private)
async def cmd_grant(client: Client, message: Message):
    """/grant <user_id> <days>   (0 = lifetime)"""
    parts = (message.text or "").split()
    if len(parts) != 3:
        return await message.reply_text("Use: <code>/grant user_id days</code>",
                                        parse_mode=enums.ParseMode.HTML)
    try:
        uid, days = int(parts[1]), int(parts[2])
    except ValueError:
        return await message.reply_text("user_id aur days number hone chahiye.")
    expiry = await db.grant_premium_days(uid, days)
    when = "Lifetime" if expiry is None else expiry
    await message.reply_text(f"✅ <code>{uid}</code> → {when}",
                             parse_mode=enums.ParseMode.HTML)
    try:
        await client.send_message(
            uid, f"<b>🎉 Premium Activated!</b>\n\n<blockquote>Your plan is {when}.</blockquote>",
            parse_mode=enums.ParseMode.HTML)
    except Exception:
        pass


@Client.on_message(filters.command("revoke") & filters.user(ADMINS) & filters.private)
async def cmd_revoke(client: Client, message: Message):
    parts = (message.text or "").split()
    if len(parts) != 2:
        return await message.reply_text("Use: <code>/revoke user_id</code>",
                                        parse_mode=enums.ParseMode.HTML)
    try:
        uid = int(parts[1])
    except ValueError:
        return await message.reply_text("user_id number hona chahiye.")
    await db.remove_premium(uid)
    await message.reply_text(f"✅ <code>{uid}</code> ka premium hata diya.")
