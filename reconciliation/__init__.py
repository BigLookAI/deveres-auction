"""deVeres Auction — Contact Reconciliation Engine.

The preprocessing layer that reconciles an uploaded Blue Cubes buyer export
against the immutable canonical client database before auction data enters the
System of Record / Odoo.

Public API:
    from reconciliation import MasterRepository, ReconciliationEngine, load_incoming
"""
from .engine import ReconciliationEngine
from .models import (
    Action, Classification, DiffStatus, FieldDiff, Recommendation,
    ReconResult, ReconSummary,
)
from .repository import MasterRepository, load_incoming, load_lots
from .staging import StagingRepository
from .states import (
    ALLOWED_TRANSITIONS, STATE_LABELS, STAGED_STATES,
    RecordState, TransitionError, initial_state, validate_transition,
)

__all__ = [
    "ReconciliationEngine", "MasterRepository", "load_incoming", "load_lots",
    "Classification", "Recommendation", "DiffStatus", "Action",
    "FieldDiff", "ReconResult", "ReconSummary",
    "StagingRepository", "RecordState", "TransitionError",
    "initial_state", "validate_transition",
    "ALLOWED_TRANSITIONS", "STATE_LABELS", "STAGED_STATES",
]
