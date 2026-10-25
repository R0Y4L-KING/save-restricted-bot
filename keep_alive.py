"""
========================================================
Keep-alive HTTP server for Render / Heroku

Also hosts the ad-gate "Security Check" gateway:

  GET /r/<token>      -> browser-check page (JS)      (alias: /v/<token>)
                         Auto-runs the checks, then REDIRECTS on its own -
                         no button to tap. A link can only be opened once;
                         opening it again shows "Link Expired".
  GET /r/<token>/go   -> marks gateway_passed + link_used and returns what
                         to open next:
                           page_first (default) -> the AD (shortener) link
                           shortener / direct   -> the Telegram deep link

Why page_first is the default: the bot hands out OUR OWN link
(https://<host>/r/<token>), never the shortener link. Opening it runs the
checks and then redirects to the ad, so the user never sees/copies the
shortener URL and cannot feed it to a bypass bot.
========================================================
"""

import html
import os
import threading
import time

from flask import Flask, Response, jsonify, request

app = Flask(__name__)

# Set by bot.py at startup (keep_alive.BOT_USERNAME = me.username)
BOT_USERNAME = os.environ.get("BOT_USERNAME", "")
TOKEN_TTL = int(os.environ.get("VERIFY_TOKEN_TTL", "600"))

SHORTLINK_URL = os.environ.get("SHORTLINK_URL", "vipshort.in")
SHORTLINK_HOST = SHORTLINK_URL.replace("https://", "").replace("http://", "").strip("/").split("/")[0].lower()

REQUIRE_REFERER = os.environ.get("REQUIRE_REFERER", "True").lower() == "true"

# page_first (default) | shortener | direct
VERIFY_LINK_MODE = os.environ.get("VERIFY_LINK_MODE", "page_first").strip().lower()

_NO_REFERER_MODES = ("direct", "page_first")

_mongo_client = None


def _db():
    """Lazy sync Mongo handle (motor/pymongo ship together)."""
    global _mongo_client
    uri = os.environ.get("DB_URI", "")
    if not uri:
        return None
    if _mongo_client is None:
        import pymongo
        _mongo_client = pymongo.MongoClient(uri)
    return _mongo_client[os.environ.get("DB_NAME", "SaveRestricted2")]


@app.route("/", methods=["GET"])
def health():
    return Response("OK", status=200)


PAGE_CSS = (
    "body{margin:0;background:#0b0f14;color:#e8eef6;font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;"
    "display:flex;min-height:100vh;align-items:center;justify-content:center}"
    ".card{width:min(92vw,420px);background:#111823;border:1px solid #1e2a3a;border-radius:18px;"
    "padding:26px 22px;text-align:center;box-shadow:0 18px 50px rgba(0,0,0,.5)}"
    ".shield{font-size:52px}"
    "h2{margin:12px 0 4px;font-size:22px}"
    "p{color:#9fb0c4;font-size:14px;margin:6px 0 16px}"
    ".bar{height:8px;background:#1b2534;border-radius:6px;overflow:hidden;margin:14px 0 18px}"
    ".bar>div{height:100%;width:0;background:linear-gradient(90deg,#22c55e,#16a34a);transition:width .4s}"
    "ul{list-style:none;padding:0;margin:0 0 18px;text-align:left}"
    "li{font-size:14px;padding:7px 0;color:#8fa3b8}"
    "li.ok{color:#22c55e}"
    ".err{color:#ef4444;font-size:14px}"
    ".foot{margin-top:14px;font-size:12px;color:#5c6b7e}"
)


BLOCKED_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Verification</title><style>__CSS__</style></head><body>
<div class="card">
 <div class="shield">\U0001f6ab</div>
 <h2>Open the link properly</h2>
 <p>This verification page must be opened from the <b>Verify Now</b> button in the bot.<br><br>
 Go back to Telegram, tap <b>🔓 Verify Now</b> and complete the steps.</p>
</div></body></html>
""".replace("__CSS__", PAGE_CSS)


EXPIRED_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Link Expired</title><style>__CSS__</style></head><body>
<div class="card">
 <div class="shield">\U0001f480</div>
 <h2 style="color:#ef4444">Link Expired</h2>
 <p>This link has already been used and is no longer available.<br>
 Request a new link from the bot.</p>
</div></body></html>
""".replace("__CSS__", PAGE_CSS)


GATEWAY_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Security Check</title>
<style>__CSS__</style>
</head>
<body>
<div class="card">
  <div class="shield">🛡️</div>
  <h2>Security Verification</h2>
  <p id="status">Checking your browser…</p>
  <div class="bar"><div id="fill"></div></div>
  <ul id="list"></ul>
  <div class="foot">Powered by ModAppsKing Security</div>
