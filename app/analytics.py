"""Risk levels, statistics and models. Pure Python + numpy so results are easy to audit."""
import math
import statistics
from collections import defaultdict
from datetime import date, timedelta

import numpy as np
from sqlalchemy.orm import Session

from . import config
from .models import (HomeVisit, HouseholdSurvey, LabResult, Person, Registration, Site, StationRecord, Weather,
                     WaterSample)

LEVELS = ("low", "watch", "high")


def level(value, watch, high):
    if value is None:
        return None
    return "high" if value >= high else "watch" if value >= watch else "low"


def site_codes(db: Session, include_test=False, allowed=None):
    q = db.query(Site).filter(Site.active.is_(True))
    out = []
    for s in q.order_by(Site.code):
        if not include_test and s.site_type in config.TEST_SITE_TYPES:
            continue
        if allowed is not None and s.code not in allowed:
            continue
        out.append(s)
    return out


# ------------------------------------------------------------------ water results

def sample_results(db: Session, sites=None, since: date | None = None):
    """Each sample with its best result: NIO lab if available, else Aquadip©."""
    q = db.query(WaterSample)
    if sites is not None:
        q = q.filter(WaterSample.site_code.in_(sites))
    if since:
        q = q.filter(WaterSample.collected_on >= since)
    samples = q.all()
    labs = defaultdict(dict)
    for r in db.query(LabResult).filter(LabResult.sample_id.in_([s.sample_id for s in samples] or [""])):
        labs[r.sample_id][r.method] = r
    out = []
    for s in samples:
        res = labs[s.sample_id].get("nio_lab") or labs[s.sample_id].get("aquadip")
        out.append((s, None if res is None else res.positive, labs[s.sample_id]))
    return out


# ------------------------------------------------------------------ climate

def heat_index_c(temp_c: float, rh: float) -> float:
    """US NWS Rothfusz regression with its standard adjustments, returned in °C."""
    t = temp_c * 9 / 5 + 32
    simple = 0.5 * (t + 61.0 + (t - 68.0) * 1.2 + rh * 0.094)
    if (simple + t) / 2 < 80:
        hi = simple
    else:
        hi = (-42.379 + 2.04901523 * t + 10.14333127 * rh - 0.22475541 * t * rh - 0.00683783 * t * t
              - 0.05481717 * rh * rh + 0.00122874 * t * t * rh + 0.00085282 * t * rh * rh
              - 0.00000199 * t * t * rh * rh)
        if rh < 13 and 80 <= t <= 112:
            hi -= ((13 - rh) / 4) * math.sqrt((17 - abs(t - 95)) / 17)
        elif rh > 85 and 80 <= t <= 87:
            hi += ((rh - 85) / 10) * ((87 - t) / 5)
    return round((hi - 32) * 5 / 9, 1)


def heat_band(hi_c):
    if hi_c is None:
        return None
    if hi_c >= 54:
        return "Extreme danger"
    if hi_c >= 41:
        return "Danger"
    if hi_c >= 32:
        return "Extreme caution"
    if hi_c >= 27:
        return "Caution"
    return "Low"


def contamination_probability(rain_mm, tide_m, temp_c):
    m = config.MODEL
    z = (m["intercept"] + m["rain_mm"] * rain_mm + m["tide_m_above_0_8"] * (tide_m - 0.8)
         + m["temp_c_above_28"] * (temp_c - 28))
    return 1 / (1 + math.exp(-z))


