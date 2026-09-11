"""Model metadata must declare the indexes the migrations create.

`alembic check` catches drift only against a live database. These assertions
run without one, so a model edit that drops an index declaration fails fast.
"""

import pytest

from app.db import Base

EXPECTED_INDEXES = {
    "audio_recordings": {
        "ux_audio_recordings_active",
        "ix_audio_recordings_campaign_key_active",
    },
    "calls": {
        "ux_calls_session_dial_sid",
        "ix_calls_insights_candidates",
        "ix_calls_session_id",
        "ix_calls_campaign_id",
        "ix_calls_target_id",
    },
    "call_sessions": {
        "ix_call_sessions_created_at",
        "ix_call_sessions_campaign_created",
        "ix_call_sessions_campaign_id",
    },
    "campaigns": {"ux_campaigns_name_active"},
    "targets": {"ix_targets_rep_lookup"},
}

PARTIAL_INDEX_PREDICATES = {
    "ux_calls_session_dial_sid": "twilio_call_sid <> ''",
    "ix_calls_insights_candidates": "status = 'completed' AND quality_details IS NULL",
    "ix_targets_rep_lookup": "external_id = 'rep_lookup'",
    "ux_campaigns_name_active": "status <> 'archived'",
    "ux_audio_recordings_active": "is_active",
}

UNIQUE_INDEXES = {
    "ux_calls_session_dial_sid",
    "ux_campaigns_name_active",
    "ux_audio_recordings_active",
    "ix_users_email",
    "ix_phone_numbers_number",
}


def _index(table_name: str, index_name: str):
    table = Base.metadata.tables[table_name]
    for index in table.indexes:
        if index.name == index_name:
            return index
    pytest.fail(f"{table_name} does not declare index {index_name}")


@pytest.mark.parametrize(
    ("table_name", "index_name"),
    [(table, name) for table, names in EXPECTED_INDEXES.items() for name in names],
)
def test_index_is_declared(table_name: str, index_name: str) -> None:
    assert _index(table_name, index_name) is not None


@pytest.mark.parametrize(("index_name", "predicate"), PARTIAL_INDEX_PREDICATES.items())
def test_partial_index_predicate(index_name: str, predicate: str) -> None:
    table_name = next(
        table for table, names in EXPECTED_INDEXES.items() if index_name in names
    )
    index = _index(table_name, index_name)
    assert str(index.dialect_options["postgresql"]["where"]) == predicate


@pytest.mark.parametrize("index_name", sorted(UNIQUE_INDEXES))
def test_index_is_unique(index_name: str) -> None:
    matches = [
        index
        for table in Base.metadata.tables.values()
        for index in table.indexes
        if index.name == index_name
    ]
    assert matches, f"no table declares index {index_name}"
    assert all(index.unique for index in matches)


def test_email_and_number_uniqueness_is_index_only() -> None:
    """The unique index carries uniqueness; a separate constraint would duplicate it."""
    for table_name, column in (("users", "email"), ("phone_numbers", "number")):
        table = Base.metadata.tables[table_name]
        unique_constraints = [
            constraint
            for constraint in table.constraints
            if getattr(constraint, "columns", None) is not None
            and {c.name for c in constraint.columns} == {column}
            and type(constraint).__name__ == "UniqueConstraint"
        ]
        assert not unique_constraints
