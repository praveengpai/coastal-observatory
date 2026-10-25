"""Household reports: illness and One Health events reported by ASHAs, volunteers and ward members.

A report form is any ODK form whose ID starts with obs_report_. Reporters scan the household's door
sticker, pick the person from the household list (or add them) and fill the report. Every illness
report asks the same "effect on daily life" questions, so workdays lost add up across forms.

Water-related illness follows the classic Bradley classification:
  water_borne   drunk in water: diarrhoea, dysentery, typhoid, jaundice (hepatitis A/E), cholera
  water_washed  too little water for hygiene: skin and eye infections
  water_contact caught through contact with water: leptospirosis
  vector        insects that breed in water: dengue, malaria, chikungunya
"""
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy.orm import Session

from .models import HomeVisit, Person, PersonPII, Report, ReportForm, Setting

REPORT_PREFIX = "obs_report_"
WATER_CLASS = {
    "diarrhoea": "water_borne", "dysentery": "water_borne", "typhoid": "water_borne", "jaundice": "water_borne",
    "cholera": "water_borne", "skin_water": "water_washed", "eye": "water_washed", "lepto": "water_contact",
    "vector": "vector",
}
CLASS_LABEL = {"water_borne": "Water-borne (drinking water)", "water_washed": "Water-washed (hygiene)",
               "water_contact": "Water contact (leptospirosis)", "vector": "Mosquito-borne (breeds in water)"}
CONDITION_LABEL = {
    "diarrhoea": "Diarrhoea", "dysentery": "Dysentery (blood in stool)", "typhoid": "Typhoid", "jaundice": "Jaundice",
    "cholera": "Cholera", "skin_water": "Skin infection after water contact", "eye": "Red or sticky eyes",
    "lepto": "Leptospirosis", "vector": "Dengue, malaria or chikungunya", "fever": "Fever", "resp": "Respiratory",
    "heat": "Heat illness", "injury": "Injury or fall", "chronic": "Long-term illness", "mental": "Mood or memory",
    "other": "Other",
}
WORKING = {"daily_wage", "fishing", "salaried", "self_emp", "home"}
ALL_ROLES = "admin coordinator scientist doctor asha ward"
DEFAULT_FORMS = [
    ("obs_report_diarrhoea", "Report: diarrhoeal disease", ALL_ROLES,
     "Field team (ASHA / volunteer), Ward members, Training phone"),
    ("obs_report_health", "Report: health issue", "admin coordinator scientist doctor asha",
     "Field team (ASHA / volunteer), Ward members, Training phone"),
    ("obs_report_onehealth", "Report: One Health event", ALL_ROLES,
     "Field team (ASHA / volunteer), Ward members, NIO water sampling, Training phone"),
]
PRIVATE_FIELDS = {"new_name", "name"}


def is_report_form(form_id: str) -> bool:
    return form_id.startswith(REPORT_PREFIX)


def ensure_defaults(db: Session):
    for form_id, title, roles, groups in DEFAULT_FORMS:
        if not db.get(ReportForm, form_id):
            db.add(ReportForm(form_id=form_id, title=title, visible_roles=roles, phone_groups=groups, active=True))
    db.commit()


def get_setting(db: Session, key: str):
    row = db.get(Setting, key)
    return row.value if row else None


def set_setting(db: Session, key: str, value):
    db.merge(Setting(key=key, value=None if value in (None, "") else str(value)))
    db.commit()


# ------------------------------------------------------------------ ingest

