"""
Save Restricted Content Bot Configuration

Developed by: LastPerson07Xcantarella
Telegram: @cantarellabots X @THEUPDATEDGUYS

Please retain this credit if you use or modify this project.
"""

import os


# ==============================
# Telegram Bot Credentials
# ==============================

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")


# ==============================
# Admin Configuration
# ==============================

# Add admin user IDs separated by commas in environment variables
ADMINS = [int(admin) for admin in os.environ.get("ADMINS", "").split(",") if admin]


# ==============================
# Database Configuration
# ==============================

DB_URI = os.environ.get("DB_URI", "")
DB_NAME = os.environ.get("DB_NAME", "SaveRestricted2")


# ==============================
# Logging Configuration
# ==============================

# Replace with your Telegram log channel ID (example: -1001234567890)
LOG_CHANNEL = int(os.environ.get("LOG_CHANNEL", "0"))


# ==============================
# Error Handling
# ==============================

# Set to True to send error messages to users
ERROR_MESSAGE = os.environ.get("ERROR_MESSAGE", "True").lower() == "true"


# ==============================
# Ad / Token Verification (Shortener)
# ==============================

# Master switch for the ad-verification gate.
# True  -> free users must complete the shortener before downloading
# False -> gate disabled for everyone
IS_VERIFY = os.environ.get("IS_VERIFY", "True").lower() == "true"

# Shortener / ad network used to gate free users.
# vipshort.in API: https://vipshort.in/api?api=<KEY>&url=<dest>&alias=<alias>
SHORTLINK_URL = os.environ.get("SHORTLINK_URL", "vipshort.in")
SHORTLINK_API = os.environ.get("SHORTLINK_API", "")
SHORTLINK_ALIAS = os.environ.get("SHORTLINK_ALIAS", "")

# How long a user stays verified after completing the shortener (seconds). Default 6 hours.
VERIFY_EXPIRE = int(os.environ.get("VERIFY_EXPIRE", "21600"))

# A verify link must be used within this many seconds (seconds). Default 10 minutes.
VERIFY_TOKEN_TTL = int(os.environ.get("VERIFY_TOKEN_TTL", "600"))

# Tutorial video + photo shown on the verify screen
TUT_VID = os.environ.get("TUT_VID", "https://t.me/ModAppsKing")
VERIFY_PIC = os.environ.get(
    "VERIFY_PIC",
    "https://raw.githubusercontent.com/R0Y4L-KING/save-restricted-bot/main/assets/start_banner.jpg"
)
