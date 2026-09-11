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
    },
    "campaigns": {"ux_campaigns_name_active"},
    "targets": {"ix_targets_rep_lookup"},
    "users": {"ix_users_email", "ix_users_email_lower"},
}

EXPRESSION_INDEXES = {"ix_users_email_lower": ["lower(users.email)"]}

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
    "ix_users_email_lower",
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


@pytest.mark.parametrize(("index_name", "expressions"), EXPRESSION_INDEXES.items())
def test_expression_index_targets_the_right_expression(
    index_name: str, expressions: list[str]
) -> None:
    """Two addresses differing only by case must collide on the same index key."""
    table_name = next(
        table for table, names in EXPECTED_INDEXES.items() if index_name in names
    )
    index = _index(table_name, index_name)
    assert [str(expression) for expression in index.expressions] == expressions


def test_campaign_id_lookups_ride_the_composite_index() -> None:
    """A standalone call_sessions.campaign_id index is a prefix of the composite."""
    table = Base.metadata.tables["call_sessions"]
    single_column = [
        index.name
        for index in table.indexes
        if [column.name for column in index.columns] == ["campaign_id"]
    ]
    assert not single_column

    composite = _index("call_sessions", "ix_call_sessions_campaign_created")
    assert [column.name for column in composite.columns] == ["campaign_id", "created_at"]


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