def ingest_report(db: Session, form_id: str, f: dict, helpers):
    """`helpers` is sync_odk (passed in to avoid a circular import)."""
    _int, _date, _bool = helpers._int, helpers._date, helpers._bool
    hh = f.get("hh_id") or None
    site = f.get("camp_site") or (hh.split("-")[0] if hh else None)
    if not site:
        return
    helpers._site(db, site)
    helpers._household(db, hh, site)
    on = _date(f.get("today"))
    named = f.get("consent_named") == "yes"
    pid = (f.get("person_id") or None) if named else None
    if named and pid and f.get("in_list_eff") == "no" and not db.get(Person, pid):
        db.add(Person(person_id=pid, hh_id=hh, site_code=site, sex=f.get("p_sex"), age=_int(f.get("p_age")),
                      resident=True, consent_research=False, registered_on=on))
        db.flush()
        db.merge(PersonPII(person_id=pid, name=f.get("new_name"), contact_ok=False))
    condition = f.get("condition") or None
    activity = f.get("activity") or None
    n = lambda k: _int(f.get(k)) or 0  # noqa: E731
    db.merge(Report(
        instance_id=f["_instance_id"], form_id=form_id, site_code=site, hh_id=hh, person_id=pid, named=named,
        reporter_role=f.get("role"), reported_on=on, onset=_date(f.get("onset")), age=_int(f.get("p_age")),
        sex=f.get("p_sex") or None, condition=condition, water_class=WATER_CLASS.get(condition or ""),
        danger=_bool(f.get("danger")), days_ill=_int(f.get("days_ill")), activity=activity,
        work_days=n("work_days") if activity in WORKING else 0, school_days=n("school_days"),
        carer_days=n("carer_days"), care=f.get("care") or None, cost_rs=_int(f.get("cost_rs")),
        events=f.get("event") or None,
        data={k: v for k, v in f.items() if k not in PRIVATE_FIELDS}))


# ------------------------------------------------------------------ reading

def visible_forms(db: Session, role: str):
    forms = db.query(ReportForm).order_by(ReportForm.form_id).all()
    return [x for x in forms if role == "admin" or role in (x.visible_roles or "").split()]


def list_reports(db: Session, principal, codes, form_id=None, days=90, today=None):
    today = today or date.today()
    forms = {x.form_id: x for x in visible_forms(db, principal.role)}
    if form_id:
        forms = {k: v for k, v in forms.items() if k == form_id}
    if not forms or not codes:
        return []
    q = (db.query(Report).filter(Report.form_id.in_(list(forms)), Report.site_code.in_(codes),
                                 Report.reported_on >= today - timedelta(days=days))
         .order_by(Report.reported_on.desc(), Report.instance_id))
    rows = q.limit(1000).all()
    names = {}
    if principal.pii:
        ids = [r.person_id for r in rows if r.named and r.person_id]
        names = {x.person_id: x.name for x in db.query(PersonPII).filter(PersonPII.person_id.in_(ids or [""]))}
    ward = principal.role == "ward"
    out = []
    for r in rows:
        out.append({
            "id": r.instance_id, "form": forms[r.form_id].title, "form_id": r.form_id,
            "date": r.reported_on.isoformat() if r.reported_on else None, "site": r.site_code,
            "hh_id": None if ward else r.hh_id, "person_id": None if ward else r.person_id,
            "name": names.get(r.person_id), "age": r.age, "sex": r.sex,
            "condition": CONDITION_LABEL.get(r.condition or "", r.condition),
            "water_related": CLASS_LABEL.get(r.water_class) if r.water_class else None,
            "danger": r.danger, "days_ill": r.days_ill, "work_days": r.work_days, "school_days": r.school_days,
            "carer_days": r.carer_days, "care": r.care, "events": r.events, "reported_by": r.reporter_role})
    return out


