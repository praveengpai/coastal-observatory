"""Turns data into actions: advisories, ward decisions, ASHA task lists and named queries.

Every advisory is created as a DRAFT and must be approved by a doctor before it is sent.
"""
from datetime import date, timedelta

from sqlalchemy.orm import Session

from . import analytics, config, reports
from .models import Advisory, Decision, HomeVisit, Person, PersonPII, StationRecord

TEMPLATES = {
    "boil": (
        "Your water test result: not safe to drink as it is. Boil drinking water for at least one minute. "
        "Your ASHA worker will visit with advice.",
        "നിങ്ങളുടെ വെള്ള പരിശോധനാ ഫലം: ഇപ്പോഴത്തെ നിലയിൽ കുടിക്കാൻ സുരക്ഷിതമല്ല. കുറഞ്ഞത് ഒരു മിനിറ്റ് തിളപ്പിച്ച ശേഷം മാത്രം കുടിക്കുക. "
        "ആശാ പ്രവർത്തക നിർദ്ദേശങ്ങളുമായി വീട്ടിലെത്തും."),
    "heat": (
        "Very hot days ahead. Stay out of the sun from 12 to 3 pm, drink water often, and check on elders who live alone.",
        "വരും ദിവസങ്ങളിൽ കടുത്ത ചൂട്. ഉച്ചയ്ക്ക് 12 മുതൽ 3 വരെ വെയിലത്ത് ഇറങ്ങരുത്, ഇടയ്ക്കിടെ വെള്ളം കുടിക്കുക, "
        "ഒറ്റയ്ക്ക് താമസിക്കുന്ന പ്രായമായവരെ അന്വേഷിക്കുക."),
    "tide": (
        "High tide expected. Keep medicines for 5 days and a charged phone ready. Call your ASHA worker if you need help to move.",
        "ഉയർന്ന വേലിയേറ്റം പ്രതീക്ഷിക്കുന്നു. 5 ദിവസത്തേക്കുള്ള മരുന്നും ചാർജുള്ള ഫോണും കരുതുക. "
        "മാറാൻ സഹായം വേണമെങ്കിൽ ആശാ പ്രവർത്തകയെ വിളിക്കുക."),
}


def _upsert_advisory(db, key, site, kind, hh=None):
    if db.query(Advisory).filter_by(rule_key=key).first():
        return 0
    en, ml = TEMPLATES[kind]
    db.add(Advisory(rule_key=key, site_code=site, hh_id=hh, kind=kind, text_en=en, text_ml=ml))
    return 1


def _upsert_decision(db, key, site, title, reason):
    if db.query(Decision).filter_by(rule_key=key).first():
        return 0
    db.add(Decision(rule_key=key, site_code=site, title=title, reason=reason))
    return 1


