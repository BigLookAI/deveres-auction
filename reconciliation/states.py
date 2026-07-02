"""
deVeres Auction — Reconciliation · Record lifecycle state engine
=================================================================

Every reconciled record carries an explicit lifecycle state. All state changes
go through `transition()`, which validates the move against ALLOWED_TRANSITIONS
and returns a history entry — so an invalid move is an error, never a silent
no-op, and every legal move is persisted and auditable.

Lifecycles (from the 2-Jul-2026 review meeting):

  matched update:   UPDATE_SUGGESTED → (MANUAL_EDIT) → UPDATE_READY → PUSHED_TO_ODOO
  new client:       NEW_RECORD       → (MANUAL_EDIT) → IMPORT_READY → PUSHED_TO_ODOO
  uncertain match:  NEEDS_REVIEW     → UPDATE_READY | IMPORT_READY | EXISTING_OK | REJECTED
  no-change match:  EXISTING_OK      (terminal unless manually edited)
  any pre-push:     → REJECTED       (and REJECTED can be reopened)

UPDATE_READY / IMPORT_READY mean the record has been APPROVED and now lives in
the staging repository (the "pending changes" dataset that becomes the Odoo
push payload). PUSHED_TO_ODOO is terminal.
"""
from __future__ import annotations

from enum import Enum


class RecordState(str, Enum):
    # Initial states — assigned by the classifier
    NEW_RECORD       = "new_record"        # no master match → will be created
    UPDATE_SUGGESTED = "update_suggested"  # confident match with substantive changes
    EXISTING_OK      = "existing_ok"       # confident match, nothing substantive to change
    NEEDS_REVIEW     = "needs_review"      # uncertain match → a human must decide

    # Working state
    MANUAL_EDIT      = "manual_edit"       # reviewer has edited fields; awaiting approval

    # Staged states (record is in the staging repository, ready for the push)
    UPDATE_READY     = "update_ready"      # approved update to an existing client
    IMPORT_READY     = "import_ready"      # approved brand-new client

    # Terminal states
    REJECTED         = "rejected"          # reviewer rejected; excluded from the push
    PUSHED_TO_ODOO   = "pushed_to_odoo"    # written to Odoo (terminal)


# Which state a record starts in, per classification VALUE (string-keyed to
# avoid a circular import with models.py, whose ReconResult carries the state).
INITIAL_STATE = {
    "new":                RecordState.NEW_RECORD,
    "update":             RecordState.UPDATE_SUGGESTED,
    "retain":             RecordState.EXISTING_OK,
    "possible_duplicate": RecordState.NEEDS_REVIEW,
}

# The full transition map. Anything not listed here is an illegal move.
ALLOWED_TRANSITIONS: dict[RecordState, set[RecordState]] = {
    RecordState.UPDATE_SUGGESTED: {RecordState.MANUAL_EDIT, RecordState.UPDATE_READY,
                                   RecordState.EXISTING_OK, RecordState.REJECTED},
    RecordState.NEW_RECORD:       {RecordState.MANUAL_EDIT, RecordState.IMPORT_READY,
                                   RecordState.REJECTED},
    RecordState.NEEDS_REVIEW:     {RecordState.MANUAL_EDIT, RecordState.UPDATE_READY,
                                   RecordState.IMPORT_READY, RecordState.EXISTING_OK,
                                   RecordState.REJECTED},
    RecordState.EXISTING_OK:      {RecordState.MANUAL_EDIT, RecordState.REJECTED},
    RecordState.MANUAL_EDIT:      {RecordState.UPDATE_READY, RecordState.IMPORT_READY,
                                   RecordState.UPDATE_SUGGESTED, RecordState.NEW_RECORD,
                                   RecordState.NEEDS_REVIEW, RecordState.EXISTING_OK,
                                   RecordState.REJECTED},
    # Un-approve: a staged record can go back to review or be rejected — until pushed.
    RecordState.UPDATE_READY:     {RecordState.PUSHED_TO_ODOO, RecordState.UPDATE_SUGGESTED,
                                   RecordState.MANUAL_EDIT, RecordState.REJECTED},
    RecordState.IMPORT_READY:     {RecordState.PUSHED_TO_ODOO, RecordState.NEW_RECORD,
                                   RecordState.MANUAL_EDIT, RecordState.REJECTED},
    # A rejection can be reconsidered (reopen) as long as nothing was pushed.
    RecordState.REJECTED:         {RecordState.UPDATE_SUGGESTED, RecordState.NEW_RECORD,
                                   RecordState.NEEDS_REVIEW, RecordState.EXISTING_OK,
                                   RecordState.MANUAL_EDIT},
    RecordState.PUSHED_TO_ODOO:   set(),   # terminal — no way back
}

# Human-readable badge labels for the UI.
STATE_LABELS = {
    RecordState.NEW_RECORD:       "New client",
    RecordState.UPDATE_SUGGESTED: "Update suggested",
    RecordState.EXISTING_OK:      "Existing — no change",
    RecordState.NEEDS_REVIEW:     "Manual review",
    RecordState.MANUAL_EDIT:      "Edited — awaiting approval",
    RecordState.UPDATE_READY:     "Update ready",
    RecordState.IMPORT_READY:     "Import ready",
    RecordState.REJECTED:         "Rejected",
    RecordState.PUSHED_TO_ODOO:   "Pushed to Odoo",
}

# States whose records live in the staging repository (= the Odoo push payload).
STAGED_STATES = {RecordState.UPDATE_READY, RecordState.IMPORT_READY}


class TransitionError(ValueError):
    """Raised when a state change is not allowed by the lifecycle."""


def initial_state(classification) -> RecordState:
    """Accepts a Classification enum or its string value."""
    key = getattr(classification, "value", classification)
    return INITIAL_STATE[key]


def validate_transition(current: RecordState, target: RecordState) -> None:
    if target == current:
        raise TransitionError(f"Record is already in state '{current.value}'.")
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        allowed = ", ".join(sorted(s.value for s in ALLOWED_TRANSITIONS.get(current, set()))) or "none"
        raise TransitionError(
            f"Illegal transition {current.value} → {target.value}. "
            f"Allowed from {current.value}: {allowed}.")
