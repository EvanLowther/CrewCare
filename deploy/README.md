# Hosting on Vultr

One Vultr server (Miami, Ubuntu 24.04, 2 vCPU / 4 GB, backups off) runs everything; Tiger Data stays the database.

```
phone / browser ──HTTPS──▶ Caddy :443 ──/api/*──▶ FastAPI 127.0.0.1:8000 (planit-api)
                                      └─ else ──▶ Next.js 127.0.0.1:3000 (planit-web)
                           planit-worker (weather, alerts, scoring, briefings) ──▶ Tiger
```

- **Site:** `https://planit.<server-ip-with-dashes>.sslip.io` (free hostname; swap for a real domain in the Caddyfile).
- **Updates:** `planit-deploy.timer` checks GitHub `main` every minute and runs `deploy.sh` when it changed:
  Python packages if `pyproject.toml` changed, migrations if `db/migrations/` changed, and a website rebuild if
  `frontend/` changed. The new build is made beside the live one and swapped in only if it succeeds.
- **Secrets:** only in `/opt/planit/.env` on the server (template: `env.production.example`).
- **Only one worker:** don't run `python dev.py worker` on a laptop while the server's worker is on; both would
  poll the same APIs and run demo jobs twice.

## First-time setup

1. Create the server in Vultr with the `planit-mac` SSH key. Note its IPv4.
2. `scp deploy/bootstrap.sh root@<ip>:` then `ssh root@<ip> bash bootstrap.sh planit.<ip-with-dashes>.sslip.io`.
   The first run prints a deploy key: add it to the repo as **read-only**
   (`gh repo deploy-key add key.pub --title planit-server`), then run bootstrap again.
3. `ssh -t root@<ip> nano /opt/planit/.env`: paste the Tiger connection string and Gemini key.
4. `ssh root@<ip> '/opt/planit/deploy/deploy.sh --force && systemctl start planit-deploy.timer'`.

## Everyday

| Task | Command (from your Mac) |
|---|---|
| Logs | `ssh root@<ip> journalctl -u planit-api -u planit-worker -u planit-web -u planit-deploy -f` |
| Deploy log | `ssh root@<ip> journalctl -u planit-deploy -n 50` |
| Redeploy now | `ssh root@<ip> /opt/planit/deploy/deploy.sh --force` |
| Restart | `ssh root@<ip> systemctl restart planit-api planit-worker planit-web` |
| Pause auto-deploy | `ssh root@<ip> systemctl stop planit-deploy.timer` |

## Cost

About $20/month, billed hourly up to that cap, so the $100 credit lasts roughly 5 months. A stopped server is
still billed: **Destroy** it in Vultr when the project is done, before the credit expires (see Billing).
