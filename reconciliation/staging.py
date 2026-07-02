"""
deVeres Auction — Reconciliation · Staging repository (pending changes)
========================================================================

The staging layer is the contract between review and Odoo (2-Jul meeting):

  • Pressing Approve NEVER touches Odoo. It writes the approved record here.
  • Every approved update, approved new record and manual edit lands here.
  • This repository IS the official payload for the Odoo push — nothing else is.
  • The original imported records are never modified; edits exist only here.

Storage is SQLite (stdlib, transactional, survives restarts) at
`output/staging.db` (override with RECON_STAGING_DB). Two tables:

  staging      one row per approved record: original + incoming + approved
               values, change type (update|create), approval metadata, status
               (ready → pushed | withdrawn).
  transitions  append-only log of every record state change (the approval
               history shown in the UI and the audit basis).

A CSV/JSON export of the ready rows is available for eyeballing before a push.
"""
from __future__ import annotations

import csv
import io
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent
DEFAULT_DB = _BASE / "output" / "staging.db"

# Columns of the flat staging CSV export, in order.
EXPORT_COLUMNS = [
    "change_type", "status", "master_ref", "buyer_number", "name",
    "first_name", "last_name", "email", "phone", "company",
    "address1", "address2", "town", "county", "postcode", "country",
    "fields_changed", "fields_edited", "confidence", "matched_by",
    "approved_by", "approved_at", "session",
]

