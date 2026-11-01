"""Document-age labels from config/freshness.json. These indicate how old a
report is relative to answer time; they are not a statement that the
forecasts inside remain valid."""
from __future__ import annotations

from datetime import date

from app.common import config
from app.common.timeutil import today_sgt


def policy() -> dict:
    return config.load_json_config("freshness.json")


def label(publication_date: str | None, report_type: str | None, date_confidence: str | None,
          today: date | None = None) -> dict:
    pol = policy()
    rtype = report_type if report_type in pol["policies"] else pol["default"]
    rule = pol["policies"][rtype]
    if not publication_date or date_confidence == "low":
        return {"label": "Date uncertain", "age_days": None, "report_type": rtype,
                "rule": "publication date could not be established with confidence"}
    age = ((today or today_sgt()) - date.fromisoformat(publication_date)).days
    if age <= rule["recent_max_days"]:
        lab = "Recent"
    elif age <= rule["older_max_days"]:
        lab = "Older"
    else:
        lab = "Stale"
    return {"label": lab, "age_days": age, "report_type": rtype,
            "rule": f"{rule['label']}: Recent ≤ {rule['recent_max_days']} days, Older ≤ {rule['older_max_days']} days, "
                    f"Stale beyond"}


def horizon_passed(horizon_end: str | None, today: date | None = None) -> bool:
    return bool(horizon_end) and date.fromisoformat(horizon_end) < (today or today_sgt())
