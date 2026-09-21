"""In-memory Lakeside Home Services store (deterministic seed)."""

from __future__ import annotations

import hashlib
import random
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

PHONE_RE = re.compile(r"^\d{10}$")
CODE_RE = re.compile(r"^LHS-[A-Z0-9]{6}$")

SERVICE_TYPES: tuple[tuple[str, str, tuple[int, int], int], ...] = (
    ("hvac_repair", "HVAC repair", (120, 450), 90),
    ("plumbing_repair", "Plumbing repair", (95, 380), 75),
    ("maintenance_visit", "Maintenance visit", (80, 160), 60),
)

# Service-area zips (fictional Lakeside metro).
SERVICE_ZIPS: tuple[str, ...] = (
    "98101",
    "98102",
    "98103",
    "98105",
    "98107",
    "98109",
    "98115",
    "98117",
    "98119",
    "98121",
    "98122",
    "98125",
)


@dataclass
class Service:
    service_type: str
    display_name: str
    price_low: int
    price_high: int
    duration_min: int


@dataclass
class Slot:
    slot_id: str
    service_type: str
    starts_at: datetime
    ends_at: datetime
    zip_scope: list[str]
    is_open: bool = True


@dataclass
class Appointment:
    confirmation_code: str
    customer_name: str
    phone: str
    address: str
    service_type: str
    slot_id: str
    notes: str | None
    status: str
    idempotency_key: str | None
    created_call_id: str | None
    created_at: datetime


@dataclass
class Callback:
    ticket_id: str
    customer_name: str
    phone: str
    reason: str
    preferred_window: str | None
    created_call_id: str | None
    created_at: datetime


@dataclass
class KbDoc:
    doc_id: str
    title: str
    body: str


@dataclass
class BizStore:
    seed: int = 0
    services: dict[str, Service] = field(default_factory=dict)
    slots: dict[str, Slot] = field(default_factory=dict)
    appointments: dict[str, Appointment] = field(default_factory=dict)
    callbacks: dict[str, Callback] = field(default_factory=dict)
    kb: dict[str, KbDoc] = field(default_factory=dict)
    idempotency: dict[str, str] = field(default_factory=dict)  # key -> confirmation_code

    def fingerprint(self) -> str:
        """Stable hash of seeded content (services, slots, kb) for equality tests."""
        blob = {
            "seed": self.seed,
            "services": sorted(self.services),
            "slots": sorted(
                (s.slot_id, s.service_type, s.starts_at.isoformat(), s.is_open)
                for s in self.slots.values()
            ),
            "kb": sorted((d.doc_id, d.title, d.body) for d in self.kb.values()),
        }
        return hashlib.sha256(repr(blob).encode()).hexdigest()


def _rng(seed: int) -> random.Random:
    return random.Random(seed)


def _anchor_monday(seed: int) -> date:
    """Fixed calendar anchor so seed→slots is stable across wall-clock days."""
    # 2026-09-21 is a Monday; offset by seed days modulo 7 keeps weekday alignment.
    return date(2026, 9, 21) + timedelta(days=(seed % 7))


def build_kb_docs() -> list[KbDoc]:
    """~25 FAQ documents. Deliberate gaps are listed in docs/kb_gaps.md."""
    docs: list[tuple[str, str, str]] = [
        (
            "hours",
            "Business hours",
            "Lakeside Home Services is open Monday through Friday 8:00 AM to 6:00 PM local time. "
            "Saturday appointments are available 9:00 AM to 1:00 PM for maintenance visits only. "
            "We are closed Sundays and major US holidays.",
        ),
        (
            "service_area",
            "Service area ZIP codes",
            "We serve ZIP codes 98101, 98102, 98103, 98105, 98107, 98109, 98115, 98117, 98119, "
            "98121, 98122, and 98125. Addresses outside these ZIPs are out of area; we can take "
            "a callback for partner referrals.",
        ),
        (
            "hvac_range",
            "HVAC repair price range",
            "HVAC repair visits are typically priced between 120 and 450 US dollars depending on "
            "parts and labour. This is a range only; technicians quote after inspection.",
        ),
        (
            "plumbing_range",
            "Plumbing repair price range",
            "Plumbing repair visits are typically priced between 95 and 380 US dollars. "
            "Emergency after-hours work may differ; see emergency policy.",
        ),
        (
            "maintenance_range",
            "Maintenance visit price range",
            "Scheduled maintenance visits are typically 80 to 160 US dollars.",
        ),
        (
            "cancel_policy",
            "Cancellation policy",
            "Cancel or reschedule at least 4 hours before the appointment start to avoid a "
            "35 dollar late-cancel fee. Same-day cancellations under 4 hours may incur the fee. "
            "Weather and safety closures are fee-waived.",
        ),
        (
            "warranty",
            "Workmanship warranty",
            "Labour on completed repairs carries a 90-day workmanship warranty. Parts follow "
            "manufacturer warranties. Warranty does not cover misuse, storms, or third-party changes.",
        ),
        (
            "emergency",
            "Emergency policy",
            "For active flooding, gas smell, or no-heat below freezing overnight, call us and ask "
            "for an emergency callback. We triage emergency callbacks during business hours first; "
            "after-hours emergency dispatch is not guaranteed.",
        ),
        (
            "what_to_expect",
            "What to expect on a visit",
            "A technician arrives in a marked Lakeside van, confirms the confirmation code, "
            "inspects, explains options, and gets approval before paid parts work beyond the "
            "diagnostic visit.",
        ),
        (
            "payment",
            "Payment methods",
            "We accept major credit cards and ACH. Payment is due upon completion unless a "
            "financing plan was arranged in advance.",
        ),
        (
            "prep_hvac",
            "Prepare for HVAC visit",
            "Clear access to the furnace or outdoor unit, secure pets, and note any recent error "
            "codes on the thermostat.",
        ),
        (
            "prep_plumbing",
            "Prepare for plumbing visit",
            "Know where the main water shutoff is. If safe, stop using the affected fixture.",
        ),
        (
            "reschedule",
            "How to reschedule",
            "Provide your confirmation code and the last four digits of the booking phone number. "
            "We will offer open slots in the same service type.",
        ),
        (
            "confirm_code",
            "Confirmation codes",
            "Confirmation codes look like LHS-ABC123. Keep the code and the phone number used to book.",
        ),
        (
            "callback",
            "Callback requests",
            "If we cannot book or answer a question from our knowledge base, we can open a callback "
            "ticket. A coordinator returns calls during business hours.",
        ),
        (
            "noise",
            "Common HVAC noises",
            "Rattling often means loose panels; screeching may indicate belt or bearing issues. "
            "We diagnose on-site; do not open sealed refrigerant systems yourself.",
        ),
        (
            "leaks",
            "Minor plumbing leaks",
            "For slow drips under a sink, place a bucket and shut the fixture valve if possible. "
            "For ceiling leaks or main-line breaks, shut the main water valve and request emergency callback.",
        ),
        (
            "filters",
            "Filter changes",
            "We recommend checking HVAC filters every 1 to 3 months. Filter replacement can be part "
            "of a maintenance visit.",
        ),
        (
            "permits",
            "Permits",
            "Most residential repair visits do not require a city permit. Larger replacements may; "
            "the office will advise if a permit is needed after inspection.",
        ),
        (
            "pets",
            "Pets on site",
            "Please secure pets before the technician arrives for safety.",
        ),
        (
            "access",
            "Property access",
            "Someone 18 or older should be present, or leave lockbox instructions when booking notes.",
        ),
        (
            "covid",
            "On-site health practices",
            "Technicians can wear masks on request. Please share known illness in the home when booking.",
        ),
        (
            "reviews",
            "Feedback",
            "After a completed visit you may receive a short survey. Ratings help trainings; they do "
            "not change billing.",
        ),
        (
            "privacy",
            "Customer privacy",
            "We do not share appointment lists. Callers can only access their own booking with the "
            "confirmation code and matching phone last four digits.",
        ),
        (
            "out_of_scope",
            "Out of scope work",
            "We do not perform new construction plumbing, commercial refrigeration, or electrical "
            "panel upgrades. We can take a callback for referrals.",
        ),
    ]
    return [KbDoc(doc_id=i, title=t, body=b) for i, t, b in docs]