def generate(db: Session, sites, today: date | None = None):
    """Create new draft advisories and open ward decisions from current data. Idempotent."""
    today = today or date.today()
    fc = analytics.forecast(db, today)
    n_adv = n_dec = 0
    for s, p, _ in analytics.sample_results(db, sites, today - timedelta(days=28)):
        if p and s.hh_id:
            n_adv += _upsert_advisory(db, f"boil:{s.sample_id}", s.site_code, "boil", s.hh_id)
    hi_next = max([d["heat_index_c"] for d in fc[:3] if d["heat_index_c"] is not None], default=None)
    tide_next = max([d["tide_m"] or 0 for d in fc[:3]], default=0)
    week = today.isocalendar()
    for code in sites:
        site = db.get(analytics.Site, code)
        risk = analytics.site_risk(db, site, today, fc)
        m = risk["metrics"]
        geri = db.query(StationRecord).filter(StationRecord.site_code == code, StationRecord.station == "geri").all()
        evac = sum(1 for g in geri if g.evac)
        alone = sum(1 for g in geri if g.alone)
        if hi_next is not None and hi_next >= config.HEAT_HIGH:
            n_adv += _upsert_advisory(db, f"heat:{code}:{week[0]}-{week[1]}", code, "heat")
            if alone:
                n_dec += _upsert_decision(db, f"coolroom:{code}:{week[0]}-{week[1]}", code,
                                          "Open a community hall or PHC as a cool room on the hottest days",
                                          f"Heat index up to {hi_next} °C forecast; {alone} screened elders live alone")
        if tide_next >= config.TIDE_ALERT_M:
            n_adv += _upsert_advisory(db, f"tide:{code}:{week[0]}-{week[1]}", code, "tide")
            if evac:
                n_dec += _upsert_decision(db, f"vehicle:{code}:{week[0]}-{week[1]}", code,
                                          f"Arrange transport for {evac} elders before the high tide",
                                          f"Tide of {tide_next} m forecast; they cannot walk to the relief centre")
        if risk["layers"]["water"] == "high":
            n_dec += _upsert_decision(db, f"safewater:{code}:{week[0]}-{week[1]}", code,
                                      "Set up a temporary safe drinking-water point",
                                      f"{round(100 * m['positivity'])}% of samples positive in 8 weeks")
        if risk["layers"]["salinity"] == "high":
            n_dec += _upsert_decision(db, f"salinity:{code}:{today.year}", code,
                                      "Explore an alternative drinking-water source and add BP screening",
                                      f"Median water TDS {m['tds_median']} mg/L")
    for code, n, kinds in reports.clusters(db, sites, today):
        n_dec += _upsert_decision(db, f"cluster:{code}:{week[0]}-{week[1]}", code,
                                  "Investigate a cluster of water-related illness: test the water sources",
                                  f"{n} reports in 7 days ({', '.join(kinds)})")
    db.commit()
    return {"advisories_created": n_adv, "decisions_created": n_dec}


def _names(db, ids, show):
    if not show or not ids:
        return {}
    return {p.person_id: p for p in db.query(PersonPII).filter(PersonPII.person_id.in_(ids))}


def asha_tasks(db: Session, sites, show_pii: bool, today: date | None = None):
    today = today or date.today()
    tasks = []
    refs = db.query(StationRecord).filter(StationRecord.site_code.in_(sites), StationRecord.referral.isnot(None)).all()
    done = {p for (p,) in db.query(HomeVisit.ref_person).filter(HomeVisit.ref_status.in_(["went", "refused", "moved"]))}
    pending = [r for r in refs if r.person_id not in done]
    pii = _names(db, [r.person_id for r in pending], show_pii)
    people = {p.person_id: p for p in db.query(Person).filter(Person.person_id.in_([r.person_id for r in pending] or [""]))}
    for r in pending:
        who = pii.get(r.person_id)
        tasks.append({"kind": "referral", "site": r.site_code, "person_id": r.person_id,
                      "hh_id": people.get(r.person_id).hh_id if people.get(r.person_id) else None,
                      "title": f"Follow up {r.station} referral: {r.referral}",
                      "detail": (who.name if who else r.person_id) + (f", {who.phone}" if who and who.phone else ""),
                      "since": r.collected_on.isoformat() if r.collected_on else None})
    for s, p, _ in analytics.sample_results(db, sites, today - timedelta(days=28)):
        if not p or not s.hh_id:
            continue
        advised = db.query(HomeVisit).filter(HomeVisit.hh_id == s.hh_id, HomeVisit.visit_on >= s.collected_on).all()
        if not any(analytics.ADVICE_CODES & set((v.advice or "").split()) for v in advised):
            tasks.append({"kind": "advice", "site": s.site_code, "hh_id": s.hh_id,
                          "title": f"Give water result and boiling advice to {s.hh_id}",
                          "detail": f"Sample {s.sample_id} positive on {s.collected_on}", "since": str(s.collected_on)})
        elif (today - s.collected_on).days >= 7:
            tasks.append({"kind": "resample", "site": s.site_code, "hh_id": s.hh_id,
                          "title": f"Collect a repeat sample from {s.hh_id}",
                          "detail": f"First sample {s.sample_id} positive on {s.collected_on}", "since": str(s.collected_on)})
    fc = analytics.forecast(db, today)
    tide = max([d["tide_m"] or 0 for d in fc[:3]], default=0)
    hi = max([d["heat_index_c"] for d in fc[:3] if d["heat_index_c"] is not None], default=None)
    if tide >= config.TIDE_ALERT_M or (hi is not None and hi >= config.HEAT_WATCH):
        geri = db.query(StationRecord).filter(StationRecord.site_code.in_(sites), StationRecord.station == "geri").all()
        targets = [g for g in geri if (tide >= config.TIDE_ALERT_M and g.evac) or
                   (hi is not None and hi >= config.HEAT_WATCH and g.alone)]
        pii = _names(db, [g.person_id for g in targets], show_pii)
        for g in targets:
            who = pii.get(g.person_id)
            why = "high tide, needs help to evacuate" if tide >= config.TIDE_ALERT_M and g.evac else "heat, lives alone"
            tasks.append({"kind": "elder", "site": g.site_code, "person_id": g.person_id,
                          "title": f"Check on elder before {why.split(',')[0]}",
                          "detail": (who.name if who else g.person_id) + f": {why}", "since": today.isoformat()})
    tasks += reports.tasks(db, sites, show_pii, today)
    return tasks


