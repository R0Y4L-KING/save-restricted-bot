import io
import os
import random
import time
from datetime import date, datetime, timedelta

from pyrogram import Client, filters, enums
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from config import ADMINS
from database.db import db
from logger import LOGGER

logger = LOGGER(__name__)

# ======================================================
# Payment config (UPI only)
# ======================================================
UPI_ID = os.environ.get("UPI_ID", "20213904@axl")
UPI_NAME = os.environ.get("UPI_NAME", "ModAppsKing")
# Static fallback QR (used only if the dynamic QR cannot be generated)
QR_CODE = os.environ.get(
    "QR_CODE",
    "https://raw.githubusercontent.com/R0Y4L-KING/save-restricted-bot/main/assets/upi_qr.png",
)
PREMIUM_BANNER = os.environ.get(
    "SUBSCRIPTION", "https://graph.org/file/242b7f1b52743938d81f1.jpg"
)
HELP_LINK = os.environ.get("HELP_LINK", "https://t.me/SANATANI_B0Y")

# ---- Prices: change only here (price / days / label) ----
PLANS = {
    "p15":  {"price": 20,  "days": 15,  "label": "15 Days — ₹20"},
    "p1m":  {"price": 40,  "days": 30,  "label": "1 Month — ₹40"},
    "p2m":  {"price": 70,  "days": 60,  "label": "2 Months — ₹70"},
    "p3m":  {"price": 100, "days": 90,  "label": "3 Months — ₹100"},
    "life": {"price": 180, "days": 0,   "label": "👑 Lifetime — ₹180"},
}

# user_id -> (order_id, started_ts)
PENDING_UTR = {}

PROOF_TTL = 15 * 60  # user has 15 minutes to send the UTR / screenshot


# ======================================================
# Helpers
# ======================================================
def _validity_text(days):
    return "Lifetime" if int(days) == 0 else f"{int(days)} days"


def _upi_qr_bytes(amount, note):
    """Dynamic UPI QR with the amount pre-filled. Returns BytesIO or None."""
    try:
        import qrcode
        from qrcode.image.pil import PilImage

        url = (
            f"upi://pay?pa={UPI_ID}&pn={UPI_NAME}"
            f"&am={amount}&cu=INR&tn={note}"
        )
        img = qrcode.make(url, image_factory=PilImage, box_size=10, border=2)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        buf.name = "upi_qr.png"
        return buf
    except Exception as e:
        logger.warning(f"Dynamic QR failed, falling back to static: {e}")
        return None


def plans_markup():
    rows = [[InlineKeyboardButton(p["label"], callback_data=f"plan:{k}")]
            for k, p in PLANS.items()]
    rows.append([InlineKeyboardButton("⬅️ Back to Home", callback_data="start_btn")])
    return InlineKeyboardMarkup(rows)


PLANS_TEXT = (
    "<b>💎 Premium Plans</b>\n\n"
    "<blockquote><b>Why go Premium?</b>\n"
    "• ♾️ Unlimited daily saves\n"
    "• 🚫 No verification / ads\n"
    "• 📂 Larger file sizes\n"
    "• 🖼 Custom thumbnail &amp; caption\n"
    "• ⚡ Priority speed</blockquote>\n\n"
    "<b>Choose your plan below 👇</b>\n"
    f"<i>UPI: <code>{UPI_ID}</code></i>"
)


async def show_plans(client: Client, message_or_query):
    """Show the plan picker (works for a Message or a CallbackQuery)."""
    if isinstance(message_or_query, CallbackQuery):
        try:
            await message_or_query.edit_message_text(
                PLANS_TEXT,
                reply_markup=plans_markup(),
                parse_mode=enums.ParseMode.HTML,
                disable_web_page_preview=True,
            )
            return
        except Exception:
            message_or_query = message_or_query.message

    await message_or_query.reply_text(
        PLANS_TEXT,
        reply_markup=plans_markup(),
        parse_mode=enums.ParseMode.HTML,
        disable_web_page_preview=True,
    )


