# WZML-X Branch Patcher

A tiny one-shot service that patches `UPSTREAM_BRANCH` (and optionally `UPSTREAM_REPO`)
directly in your WZML-X MongoDB, so the next bot restart picks up the right branch.

It writes to both `settings.config` and `settings.deployConfig` (if it exists).

---

## Environment variables

| Variable          | Required | Description                                              |
|-------------------|----------|----------------------------------------------------------|
| `DATABASE_URL`    | ✅        | Your MongoDB connection string (same one WZML-X uses)   |
| `BOT_TOKEN`       | ✅        | Your Telegram bot token — used to derive the document ID |
| `UPSTREAM_BRANCH` | ❌        | Branch to set. Defaults to `lxhem03`                    |
| `UPSTREAM_REPO`   | ❌        | Repo to set. Leave empty to leave it unchanged           |

---

## Deploy on Koyeb

1. Push this repo to GitHub.
2. Go to **Koyeb → Create Service → GitHub**.
3. Set **Service type → Worker** (not Web).
4. Add the three env vars above.
5. Deploy — it runs `python patch.py`, patches the DB, and exits.
6. Koyeb will mark the service as "completed". You can re-run it anytime
   by triggering a new deployment.

---

## Run locally

```bash
pip install -r requirements.txt
DATABASE_URL="mongodb+srv://..." BOT_TOKEN="123:ABC" python patch.py
```
