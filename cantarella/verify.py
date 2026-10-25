# Ad / token verification gate (shortener based)
#
# Flow:
#   1. Free user sends a content link.
#   2. Bot creates a one-time token, builds t.me/<bot>?start=verify_<token>,
#      shortens it through the ad shortener (vipshort) and shows a Verify button.
#   3. User completes the shortener -> is redirected back to the bot with the token.
#   4. Bot validates the token (one-time, user-bound, not expired), grants access
#      for VERIFY_EXPIRE seconds and resumes the original request.
#
# Security notes:
#   - Tokens are 128-bit random (secrets.token_urlsafe), so they cannot be guessed.
#   - One-time use + short TTL + bound to the requesting user id.
#   - No forgeable prefix trick: without a valid DB record the gate cannot be passed.

import json
import secrets
import time

import aiohttp
from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from config import (
    IS_VERIFY, SHORTLINK_URL, SHORTLINK_API, SHORTLINK_ALIAS,
    VERIFY_EXPIRE, VERIFY_TOKEN_TTL, TUT_VID, VERIFY_PIC,
)
from database.db import db
from logger import LOGGER

logger = LOGGER(__name__)

VERIFY_PREFIX = "verify_"


def _duration_text(seconds: int) -> str:
    seconds = int(seconds or 0)
    hours, rem = divmod(seconds, 3600)
    minutes, _ = divmod(rem, 60)
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    return " ".join(parts) or f"{seconds}s"


async def shorten_url(dest: str):
    """Shorten a URL with the configured shortener. Returns None on failure."""
    if not SHORTLINK_API:
        logger.warning("SHORTLINK_API not set - skipping shortener.")
        return None

    base = (SHORTLINK_URL or "").strip()
    if not base:
        return None
    if not base.startswith("http"):
        base = "https://" + base
    if not base.rstrip("/").endswith("/api"):
        base = base.rstrip("/") + "/api"

    params = {"api": SHORTLINK_API, "url": dest}
    if SHORTLINK_ALIAS:
        params["alias"] = SHORTLINK_ALIAS

    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(base, params=params) as resp:
                body = (await resp.text()).strip()
    except Exception as e:
        logger.error(f"Shortener request failed: {e}")
        return None

    # Most shorteners answer with JSON; accept a few common field names.
    try:
        data = json.loads(body)
        if isinstance(data, dict):
            for key in ("shortenedUrl", "shortened_url", "short", "shortened",
                        "url", "result", "link"):
                val = data.get(key)
                if val and str(val).startswith("http"):
                    return str(val)
    except Exception:
        pass

    # Some answer with the plain shortened URL.
    if body.startswith("http"):
        return body.split()[0]

    logger.error(f"Shortener returned an unexpected response: {body[:200]}")
    return None


async def is_user_verified(user_id) -> bool:
    """Premium users pass; when IS_VERIFY is off everyone passes."""
    if not IS_VERIFY:
        return True
    try:
        if await db.check_premium(user_id):
            return True
    except Exception as e:
        logger.error(f"Premium check failed during verify: {e}")
    try:
        until = await db.get_verified_until(user_id)
    except Exception:
        until = 0
    return until > int(time.time())


VERIFY_TEXT = (
    "<b>🔐 Verification Required</b>\n\n"
    "To keep this bot <b>free</b> for everyone, please complete a quick verification.\n\n"
    "<blockquote><b>What you get:</b>\n"
    "• ✅ Full access for <b>{duration}</b>\n"
    "• ♾️ Unlimited downloads during that time\n"
    "• 🚀 No daily limit</blockquote>\n\n"
    "<b>How to verify:</b>\n"
    "1. Tap <b>🔓 Verify Now</b> below\n"
    "2. Complete the short step\n"
    "3. Come back — you're in! 🎉\n\n"
    "<i>Stuck? Watch the tutorial, or get Premium for instant access.</i>"
)


def _verify_buttons(verify_link: str):
    return [
        [InlineKeyboardButton("🔓 Verify Now", url=verify_link)],
        [InlineKeyboardButton("📺 How To Verify", url=TUT_VID)],
        [InlineKeyboardButton("💎 Get Premium", callback_data="buy_premium")],
    ]


async def send_verify_prompt(client: Client, message: Message, target: str = None, count: int = None):
    """Create a one-time token, shorten the deep link and send the verify screen."""
    user_id = message.from_user.id
    token = secrets.token_urlsafe(16)

    try:
        await db.create_verify_token(token, user_id, target, count)
    except Exception as e:
        logger.error(f"Failed to store verify token: {e}")

    bot = await client.get_me()
    deep_link = f"https://t.me/{bot.username}?start={VERIFY_PREFIX}{token}"
    short_link = await shorten_url(deep_link)
    verify_link = short_link or deep_link
    if not short_link:
        logger.warning("Shortener unavailable - falling back to direct deep link (no ads).")

    caption = VERIFY_TEXT.format(duration=_duration_text(VERIFY_EXPIRE))
    markup = InlineKeyboardMarkup(_verify_buttons(verify_link))

    try:
        await message.reply_photo(
            photo=VERIFY_PIC,
            caption=caption,
            reply_markup=markup,
            parse_mode=enums.ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Verify photo failed, sending text: {e}")
        await message.reply(caption, reply_markup=markup, parse_mode=enums.ParseMode.HTML)


async def handle_verify(client: Client, message: Message):
    """Handle the /start verify_<token> redirect coming back from the shortener."""
    payload = message.command[1] if len(message.command) > 1 else ""
    token = payload[len(VERIFY_PREFIX):] if payload.startswith(VERIFY_PREFIX) else payload
    user_id = message.from_user.id

    if not token:
        return

    rec = await db.consume_verify_token(token, user_id, VERIFY_TOKEN_TTL)
    if not rec:
        await message.reply(
            "<b>❌ This verification link is invalid, already used, or expired.</b>\n\n"
            "<i>Send the link you want to save again to get a fresh verification link.</i>",
            parse_mode=enums.ParseMode.HTML
        )
        return

    until = int(time.time()) + VERIFY_EXPIRE
    await db.set_verified(user_id, until)

    await message.reply(
        "<b>✅ Verification successful! 🎉</b>\n\n"
        f"<blockquote>You now have <b>full access for {_duration_text(VERIFY_EXPIRE)}</b>.</blockquote>\n"
        "<i>Enjoy unlimited downloads! 🚀</i>",
        parse_mode=enums.ParseMode.HTML
    )

    target = rec.get("target")
    if target:
        try:
            # Imported here to avoid a circular import at module load time.
            from cantarella.start import process_save_link
            await process_save_link(client, message, target, rec.get("count"))
        except Exception as e:
            logger.error(f"Failed to resume save after verify: {e}")


@Client.on_message(filters.command("verify") & filters.private)
async def verify_command(client: Client, message: Message):
    """Let a user verify on demand, without sending a link first."""
    if await is_user_verified(message.from_user.id):
        await message.reply(
            "<b>✅ You are already verified.</b>\n\n"
            "<i>Send me any post link to save it.</i>",
            parse_mode=enums.ParseMode.HTML
        )
        return
    await send_verify_prompt(client, message)
