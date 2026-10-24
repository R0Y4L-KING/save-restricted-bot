# Deploy on Render (Web Service)

This bot runs as a **Render Web Service**. The bundled `keep_alive.py` starts a tiny
Flask server on Render's `PORT` so the service stays healthy, and `render.yaml`
already defines the build/start commands and every environment variable.

> Need a database? See **[SETUP_MONGODB.md](SETUP_MONGODB.md)** to create a free
> MongoDB Atlas cluster and get your `DB_URI`.

---

## 1. Create the service

1. Go to <https://dashboard.render.com> → **New +** → **Blueprint** (recommended)
   **or** **New +** → **Web Service**.
2. Connect the GitHub repo `R0Y4L-KING/save-restricted-bot`.
3. If you picked **Web Service** manually, set:
   - **Runtime:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python3 bot.py`
   - **Health Check Path:** `/`
   - **Instance Type:** Free

> Using the **Blueprint** flow, Render reads `render.yaml` and fills all of the above
> for you automatically.

---

## 2. Add environment variables

Yes — you add them from the dashboard, no code change needed.

Render Dashboard → your service → **Environment** → **Add Environment Variable**,
then add these (the ones marked *secret* should be set as plain env vars, not committed):

| Key              | Value / example                          | Required |
| ---------------- | ---------------------------------------- | -------- |
| `PYTHON_VERSION` | `3.10.13`                                | yes (in render.yaml) |
| `BOT_TOKEN`      | from @BotFather                          | yes |
| `API_ID`         | from https://my.telegram.org             | yes |
| `API_HASH`       | from https://my.telegram.org             | yes |
| `ADMINS`         | your Telegram user id, e.g. `123456789`  | yes |
| `DB_URI`         | MongoDB Atlas connection string          | yes |
| `DB_NAME`        | `SaveRestricted2`                        | no (default) |
| `LOG_CHANNEL`    | e.g. `-1001234567890`                    | yes |
| `ERROR_MESSAGE`  | `True`                                   | no (default) |
| `SUBSCRIPTION`   | image URL for the premium screen         | no |
| `UPI_ID`         | e.g. `yourid@oksbi`                      | no |
| `QR_CODE`        | QR image URL for the payment screen      | no |

`render.yaml` marks the secret ones with `sync: false`, so Render will prompt you
for each value the first time it creates the service.

---

## 3. Stop the free instance from sleeping (keep-alive)

Render's free Web Services spin down after ~15 minutes of no traffic. Fix it with a
free uptime monitor:

1. Copy your service URL, e.g. `https://save-restricted-bot.onrender.com`.
2. Create a free monitor at <https://uptimerobot.com> → **Add New Monitor**.
3. Type **HTTP(s)**, URL = your service URL, interval = **5 minutes**.

This pings `/` (served by `keep_alive.py`) and keeps the bot awake 24×7.

---

## 4. First run checklist

- The bot must be an **admin** of your `LOG_CHANNEL`, otherwise startup logs fail.
- Check the Render **Logs** tab: you should see `🤖 Bot Successfully Started` in your
  log channel and `MongoDB Connected` in the logs.
- If the build fails on Flask/Werkzeug, confirm `PYTHON_VERSION` is `3.10.13` — the
  pinned Flask 1.1.2 stack is not compatible with Python 3.12+.

---

## Local run (optional)

```bash
pip install -r requirements.txt
cp .env.example .env      # fill in your values
python3 bot.py
```
