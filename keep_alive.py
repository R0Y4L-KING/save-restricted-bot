"""
========================================================
Keep-alive HTTP server for Render / Heroku

Also hosts the ad-gate "Security Check" gateway:

  GET /v/<token>      -> browser-check page (JS)
  GET /v/<token>/go   -> validates the token, flags gateway_passed
                         and only then returns the bot deep link

Why: the shortener points at /v/<token> instead of the raw Telegram
deep link. A shortener-bypass service that only follows redirects gets
the check page and NOT the deep link.

Extra anti-bypass layer: the check page itself only loads when the
browser arrives FROM the shortener (Referer header). A bypassed link
opened directly carries no shortener referer and is refused.
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

# Host of the shortener, used for the Referer check (e.g. "vipshort.in")
SHORTLINK_URL = os.environ.get("SHORTLINK_URL", "vipshort.in")
SHORTLINK_HOST = SHORTLINK_URL.replace("https://", "").replace("http://", "").strip("/").split("/")[0].lower()

# Require the browser to arrive from the shortener. Set REQUIRE_REFERER=False
# if a legitimate flow ever gets blocked (see the logs).
REQUIRE_REFERER = os.environ.get("REQUIRE_REFERER", "True").lower() == "true"

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


BLOCKED_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Verification</title>
<style>
 body{margin:0;background:#0b0f14;color:#e8eef6;font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;display:flex;min-height:100vh;align-items:center;justify-content:center}
 .card{width:min(92vw,420px);background:#111823;border:1px solid #2a1e1e;border-radius:18px;padding:26px 22px;text-align:center}
 h2{margin:10px 0 8px;font-size:20px}
 p{color:#9fb0c4;font-size:14px;line-height:1.5}
 .warn{font-size:46px}
</style></head><body>
<div class="card">
 <div class="warn">\U0001f6ab</div>
 <h2>Open the link properly</h2>
 <p>This verification page must be opened from the <b>Verify Now</b> button in the bot.<br><br>
 Go back to Telegram, tap <b>🔓 Verify Now</b> and complete the steps.</p>
</div></body></html>
"""


GATEWAY_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Security Check</title>
<style>
  body{margin:0;background:#0b0f14;color:#e8eef6;font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;display:flex;min-height:100vh;align-items:center;justify-content:center}
  .card{width:min(92vw,420px);background:#111823;border:1px solid #1e2a3a;border-radius:18px;padding:26px 22px;text-align:center;box-shadow:0 18px 50px rgba(0,0,0,.5)}
  .shield{font-size:52px}
  h2{margin:12px 0 4px;font-size:22px}
  p{color:#9fb0c4;font-size:14px;margin:6px 0 16px}
  .bar{height:8px;background:#1b2534;border-radius:6px;overflow:hidden;margin:14px 0 18px}
  .bar>div{height:100%;width:0;background:linear-gradient(90deg,#22c55e,#16a34a);transition:width .4s}
  ul{list-style:none;padding:0;margin:0 0 18px;text-align:left}
  li{font-size:14px;padding:7px 0;color:#8fa3b8}
  li.ok{color:#22c55e}
  button{width:100%;padding:14px;border:0;border-radius:12px;background:#22c55e;color:#06210f;font-size:16px;font-weight:700;opacity:.45}
  button:enabled{opacity:1;cursor:pointer}
  .err{color:#ef4444;font-size:14px}
  .foot{margin-top:14px;font-size:12px;color:#5c6b7e}
</style>
</head>
<body>
<div class="card">
  <div class="shield">🛡️</div>
  <h2>Security Verification</h2>
  <p id="status">Checking your browser…</p>
  <div class="bar"><div id="fill"></div></div>
  <ul id="list"></ul>
  <button id="go" disabled>Continue</button>
  <div class="foot">Powered by ModAppsKing Security</div>
</div>
<script>
(function(){
  var token = "__TOKEN__";
  var steps = ["Browser Environment","WebDriver Detection","Canvas Fingerprint","Human Interaction"];
  var list = document.getElementById("list");
  var fill = document.getElementById("fill");
  var status = document.getElementById("status");
  var btn = document.getElementById("go");
  var done = 0;

  function add(name, ok){
    var li = document.createElement("li");
    li.textContent = (ok ? "\u2705 " : "\u274c ") + name;
    if (ok) { li.className = "ok"; }
    list.appendChild(li);
    done++;
    fill.style.width = Math.round(done / steps.length * 100) + "%";
  }

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
  add(steps[0], envOk);

  var wd = (navigator.webdriver === true)
        || /HeadlessChrome|PhantomJS|Selenium|puppeteer|playwright/i.test(navigator.userAgent)
        || (navigator.plugins && navigator.plugins.length === 0 && /Chrome/i.test(navigator.userAgent));
  add(steps[1], !wd);

  add(steps[2], fingerprint());

  var start = Date.now();
  function armHuman(){
    if (Date.now() - start < 1500) { setTimeout(armHuman, 300); return; }
    add(steps[3], true);
    status.textContent = "Verification passed! Tap Continue.";
    btn.disabled = false;
  }
  setTimeout(armHuman, 1200);

  btn.addEventListener("click", function(){
    btn.disabled = true;
    status.textContent = "Verifying…";
    fetch("/v/" + encodeURIComponent(token) + "/go", {method: "POST"})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (d && d.ok && d.url) { window.location.href = d.url; }
        else { status.innerHTML = '<span class="err">' + ((d && d.error) || "Verification failed. Please try again.") + "</span>"; btn.disabled = false; }
      })
      .catch(function(){
        status.innerHTML = '<span class="err">Network error. Please try again.</span>';
        btn.disabled = false;
      });
  });
})();
</script>
</body>
</html>
"""


@app.route("/v/<token>", methods=["GET"])
def gateway(token):
    referer = (request.headers.get("Referer") or "").lower()

    if REQUIRE_REFERER and SHORTLINK_HOST:
        if SHORTLINK_HOST not in referer:
            # No shortener referer -> this link was opened directly (bypassed).
            print(f"[gateway] BLOCKED token={token[:8]}... referer={referer!r}", flush=True)
            return Response(BLOCKED_PAGE, mimetype="text/html", status=403)

    print(f"[gateway] OK token={token[:8]}... referer={referer!r}", flush=True)
    page = GATEWAY_PAGE.replace("__TOKEN__", html.escape(token, quote=True))
    return Response(page, mimetype="text/html")


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
        if rec.get("used"):
            return jsonify(ok=False, error="This verification link was already used.")
        created = int(rec.get("created_ts", 0) or 0)
        if created and (int(time.time()) - created) > TOKEN_TTL:
            return jsonify(ok=False, error="This link has expired. Please request a new one.")
        db.verify_tokens.update_one({"_id": token}, {"$set": {"gateway_passed": True}})
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
