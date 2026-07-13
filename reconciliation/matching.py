"""
deVeres Auction — Reconciliation · Matching engine
====================================================

Finds the best canonical (master) client for an incoming contact using:
  1. Blocking  — cheap index lookups (email / phone / name-key) to gather a small
     candidate set instead of scanning all 13k+ masters per contact. O(1) per key.
  2. Scoring   — a weighted, field-aware similarity over the candidates. Weights
     reflect discriminative power: email > phone > name > address > postcode/company.

Similarity is dependency-free (stdlib difflib), so there are no external installs.
A token-set ratio makes name/address order- and duplication-insensitive.
"""
from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Optional

from . import normalize as N

# Field weights (only fields PRESENT on BOTH records contribute; weights are
# renormalised over present fields so missing data neither helps nor hurts).
WEIGHTS = {
    "email":    0.34,   # highest confidence
    "phone":    0.24,   # high
    "name":     0.20,   # medium
    "address":  0.12,   # medium
    "postcode": 0.05,
    "country":  0.03,
    "company":  0.02,   # lower (often absent in the buyer export)
}

# A strong identifier match (exact normalised email or phone) is decisive.
STRONG_MATCH_FLOOR = 0.90


def ratio(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def token_set_ratio(a: str, b: str) -> float:
    """Order/duplication-insensitive similarity: compare sorted unique tokens
    plus their intersection, take the best. Good for names & addresses."""
    at, bt = set(a.split()), set(b.split())
    if not at and not bt:
        return 1.0
    if not at or not bt:
        return 0.0
    inter = " ".join(sorted(at & bt))
    sa = " ".join(sorted(at)); sb = " ".join(sorted(bt))
    return max(ratio(sa, sb), ratio(inter, sa), ratio(inter, sb))


@dataclass
class Candidate:
    master: dict          # canonical master record
    score:  float
    matched_by: list      # fields that matched strongly
    field_sims: dict      # per-field similarity for transparency


def _field_similarities(inc: dict, mas: dict) -> dict:
    sims: dict[str, float] = {}
    # email
    ie, me = N.normalize_email(inc.get("email", "")), N.normalize_email(mas.get("email", ""))
    if ie and me:
        sims["email"] = 1.0 if ie == me else ratio(ie, me)
    # phone (incoming has one 'phone'; master has telNo + mobile — take best)
    ip = N.phone_key(inc.get("phone", ""))
    m_keys = [k for k in (N.phone_key(mas.get("phone", "")), N.phone_key(mas.get("mobile", ""))) if k]
    if ip and m_keys:
        sims["phone"] = 1.0 if ip in m_keys else max(ratio(ip, k) for k in m_keys)
    # name
    inm = N.normalize_name(inc.get("first_name", ""), inc.get("last_name", ""))
    man = N.normalize_name(mas.get("first_name", ""), mas.get("last_name", ""))
    if inm and man:
        sims["name"] = token_set_ratio(inm, man)
    # address (address1 + address2 + town)
    ia = N.normalize_address(inc.get("address1", ""), inc.get("address2", ""), inc.get("town", ""))
    ma = N.normalize_address(mas.get("address1", ""), mas.get("address2", ""),
                             mas.get("address3", ""), mas.get("town", ""))
    if ia and ma:
        sims["address"] = token_set_ratio(ia, ma)
    # postcode — BINARY by client decision (8-Jul): "any change of postcode
    # makes the postcode completely different — there's no spectrum there".
    # Partial character overlap must not inflate the match score.
    ipc, mpc = N.normalize_postcode(inc.get("postcode", "")), N.normalize_postcode(mas.get("postcode", ""))
    if ipc and mpc:
        sims["postcode"] = 1.0 if ipc == mpc else 0.0
    # country
    ic, mc = N.normalize_country(inc.get("country", "")), N.normalize_country(mas.get("country", ""))
    if ic and mc:
        sims["country"] = 1.0 if ic == mc else 0.0
    # company
    ico, mco = N.normalize_name(inc.get("company", "")), N.normalize_name(mas.get("company", ""))
    if ico and mco:
        sims["company"] = token_set_ratio(ico, mco)
    return sims


def score_pair(inc: dict, mas: dict) -> Candidate:
    """Weighted similarity between an incoming contact and a master record."""
    sims = _field_similarities(inc, mas)
    present_w = {f: WEIGHTS[f] for f in sims if f in WEIGHTS}
    wsum = sum(present_w.values()) or 1.0
    score = sum(sims[f] * present_w[f] for f in present_w) / wsum

    matched_by: list[str] = []
    if sims.get("email", 0) >= 0.99:  matched_by.append("email")
    if sims.get("phone", 0) >= 0.99:  matched_by.append("phone")
    if sims.get("name", 0) >= 0.90:   matched_by.append("name")
    if sims.get("address", 0) >= 0.90: matched_by.append("address")

    # An exact strong identifier (email or phone) makes this a confident match
    # even if other free-text fields drift.
    if "email" in matched_by or "phone" in matched_by:
        score = max(score, STRONG_MATCH_FLOOR)

    return Candidate(master=mas, score=round(score, 4), matched_by=matched_by, field_sims=sims)


class MasterIndex:
    """In-memory blocking indexes over the canonical master list.
    Built once; reused for every incoming contact. Scales to 50k+ comfortably."""

    def __init__(self, masters: list[dict]):
        self.masters = masters
        self.by_email: dict[str, list[int]] = {}
        self.by_phone: dict[str, list[int]] = {}
        self.by_name:  dict[str, list[int]] = {}
        for i, m in enumerate(masters):
            e = N.normalize_email(m.get("email", ""))
            if e:
                self.by_email.setdefault(e, []).append(i)
            for pk in (N.phone_key(m.get("phone", "")), N.phone_key(m.get("mobile", ""))):
                if pk:
                    self.by_phone.setdefault(pk, []).append(i)
            nk = N.name_key(m.get("first_name", ""), m.get("last_name", ""))
            if nk:
                self.by_name.setdefault(nk, []).append(i)

    def candidates(self, inc: dict) -> list[int]:
        idxs: set[int] = set()
        e = N.normalize_email(inc.get("email", ""))
        if e:
            idxs.update(self.by_email.get(e, []))
        pk = N.phone_key(inc.get("phone", ""))
        if pk:
            idxs.update(self.by_phone.get(pk, []))
        nk = N.name_key(inc.get("first_name", ""), inc.get("last_name", ""))
        if nk:
            idxs.update(self.by_name.get(nk, []))
        return list(idxs)

    def best_match(self, inc: dict) -> Optional[Candidate]:
        cands = self.candidates(inc)
        if not cands:
            return None
        scored = [score_pair(inc, self.masters[i]) for i in cands]
        scored.sort(key=lambda c: c.score, reverse=True)
        return scored[0]