def seed_store(seed: int = 42) -> BizStore:
    """Deterministic Lakeside seed: services, 2 weeks of slots, KB docs."""
    rng = _rng(seed)
    store = BizStore(seed=seed)
    for st, name, (lo, hi), dur in SERVICE_TYPES:
        store.services[st] = Service(st, name, lo, hi, dur)

    start = _anchor_monday(seed)
    slot_n = 0
    for day_offset in range(14):
        day = start + timedelta(days=day_offset)
        weekday = day.weekday()  # Mon=0
        if weekday == 6:  # Sunday closed
            continue
        allowed: tuple[str, ...]
        if weekday == 5:  # Saturday: maintenance only, 9-13
            hours = [(9, 0), (10, 0), (11, 0), (12, 0)]
            allowed = ("maintenance_visit",)
        else:
            hours = [(8, 0), (10, 0), (13, 0), (15, 0)]
            allowed = tuple(s[0] for s in SERVICE_TYPES)
        for hour, minute in hours:
            for service_type in allowed:
                # Deterministic openness: ~85% open
                open_flag = rng.random() < 0.85
                slot_n += 1
                starts = datetime(day.year, day.month, day.day, hour, minute, tzinfo=UTC)
                dur = store.services[service_type].duration_min
                ends = starts + timedelta(minutes=dur)
                # Rotate zip scopes
                z0 = (slot_n * 3) % len(SERVICE_ZIPS)
                zips = [SERVICE_ZIPS[(z0 + i) % len(SERVICE_ZIPS)] for i in range(4)]
                sid = f"SLOT-{seed:04d}-{slot_n:04d}"
                store.slots[sid] = Slot(
                    slot_id=sid,
                    service_type=service_type,
                    starts_at=starts,
                    ends_at=ends,
                    zip_scope=zips,
                    is_open=open_flag,
                )

    for doc in build_kb_docs():
        store.kb[doc.doc_id] = doc
    return store


def make_confirmation_code(rng: random.Random) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "LHS-" + "".join(rng.choice(alphabet) for _ in range(6))


def phone_last4(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    return digits[-4:] if len(digits) >= 4 else digits


def kb_search(store: BizStore, q: str, k: int = 3) -> list[dict[str, Any]]:
    """Simple ranked search approximating tsvector ranking (token overlap + title boost)."""
    tokens = [t.lower() for t in re.findall(r"[a-z0-9]+", q.lower()) if len(t) > 1]
    if not tokens:
        return []
    scored: list[tuple[float, KbDoc]] = []
    for doc in store.kb.values():
        text = (doc.title + " " + doc.body).lower()
        score = 0.0
        for tok in tokens:
            score += text.count(tok)
            if tok in doc.title.lower():
                score += 2.0
        if score > 0:
            scored.append((score, doc))
    scored.sort(key=lambda x: (-x[0], x[1].doc_id))
    out: list[dict[str, Any]] = []
    for score, doc in scored[: max(1, k)]:
        out.append(
            {
                "doc_id": doc.doc_id,
                "title": doc.title,
                "snippet": doc.body[:240],
                "score": round(score, 3),
            }
        )
    return out
