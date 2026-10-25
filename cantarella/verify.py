# Ad / token verification gate (shortener + anti-bypass gateway)
#
# Three modes (VERIFY_LINK_MODE):
#   shortener  (default) - bot -> AD -> own-domain checks page -> bot
#   page_first           - bot -> own-domain checks page -> AD -> bot   (Codeflix order)
#   direct               - bot -> own-domain checks page -> bot         (no ad)
#
# In every mode the Telegram deep link is only accepted once the gateway page
# has set gateway_passed, and it is one-time, short-lived and user-bound.

import html
import json
import os
import secrets
import time

import aiohttp
from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from config import (
    IS_VERIFY, SHORTLINK_URL, SHORTLINK_API, SHORTLINK_ALIAS,
    VERIFY_EXPIRE, VERIFY_TOKEN_TTL, TUT_VID, VERIFY_PIC, ADMINS, LOG_CHANNEL,
    PUBLIC_URL,
)
from database.db import db
from logger import LOGGER

logger = LOGGER(__name__)

VERIFY_PREFIX = "verify_"
GATEWAY_BASE = (PUBLIC_URL or "").rstrip("/")

# "shortener" | "page_first" | "direct"
VERIFY_LINK_MODE = os.environ.get("VERIFY_LINK_MODE", "shortener").strip().lower()

# Some shorteners reject the default aiohttp/python User-Agent.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)

_ALERT_COOLDOWN = 600
_last_alert_ts = 0


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


def _api_endpoint() -> str:
    base = (SHORTLINK_URL or "").strip()
    if not base:
        return ""
    if not base.startswith("http"):
        base = "https://" + base
    if not base.rstrip("/").endswith("/api"):
        base = base.rstrip("/") + "/api"
    return base


async def _notify_admin(client: Client, text: str):
    global _last_alert_ts
    now = time.time()
    if now - _last_alert_ts < _ALERT_COOLDOWN:
        return
    _last_alert_ts = now
    try:
        if LOG_CHANNEL:
            await client.send_message(LOG_CHANNEL, text, parse_mode=enums.ParseMode.HTML)
    except Exception as e:
        logger.error(f"notify_admin failed: {e}")


async def _shortener_call(dest: str):
    """Call the shortener. Returns (raw_body, error_string)."""
    if not SHORTLINK_API:
        return None, "SHORTLINK_API is not set"
    endpoint = _api_endpoint()
    if not endpoint:
        return None, "SHORTLINK_URL is not set"

    params = {"api": SHORTLINK_API, "url": dest}
    if SHORTLINK_ALIAS:
        params["alias"] = SHORTLINK_ALIAS

    try:
        timeout = aiohttp.ClientTimeout(total=15)
        headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(endpoint, params=params) as resp:
                body = (await resp.text()).strip()
                if resp.status != 200:
                    return body, f"HTTP {resp.status}"
        return body, None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def _extract_link(body: str):
    if not body:
        return None
    try:
        data = json.loads(body)
    except Exception:
        data = None

    if isinstance(data, dict):
        for key in ("shortenedUrl", "shortened_url", "shortUrl", "short_url",
                    "shorturl", "short", "shortened", "url", "result", "link"):
            val = data.get(key)
            if val and str(val).startswith("http"):
                return str(val)
        inner = data.get("data")
        if isinstance(inner, dict):
            for key in ("shortenedUrl", "shortUrl", "url", "link", "short"):
                val = inner.get(key)
                if val and str(val).startswith("http"):
                    return str(val)

    if body.startswith("http"):
        return body.split()[0]
    return None


async def shorten_url_verbose(dest: str):
    body, err = await _shortener_call(dest)
    if err:
        return None, f"call failed: {err}"
    link = _extract_link(body)
    if link:
        return link, "ok"
    return None, f"unparsed response: {str(body)[:300]}"


async def shorten_url(dest: str):
    link, detail = await shorten_url_verbose(dest)
    if not link:
        logger.error(f"Shortener failed: {detail}")
    return link


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


def _admin_hint(detail: str) -> str:
    if "SHORTLINK_API is not set" in detail:
        return "Set SHORTLINK_API in Render -> Environment, then redeploy."
    if "HTTP 401" in detail or "HTTP 403" in detail:
        return "Shortener rejected the API key (wrong/invalid key, or server IP blocked)."
    if "unparsed response" in detail:
        return "Shortener replied in an unknown format - send /shorttest output to your dev."
    return "Shortener unreachable from Render - check the key and try /shorttest."