def scenario(db: Session, rain_mm, tide_m, temp_c, rh, sites):
    p = contamination_probability(rain_mm, tide_m, temp_c)
    hi = heat_index_c(temp_c, rh)
    band = heat_band(hi)
    share = {"Extreme danger": 0.6, "Danger": 0.35, "Extreme caution": 0.15, "Caution": 0.05, "Low": 0.02}[band]
    households = db.query(HouseholdSurvey.hh_id).filter(HouseholdSurvey.site_code.in_(sites)).distinct().count()
    elders = db.query(Person).filter(Person.site_code.in_(sites), Person.age >= 60).count()
    return {
        "inputs": {"rain_mm": rain_mm, "tide_m": tide_m, "temp_c": temp_c, "rh": rh},
        "contamination_probability": round(p, 3),
        "households_surveyed": households,
        "households_needing_advisory": round(households * p),
        "heat_index_c": hi, "heat_band": band,
        "elders_registered": elders, "elders_at_heat_risk": round(elders * share),
        "model": dict(config.MODEL),
        "note": "Prior coefficients until refitted on Phase 1 data (tools/fit_model.py).",
    }


def forecast(db: Session, today: date | None = None):
    today = today or date.today()
    rows = db.query(Weather).filter(Weather.day >= today).order_by(Weather.day).limit(7).all()
    out = []
    for w in rows:
        hi = heat_index_c(w.temp_max, w.rh_mean) if w.temp_max is not None and w.rh_mean is not None else None
        p = contamination_probability(w.rain_mm or 0, w.tide_max_m or 0.8, w.temp_max or 28)
        lvl = max([level(p, 0.2, 0.5), level(hi, config.HEAT_WATCH, config.HEAT_HIGH),
                   "high" if (w.tide_max_m or 0) >= config.TIDE_ALERT_M else None,
                   "high" if (w.rain_mm or 0) >= config.RAIN_ALERT_MM else None],
                  key=lambda x: -1 if x is None else LEVELS.index(x))
        actions = []
        if (w.tide_max_m or 0) >= config.TIDE_ALERT_M:
            actions.append("High tide: check elders who need help to evacuate")
        if (w.rain_mm or 0) >= config.RAIN_ALERT_MM:
            actions.append("Heavy rain: pre-position chlorine, plan repeat sampling")
        if hi is not None and hi >= config.HEAT_HIGH:
            actions.append("Heat danger: call elders living alone")
        elif hi is not None and hi >= config.HEAT_WATCH:
            actions.append("Heat caution: heat advice to elders")
        out.append({"day": w.day.isoformat(), "rain_mm": w.rain_mm, "tide_m": w.tide_max_m, "temp_max": w.temp_max,
                    "rh": w.rh_mean, "heat_index_c": hi, "contamination_probability": round(p, 3),
                    "level": lvl or "low", "actions": actions or ["Routine sampling and visits"]})
    return out


# ------------------------------------------------------------------ risk map

def site_risk(db: Session, site: Site, today: date | None = None, fc=None):
    today = today or date.today()
    code = site.code
    res = [p for _, p, _ in sample_results(db, [code], today - timedelta(days=56)) if p is not None]
    positivity = sum(res) / len(res) if res else None

    visits = db.query(HomeVisit).filter(HomeVisit.site_code == code,
                                        HomeVisit.visit_on >= today - timedelta(days=28)).all()
    hh_visited = len({v.hh_id for v in visits})
    illness = (100 * sum(v.n_diarrhoea for v in visits) / hh_visited) if hh_visited else None

    tds = [t for (t,) in db.query(HouseholdSurvey.tds).filter(HouseholdSurvey.site_code == code,
                                                             HouseholdSurvey.tds.isnot(None))]
    tds += [t for (t,) in db.query(WaterSample.tds).filter(WaterSample.site_code == code, WaterSample.tds.isnot(None),
                                                         WaterSample.point_type == "household")]
    tds_median = statistics.median(tds) if tds else None

    geri = db.query(StationRecord).filter(StationRecord.site_code == code, StationRecord.station == "geri").all()
    vuln = (sum(1 for g in geri if g.alone or g.evac or (g.cfs or 0) >= 5) / len(geri)) if geri else None

    fc = fc if fc is not None else forecast(db, today)
    hi_next = max([d["heat_index_c"] for d in fc[:3] if d["heat_index_c"] is not None], default=None)

    layers = {
        "water": level(positivity, config.POSITIVITY_WATCH, config.POSITIVITY_HIGH),
        "illness": level(illness, config.ILLNESS_WATCH, config.ILLNESS_HIGH),
        "salinity": level(tds_median, config.TDS_WATCH, config.TDS_HIGH),
        "heat": level(hi_next, config.HEAT_WATCH, config.HEAT_HIGH),
        "vulnerability": level(vuln, config.VULN_WATCH, config.VULN_HIGH),
    }
    known = [v for v in layers.values() if v]
    layers["combined"] = max(known, key=LEVELS.index) if known else None
    elders = db.query(Person).filter(Person.site_code == code, Person.age >= 60).count()
    return {
        "code": code, "label": site.label, "site_type": site.site_type, "lat": site.lat, "lon": site.lon,
        "layers": layers,
        "metrics": {
            "samples_8wk": len(res), "positivity": None if positivity is None else round(positivity, 3),
            "diarrhoea_per_100hh_4wk": None if illness is None else round(illness, 1),
            "households_visited_4wk": hh_visited,
            "tds_median": tds_median, "elders_registered": elders,
            "elders_screened": len(geri), "vulnerable_share": None if vuln is None else round(vuln, 3),
            "heat_index_next3d": hi_next,
        },
    }


