#!/usr/bin/env bash
# One-command setup of ODK Central + the Observatory on a fresh Ubuntu 22.04/24.04 server
# (Hostinger VPS, Oracle Cloud, or the NIO server). Run as root:
#
#   OBS_DOMAIN=observatory.example.org ODK_DOMAIN=odk.example.org ADMIN_EMAIL=you@example.org \
#     bash deploy/install_vps.sh
#
# No domain yet? Use free sslip.io names built from the server's IP, e.g. for 203.0.113.7:
#   OBS_DOMAIN=obs.203-0-113-7.sslip.io ODK_DOMAIN=odk.203-0-113-7.sslip.io
#
# Free setup with KoboToolbox as the form server (no ODK Central, works on Arm servers such as
# Oracle Cloud Always Free):   FORM_SERVER=kobo OBS_DOMAIN=... ADMIN_EMAIL=... bash deploy/install_vps.sh
#
# Layout: Caddy (automatic HTTPS) in front of both; ODK Central on 127.0.0.1:8080,
# Observatory on 127.0.0.1:8000. Safe to re-run.
set -euo pipefail
: "${OBS_DOMAIN:?set OBS_DOMAIN}" "${ADMIN_EMAIL:?set ADMIN_EMAIL}"
FORM_SERVER=${FORM_SERVER:-odk}
[ "$FORM_SERVER" = kobo ] || : "${ODK_DOMAIN:?set ODK_DOMAIN (or FORM_SERVER=kobo)}"
HERE=$(cd "$(dirname "$0")/.." && pwd)

echo "== 1. System packages, Docker, firewall"
apt-get update -y
apt-get install -y ca-certificates curl git ufw gnupg debian-keyring debian-archive-keyring apt-transport-https
command -v docker >/dev/null || curl -fsSL https://get.docker.com | sh
ufw allow OpenSSH && ufw allow 80/tcp && ufw allow 443/tcp && ufw --force enable
if ! swapon --show | grep -q swap; then             # ODK Central builds need memory headroom
  fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

echo "== 2. Caddy (HTTPS certificates are automatic)"
if ! command -v caddy >/dev/null; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -y && apt-get install -y caddy
fi
cat > /etc/caddy/Caddyfile <<CADDY
{
    email ${ADMIN_EMAIL}
}
${OBS_DOMAIN} {
    encode gzip
    reverse_proxy 127.0.0.1:8000
}
CADDY
[ "$FORM_SERVER" = kobo ] || printf '%s {\n    reverse_proxy 127.0.0.1:8080\n}\n' "${ODK_DOMAIN}" >> /etc/caddy/Caddyfile

if [ "$FORM_SERVER" != kobo ]; then
echo "== 3. ODK Central"
if [ ! -d /opt/central ]; then
  git clone https://github.com/getodk/central /opt/central
  cd /opt/central && git submodule update -i
fi
cd /opt/central
[ -f .env ] || cp .env.template .env
sed -i "s/^DOMAIN=.*/DOMAIN=${ODK_DOMAIN}/; s/^SYSADMIN_EMAIL=.*/SYSADMIN_EMAIL=${ADMIN_EMAIL}/; s/^SSL_TYPE=.*/SSL_TYPE=upstream/" .env
grep -q '^HTTP_PORT=' .env && sed -i 's/^HTTP_PORT=.*/HTTP_PORT=127.0.0.1:8080/' .env || echo 'HTTP_PORT=127.0.0.1:8080' >> .env
grep -q '^HTTPS_PORT=' .env && sed -i 's/^HTTPS_PORT=.*/HTTPS_PORT=127.0.0.1:8443/' .env || echo 'HTTPS_PORT=127.0.0.1:8443' >> .env
docker compose build && docker compose up -d
# Check these settings against ODK's "Using a custom reverse proxy" guide for the Central version installed.
fi

echo "== 4. Observatory"
cd "$HERE"
if [ ! -f .env ]; then
  cp .env.example .env
  sed -i "s/^OBS_SECRET_KEY=.*/OBS_SECRET_KEY=$(openssl rand -base64 48 | tr -d '\n/+=')/" .env
  sed -i "s/^OBS_DB_PASSWORD=.*/OBS_DB_PASSWORD=$(openssl rand -base64 24 | tr -d '\n/+=')/" .env
  if [ "$FORM_SERVER" = kobo ]; then
    printf '\nOBS_FORM_SERVER=kobo\nOBS_KOBO_URL=https://kf.kobotoolbox.org\nOBS_KOBO_TOKEN=\nOBS_KOBO_ASSETS=\n' >> .env
  else
    sed -i "s#^OBS_ODK_URL=.*#OBS_ODK_URL=https://${ODK_DOMAIN}#" .env
  fi
  chmod 600 .env
fi
docker compose up -d --build
systemctl reload caddy || systemctl restart caddy

cat <<DONE

Installed (form server: ${FORM_SERVER}). Next steps (with Kobo: skip 1 and 2, see docs/DEPLOYMENT.md "Free setup"):
  1. Create the ODK web admin:    cd /opt/central && docker compose exec service odk-cmd --email ${ADMIN_EMAIL} user-create
                                  docker compose exec service odk-cmd --email ${ADMIN_EMAIL} user-promote
  2. In https://${ODK_DOMAIN}: create the project, upload the 4 forms from forms/dist with forms/sites.csv,
     create a Project Viewer web user and put its email and password in ${HERE}/.env (OBS_ODK_EMAIL, OBS_ODK_PASSWORD),
     then: cd ${HERE} && docker compose up -d
  3. Observatory admin:           cd ${HERE} && docker compose exec app python -m tools.create_user admin "Administrator" admin
  4. Optional demo data (staging only: set OBS_ENVIRONMENT=staging in .env first):
                                  docker compose exec app python -m tools.seed_demo
  5. Add deploy/backup.sh to root's crontab.
Open https://${OBS_DOMAIN}
DONE
