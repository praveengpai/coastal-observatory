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
| `tests/` | 52 automated tests (pass on SQLite and PostgreSQL 16) |
| `deploy/`, `Dockerfile`, `docker-compose.yml` | Production deployment for the NIO server |
| `docs/` | Deployment, security and audit notes, field guide, data dictionary |

## The four forms

| Form | Used by | Purpose |
| --- | --- | --- |
| `obs_camp_registration` | Welcome desk, waiting-area volunteers | Consent, IDs, household water and sanitation, TDS, recent illness, health history |
| `obs_camp_station` | Measurements, eye, dental, geriatric (MSW) and doctor stations | One form; each phone is set to its station once |
| `obs_household_visit` | ASHAs and volunteers, between camps | Illness counts, referral follow-up, elder checks, advice given |
| `obs_water_sample` | NIO team, citizen scientists | Sample bottle ID, GPS, field readings, Aquadip© result and photo |
| `obs_report_diarrhoea` | ASHAs, volunteers, ward members | Scan the door sticker, pick or add the person, report diarrhoea and days lost |
| `obs_report_health` | ASHAs, volunteers, ward members | Same, for other illness (water-related or not) |
| `obs_report_onehealth` | Anyone in the field | Sick or dead animals, dead fish, rats, mosquito breeding, flooding, water changes |
| `obs_idsp_s` | ASHAs, JPHNs, medical officers | IDSP Form S: one person with an IHIP syndrome, or a weekly nil report |

Camp registration adds each person to a **household list on every phone** (an ODK entity list), so the
report forms can show "who in this house is ill?" offline. A person added in a report joins the list too.
Admins can add more report forms from the Admin tab (start from `forms/dist/report_form_template.xlsx`)
and choose which dashboard roles see each form's reports.

## IDSP module

A separate **IDSP surveillance** tab for the Integrated Disease Surveillance Programme team, on the same
database (details in [docs/IDSP_MODULE.md](docs/IDSP_MODULE.md)):

- **IDSP Form S** (`obs_idsp_s`) for ASHAs, JPHNs and medical officers: IHIP Form S syndromes, nil reports,
  household sticker, GPS, water source and days lost. Entries count as verified.
- **Community signals:** illness reported by volunteers, ward members and camp doctors is captured
  automatically, linked to the same episode, and waits for an IDSP worker to confirm it. Unverified signals
  never enter IDSP counts, exports or outbreak alerts.
- **Forms S, P and L** in the IHIP layout (male and female, up to 5 and over 5 years), reporting completeness
  with nil reports, CSV export of the weekly form and the line list.
- **Alerts** with a named owner and closure: diarrhoea and jaundice clusters (500 m), suspected cholera and
  bloody diarrhoea under 5, admissions and deaths, a leptospirosis signal, contaminated water next to
  water-borne illness, and rises above the ward's own baseline. The District Surveillance Officer sets the thresholds.
- **Roles:** `jphn`, `mo` (medical officer), `dso` (no names), `lab`. Demo data: `python -m tools.seed_idsp_demo`.

## Workdays lost

Every illness report asks the same questions: days ill, the person's usual work, days unable to work,
school days missed and days a family member stayed home to care. The Household reports tab adds these
up for water-related illness (water-borne, water-washed, water contact and mosquito-borne), by site and
type, per 1,000 people registered, and in rupees once an admin sets a daily wage.

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

Demo logins: `admin`, `coordinator`, `scientist`, `doctor`, `asha`, `ward`, `jphn`, `mo`, `dso`, `lab`;
password `demo-password-2026`.

## Common tasks

```bash
python -m tools.stickers person 1 240              # person ID stickers OBS-P-000001..000240
python -m tools.stickers household CVB 1 120       # household stickers for site CVB
python -m tools.stickers sample 1 480              # water sample bottle labels
python -m tools.publish_sites forms/sites.csv      # new site list → ODK Central and the database
python -m tools.create_user anas "Dr. Anas Abdulaziz" scientist
python forms/build_forms.py forms/dist             # rebuild the forms after a question change
python -m tools.publish_forms                      # publish all forms to ODK Central (inside the app container)
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
| jphn | IDSP tab: verifies signals (escalations come here), acts on alerts; names shown |
| mo | IDSP tab: verifies, enters Form P and lab results, exports; master dashboard; names shown |
| dso | IDSP tab: alerts, thresholds, weekly forms and exports; master dashboard; no names |
| lab | IDSP tab: enters laboratory results for verified cases; no names |

Users can be restricted to a list of site codes.
