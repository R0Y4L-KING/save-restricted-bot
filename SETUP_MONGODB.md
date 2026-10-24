# Set up MongoDB for the bot

The bot stores users, login sessions, captions, thumbnails, premium status and
ban lists in MongoDB. It talks to it through `motor` (async driver), so any
standard MongoDB — including the free **MongoDB Atlas** tier — works.

You only need one value from this guide: **`DB_URI`** (the connection string).

---

## Option A — MongoDB Atlas (free, recommended)

### 1. Create the account and cluster

1. Sign up at <https://www.mongodb.com/cloud/atlas/register>.
2. Create an organisation/project, then click **Build a Database**.
3. Choose **M0 — FREE** (512 MB storage, shared). Pick the region closest to your
   Render region (`singapore` in `render.yaml`) — e.g. **AWS / ap-southeast-1**.
4. Give the cluster a name (e.g. `save-bot`) and click **Create**.

### 2. Create a database user

1. Under **Security → Database Access**, click **Add New Database User**.
2. Choose **Password** authentication.
3. Username: e.g. `savebot`  ·  Password: click **Autogenerate** and **copy it**.
4. Role: **Read and write to any database**.
5. Click **Add User**.

### 3. Allow network access

1. Under **Security → Network Access**, click **Add IP Address**.
2. Choose **Allow Access from Anywhere** (`0.0.0.0/0`) and confirm.

> This is required because Render's outbound IPs are not fixed on the free plan.
> The password on the DB user is what protects the database — keep it secret.

### 4. Get the connection string

1. Go to your cluster → **Connect** → **Drivers**.
2. Copy the string. It looks like:

   ```
   mongodb+srv://savebot:<password>@save-bot.xxxxx.mongodb.net/?retryWrites=true&w=majority
   ```

3. Replace `<password>` with the password from step 2.
4. Add a database name before the `?` so the bot uses it directly:

   ```
   mongodb+srv://savebot:YOUR_PASSWORD@save-bot.xxxxx.mongodb.net/SaveRestricted2?retryWrites=true&w=majority
   ```

   Keep `DB_NAME=SaveRestricted2` in the environment too — it matches.

---

## Option B — Self-hosted MongoDB

If you already run a server, install MongoDB there and point `DB_URI` at it:

```
mongodb://<user>:<password>@<host>:27017/SaveRestricted2?authSource=admin
```

Then set `DB_NAME=SaveRestricted2`. Make sure port 27017 is reachable from Render.

---

## Put it into the environment

**Render:** Service → **Environment** → add `DB_URI` (paste the full string) and
`DB_NAME=SaveRestricted2`, then redeploy.

**Local:** put them in your `.env`.

---

## Verify

After deploying, open the Render **Logs** tab. A healthy start shows:

```
MongoDB Connected: 0 users found.
```

If you see `DB stats failed` or a timeout instead, check:

- the `<password>` placeholder was actually replaced,
- the DB user has **Read and write** permission,
- Network Access includes `0.0.0.0/0`,
- the password has no unescaped special characters (`@`, `#`, `:` …) — if it does,
  URL-encode them or regenerate a simpler password.