</div>
<script>
(function(){
  var token = "__TOKEN__";
  var steps = ["Browser Environment","WebDriver Detection","Canvas Fingerprint","Human Interaction"];
  var list = document.getElementById("list");
  var fill = document.getElementById("fill");
  var status = document.getElementById("status");
  var done = 0;

  function add(name, ok, pending){
    var li = document.createElement("li");
    li.textContent = (pending ? "\u23f3 " : (ok ? "\u2705 " : "\u274c ")) + name;
    if (ok) { li.className = "ok"; }
    list.appendChild(li);
    return li;
  }
  function tick(){ done++; fill.style.width = Math.round(done / steps.length * 100) + "%"; }

  function fingerprint(){
    try{
      var c = document.createElement("canvas");
      var ctx = c.getContext("2d");
      ctx.textBaseline = "top";
      ctx.font = "14px Arial";
      ctx.fillStyle = "#f60";
      ctx.fillRect(0,0,60,20);
      ctx.fillStyle = "#069";
      ctx.fillText("modappsking", 2, 2);
      return c.toDataURL().length > 100;
    }catch(e){ return false; }
  }

  var envOk = !!(window.navigator && window.navigator.userAgent) && typeof window.fetch === "function";
  add(steps[0], envOk); tick();

  var wd = (navigator.webdriver === true)
        || /HeadlessChrome|PhantomJS|Selenium|puppeteer|playwright/i.test(navigator.userAgent)
        || (navigator.plugins && navigator.plugins.length === 0 && /Chrome/i.test(navigator.userAgent));
  add(steps[1], !wd); tick();

  add(steps[2], fingerprint()); tick();

  // Human interaction: brief settle time, shown as pending then passed.
  var humanLi = add(steps[3], false, true);
  status.textContent = "Finalizing verification…";
  setTimeout(function(){
    humanLi.textContent = "\u2705 " + steps[3];
    humanLi.className = "ok";
    tick();

    if (!envOk || wd) {
      status.innerHTML = '<span class="err">Verification failed. Please open the link from the bot again.</span>';
      return;
    }

    // Auto-redirect - no button to tap.
    fetch("/r/" + encodeURIComponent(token) + "/go", {method: "POST"})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (d && d.ok && d.url) { window.location.replace(d.url); }
        else { status.innerHTML = '<span class="err">' + ((d && d.error) || "Verification failed. Please try again.") + "</span>"; }
      })
      .catch(function(){
        status.innerHTML = '<span class="err">Network error. Please try again.</span>';
      });
  }, 1800);
})();
</script>
</body>
</html>
""".replace("__CSS__", PAGE_CSS)


@app.route("/r/<token>", methods=["GET"])
@app.route("/v/<token>", methods=["GET"])
def gateway(token):
    referer = (request.headers.get("Referer") or "").lower()

    if (REQUIRE_REFERER and SHORTLINK_HOST
            and VERIFY_LINK_MODE not in _NO_REFERER_MODES):
        if SHORTLINK_HOST not in referer:
            print(f"[gateway] BLOCKED token={token[:8]}... referer={referer!r}", flush=True)
            return Response(BLOCKED_PAGE, mimetype="text/html", status=403)

    # One-time link: already used / expired -> show the expired page.
    db = _db()
    if db is not None:
        try:
            rec = db.verify_tokens.find_one({"_id": token})
            if not rec or rec.get("used") or rec.get("link_used"):
                print(f"[gateway] EXPIRED token={token[:8]}...", flush=True)
                return Response(EXPIRED_PAGE, mimetype="text/html", status=410)
            created = int(rec.get("created_ts", 0) or 0)
            if created and (int(time.time()) - created) > TOKEN_TTL:
                print(f"[gateway] EXPIRED (ttl) token={token[:8]}...", flush=True)
                return Response(EXPIRED_PAGE, mimetype="text/html", status=410)
        except Exception as e:
            print(f"[gateway] db check failed: {e}", flush=True)

    print(f"[gateway] OK token={token[:8]}... mode={VERIFY_LINK_MODE} referer={referer!r}", flush=True)
    page = GATEWAY_PAGE.replace("__TOKEN__", html.escape(token, quote=True))
    return Response(page, mimetype="text/html")


@app.route("/r/<token>/go", methods=["POST", "GET"])
@app.route("/v/<token>/go", methods=["POST", "GET"])
def gateway_go(token):
    if not BOT_USERNAME:
        return jsonify(ok=False, error="Bot is still starting, please retry in a moment.")
    db = _db()
    if db is None:
        return jsonify(ok=False, error="Server is not configured (DB_URI missing).")
    try:
        rec = db.verify_tokens.find_one({"_id": token})
        if not rec:
            return jsonify(ok=False, error="This verification link is invalid.")
        if rec.get("used") or rec.get("link_used"):
            return jsonify(ok=False, error="This link has already been used. Request a new one from the bot.")
        created = int(rec.get("created_ts", 0) or 0)
        if created and (int(time.time()) - created) > TOKEN_TTL:
            return jsonify(ok=False, error="This link has expired. Please request a new one.")

        # Burn the link (one-time) and mark the gateway as passed.
        db.verify_tokens.update_one(
            {"_id": token},
            {"$set": {"gateway_passed": True, "link_used": True, "link_used_ts": int(time.time())}}
        )

        if VERIFY_LINK_MODE == "page_first":
            ad_link = rec.get("ad_link")
            if not ad_link:
                return jsonify(ok=False, error="Ad step is not ready. Please try again in a moment.")
            return jsonify(ok=True, url=ad_link)
    except Exception:
        return jsonify(ok=False, error="Verification service error. Please try again.")

    return jsonify(ok=True, url="https://t.me/%s?start=verify_%s" % (BOT_USERNAME, token))


def _run():
    port = int(os.environ.get("PORT", 8080))
    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
        use_reloader=False,
        threaded=True
    )


def keep_alive(*_args, **_kwargs):
    t = threading.Thread(target=_run)
    t.daemon = True
    t.start()