# ======================================================
# Payment flow
# ======================================================
async def start_payment(client: Client, chat_id, user_id, key):
    plan = PLANS.get(key)
    if not plan:
        await client.send_message(chat_id, "Plan not found. Send /premium again.")
        return

    order_id = str(random.randint(10000000, 99999999))
    await db.save_order(order_id, {
        "user_id": int(user_id),
        "plan": key,
        "price": int(plan["price"]),
        "days": int(plan["days"]),
        "status": "pending",
        "created": datetime.utcnow().isoformat(),
    })

    caption = (
        "<b>💎 Premium Subscription Payment</b>\n\n"
        f"<b>💰 Amount:</b> <code>₹{plan['price']}</code>\n"
        f"<b>📅 Validity:</b> {_validity_text(plan['days'])}\n"
        f"<b>🧾 Order ID:</b> <code>{order_id}</code>\n"
        f"<b>🏦 UPI ID:</b> <code>{UPI_ID}</code>\n\n"
        "<b>How to pay</b>\n"
        "<blockquote>1️⃣ Neeche wala QR kisi bhi UPI app se scan karo\n"
        f"2️⃣ Exactly <b>₹{plan['price']}</b> pay karo\n"
        "3️⃣ Payment ke baad <b>Send Payment Proof</b> dabao</blockquote>\n"
        f"⚠️ Sirf exact ₹{plan['price']} pay karo, warna order verify nahi hoga."
    )

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Send Payment Proof", callback_data=f"paid:{order_id}")],
        [InlineKeyboardButton("❌ Cancel Order", callback_data=f"cancelorder:{order_id}")],
    ])

    qr = _upi_qr_bytes(plan["price"], f"Premium {order_id}")
    try:
        await client.send_photo(
            chat_id,
            qr if qr else QR_CODE,
            caption=caption,
            reply_markup=markup,
            parse_mode=enums.ParseMode.HTML,
        )
    except Exception as e:
        logger.error(f"Payment screen failed: {e}")
        await client.send_message(
            chat_id,
            caption,
            reply_markup=markup,
            parse_mode=enums.ParseMode.HTML,
        )


async def handle_utr_input(client: Client, message: Message):
    """Called from start.py's text/photo routing when a proof is expected."""
    saved = PENDING_UTR.pop(message.from_user.id, None)
    if not saved:
        return False

    order_id, started_at = saved
    if time.time() - started_at > PROOF_TTL:
        await message.reply_text(
            "⌛ Proof bhejne ka time nikal gaya. <b>Send Payment Proof</b> dobara dabao.",
            parse_mode=enums.ParseMode.HTML,
        )
        return True

    order = await db.get_order(order_id)
    if not order:
        await message.reply_text("Order nahi mila. /premium se naya order banao.")
        return True

    utr = (message.text or "").strip() or "(screenshot)"
    await db.save_order(order_id, {
        "utr": utr,
        "status": "claimed",
        "claimed_ts": int(time.time()),
        "claimed_at": datetime.utcnow().isoformat(),
    })

    await message.reply_text(
        "<b>✅ Payment claim mil gaya!</b>\n\n"
        "<blockquote>Verify hone me 5–10 minute lag sakte hain. "
        "Approve hote hi premium activate ho jaayega.</blockquote>",
        parse_mode=enums.ParseMode.HTML,
    )

    owner_text = (
        "<b>🔔 NEW PAYMENT CLAIM</b>\n\n"
        f"<b>User:</b> {message.from_user.mention} "
        f"(<code>{message.from_user.id}</code>)\n"
        f"<b>Order:</b> <code>{order_id}</code>\n"
        f"<b>Amount:</b> ₹{order.get('price')}\n"
        f"<b>Days:</b> {_validity_text(order.get('days', 0))}\n"
        f"<b>UTR / Note:</b> <code>{utr}</code>"
    )
    markup = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Approve", callback_data=f"approve:{order_id}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"reject:{order_id}"),
    ]])

    for admin in ADMINS:
        try:
            if message.photo:
                await client.send_photo(admin, message.photo.file_id,
                                        caption=owner_text, reply_markup=markup,
                                        parse_mode=enums.ParseMode.HTML)
            else:
                await client.send_message(admin, owner_text, reply_markup=markup,
                                          parse_mode=enums.ParseMode.HTML)
        except Exception as e:
            logger.warning(f"Could not notify admin {admin}: {e}")
    return True


