"""English → Malayalam machine translation via Sarvam AI (optional).

Used only for message text written by the team (advisories). Never send names, phone numbers
or other personal data here. Results are cached so the same text is translated once.
Malayalam output is a machine-assisted translation for accessibility; English stays the reference.
"""
import hashlib
import os

import requests
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, Session, mapped_column

from .db import Base

SARVAM_URL = "https://api.sarvam.ai/translate"
MODEL = os.environ.get("OBS_SARVAM_MODEL", "sarvam-translate:v1")
MAX_CHARS = 2000 if MODEL.startswith("sarvam-translate") else 1000
DISCLAIMER_EN = "Malayalam text is a machine-assisted translation for accessibility. English is the reference."
DISCLAIMER_ML = "മലയാളം യന്ത്രസഹായത്തോടെയുള്ള വിവർത്തനമാണ്; ഇംഗ്ലീഷ് പാഠമാണ് ആധികാരികം."


class Translation(Base):
    __tablename__ = "translation"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    source: Mapped[str] = mapped_column(Text)
    target: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(40))


def enabled() -> bool:
    return bool(os.environ.get("OBS_SARVAM_API_KEY"))


def _chunks(text: str):
    """Split on sentence ends so each request stays under the model's limit."""
    out, cur = [], ""
    for part in text.replace("\n", " \n").split(". "):
        piece = part if part.endswith((".", "\n")) else part + ". "
        if len(cur) + len(piece) > MAX_CHARS and cur:
            out.append(cur.strip())
            cur = ""
        cur += piece
    if cur.strip():
        out.append(cur.strip().removesuffix(". ").rstrip())
    return out


def to_malayalam(db: Session, text: str) -> str | None:
    """Returns Malayalam text, or None when no API key is configured or the service fails."""
    text = (text or "").strip()
    if not text or not enabled():
        return None
    key = hashlib.sha256(f"{MODEL}|{text}".encode()).hexdigest()
    hit = db.get(Translation, key)
    if hit:
        return hit.target
    parts = []
    for chunk in _chunks(text):
        try:
            r = requests.post(SARVAM_URL, timeout=30,
                              headers={"api-subscription-key": os.environ["OBS_SARVAM_API_KEY"],
                                       "Content-Type": "application/json"},
                              json={"input": chunk, "source_language_code": "en-IN",
                                    "target_language_code": "ml-IN", "model": MODEL, "mode": "formal"})
            r.raise_for_status()
            parts.append(r.json()["translated_text"])
        except (requests.RequestException, KeyError, ValueError):
            return None
    result = " ".join(parts)
    db.merge(Translation(key=key, source=text, target=result, model=MODEL))
    db.commit()
    return result
