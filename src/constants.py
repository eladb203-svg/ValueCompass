class FinancialWorkflow:
    """Single source of truth for ETL workflow names.

    Used by the audit work plan, the capability write guard and
    documented in .agents/skills/financial-data-etl/SKILL.md.
    """

    METADATA_REPAIR = "METADATA_REPAIR"
    INITIAL_IMPORT = "INITIAL_IMPORT"
    BACKFILL = "BACKFILL"
    REPAIR = "REPAIR"
    NO_ACTION = "NO_ACTION"

    # Planned, not triggered by the backend yet.
    CHECK_FOR_NEW_FILING = "CHECK_FOR_NEW_FILING"
    INCREMENTAL_UPDATE = "INCREMENTAL_UPDATE"

    # Workflows allowed to write financial_yearly.
    FINANCIAL_WRITE = frozenset({INITIAL_IMPORT, BACKFILL, REPAIR})