_CONTACT_FIELDS = ["first_name", "last_name", "email", "phone", "company",
                   "address1", "address2", "town", "county", "postcode", "country"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class StagingRepository:
    """Transactional store of approved (pending) changes. Thread-safe via
    SQLite's serialized mode + short-lived connections."""

    def __init__(self, db_path: str | Path | None = None):
        self.path = Path(db_path or os.environ.get("RECON_STAGING_DB", DEFAULT_DB))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=10)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        return con

    def _init_schema(self) -> None:
        with self._conn() as con:
            con.executescript("""
            CREATE TABLE IF NOT EXISTS staging (
                id            INTEGER PRIMARY KEY,
                session       TEXT NOT NULL,
                record_index  INTEGER NOT NULL,
                buyer_number  TEXT DEFAULT '',
                change_type   TEXT NOT NULL CHECK (change_type IN ('update','create')),
                status        TEXT NOT NULL DEFAULT 'ready'
                              CHECK (status IN ('ready','pushed','withdrawn')),
                master_ref    TEXT DEFAULT '',
                name          TEXT DEFAULT '',
                original_json TEXT NOT NULL,     -- master snapshot (source of truth)
                incoming_json TEXT NOT NULL,     -- Blue Cubes snapshot (never edited)
                approved_json TEXT NOT NULL,     -- final approved values
                edited_fields_json  TEXT NOT NULL DEFAULT '[]',
                changed_fields_json TEXT NOT NULL DEFAULT '[]',
                confidence    REAL DEFAULT 0,
                matched_by_json TEXT NOT NULL DEFAULT '[]',
                lots_json     TEXT NOT NULL DEFAULT '[]',
                approved_by   TEXT DEFAULT '',
                approved_at   TEXT DEFAULT '',
                updated_at    TEXT DEFAULT '',
                pushed_at     TEXT DEFAULT '',
                odoo_partner_id INTEGER,
                note          TEXT DEFAULT '',
                UNIQUE (session, record_index)
            );
            CREATE TABLE IF NOT EXISTS transitions (
                id           INTEGER PRIMARY KEY,
                session      TEXT NOT NULL,
                record_index INTEGER NOT NULL,
                from_state   TEXT,
                to_state     TEXT NOT NULL,
                actor        TEXT DEFAULT '',
                at           TEXT NOT NULL,
                note         TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_staging_session ON staging (session, status);
            CREATE INDEX IF NOT EXISTS idx_trans_record ON transitions (session, record_index);
            """)

    # ── writes ────────────────────────────────────────────────────────────────
    def stage(self, *, session: str, record_index: int, buyer_number: str,
              change_type: str, master_ref: str, name: str,
              original: dict, incoming: dict, approved: dict,
              edited_fields: list[str], changed_fields: list[str],
              confidence: float, matched_by: list[str], lots: list[dict],
              actor: str, note: str = "") -> int:
        """Insert or refresh the staged row for (session, record_index).
        Re-approving after another edit simply overwrites the approved values —
        the record is identified by its position in the session, so no duplicates."""
        if change_type not in ("update", "create"):
            raise ValueError(f"change_type must be 'update' or 'create', got {change_type!r}")
        now = _now()
        with self._conn() as con:
            cur = con.execute("""
                INSERT INTO staging (session, record_index, buyer_number, change_type,
                    status, master_ref, name, original_json, incoming_json, approved_json,
                    edited_fields_json, changed_fields_json, confidence, matched_by_json,
                    lots_json, approved_by, approved_at, updated_at, note)
                VALUES (?,?,?,?, 'ready', ?,?,?,?,?, ?,?,?,?, ?,?,?,?,?)
                ON CONFLICT (session, record_index) DO UPDATE SET
                    buyer_number=excluded.buyer_number, change_type=excluded.change_type,
                    status='ready', master_ref=excluded.master_ref, name=excluded.name,
                    original_json=excluded.original_json, incoming_json=excluded.incoming_json,
                    approved_json=excluded.approved_json,
                    edited_fields_json=excluded.edited_fields_json,
                    changed_fields_json=excluded.changed_fields_json,
                    confidence=excluded.confidence, matched_by_json=excluded.matched_by_json,
                    lots_json=excluded.lots_json, approved_by=excluded.approved_by,
                    approved_at=excluded.approved_at, updated_at=excluded.updated_at,
                    note=excluded.note, pushed_at='', odoo_partner_id=NULL
            """, (session, record_index, buyer_number, change_type, master_ref, name,
                  json.dumps(original, ensure_ascii=False),
                  json.dumps(incoming, ensure_ascii=False),
                  json.dumps(approved, ensure_ascii=False),
                  json.dumps(edited_fields), json.dumps(changed_fields),
                  round(float(confidence), 4), json.dumps(matched_by),
                  json.dumps(lots, ensure_ascii=False), actor, now, now, note))
            return cur.lastrowid

    def withdraw(self, session: str, record_index: int, actor: str, note: str = "") -> bool:
        """Remove a record from the pending push (reject / un-approve)."""
        with self._conn() as con:
            cur = con.execute(
                "UPDATE staging SET status='withdrawn', updated_at=?, note=? "
                "WHERE session=? AND record_index=? AND status='ready'",
                (_now(), note or f"withdrawn by {actor}", session, record_index))
            return cur.rowcount > 0

    def mark_pushed(self, session: str, record_index: int,
                    odoo_partner_id: int | None = None) -> bool:
        with self._conn() as con:
            cur = con.execute(
                "UPDATE staging SET status='pushed', pushed_at=?, odoo_partner_id=? "
                "WHERE session=? AND record_index=? AND status='ready'",
                (_now(), odoo_partner_id, session, record_index))
            return cur.rowcount > 0

    def log_transition(self, session: str, record_index: int, from_state: str | None,
                       to_state: str, actor: str, note: str = "") -> None:
        with self._conn() as con:
            con.execute(
                "INSERT INTO transitions (session, record_index, from_state, to_state, actor, at, note) "
                "VALUES (?,?,?,?,?,?,?)",
                (session, record_index, from_state, to_state, actor, _now(), note))

    # ── reads ─────────────────────────────────────────────────────────────────
    @staticmethod
    def _row_to_dict(r: sqlite3.Row) -> dict:
        d = dict(r)
        for k in ("original_json", "incoming_json", "approved_json",
                  "edited_fields_json", "changed_fields_json", "matched_by_json", "lots_json"):
            d[k.removesuffix("_json")] = json.loads(d.pop(k) or "null")
        return d

    def entries(self, session: str | None = None, status: str = "ready") -> list[dict]:
        q = "SELECT * FROM staging WHERE 1=1"
        args: list = []
        if session:
            q += " AND session=?"; args.append(session)
        if status and status != "all":
            q += " AND status=?"; args.append(status)
        q += " ORDER BY change_type, record_index"
        with self._conn() as con:
            return [self._row_to_dict(r) for r in con.execute(q, args)]

    def counts(self, session: str | None = None) -> dict:
        q = "SELECT change_type, status, COUNT(*) AS n FROM staging"
        args: list = []
        if session:
            q += " WHERE session=?"; args.append(session)
        q += " GROUP BY change_type, status"
        out = {"ready": {"update": 0, "create": 0}, "pushed": {"update": 0, "create": 0},
               "withdrawn": {"update": 0, "create": 0}}
        with self._conn() as con:
            for r in con.execute(q, args):
                out.setdefault(r["status"], {}).setdefault(r["change_type"], 0)
                out[r["status"]][r["change_type"]] = r["n"]
        out["pending_total"] = sum(out["ready"].values())
        return out

    def history(self, session: str, record_index: int | None = None) -> list[dict]:
        q = "SELECT * FROM transitions WHERE session=?"
        args: list = [session]
        if record_index is not None:
            q += " AND record_index=?"; args.append(record_index)
        q += " ORDER BY id"
        with self._conn() as con:
            return [dict(r) for r in con.execute(q, args)]

    # ── exports (the reviewable "pending changes" file) ───────────────────────
    def export_rows(self, session: str | None = None, status: str = "ready") -> list[dict]:
        rows = []
        for e in self.entries(session, status):
            approved = e["approved"] or {}
            rows.append({
                "change_type": e["change_type"].upper(),        # UPDATE | CREATE — no ambiguity
                "status": e["status"],
                "master_ref": e["master_ref"],
                "buyer_number": e["buyer_number"],
                "name": e["name"],
                **{f: approved.get(f, "") for f in _CONTACT_FIELDS},
                "fields_changed": "|".join(e["changed_fields"] or []),
                "fields_edited": "|".join(e["edited_fields"] or []),
                "confidence": e["confidence"],
                "matched_by": "|".join(e["matched_by"] or []),
                "approved_by": e["approved_by"],
                "approved_at": e["approved_at"],
                "session": e["session"],
            })
        return rows

    def export_csv(self, session: str | None = None, status: str = "ready") -> str:
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=EXPORT_COLUMNS)
        w.writeheader()
        for row in self.export_rows(session, status):
            w.writerow(row)
        return buf.getvalue()

    def export_json(self, session: str | None = None, status: str = "ready") -> str:
        return json.dumps({"generated_at": _now(), "session": session,
                           "counts": self.counts(session),
                           "entries": self.entries(session, status)},
                          indent=2, ensure_ascii=False)

    # ── retention (GDPR data minimisation) ────────────────────────────────────
    def purge(self, retention_days: int | None = None) -> dict:
        """Delete pushed/withdrawn staging rows older than the retention window
        (env RECON_STAGING_RETENTION_DAYS, default 90). 'ready' rows are NEVER
        purged — pending work is not data to minimise. The transitions table
        (audit trail) is kept. Returns what was removed."""
        days = retention_days if retention_days is not None else \
            int(os.environ.get("RECON_STAGING_RETENTION_DAYS", "90"))
        if days < 1:
            raise ValueError("retention_days must be >= 1")
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
        with self._conn() as con:
            cur = con.execute(
                "DELETE FROM staging WHERE status IN ('pushed','withdrawn') "
                "AND COALESCE(NULLIF(updated_at,''), approved_at) < ?", (cutoff,))
        return {"purged": cur.rowcount, "retention_days": days, "cutoff": cutoff}
