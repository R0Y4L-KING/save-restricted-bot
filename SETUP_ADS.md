# Ad / Token Verification (Shortener Gate)

This bot can gate **free** users behind a shortener (ad) step. Completing it earns
you ad revenue; in return the user gets full access for a few hours. Premium users
skip the gate entirely.

---

## How the flow works

1. A free user sends a content link.
2. The bot creates a **one-time token**, builds a deep link
   `https://t.me/<yourbot>?start=verify_<token>`, shortens it with your shortener
   and shows a **🔓 Verify Now** button.
3. The user completes the shortener (sees the ad), gets redirected back to the bot.
4. The bot validates the token, grants access for `VERIFY_EXPIRE` seconds and
   **automatically resumes** the link the user originally sent.

If the shortener is unreachable the bot falls back to the direct deep link so users
are never fully blocked (you just miss the ad on that attempt).

---

## Environment variables

| Variable            | Default            | Meaning                                                        |
| ------------------- | ------------------ | -------------------------------------------------------------- |
| `IS_VERIFY`         | `True`             | Master switch. `False` disables the gate for everyone.         |
| `SHORTLINK_URL`     | `vipshort.in`      | Your shortener host.                                           |
| `SHORTLINK_API`     | *(empty)*          | **Secret** — your shortener API key.                           |
| `VERIFY_EXPIRE`     | `21600`            | How long a user stays verified, in seconds (21600 = 6 hours).  |
| `VERIFY_TOKEN_TTL`  | `600`              | How long a verify link stays usable, in seconds (10 minutes).  |
| `TUT_VID`           | `https://t.me/ModAppsKing` | Tutorial link shown on the verify screen.              |
| `VERIFY_PIC`        | start banner       | Photo shown on the verify screen.                              |

> **Never commit `SHORTLINK_API`.** This repository is public. Set it in the Render
> dashboard (Service → Environment), or in your local `.env`.

---

## vipshort setup

The bot calls:

```
https://vipshort.in/api?api=<SHORTLINK_API>&url=<encoded deep link>
```

1. Create an account at <https://vipshort.in>.
2. Copy your API key from the dashboard.
3. Set `SHORTLINK_API` to that key (Render → Environment).

The response can be JSON (`shortenedUrl`, `short`, `url`, …) or a plain URL — the
bot accepts either. If your shortener uses a different response shape, check the
Render logs for `Shortener returned an unexpected response: ...` and tell me.

---

## Security (why links can't be bypassed)

The gate is enforced **server-side**, not by a URL prefix:

- **128-bit random token** (`secrets.token_urlsafe(16)`) — cannot be guessed or brute-forced.
- **One-time use** — the token is marked used the moment it is consumed.
- **Short TTL** — a link older than `VERIFY_TOKEN_TTL` is rejected.
- **User-bound** — the token is stored against the user id that requested it, so
  sharing a verify link with someone else does nothing.
- **Stored in MongoDB** — a forged `/start verify_...` payload with no matching
  record simply fails.

There is no `?start=<magic-prefix>` shortcut (unlike some public forks), so a user
cannot fake verification by crafting a deep link.

> Note: the browser checks on some "Security Verification" pages (WebDriver,
> canvas fingerprint, etc.) are client-side and can be bypassed. The server-side
> checks above are what actually stop abuse.

---

## Testing

1. As a **free** user, send any `https://t.me/...` link → you should get the verify screen.
2. Complete the shortener → you should land back in the bot, see
   *"✅ Verification successful!"* and the original download should start.
3. Send another link within 6 hours → it should work **without** asking again.
4. `/verify` shows the verify screen on demand (or "already verified").
5. Premium users (`/add_premium`) should never see the gate.