QUERIES = {
    "elders_salty_high_bp": "Elders 60+ on salty water (TDS over 1,000 mg/L) with high blood pressure",
    "referrals_pending": "People referred at a camp who have not yet been followed up",
    "positive_not_advised": "Households with a positive water sample not yet given advice",
    "elders_alone_or_evac": "Elders 60+ who live alone or need help to evacuate",
    "frail_or_cognitive": "Elders who are frail (CFS 5+) or screened positive on Mini-Cog",
}


def run_query(db: Session, name: str, sites, show_pii: bool):
    rows = []
    if name == "elders_salty_high_bp":
        tds = analytics._hh_tds(db, sites)
        for m, p in (db.query(StationRecord, Person).join(Person, Person.person_id == StationRecord.person_id)
                     .filter(StationRecord.station == "meas", StationRecord.site_code.in_(sites), Person.age >= 60)):
            if tds.get(p.hh_id, 0) > 1000 and ((m.sbp or 0) >= 140 or (m.dbp or 0) >= 90):
                rows.append({"person_id": p.person_id, "hh_id": p.hh_id, "site": p.site_code, "age": p.age,
                             "bp": f"{m.sbp:.0f}/{m.dbp:.0f}", "tds": tds[p.hh_id]})
    elif name == "referrals_pending":
        rows = [t for t in asha_tasks(db, sites, False) if t["kind"] == "referral"]
    elif name == "positive_not_advised":
        rows = [t for t in asha_tasks(db, sites, False) if t["kind"] == "advice"]
    elif name == "elders_alone_or_evac":
        for g in db.query(StationRecord).filter(StationRecord.site_code.in_(sites), StationRecord.station == "geri"):
            if g.alone or g.evac:
                rows.append({"person_id": g.person_id, "site": g.site_code, "age": g.age,
                             "lives_alone": g.alone, "needs_evacuation_help": g.evac, "cfs": g.cfs})
    elif name == "frail_or_cognitive":
        for g in db.query(StationRecord).filter(StationRecord.site_code.in_(sites), StationRecord.station == "geri"):
            if (g.cfs or 0) >= 5 or (g.minicog is not None and g.minicog < 3):
                rows.append({"person_id": g.person_id, "site": g.site_code, "age": g.age, "cfs": g.cfs,
                             "minicog": g.minicog, "phq2": g.phq2})
    else:
        raise KeyError(name)
    if show_pii:
        pii = _names(db, [r.get("person_id") for r in rows if r.get("person_id")], True)
        for r in rows:
            who = pii.get(r.get("person_id"))
            if who:
                r["name"], r["phone"] = who.name, who.phone
    return {"query": name, "question": QUERIES[name], "count": len(rows), "rows": rows}
