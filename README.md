# Kochi Coastal One Health Observatory: platform

Field data collection, linked water–health database, analytics and role-based dashboards for the
CSIR-NIO × MAGICS / CEDAC Aquadip© project and the longer-term Observatory.

## How it fits together

```
 Phones (ODK Collect, offline)           NIO lab / Aquadip©        Open-Meteo + tide table
   4 forms, Malayalam + English             results CSV               weather, tides
            │ sync when online                   │                        │
            ▼                                    ▼                        ▼
      ODK Central  ──── every 15 min ────►  Observatory API  ◄──── scheduled jobs
     (self-hosted)                          (FastAPI + PostgreSQL)
                                                  │
                                                  ▼
                         Dashboard: master · ASHA · ward · scientist · advisories · admin
```

- **ODK** handles what is hard in the field: offline saving, upload when a phone reaches wifi,
  validation, QR scanning, voice and Manglish typing through the phone keyboard.
- **The Observatory** owns the data model. Everything is keyed by printed sticker IDs:
  person `OBS-P-000123`, household `CVB-014`, water sample `WS-000123`.
- A custom phone app can replace ODK later without losing data: it would write to the same tables.

## What is in this folder

| Path | What it is |
| --- | --- |
| `forms/build_forms.py` | Builds the four ODK forms (`forms/dist/*.xlsx`), all validated with ODK Validate |
| `forms/sites.csv` | The site list attached to every form. Edit this, not the forms, when sites change |
| `app/` | API, database models, ODK sync, analytics, rules |
| `web/` | Dashboard (plain HTML, CSS and JavaScript; no external libraries or fonts) |
| `tools/` | QR stickers, demo data, site publishing, user creation, scheduled jobs, data dictionary |
| `tests/` | 35 automated tests (pass on SQLite and PostgreSQL 16) |
| `deploy/`, `Dockerfile`, `docker-compose.yml` | Production deployment for the NIO server |
| `docs/` | Deployment, security and audit notes, field guide, data dictionary |

## The four forms

| Form | Used by | Purpose |
| --- | --- | --- |
| `obs_camp_registration` | Welcome desk, waiting-area volunteers | Consent, IDs, household water and sanitation, TDS, recent illness, health history |
| `obs_camp_station` | Measurements, eye, dental, geriatric (MSW) and doctor stations | One form; each phone is set to its station once |
| `obs_household_visit` | ASHAs and volunteers, between camps | Illness counts, referral follow-up, elder checks, advice given |
| `obs_water_sample` | NIO team, citizen scientists | Sample bottle ID, GPS, field readings, Aquadip© result and photo |

Site and role carry over from each phone's last form, so they are set once per day.

## Malayalam

Forms, dashboard messages and advisories carry Malayalam for accessibility. Malayalam text is a
machine-assisted translation; English is the reference, and every screen says so. With a Sarvam AI
key in `.env` (`OBS_SARVAM_API_KEY`), messages the team writes on the Advisories tab are translated
automatically. Only team-written message text is sent to Sarvam, never personal data.

## Try it on a laptop (demo data only)

```bash
pip install -r requirements.txt
python -m tools.seed_demo --reset          # dummy data; refuses to run in production
uvicorn app.main:app --port 8000           # open http://localhost:8000
```

Demo logins: `admin`, `coordinator`, `scientist`, `doctor`, `asha`, `ward`; password `demo-password-2026`.

## Common tasks

```bash
python -m tools.stickers person 1 240              # person ID stickers OBS-P-000001..000240
python -m tools.stickers household CVB 1 120       # household stickers for site CVB
python -m tools.stickers sample 1 480              # water sample bottle labels
python -m tools.publish_sites forms/sites.csv      # new site list → ODK Central and the database
python -m tools.create_user anas "Dr. Anas Abdulaziz" scientist
python forms/build_forms.py forms/dist             # rebuild the forms after a question change
python -m tools.data_dictionary                    # refresh docs/data_dictionary.md
python -m pytest -q tests                          # run the tests
```

## Roles

| Role | Sees |
| --- | --- |
| admin | Everything, users, audit log |
| coordinator | All views except user management; runs sync and rules |
| scientist | Master dashboard, statistics, models, de-identified records and exports, lab and tide uploads |
| doctor | Master dashboard, field tasks, approves or rejects every advisory |
| asha | Tasks for their own sites with names and phones, approved messages to send |
| ward | Decisions for their wards, risk summary, counts of vulnerable elders (no names) |

Users can be restricted to a list of site codes.