# ======================================================
# Callbacks — plans / payment
# ======================================================
@Client.on_callback_query(filters.regex(r"^premium_plans_btn$"))
async def cb_premium_plans(client: Client, cq: CallbackQuery):
    await cq.answer()
    await show_plans(client, cq)


@Client.on_callback_query(filters.regex(r"^plan:"))
async def cb_plan(client: Client, cq: CallbackQuery):
    key = cq.data.split(":", 1)[1]
    if key not in PLANS:
        return await cq.answer("Plan not found, send /premium again.", show_alert=True)
    await cq.answer()
    await start_payment(client, cq.message.chat.id, cq.from_user.id, key)


@Client.on_callback_query(filters.regex(r"^paid:"))
async def cb_paid(client: Client, cq: CallbackQuery):
    order_id = cq.data.split(":", 1)[1]
    order = await db.get_order(order_id)
    if not order or order.get("status") in ("cancelled", "approved", "rejected"):
        return await cq.answer("Ye order valid nahi hai. /premium se naya banao.",
                               show_alert=True)
    PENDING_UTR[cq.from_user.id] = (order_id, time.time())
    await cq.answer()
    await cq.message.reply_text(
        "<b>🧾 Payment proof bhejo</b>\n\n"
        "<blockquote>• <b>UTR / Transaction ID</b> type karo (12 digit), ya\n"
        "• Payment ka <b>screenshot</b> bhej do</blockquote>\n\n"
        f"<b>Order ID:</b> <code>{order_id}</code>",
        parse_mode=enums.ParseMode.HTML,
    )


@Client.on_callback_query(filters.regex(r"^cancelorder:"))
async def cb_cancel_order(client: Client, cq: CallbackQuery):
    order_id = cq.data.split(":", 1)[1]
    PENDING_UTR.pop(cq.from_user.id, None)
    await db.set_order_status(order_id, "cancelled")
    await cq.answer("Order cancelled")
    try:
        await cq.message.delete()
    except Exception:
        pass
    await client.send_message(
        cq.from_user.id,
        "❌ Order cancel ho gaya. Kabhi bhi /premium se naya bana sakte ho.",
    )


