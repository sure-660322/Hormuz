"""Transport-independent public input contract; no implicit UI context."""
from typing import Annotated, Literal
from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Args(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Empty(Args):
    pass


def aware(raw):
    value = datetime.fromisoformat(raw)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timestamp must have an explicit timezone")
    return value


def window(start, end, days=7):
    start, end = aware(start), aware(end)
    if not start < end or end - start > timedelta(days=days):
        raise ValueError("Invalid or oversized half-open time window")


class Window(Args):
    start_at: str = Field(max_length=64, description="Inclusive ISO 8601 timestamp with timezone")
    end_at: str = Field(max_length=64, description="Exclusive ISO 8601 timestamp with timezone")

    @model_validator(mode="after")
    def validate_window(self):
        window(self.start_at, self.end_at)
        return self


class Search(Args):
    keyword: str = Field(min_length=1, max_length=100)
    limit: int = Field(default=10, ge=1, le=20)


class Track(Window):
    ship_id: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_track_window(self):
        window(self.start_at, self.end_at, days=1)
        return self


ShipTypes = Annotated[list[Annotated[str, Field(min_length=1, max_length=100)]], Field(max_length=50)]
Direction = Literal["all", "inbound", "outbound", "east_to_west", "west_to_east"]


class Statistics(Window):
    ship_types: ShipTypes | None = None
    direction: Direction | None = None


class Compare(Args):
    start_a: str = Field(max_length=64)
    end_a: str = Field(max_length=64)
    start_b: str = Field(max_length=64)
    end_b: str = Field(max_length=64)

    @model_validator(mode="after")
    def validate_periods(self):
        window(self.start_a, self.end_a)
        window(self.start_b, self.end_b)
        return self


class CompareStatistics(Compare):
    ship_types: ShipTypes | None = None
    direction: Direction | None = None


class Rectangle(Args):
    west: float = Field(ge=-180, le=180, allow_inf_nan=False)
    south: float = Field(ge=-90, le=90, allow_inf_nan=False)
    east: float = Field(ge=-180, le=180, allow_inf_nan=False)
    north: float = Field(ge=-90, le=90, allow_inf_nan=False)


class Area(Args):
    bounds: Rectangle | None = Field(default=None, description="Omit for versioned project default area; never viewport")
    ship_types: ShipTypes | None = None


class Snapshot(Area):
    at: str = Field(max_length=64)
    freshness_seconds: int = Field(default=3600, ge=1, le=86400)

    @model_validator(mode="after")
    def validate_at(self):
        aware(self.at)
        return self


class Activity(Area, Window):
    batch_ids: list[Annotated[int, Field(gt=0)]] | None = Field(default=None, max_length=50)


class CompareActivity(Area, Compare):
    batch_ids: list[Annotated[int, Field(gt=0)]] | None = Field(default=None, max_length=50)


class Parameter(Args):
    name: str = Field(min_length=1, max_length=63)
    type: Literal["timestamptz", "date", "text", "int", "numeric", "bool"]
    value: str | int | float | bool | None


class SQL(Args):
    sql: str = Field(min_length=1, max_length=16384)
    params: list[Parameter] = Field(default_factory=list, max_length=50)
    purpose: str = Field(default="", max_length=500)


class ExecuteSQL(SQL):
    validation_token: str = Field(min_length=1, max_length=128)


TOOLS = {
    "search_ships": (Search, "Search historical AIS ship identities; names alone do not establish news identity."),
    "get_ship_track": (Track, "Read complete bounded historical track, at most 24 hours; gaps are not interpolated."),
    "query_strait_passage_statistics": (Statistics, "Daily and whole-window observed gate passages, at most 7 days; not physical crossing times."),
    "compare_strait_passage_statistics": (CompareStatistics, "Compare two bounded passage periods using shared filters and deterministic service."),
    "query_area_ship_snapshot": (Snapshot, "Observed ships in explicit rectangle or project default at a historical timestamp; bounded list."),
    "query_area_ship_activity": (Activity, "Observed area visits, entry/exit, ship-hours and quality; at most 7 days; visits are not gate passages."),
    "compare_area_ship_activity": (CompareActivity, "Compare two area activity periods in the same explicit area; at most 7 days each."),
    "get_database_schema": (Empty, "Governed SQL catalog, filters, versions and limits; metadata does not prove database readiness."),
    "check_sql": (SQL, "Offline read-only policy check; returns a short-lived, single-use token bound to client and exact arguments."),
    "execute_sql": (ExecuteSQL, "Consume check_sql token and revalidate in independent restricted reader; no arbitrary tables or writes."),
}


def output_schema(name):
    """Portable typed envelope; detailed nested facts retain service contracts."""
    fields = {
        "status": {"type": "string"}, "request_id": {"type": "string"},
        "tool_name": {"type": "string"}, "adapter_version": {"type": "string"},
        "code": {"type": "string"}, "message": {"type": "string"},
        "versions": {"type": "object", "additionalProperties": {"type": "string"}},
        "limitations": {"type": "array", "items": {"type": "string"}},
    }
    details = {
        "search_ships": {"matches": "array", "returned_count": "integer", "matched_count": "integer", "truncated": "boolean"},
        "get_ship_track": {"fixes": "array", "fix_count": "integer", "ship_id": "integer", "start_at": "string", "end_at": "string", "truncated": "boolean"},
        "query_strait_passage_statistics": {"window": "object", "daily": "array", "determination_version": "string"},
        "compare_strait_passage_statistics": {"a": "object", "b": "object", "metrics": "array", "determination_version": "string"},
        "query_area_ship_snapshot": {"area": "object", "area_context": "object", "ships": "array", "coverage": "object"},
        "query_area_ship_activity": {"area": "object", "area_context": "object", "visits": "array", "daily": "array", "coverage": "object"},
        "compare_area_ship_activity": {"area": "object", "area_context": "object", "a": "object", "b": "object", "metrics": "array"},
        "get_database_schema": {"catalog": "object", "database_readiness": "string", "token_ttl_seconds": "integer"},
        "check_sql": {"normalized_sql": "string", "catalog_version": "string", "validation_token": "string", "expires_in_seconds": "integer"},
        "execute_sql": {"query_id": "string", "columns": "array", "rows": "array", "returned_row_count": "integer", "truncated": "boolean", "source": "object", "query_executed": "boolean", "retryable": "boolean"},
    }
    fields.update({key: {"type": kind} for key, kind in details[name].items()})
    return {"type": "object", "required": ["status"], "properties": fields, "additionalProperties": True}
