#!/usr/bin/env bash
# One-time server setup for Ubuntu 24.04, run as root:  bash bootstrap.sh <hostname>
#   e.g. bash bootstrap.sh planit.203-0-113-7.sslip.io
# Safe to run again. See deploy/README.md for the full order of steps.
set -euo pipefail

HOST=${1:?usage: bootstrap.sh <hostname>}
REPO=git@github.com:EvanLowther/planit-control.git
APP=/opt/planit
export DEBIAN_FRONTEND=noninteractive

echo "== packages"
apt-get update -q
apt-get install -y -q git python3-venv python3-dev build-essential ufw curl gnupg debian-keyring \
  debian-archive-keyring apt-transport-https

# Node 22 (NodeSource apt repo) and Caddy (official apt repo)
install -d -m 0755 /etc/apt/keyrings
if [[ ! -f /etc/apt/sources.list.d/nodesource.list ]]; then
  curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg
  echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_22.x nodistro main" \
    > /etc/apt/sources.list.d/nodesource.list
fi
if [[ ! -f /etc/apt/sources.list.d/caddy-stable.list ]]; then
  curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/gpg.key | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt > /etc/apt/sources.list.d/caddy-stable.list
fi
apt-get update -q
apt-get install -y -q nodejs caddy
corepack enable

echo "== swap (Next.js builds need the headroom)"
if ! swapon --show | grep -q /swapfile; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  grep -q /swapfile /etc/fstab || echo "/swapfile none swap sw 0 0" >> /etc/fstab
fi

echo "== firewall: SSH, HTTP, HTTPS only"
ufw allow OpenSSH && ufw allow 80/tcp && ufw allow 443/tcp && ufw --force enable

echo "== SSH: keys only"
sed -i 's/^#\?PasswordAuthentication .*/PasswordAuthentication no/' /etc/ssh/sshd_config
rm -f /etc/ssh/sshd_config.d/50-cloud-init.conf   # re-enables passwords on some images
systemctl reload ssh

echo "== app user + GitHub deploy key"
id planit >/dev/null 2>&1 || useradd --system --create-home --shell /bin/bash planit
install -d -o planit -g planit -m 700 /home/planit/.ssh
if [[ ! -f /home/planit/.ssh/github_deploy ]]; then
  runuser -u planit -- ssh-keygen -t ed25519 -N "" -C "planit-server deploy key" -f /home/planit/.ssh/github_deploy -q
fi
runuser -u planit -- bash -c 'ssh-keyscan -t ed25519 github.com >> ~/.ssh/known_hosts 2>/dev/null; sort -u -o ~/.ssh/known_hosts ~/.ssh/known_hosts'
cat > /home/planit/.ssh/config <<CFG
Host github.com
  IdentityFile ~/.ssh/github_deploy
  IdentitiesOnly yes
CFG
chown planit:planit /home/planit/.ssh/config

if [[ ! -d $APP/.git ]]; then
  if ! runuser -u planit -- ssh -o BatchMode=yes -T git@github.com 2>&1 | grep -q "successfully authenticated"; then
    echo
    echo "Add this read-only deploy key to the GitHub repo, then run bootstrap.sh again:"
    cat /home/planit/.ssh/github_deploy.pub
    exit 2
  fi
  install -d -o planit -g planit "$APP"
  runuser -u planit -- git clone -q "$REPO" "$APP"
fi

echo "== Python packages"
[[ -d $APP/.venv ]] || runuser -u planit -- python3 -m venv "$APP/.venv"
runuser -u planit -- "$APP/.venv/bin/pip" install -q --upgrade pip
runuser -u planit -- "$APP/.venv/bin/pip" install -q -e "$APP/backend[ml]"

if [[ ! -f $APP/.env ]]; then
  install -o planit -g planit -m 600 "$APP/deploy/env.production.example" "$APP/.env"
fi

echo "== services"
cp "$APP"/deploy/systemd/*.service "$APP"/deploy/systemd/*.timer /etc/systemd/system/
sed "s/^PLANIT_HOST /$HOST /" "$APP/deploy/Caddyfile" > /etc/caddy/Caddyfile
systemctl daemon-reload
systemctl enable planit-api planit-worker planit-web planit-deploy.timer
systemctl reload-or-restart caddy

echo
echo "Bootstrap done. Next: fill in $APP/.env (Tiger URL + Gemini key), then:"
echo "  sudo $APP/deploy/deploy.sh --force && systemctl start planit-deploy.timer"