# ------------------------------------------------------------------ statistics

def odds_ratio(a, b, c, d):
    """2x2 table: exposed (a=outcome, b=no outcome), unexposed (c, d). Woolf 95% CI, Haldane correction."""
    n = a + b + c + d
    if n == 0 or (a + b) == 0 or (c + d) == 0:
        return None
    if 0 in (a, b, c, d):
        a, b, c, d = a + 0.5, b + 0.5, c + 0.5, d + 0.5
    or_ = (a * d) / (b * c)
    se = math.sqrt(1 / a + 1 / b + 1 / c + 1 / d)
    lo, hi = math.exp(math.log(or_) - 1.96 * se), math.exp(math.log(or_) + 1.96 * se)
    return {"or": round(or_, 2), "ci": [round(lo, 2), round(hi, 2)], "n": int(n)}


def pearson(xs, ys):
    n = len(xs)
    if n < 4:
        return None
    r = float(np.corrcoef(xs, ys)[0, 1])
    if math.isnan(r):
        return None
    z, se = math.atanh(max(min(r, 0.999999), -0.999999)), 1 / math.sqrt(n - 3)
    return {"r": round(r, 3), "ci": [round(math.tanh(z - 1.96 * se), 3), round(math.tanh(z + 1.96 * se), 3)], "n": n}


def ols(xs, ys):
    if len(xs) < 3:
        return None
    slope, intercept = np.polyfit(xs, ys, 1)
    return {"slope": float(slope), "intercept": float(intercept)}


def fit_logistic(X: np.ndarray, y: np.ndarray, names, iters=50):
    """Logistic regression by Newton-Raphson (IRLS) with Wald 95% CIs."""
    n, k = X.shape
    if n < 10 * k or y.sum() == 0 or y.sum() == n:
        return {"fitted": False, "n": int(n), "events": int(y.sum()),
                "reason": "Not enough data yet (rule of thumb: 10 events per predictor)."}
    Xc = np.column_stack([np.ones(n), X])
    beta = np.zeros(k + 1)
    converged = False
    for _ in range(iters):
        p = 1 / (1 + np.exp(-Xc @ beta))
        W = p * (1 - p)
        H = Xc.T @ (Xc * W[:, None]) + 1e-8 * np.eye(k + 1)
        step = np.linalg.solve(H, Xc.T @ (y - p))
        beta += step
        if np.max(np.abs(step)) < 1e-8:
            converged = True
            break
    cov = np.linalg.inv(H)
    se = np.sqrt(np.diag(cov))
    p = 1 / (1 + np.exp(-Xc @ beta))
    auc = _auc(y, p)
    terms = []
    for i, name in enumerate(["intercept"] + list(names)):
        terms.append({"term": name, "coef": round(float(beta[i]), 3), "se": round(float(se[i]), 3),
                      "or": round(math.exp(beta[i]), 2),
                      "ci": [round(math.exp(beta[i] - 1.96 * se[i]), 2), round(math.exp(beta[i] + 1.96 * se[i]), 2)]})
    return {"fitted": True, "converged": converged, "n": int(n), "events": int(y.sum()), "auc": auc, "terms": terms}


