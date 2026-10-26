# IDSP module

A workspace for the Integrated Disease Surveillance Programme (IDSP) team inside the Kochi Coastal One
Health Observatory. IDSP staff do their routine surveillance here; the same records feed the shared
Observatory database with CSIR-NIO, and the IDSP-relevant parts of everyone else's records reach IDSP
as signals to check.

## Principles

1. **Collect once, use many.** One database; the IDSP tab is a view of it, not a separate system.
2. **IDSP's own forms and words.** IHIP Form S syndromes and Form P diseases, Monday-to-Sunday reporting
   weeks, age bands up to 5 and over 5 years, male and female.
3. **Complement IHIP, never compete.** IHIP stays the official system. The module exports the weekly
   Form S and P and a line list as CSV, so nothing is typed twice. Column names will be matched to the
   IHIP template the District Surveillance Officer provides; a direct link needs state approval.
4. **Every record says where it came from.** Community signals count only after an IDSP worker confirms them.
5. **Early warning, not a scorecard.**

## How data flows

| Source | Becomes | Counts in IDSP |
| --- | --- | --- |
| IDSP Form S (`obs_idsp_s`), filled by ASHA, JPHN, JHI or MO | A verified case (tier S) | Yes |
| Medical officer enters a Form P disease | Tier P | Yes |
| Laboratory enters a positive result | Tier L | Yes |
| Household report by a volunteer or ward member (`obs_report_*`) | A community signal | Only once confirmed |
| Camp doctor diagnosis (acute diarrhoea, suspected leptospirosis) | A community signal | Only once confirmed |
| Nil report on Form S | The ward has reported for that week | Completeness |

Community conditions map to Form S syndromes: diarrhoea to loose watery stools, dysentery to loose
watery stools with blood, jaundice to jaundice, fever, typhoid, leptospirosis and dengue-like illness to
fever (under or over 7 days, with the suspicion kept), cough or breathing problems to ARI/ILI.

**One episode, one case.** Records join the same case when they share the household, the person (or,
without a name, sex and age within 2 years), the syndrome group and an onset within 14 days. Form S for
the same person confirms the signal automatically. A worker can also mark a signal as a duplicate of
another case.

**Verification.** ASHA, JPHN or MO confirms, or records not a case, could not be reached, or duplicate.
Signals not checked within 72 hours (24 hours if urgent) show as past the deadline and pass to the JPHN.
Urgent: danger signs, admission, death, suspected cholera, bloody diarrhoea under 5.

## Alerts (verified cases only)

| Alert | Starting threshold | To | Expected |
| --- | --- | --- | --- |
| Diarrhoea cluster | 3 cases within 500 m in 7 days | JPHN, MO | Field visit and water sample within 48 hours |
| Suspected cholera, or bloody diarrhoea under 5 | 1 case | MO, DSO | Investigate today |
| Admission or death with a water-borne or fever syndrome | 1 case | MO, DSO | Review today |
| Jaundice cluster | 2 cases within 500 m in 30 days | MO, DSO | Investigation and water source check |
| Leptospirosis signal | 2 suspected or diagnosed in a ward in 14 days | MO, DSO | Review prophylaxis |
| Contaminated water next to water-borne illness | Positive sample within 250 m of a case, 14 days | JPHN, MO, ward member | Household advice, active case search |
| Above the ward's baseline | Week's water-borne cases above mean + 2 SD of earlier weeks (8+ weeks of history), at least 3 | DSO | Review |

A household without a GPS point counts the whole ward as its neighbourhood, so a missing location never
hides a cluster. A positive sample with no illness nearby is handled by the Observatory's water advisories
and ASHA tasks, not repeated here. The DSO changes thresholds on the IDSP tab. An alert is acknowledged
and then closed with a note of what was done; the tab reports median hours to acknowledge and the share
closed within 48 hours.

## Who sees what

| Role | Verify | Form P | Lab | Alerts | Thresholds | Exports | Names |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ASHA | Yes | | | View | | | Yes |
| JPHN / JHI | Yes | | | Act | | | Yes |
| Medical officer | Yes | Yes | Yes | Act | | Yes | Yes |
| District Surveillance Officer | | | | Act | Yes | Yes | No |
| Laboratory | | | Yes | View | | | No |
| Coordinator, doctor, scientist (MAGICS, NIO) | | | | View | | Coordinator | Scientist: no |
| Ward member | No IDSP tab | | | | | | |

## Before the pilot

- MoU or joint SOP with the district IDSP unit: data ownership, purposes, who sees names, alert duties, retention.
- Confirm the syndrome list and case definitions against the current IHIP forms, and approve the thresholds.
- Consent at household enrolment under the DPDP Act 2023; notifiable-disease reporting continues through
  official channels under the Kerala Public Health Act 2023.
- Publish the form: `python -m tools.publish_forms` (creates the "IDSP staff (ASHA / JPHN / MO)" phone account).
