# Deployment

Two stages: a **staging** server for the pilot and camp 1 (dummy data until ethics clearance and a
data-sharing agreement are in place), then the **NIO server** after its security audit. The same
code runs in both; only `.env` differs.

## 0. Quickest path: one server, one command

On any fresh Ubuntu 22.04/24.04 server with root access (Hostinger VPS, Oracle Cloud, or the NIO server):

```bash
git clone https://github.com/praveengpai/coastal-observatory /opt/observatory && cd /opt/observatory
OBS_DOMAIN=observatory.example.org ODK_DOMAIN=odk.example.org ADMIN_EMAIL=you@example.org \
  bash deploy/install_vps.sh
```

It installs Docker, a firewall, Caddy (automatic HTTPS), ODK Central and the Observatory, then prints
the remaining steps. No domain yet: use free `sslip.io` names built from the server's IP address
(instructions at the top of the script). Pick an India region (Mumbai or Hyderabad) when creating the server.

**Hosting options checked in October 2026:**

| Option | Cost | Fits? |
| --- | --- | --- |
| Hostinger shared or cloud web hosting | low | **No**: cannot run Docker, PostgreSQL or ODK Central |
| Hostinger VPS KVM 2 (2 vCPU, 8 GB RAM, 100 GB) | about ₹799/month intro, ₹1,199 renewal | **Yes**, recommended for the pilot and camp 1 |
| Oracle Cloud Always Free (Arm, now 2 OCPU / 12 GB since June 2026) | free (card verification) | Yes for staging; Oracle cut this allowance without notice in 2026, so do not rely on it for live camps |
| NIO server | institutional | Final home after audit |

### Free setup (₹0): Oracle Cloud Always Free + KoboToolbox

ODK Central does not install on Arm servers, and Oracle's free servers are Arm. So in the free setup
**KoboToolbox** (free for nonprofits; 5,000 submissions a month and 1 GB storage) receives the forms,
and the Oracle server runs only the Observatory.

1. Create an Oracle Cloud account. Choose **India West (Mumbai)** or **India South (Hyderabad)** as the
   home region: it cannot be changed later and free servers must be in it.
2. Create an instance: Ubuntu 24.04, shape **VM.Standard.A1.Flex**, 2 OCPU and 12 GB. Open ports 80 and
   443 in the subnet's security list.
3. On the server: `FORM_SERVER=kobo OBS_DOMAIN=obs.<ip-with-dashes>.sslip.io ADMIN_EMAIL=you@example.org bash deploy/install_vps.sh`
4. Create a MAGICS account at kf.kobotoolbox.org. Upload the four forms from `forms/dist`; for each, upload
   `forms/sites.csv` under Settings → Media, then deploy. Note each form's ID (the code in its web address).
5. Put the Kobo API token (Account settings → Security) and the four form IDs in `.env`
   (`OBS_KOBO_TOKEN`, `OBS_KOBO_ASSETS`), then `docker compose up -d`.
6. Phones: install KoboCollect (or ODK Collect) and connect it to `https://kc.kobotoolbox.org` with the
   project's account. Offline saving, auto-send, QR scanning and the Gboard voice and Manglish keyboard work the same.

Limits to know: Oracle can reclaim a free server that stays nearly idle (under 20% CPU, network and memory)
for 7 days, and it cut its free allowance without notice in 2026; KoboToolbox stores data on its own
servers outside India. Use this for the pilot and training, keep backups, and plan the move to NIO.
Changing the site list: upload the new `sites.csv` to each Kobo form's Media and redeploy; load it into
the Observatory on the Admin tab.

## 1. Server requirements (to request from NIO IT)

- Ubuntu 22.04/24.04 LTS VM: 4 vCPU, 8–16 GB RAM, 200 GB disk (photos from water samples take most space)
- Docker Engine and the Docker Compose plugin
- Two DNS names with TLS certificates, for example `odk.<nio-domain>` and `observatory.<nio-domain>`
- Outbound HTTPS to `api.open-meteo.com` (weather). Everything else is self-contained
- Inbound 443 only. SSH restricted to the NIO admin network
- Nightly backup storage and a GPG key for encrypting backups

## 2. ODK Central

Install ODK Central with its official Docker setup (github.com/getodk/central, "Installing Central").
Then, in Central:

1. Create a project, for example "Coastal Observatory".
2. Upload each form from `forms/dist/`. When Central asks for the `sites.csv` attachment, upload `forms/sites.csv`.
3. Create **App Users** (one per phone or per person) and assign them to the forms they use.
   Each App User has a QR code; scanning it in ODK Collect configures the phone in one step.
4. Create a Web User with the **Project Viewer** role for the Observatory sync, and put its
   email and password in `.env` (`OBS_ODK_EMAIL`, `OBS_ODK_PASSWORD`). Publishing a new site
   list needs **Project Manager**.

## 3. Observatory (manual setup, if not using install_vps.sh)

With install_vps.sh, Caddy sits in front. When the Observatory has its own server instead, use the
bundled nginx: `docker compose --profile nginx up -d`.

```bash
git clone https://github.com/praveengpai/coastal-observatory /opt/observatory && cd /opt/observatory
cp .env.example .env            # fill in every value; generate secrets as the comments say
mkdir -p deploy/tls             # put fullchain.pem and privkey.pem here
docker compose up -d --build
docker compose exec app python -m tools.create_user admin "Administrator" admin
docker compose exec app python -m tools.publish_sites forms/sites.csv
```

Open `https://observatory.<domain>`, sign in, and create the other users on the Admin tab.
The `jobs` container syncs ODK every 15 minutes, drafts advisories hourly and refreshes the
weather twice a day. Tide tables are uploaded as CSV (`date,high_tide_m`) on the Scientist tab.

Backups: add `deploy/backup.sh` to the host's crontab (instructions inside the script) and test a
restore before go-live:

```bash
gpg --decrypt observatory-YYYYMMDD-HHMM.dump.gpg | docker compose exec -T db pg_restore -U observatory -d observatory --clean
```

## 4. Moving from staging to the NIO server

1. Deploy on the NIO server as above; confirm `python -m pytest -q tests` passes in the `app` container.
2. Stop field sync on staging. Back up the staging database and restore it on the NIO server
   (or, if staging held only dummy data, start fresh).
3. Point ODK Collect phones to the NIO ODK Central: issue new App User QR codes. Phones keep any
   unsent forms and send them to the new server after reconfiguration.
4. Delete the staging server and its backups once the NIO server is confirmed. Record the deletion.

## 5. When sites are decided

1. Add rows to `forms/sites.csv`: `name` (2–4 capitals, printed on stickers), `label`
   (English · Malayalam), `site_type` (village, colony, flats, ward), `lat`, `lon`.
2. `python -m tools.publish_sites forms/sites.csv` updates the forms on Central and the database.
3. Phones get the new list next time they refresh blank forms (ODK Collect: "Download form").
4. Print household stickers for each new site code.

## Not tested in this build environment

The Docker image could not be built here (no Docker daemon). The code, all four forms and all 35
tests were verified on Python 3.13 with SQLite and with PostgreSQL 16. Build and smoke-test the
image on the staging server first. `deploy/install_vps.sh` was syntax-checked but not run on a real
server; confirm the ODK Central reverse-proxy settings (step 3 of the script) against the ODK guide for
the Central version installed.