@Client.on_callback_query(filters.regex(r"^(approve|reject):"))
async def cb_verify_payment(client: Client, cq: CallbackQuery):
    if cq.from_user.id not in ADMINS:
        return await cq.answer("Sirf admin ye kar sakta hai.", show_alert=True)

    action, order_id = cq.data.split(":", 1)
    order = await db.get_order(order_id)
    if not order:
        return await cq.answer("Order nahi mila.", show_alert=True)
    if order.get("status") in ("approved", "rejected"):
        return await cq.answer(f"Already {order.get('status')}.", show_alert=True)

    user_id = int(order.get("user_id"))
    days = int(order.get("days", 0))

    if action == "approve":
        expiry = await db.grant_premium_days(user_id, days)
        await db.set_order_status(order_id, "approved",
                                  approved_at=datetime.utcnow().isoformat())
        await cq.answer("Approved ✅")
        when = "Lifetime" if expiry is None else f"valid till <code>{expiry}</code>"
        try:
            await client.send_message(
                user_id,
                "<b>🎉 Premium Activated!</b>\n\n"
                f"<blockquote>Payment mil gaya ✅\nYour plan is {when}.</blockquote>\n\n"
                "♾️ Unlimited saves\n🚫 No verification\n📂 Larger files\n⚡ Priority speed\n\n"
                "<i>Send me any post link to start. Enjoy!</i>",
                parse_mode=enums.ParseMode.HTML,
            )
        except Exception as e:
            logger.warning(f"Could not DM user {user_id}: {e}")
    else:
        await db.set_order_status(order_id, "rejected",
                                  rejected_at=datetime.utcnow().isoformat())
        await cq.answer("Rejected ❌")
        try:
            await client.send_message(
                user_id,
                "<b>❌ Payment verify nahi hua.</b>\n\n"
                f"<blockquote>Agar paisa cut gaya hai to admin se baat karo: {HELP_LINK}\n"
                f"Order ID: <code>{order_id}</code></blockquote>",
                parse_mode=enums.ParseMode.HTML,
            )
        except Exception as e:
            logger.warning(f"Could not DM user {user_id}: {e}")

    label = "✅ APPROVED" if action == "approve" else "❌ REJECTED"
    try:
        if cq.message.caption:
            await cq.message.edit_caption(
                caption=cq.message.caption + f"\n\n<b>{label}</b>",
                parse_mode=enums.ParseMode.HTML,
            )
        else:
            await cq.message.edit_text(
                (cq.message.text or "") + f"\n\n<b>{label}</b>",
                parse_mode=enums.ParseMode.HTML,
            )
    except Exception:
        pass


# ======================================================
# UTR / screenshot input (text comes via start.py's router)
# ======================================================
@Client.on_message(filters.photo & filters.private)
async def utr_photo(client: Client, message: Message):
    if message.from_user.id in PENDING_UTR:
        await handle_utr_input(client, message)


# ======================================================
# /myplan
# ======================================================
@Client.on_message(filters.command("myplan") & filters.private)
async def my_plan(client: Client, message: Message):
    user_id = message.from_user.id

    if not await db.is_user_exist(user_id):
        await db.add_user(user_id, message.from_user.first_name)

    user_data = await db.col.find_one({'id': user_id}) or {}
    is_premium = bool(await db.check_premium(user_id))
    expiry = user_data.get('premium_expiry')
    daily_usage = user_data.get('daily_usage', 0)
    total_saves = user_data.get('total_saves', 0)

    if is_premium:
        if expiry:
            try:
                exp_date = (expiry if isinstance(expiry, (date, datetime))
                            else date.fromisoformat(str(expiry)[:10]))
                days_left = (exp_date - date.today()).days
                expiry_text = f"<code>{expiry}</code> ({days_left} days left)"
            except Exception:
                expiry_text = "<code>Active</code>"
        else:
            expiry_text = "<code>Lifetime</code>"

        plan_text = (
            "<b>👑 Premium Status: Active</b>\n\n"
            f"<b>📅 Expiry:</b> {expiry_text}\n\n"
            "<b>♾️ Daily Tokens:</b> Unlimited\n"
            "<b>♾️ Batch Limit:</b> Unlimited\n"
            f"<b>📊 Total Lifetime Saves:</b> <code>{total_saves}</code>\n\n"
            "<i>Thank you for supporting the bot! 🎉</i>"
        )
    else:
        daily_limit = 10
        tokens_left = max(0, daily_limit - daily_usage)
        plan_text = (
            "<b>👤 Plan: Free Tier</b>\n\n"
            f"<b>🎫 Daily Tokens:</b> <code>{tokens_left} / {daily_limit}</code>\n"
            "<b>📦 File Size Limit:</b> <code>2 GB</code>\n"
            f"<b>📊 Total Lifetime Saves:</b> <code>{total_saves}</code>\n\n"
            "<i>Upgrade to Premium for unlimited access! 🚀</i>"
        )

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 View Premium Plans", callback_data="premium_plans_btn")],
        [InlineKeyboardButton("📞 Contact Admin", url=HELP_LINK)],
    ])

    await message.reply_text(plan_text, reply_markup=buttons,
                             parse_mode=enums.ParseMode.HTML)