def _auc(y, p):
    pos, neg = p[y == 1], p[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return None
    wins = sum((pp > pn) + 0.5 * (pp == pn) for pp in pos for pn in neg)
    return round(float(wins / (len(pos) * len(neg))), 3)


def sample_model(db: Session, sites):
    rows = [(s, p) for s, p, _ in sample_results(db, sites) if p is not None]
    if not rows:
        return fit_logistic(np.zeros((0, 4)), np.zeros(0), [])
    X = np.array([[1.0 if s.rain_48h else 0.0, 1.0 if s.flooded_7d else 0.0,
                   1.0 if s.source in ("own_well", "shared_well") else 0.0,
                   1.0 if s.taken_at == "stored" else 0.0] for s, _ in rows])
    y = np.array([1.0 if p else 0.0 for _, p in rows])
    return fit_logistic(X, y, ["heavy rain 48h", "flooded 7d", "well source", "stored water"])


def weekly_trend(db: Session, sites, weeks=8, today: date | None = None):
    today = today or date.today()
    start = today - timedelta(weeks=weeks)
    monday = start - timedelta(days=start.weekday())
    buckets = []
    for i in range(weeks + 1):
        ws = monday + timedelta(weeks=i)
        buckets.append({"week": ws.isoformat(), "samples": 0, "positive": 0, "diarrhoea": 0})
    idx = lambda d: (d - monday).days // 7  # noqa: E731
    for s, p, _ in sample_results(db, sites, monday):
        if p is None or not s.collected_on:
            continue
        i = idx(s.collected_on)
        if 0 <= i < len(buckets):
            buckets[i]["samples"] += 1
            buckets[i]["positive"] += int(p)
    for v in db.query(HomeVisit).filter(HomeVisit.site_code.in_(sites), HomeVisit.visit_on >= monday):
        i = idx(v.visit_on)
        if 0 <= i < len(buckets):
            buckets[i]["diarrhoea"] += v.n_diarrhoea
    for b in buckets:
        b["positivity"] = round(b["positive"] / b["samples"], 3) if b["samples"] else None
    pos = [b["positivity"] for b in buckets]
    dia = [b["diarrhoea"] for b in buckets]
    lag = None
    pairs = [(pos[i], dia[i + 1]) for i in range(len(buckets) - 1) if pos[i] is not None]
    if len(pairs) >= 4:
        lag = pearson([a for a, _ in pairs], [b for _, b in pairs])
    return {"weeks": buckets, "lag1_correlation": lag}


def _hh_tds(db: Session, sites):
    tds = {}
    for hh, t in db.query(HouseholdSurvey.hh_id, HouseholdSurvey.tds).filter(
            HouseholdSurvey.site_code.in_(sites), HouseholdSurvey.tds.isnot(None)):
        tds[hh] = t
    for hh, t in db.query(WaterSample.hh_id, WaterSample.tds).filter(
            WaterSample.site_code.in_(sites), WaterSample.tds.isnot(None), WaterSample.hh_id.isnot(None)):
        tds.setdefault(hh, t)
    return tds


def salinity_bp(db: Session, sites):
    tds = _hh_tds(db, sites)
    pts = []
    for m, p in (db.query(StationRecord, Person).join(Person, Person.person_id == StationRecord.person_id)
                 .filter(StationRecord.station == "meas", StationRecord.sbp.isnot(None),
                         StationRecord.site_code.in_(sites), Person.age >= 60, Person.consent_research.is_(True))):
        if p.hh_id in tds:
            pts.append({"tds": tds[p.hh_id], "sbp": m.sbp})
    xs, ys = [p["tds"] for p in pts], [p["sbp"] for p in pts]
    return {"points": pts, "correlation": pearson(xs, ys), "fit": ols(xs, ys)}


def associations(db: Session, sites):
    out = []
    surveys = {h.hh_id: h for h in db.query(HouseholdSurvey).filter(HouseholdSurvey.site_code.in_(sites))}
    results = [(s, p) for s, p, _ in sample_results(db, sites) if p is not None]

    def table(rows, exposed, outcome):
        a = sum(1 for r in rows if exposed(r) and outcome(r))
        b = sum(1 for r in rows if exposed(r) and not outcome(r))
        c = sum(1 for r in rows if not exposed(r) and outcome(r))
        d = sum(1 for r in rows if not exposed(r) and not outcome(r))
        return odds_ratio(a, b, c, d)

    wells = [(s, p) for s, p in results if s.hh_id in surveys and surveys[s.hh_id].septic_dist in ("lt10", "10to30", "gt30")]
    out.append({"name": "Septic pit under 10 m → positive well sample",
                **(table(wells, lambda r: surveys[r[0].hh_id].septic_dist == "lt10", lambda r: r[1]) or {})})
    out.append({"name": "Heavy rain in 48 h → positive sample",
                **(table(results, lambda r: bool(r[0].rain_48h), lambda r: r[1]) or {})})
    out.append({"name": "Source flooded in 7 days → positive sample",
                **(table(results, lambda r: bool(r[0].flooded_7d), lambda r: r[1]) or {})})

    tds = _hh_tds(db, sites)
    bp = [(p, m) for m, p in (db.query(StationRecord, Person).join(Person, Person.person_id == StationRecord.person_id)
                              .filter(StationRecord.station == "meas", StationRecord.sbp.isnot(None),
                                      StationRecord.site_code.in_(sites), Person.age >= 60))
          if p.hh_id in tds]
    out.append({"name": "Household TDS over 1,000 mg/L → hypertension (60+)",
                **(table(bp, lambda r: tds[r[0].hh_id] > 1000, lambda r: r[1].sbp >= 140 or (r[1].dbp or 0) >= 90) or {})})

    geri = db.query(StationRecord).filter(StationRecord.station == "geri", StationRecord.site_code.in_(sites),
                                          StationRecord.heat_sx.isnot(None), StationRecord.alone.isnot(None)).all()
    out.append({"name": "Living alone → heat symptoms (60+)",
                **(table(geri, lambda r: r.alone, lambda r: r.heat_sx) or {})})
    return out


# ------------------------------------------------------------------ quality and loop

def kappa(pairs):
    n = len(pairs)
    if n == 0:
        return None
    po = sum(1 for a, b in pairs if a == b) / n
    pa = sum(1 for a, _ in pairs if a) / n
    pb = sum(1 for _, b in pairs if b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return None if pe == 1 else round((po - pe) / (1 - pe), 3)


def quality(db: Session, sites):
    regs = db.query(Registration).filter(Registration.site_code.in_(sites)).all()
    meas = db.query(StationRecord).filter(StationRecord.site_code.in_(sites), StationRecord.station == "meas").all()
    adults = [m for m in meas if (m.age or 0) >= 18]
    samples = sample_results(db, sites)
    pairs = [(labs["aquadip"].positive, labs["nio_lab"].positive) for _, _, labs in samples
             if "aquadip" in labs and "nio_lab" in labs
             and labs["aquadip"].positive is not None and labs["nio_lab"].positive is not None]
    tp = sum(1 for a, b in pairs if a and b)
    fn = sum(1 for a, b in pairs if not a and b)
    tn = sum(1 for a, b in pairs if not a and not b)
    fp = sum(1 for a, b in pairs if a and not b)
    share = lambda num, den: round(num / den, 3) if den else None  # noqa: E731
    return {
        "registration_completeness": share(sum(1 for r in regs if r.age is not None and r.sex and r.hh_id), len(regs)),
        "measurement_completeness": share(sum(1 for m in adults if m.sbp and m.glucose), len(adults)),
        "samples_with_gps": share(sum(1 for s, _, _ in samples if s.lat), len(samples)),
        "samples_lab_confirmed": share(sum(1 for _, _, labs in samples if "nio_lab" in labs), len(samples)),
        "aquadip_vs_lab": {
            "pairs": len(pairs), "agreement": share(tp + tn, len(pairs)), "kappa": kappa(pairs),
            "sensitivity": share(tp, tp + fn), "specificity": share(tn, tn + fp),
        },
        "counts": {"registrations": len(regs), "measurements": len(meas), "samples": len(samples)},
    }


ADVICE_CODES = {"result", "boil", "chlorinate", "tank"}


def loop_closed(db: Session, sites):
    positives = [(s, s.collected_on) for s, p, _ in sample_results(db, sites) if p and s.hh_id and s.collected_on]
    advised, delays = 0, []
    for s, on in positives:
        visits = (db.query(HomeVisit).filter(HomeVisit.hh_id == s.hh_id, HomeVisit.visit_on >= on)
                  .order_by(HomeVisit.visit_on).all())
        hit = next((v for v in visits if ADVICE_CODES & set((v.advice or "").split())), None)
        if hit:
            advised += 1
            delays.append((hit.visit_on - on).days)
    refs = (db.query(StationRecord.person_id).filter(StationRecord.site_code.in_(sites), StationRecord.referral.isnot(None))
            .distinct().all())
    ref_ids = {r for (r,) in refs}
    went = {p for (p,) in db.query(HomeVisit.ref_person).filter(HomeVisit.ref_person.in_(ref_ids or {""}),
                                                                HomeVisit.ref_status == "went")}
    from .models import Advisory
    adv = db.query(Advisory).filter(Advisory.site_code.in_(sites)).all()
    share = lambda num, den: round(num / den, 3) if den else None  # noqa: E731
    return {
        "positive_households": len(positives), "advised": advised, "advised_share": share(advised, len(positives)),
        "median_days_to_advice": statistics.median(delays) if delays else None,
        "referrals": len(ref_ids), "referrals_completed": len(went), "referral_share": share(len(went), len(ref_ids)),
        "advisories_total": len(adv),
        "advisories_reviewed_share": share(sum(1 for a in adv if a.status in ("approved", "sent")), len(adv)),
    }


def ageing(db: Session, sites, fc=None):
    elders = db.query(Person).filter(Person.site_code.in_(sites), Person.age >= 60).all()
    geri = {g.person_id: g for g in db.query(StationRecord).filter(StationRecord.site_code.in_(sites),
                                                                   StationRecord.station == "geri")}
    g = [geri[e.person_id] for e in elders if e.person_id in geri]
    fc = fc if fc is not None else forecast(db)
    hi_next = max([d["heat_index_c"] for d in fc[:3] if d["heat_index_c"] is not None], default=None)
    tide_next = max([d["tide_m"] or 0 for d in fc[:3]], default=0)
    alone = sum(1 for x in g if x.alone)
    return {
        "elders_registered": len(elders), "elders_screened": len(g),
        "living_alone": alone, "need_evacuation_help": sum(1 for x in g if x.evac),
        "frail_cfs5plus": sum(1 for x in g if (x.cfs or 0) >= 5),
        "heat_symptoms": sum(1 for x in g if x.heat_sx),
        "falls_2plus": sum(1 for x in g if (x.falls or 0) >= 2),
        "minicog_positive": sum(1 for x in g if x.minicog is not None and x.minicog < 3),
        "phq2_positive": sum(1 for x in g if x.phq2 is not None and x.phq2 >= 3),
        "heat_index_next3d": hi_next, "heat_band": heat_band(hi_next),
        "tide_next3d_m": tide_next, "tide_alert": tide_next >= config.TIDE_ALERT_M,
        "at_heat_risk_now": alone if hi_next is not None and hi_next >= config.HEAT_WATCH else 0,
    }