def workdays(db: Session, codes, year: int | None = None, today=None, daily_wage=None):
    """Productive days lost to water-related illness (human-capital method), for a calendar year or the past 365 days."""
    today = today or date.today()
    if year:
        start, end, period = date(year, 1, 1), date(year, 12, 31), str(year)
    else:
        start, end, period = today - timedelta(days=365), today, "Past 12 months"
    rows = (db.query(Report).filter(Report.site_code.in_(codes or [""]), Report.reported_on >= start,
                                    Report.reported_on <= end, Report.condition.isnot(None)).all())
    water = [r for r in rows if r.water_class]

    def totals(rs):
        return {"episodes": len(rs), "work_days": sum(r.work_days or 0 for r in rs),
                "carer_days": sum(r.carer_days or 0 for r in rs), "school_days": sum(r.school_days or 0 for r in rs),
                "cost_rs": sum(r.cost_rs or 0 for r in rs), "admitted": sum(1 for r in rs if r.care == "admitted")}

    t = totals(water)
    t["productive_days"] = t["work_days"] + t["carer_days"]
    by_class = []
    for k, label in CLASS_LABEL.items():
        rs = [r for r in water if r.water_class == k]
        if rs:
            by_class.append({"class": k, "label": label, **totals(rs)})
    by_site = defaultdict(list)
    for r in water:
        by_site[r.site_code].append(r)
    by_month = defaultdict(int)
    for r in water:
        by_month[r.reported_on.strftime("%Y-%m")] += (r.work_days or 0) + (r.carer_days or 0)
    persons = db.query(Person).filter(Person.site_code.in_(codes or [""])).count()
    wage = None
    try:
        wage = float(daily_wage) if daily_wage not in (None, "") else None
    except ValueError:
        wage = None
    return {
        "period": period, **t, "all_illness": totals(rows),
        "per_1000_people": round(1000 * t["productive_days"] / persons, 1) if persons else None,
        "people_registered": persons, "daily_wage_rs": wage,
        "value_rs": round(t["productive_days"] * wage) if wage else None,
        "by_class": by_class,
        "by_site": [{"site": s, **totals(rs)} for s, rs in sorted(by_site.items())],
        "by_month": [{"month": m, "days": d} for m, d in sorted(by_month.items())],
        "note": "Workdays include home duties. Productive days = the ill person's workdays plus days a family member "
                "missed work to care for them. Counts only illness reported through the household report forms.",
    }


# ------------------------------------------------------------------ actions

def tasks(db: Session, codes, show_pii: bool, today=None):
    """ASHA tasks from recent reports: danger signs, and diarrhoea not yet followed by a household visit."""
    today = today or date.today()
    rows = (db.query(Report).filter(Report.site_code.in_(codes or [""]), Report.reported_on >= today - timedelta(days=7),
                                    Report.condition.isnot(None)).all())
    names = {}
    if show_pii:
        ids = [r.person_id for r in rows if r.person_id and r.named]
        names = {x.person_id: x for x in db.query(PersonPII).filter(PersonPII.person_id.in_(ids or [""]))}
    out = []
    for r in rows:
        if not (r.danger or r.water_class == "water_borne") or not r.hh_id:
            continue
        visited = db.query(HomeVisit).filter(HomeVisit.hh_id == r.hh_id, HomeVisit.visit_on >= r.reported_on).count()
        if visited:
            continue
        who = names.get(r.person_id)
        label = CONDITION_LABEL.get(r.condition, r.condition)
        out.append({"kind": "report", "site": r.site_code, "hh_id": r.hh_id, "person_id": r.person_id,
                    "title": ("Urgent: danger signs reported, " if r.danger else "Visit: ") + f"{label.lower()} at {r.hh_id}",
                    "detail": (who.name if who else (r.person_id or "Name not shared")) +
                              (f", {who.phone}" if who and who.phone else "") + "; check the water and give ORS advice",
                    "since": r.reported_on.isoformat() if r.reported_on else None})
    return out


def clusters(db: Session, codes, today=None, threshold=3):
    """Sites with `threshold` or more water-related illness reports in the past 7 days."""
    today = today or date.today()
    out = []
    for code in codes:
        rs = (db.query(Report).filter(Report.site_code == code, Report.water_class.isnot(None),
                                      Report.reported_on >= today - timedelta(days=7)).all())
        if len(rs) >= threshold:
            kinds = sorted({CONDITION_LABEL.get(r.condition, r.condition).lower() for r in rs})
            out.append((code, len(rs), kinds))
    return out