# ======================================================
# Admin commands
# ======================================================
PREMIUM_BENEFITS = (
    "<b>Your benefits are now active:</b>\n"
    "<blockquote>"
    "♾️ Unlimited downloads (no daily limit)\n"
    "🚀 No verification / ad step\n"
    "📂 Larger file sizes\n"
    "🖼 Custom thumbnail &amp; caption\n"
    "⚡ Priority speed\n"
    "</blockquote>\n\n"
    "<i>Send me any post link to start. Enjoy! ❤️</i>"
)


@Client.on_message(filters.command("add_premium") & filters.user(ADMINS) & filters.private)
async def add_premium_admin(client: Client, message: Message):
    if len(message.command) < 3:
        return await message.reply_text(
            "<b>⚠️ Admin Usage:</b>\n"
            "<code>/add_premium &lt;user_id&gt; &lt;days&gt;</code>\n\n"
            "<i>Use 0 for lifetime premium.</i>",
            parse_mode=enums.ParseMode.HTML,
        )

    try:
        user_id = int(message.command[1])
        days = int(message.command[2])
        expiry = await db.grant_premium_days(user_id, days)
        duration_text = ("Lifetime" if days == 0
                         else f"{days} days (until {expiry})")

        if days == 0:
            user_msg = ("<b>🎉 Premium Activated!</b>\n\n"
                        "<blockquote>You have received <b>Lifetime Premium</b> access.\n"
                        "It never expires.</blockquote>\n\n" + PREMIUM_BENEFITS)
        else:
            user_msg = ("<b>🎉 Premium Activated!</b>\n\n"
                        f"<blockquote>You have received premium access for <b>{days} days</b>.\n"
                        f"Expires on: <code>{expiry}</code></blockquote>\n\n" + PREMIUM_BENEFITS)

        delivered = True
        try:
            await client.send_message(user_id, user_msg,
                                      parse_mode=enums.ParseMode.HTML,
                                      disable_web_page_preview=True)
        except Exception as e:
            delivered = False
            logger.warning(f"Could not DM user {user_id}: {e}")

        note = "" if delivered else (
            "\n\n<i>⚠️ Could not message the user (blocked the bot or never started it).</i>")
        await message.reply_text(
            f"<b>✅ Premium Added Successfully</b>\n\n"
            f"<b>User ID:</b> <code>{user_id}</code>\n"
            f"<b>Duration:</b> {duration_text}" + note,
            parse_mode=enums.ParseMode.HTML,
        )
    except ValueError:
        await message.reply_text("❌ <b>Error:</b> User ID and Days must be numbers.",
                                 parse_mode=enums.ParseMode.HTML)
    except Exception as e:
        await message.reply_text(f"❌ <b>Error:</b> {e}", parse_mode=enums.ParseMode.HTML)


@Client.on_message(filters.command("remove_premium") & filters.user(ADMINS) & filters.private)
async def remove_premium_admin(client: Client, message: Message):
    if len(message.command) < 2:
        return await message.reply_text(
            "<b>⚠️ Usage:</b> <code>/remove_premium &lt;user_id&gt;</code>",
            parse_mode=enums.ParseMode.HTML,
        )
    try:
        user_id = int(message.command[1])
        await db.remove_premium(user_id)

        delivered = True
        try:
            await client.send_message(
                user_id,
                "<b>ℹ️ Premium Removed</b>\n\n"
                "<i>Your premium access has ended. You can renew anytime with "
                "/premium.</i>",
                parse_mode=enums.ParseMode.HTML,
            )
        except Exception as e:
            delivered = False
            logger.warning(f"Could not DM user {user_id}: {e}")

        note = "" if delivered else "\n<i>(user could not be messaged)</i>"
        await message.reply_text(f"✅ Premium removed from <code>{user_id}</code>.{note}")
    except Exception as e:
        await message.reply_text(f"Error: {e}")
