# Ad / Token Verification (Shortener Gate)

This bot gates **free** users behind a shortener (ad) step. Completing it earns
you ad revenue; in return the user gets full access for a few hours. Premium users
skip the gate entirely.

---

## How the flow works

1. A free user sends a content link.
2. The bot creates a **one-time token** and shortens a link to **our own gateway
   page** — `https://<PUBLIC_URL>/v/<token>` — never the raw Telegram link.
3. The user opens the shortener (sees the ad) and lands on the gateway page,
   which runs browser checks and only then releases the Telegram deep link.
4. The bot validates the token (one-time, user-bound, not expired **and
   gateway-passed**) and **automatically resumes** the link the user sent.

If the shortener is unreachable the bot **refuses** (fails closed) instead of
handing out a free pass.

---

## Anti-bypass (how links can't be skipped)

Bypass tools (bypass.vip, adlinkfly bypass, "Nick Bypass Bot", …) work by
**resolving the shortener server-side** and handing the user the destination URL,
so the user never sees the ad. We fight that at several layers:

| Layer | What it stops |
| ----- | ------------- |
| **Referer check** (`REQUIRE_REFERER`) | The security page only loads if the browser arrived **from the shortener**. A bypassed link opened directly (no Referer), or from Telegram/another site, gets **HTTP 403**. |
| **Gateway page** (`/v/<token>`) | The deep link is **not present in the HTML** — it is only returned by `/v/<token>/go` after the checks pass. A redirect-follower gets nothing. |
| **`gateway_passed` flag** | A hand-built `t.me/<bot>?start=verify_<token>` link is **rejected** unless the gateway page set the flag in MongoDB. |
| **One-time use** | Replaying a used link does nothing. |
| **Short TTL** | Links older than `VERIFY_TOKEN_TTL` are rejected. |
| **User-bound** | The token is tied to the requesting user id — sharing it with someone else does nothing. |
| **128-bit token** | `secrets.token_urlsafe(16)` — cannot be guessed. |

### If a legit user ever gets blocked

The Referer check relies on the browser sending the shortener's referrer when it
redirects. If your shortener redirects in a way that strips it, set:

```
REQUIRE_REFERER=False
```

and redeploy. The Render logs show one line per gateway hit:
`[gateway] OK/BLOCKED token=... referer='...'` — check that first.

> Honest note: the browser checks (WebDriver / canvas / human interaction) are
> **client-side** and a determined attacker with a stealth headless browser can
> evade them. The server-side layers (`REQUIRE_REFERER`, `gateway_passed`,
> one-time, TTL, user-bound) are what actually make casual bypassing pointless.

---

## Environment variables

| Variable            | Default            | Meaning                                                        |
| ------------------- | ------------------ | -------------------------------------------------------------- |
| `IS_VERIFY`         | `True`             | Master switch. `False` disables the gate for everyone.         |
| `SHORTLINK_URL`     | `vipshort.in`      | Your shortener host (also used for the Referer check).         |
| `SHORTLINK_API`     | *(empty)*          | **Secret** — your shortener API key.                           |
| `VERIFY_EXPIRE`     | `21600`            | How long a user stays verified, in seconds (21600 = 6 hours).  |
| `VERIFY_TOKEN_TTL`  | `600`              | How long a verify link stays usable, in seconds (10 minutes).  |
| `PUBLIC_URL`        | *(auto)*           | Base URL of this service, used to build the gateway. On Render it is read from `RENDER_EXTERNAL_URL` automatically. |
| `REQUIRE_REFERER`   | `True`             | Block gateway visits that did not come from the shortener.     |
| `TUT_VID`           | `https://t.me/ModAppsKing` | Tutorial link shown on the verify screen.              |
| `VERIFY_PIC`        | start banner       | Photo shown on the verify screen.                              |

> **Never commit `SHORTLINK_API`.** This repository is public. Set it in the Render
> dashboard (Service → Environment), or in your local `.env`.

---

## vipshort setup

The bot calls:

```
https://vipshort.in/api?api=<SHORTLINK_API>&url=<encoded gateway link>
```

1. Create an account at <https://vipshort.in>.
2. Copy your API key from the dashboard.
3. Set `SHORTLINK_API` to that key (Render → Environment).

The response can be JSON (`shortenedUrl`, `short`, `url`, …) or a plain URL — the
bot accepts either. If your shortener uses a different response shape, run
`/shorttest` as admin and check the Render logs.

---

## Admin commands

- `/shorttest` — calls the shortener once and shows the raw response + whether it
  parsed, and the gateway URL in use. Use this first when something looks wrong.

---

## Testing

1. As a **free** user, send any `https://t.me/...` link → you should get the verify screen.
2. Tap **Verify Now** → you land on the **Security Verification** page → tap Continue
   → you are back in the bot with *"✅ Verification successful!"* and the download starts.
3. Send another link within 6 hours → works **without** asking again.
4. Try to fake it: send `/start verify_<some-token>` directly → refused.
5. Try to bypass: paste the gateway URL straight into a browser (no referer) → 403.
6. Premium users (`/add_premium`) never see the gate.