async def send_verify_prompt(client: Client, message: Message, target: str = None, count: int = None):
    """Create a one-time token, build the verify link and send the verify screen."""
    user_id = message.from_user.id
    token = secrets.token_urlsafe(16)

    require_gateway = bool(GATEWAY_BASE)

    try:
        await db.create_verify_token(token, user_id, target, count, require_gateway)
    except Exception as e:
        logger.error(f"Failed to store verify token: {e}")

    bot = await client.get_me()
    deep_link = f"https://t.me/{bot.username}?start={VERIFY_PREFIX}{token}"
    gateway_url = f"{GATEWAY_BASE}/v/{token}" if require_gateway else None

    verify_link = None
    detail = ""

    if gateway_url and VERIFY_LINK_MODE in ("direct", "page_first"):
        # Own-domain link handed out straight from the bot (file-bot style).
        verify_link = gateway_url
        detail = f"{VERIFY_LINK_MODE} gateway link"
        if VERIFY_LINK_MODE == "page_first":
            # Checks first, then the ad, then back to the bot. The ad link is
            # stored on the token and only released by the gateway page.
            ad_link, ad_detail = await shorten_url_verbose(deep_link)
            if ad_link:
                try:
                    await db.vcol.update_one({"_id": token}, {"$set": {"ad_link": ad_link}})
                except Exception as e:
                    logger.error(f"Failed to store ad link: {e}")
            else:
                verify_link = None
                detail = f"ad link failed: {ad_detail}"
    else:
        destination = gateway_url or deep_link
        if not require_gateway:
            logger.warning("PUBLIC_URL not set - gateway disabled, using direct deep link.")
        verify_link, detail = await shorten_url_verbose(destination)

    if not verify_link:
        # FAIL CLOSED - never hand out a bypass.
        logger.error(f"Verification blocked: {detail}")
        try:
            await db.vcol.delete_one({"_id": token})
        except Exception:
            pass

        user_text = (
            "<b>⚠️ Verification is temporarily unavailable.</b>\n\n"
            "<i>Our verification service is not responding right now. "
            "Please send your link again in a minute.</i>"
        )
        if message.from_user.id in ADMINS:
            user_text += (
                "\n\n<b>🔧 Admin diagnostic</b>\n"
                f"<b>Endpoint:</b> <code>{html.escape(_api_endpoint())}</code>\n"
                f"<b>Gateway:</b> <code>{html.escape(GATEWAY_BASE or 'NOT SET')}</code>\n"
                f"<b>Mode:</b> <code>{html.escape(VERIFY_LINK_MODE)}</code>\n"
                f"<b>Reason:</b> <code>{html.escape(detail)}</code>\n"
                f"<i>{html.escape(_admin_hint(detail))}</i>"
            )
        await message.reply(user_text, parse_mode=enums.ParseMode.HTML)

        await _notify_admin(
            client,
            "<b>⚠️ Ad-gate shortener failed</b>\n\n"
            f"<b>Endpoint:</b> <code>{html.escape(_api_endpoint())}</code>\n"
            f"<b>Reason:</b> <code>{html.escape(detail)}</code>\n\n"
            f"<i>{html.escape(_admin_hint(detail))}</i>"
        )
        return

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
    """Handle the /start verify_<token> redirect coming back from the ad."""
    payload = message.command[1] if len(message.command) > 1 else ""
    token = payload[len(VERIFY_PREFIX):] if payload.startswith(VERIFY_PREFIX) else payload
    user_id = message.from_user.id

    if not token:
        return

    rec = await db.consume_verify_token(token, user_id, VERIFY_TOKEN_TTL)
    if not rec:
        await message.reply(
            "<b>❌ This verification link is invalid, already used, or expired.</b>\n\n"
            "<i>Tip: verification must be completed on the official security page — "
            "send the link you want to save again to get a fresh one.</i>",
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


@Client.on_message(filters.command("shorttest") & filters.user(ADMINS) & filters.private)
async def shorttest(client: Client, message: Message):
    """Admin: call the shortener once and show the raw response (debugging)."""
    body, err = await _shortener_call("https://t.me/ModAppsKing")
    if err:
        await message.reply(
            f"<b>❌ Shortener call failed</b>\n\n"
            f"<b>Endpoint:</b> <code>{html.escape(_api_endpoint())}</code>\n"
            f"<b>Mode:</b> <code>{html.escape(VERIFY_LINK_MODE)}</code>\n"
            f"<b>Reason:</b> <code>{html.escape(err)}</code>\n\n"
            f"<i>{html.escape(_admin_hint('call failed: ' + err))}</i>",
            parse_mode=enums.ParseMode.HTML
        )
        return

    link = _extract_link(body)
    verdict = "✅ parsed OK" if link else "❌ parser did NOT find a link"
    await message.reply(
        f"<b>Shortener endpoint:</b> <code>{html.escape(_api_endpoint())}</code>\n"
        f"<b>Gateway:</b> <code>{html.escape(GATEWAY_BASE or 'NOT SET')}</code>\n"
        f"<b>Mode:</b> <code>{html.escape(VERIFY_LINK_MODE)}</code>\n"
        f"<b>Result:</b> {verdict}\n\n"
        f"<b>Raw response:</b>\n<code>{html.escape(str(body)[:900])}</code>",
        parse_mode=enums.ParseMode.HTML
    )
