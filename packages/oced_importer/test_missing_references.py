"""Run from soup-server: python -m pytest ../soup-packages/oced_importer/test_missing_references.py."""
# ruff: noqa: PLR2004 -- literal counts in assertions describe the input data.
from __future__ import annotations

import base64
import importlib
import importlib.util
import sys
from pathlib import Path

import pytest

from soup.core.contracts import CreatedBy, ObjectRef, Upload, ValidationError

_PACKAGE = "_oced_reference_tests"
_FOLDER = Path(__file__).parent / "server"
_spec = importlib.util.spec_from_file_location(
    _PACKAGE, _FOLDER / "__init__.py", submodule_search_locations=[str(_FOLDER)]
)
assert _spec and _spec.loader
_module = importlib.util.module_from_spec(_spec)
sys.modules[_PACKAGE] = _module
_spec.loader.exec_module(_module)
csv_data = importlib.import_module(f"{_PACKAGE}.csv_data")
contributions = importlib.import_module(f"{_PACKAGE}.contributions")


def _file(text: str) -> dict[str, str]:
    return {"filename": "objects.csv", "base64": base64.b64encode(text.encode()).decode()}


def _case() -> tuple[Upload, dict]:
    upload = Upload.from_bytes("events.csv", (
        b'id,eventName,eventDatetime,playerId,teamId\n'
        b'e1,pass,2017-08-20T16:00:02.530," p1, p2, null, p2 ","t1,t2"\n'
        b'e2,goal,2017-08-20T16:00:03.530,p3,t3\n'
        b'e3,end,2017-08-20T16:00:04.530,p1,t1\n'
    ))
    return upload, {"entities": {
        "playerId": {"file": _file("source_id,name,age,enabled,joined\np1,Alice,20,true,2020-01-01\n"),
                     "id_column": "source_id",
                     "attr_types": {"age": "Integer", "enabled": "Boolean", "joined": "Datetime"}},
        "teamId": {"file": _file("id,title\nt1,First\n"), "id_column": "id"},
    }}


def test_strict_reports_all_columns_and_preview_does_not_authorize_import() -> None:
    upload, options = _case()
    preview = csv_data.prepare(upload, options, "preview", preview=True)
    assert preview.missing_references == [
        {"column": "playerId", "count": 2, "samples": ["p2", "p3"]},
        {"column": "teamId", "count": 2, "samples": ["t2", "t3"]},
    ]
    with pytest.raises(ValidationError) as error:
        csv_data.prepare(upload, options, "dataset-a")
    assert error.value.details["missing_references"] == preview.missing_references
    blocks = contributions.OcedImporter(None, None).preview(upload, options, None)
    warning = next(block for block in blocks if block["title"] == "Missing object references")
    assert warning["data"]["rows"] == [["playerId", 2, "p2, p3"], ["teamId", 2, "t2, t3"]]


def test_discard_preserves_events_and_valid_objects_and_references() -> None:
    upload, options = _case()
    prepared = csv_data.prepare(upload, {**options, "missing_reference_strategy": "discard"}, "dataset-a")
    events = csv_data.read_table(prepared.files[prepared.log.events.path])
    assert events.values("id") == ["e1", "e2", "e3"]
    assert events.values("playerId") == ["p1", "", "p1"]
    assert events.values("teamId") == ["t1", "", "t1"]
    assert events.values("eventDatetime")[0] == "2017-08-20T16:00:02.530"
    assert prepared.counts["entities"] == {"playerId": 1, "teamId": 1}
    assert all(path.startswith("dataset-a/") for path in prepared.files)
    again = csv_data.prepare(upload, {**options, "missing_reference_strategy": "discard"}, "dataset-b")
    assert all(path.startswith("dataset-b/") for path in again.files)


def test_placeholders_keep_links_and_use_id_only_with_empty_csv_null_attributes() -> None:
    upload, options = _case()
    prepared = csv_data.prepare(upload, {**options, "missing_reference_strategy": "placeholders"}, "dataset-a")
    events = csv_data.read_table(prepared.files[prepared.log.events.path])
    assert events.values("playerId") == ["p1,p2,p2", "p3", "p1"]
    assert len(events.rows) == 3
    players = csv_data.read_table(prepared.files[prepared.log.entities["playerId"].path])
    assert players.columns == ["wyId", "name", "age", "enabled", "joined"]
    assert players.rows == [["p1", "Alice", "20", "true", "2020-01-01"],
                            ["p2", "", "", "", ""], ["p3", "", "", "", ""]]
    assert b"p2,,,,\n" in prepared.files[prepared.log.entities["playerId"].path]
    assert prepared.log.entities["playerId"].attr_types["wyId"] == "String"
    assert prepared.counts["entities"] == {"playerId": 3, "teamId": 3}


def test_generated_tables_need_no_strategy_and_id_collisions_are_still_rejected() -> None:
    upload, options = _case()
    prepared = csv_data.prepare(upload, {"entities": {"playerId": {}, "teamId": {}}}, "dataset-a")
    assert not prepared.missing_references
    options["entities"]["teamId"]["file"] = _file("id,title\nt1,First\np2,Other type\n")
    with pytest.raises(ValidationError, match="globally unique"):
        csv_data.prepare(upload, {**options, "missing_reference_strategy": "placeholders"}, "dataset-a")
    # A missing ID in another type must not become an accidental cross-type CORR.
    prepared = csv_data.prepare(upload, {**options, "missing_reference_strategy": "discard"}, "dataset-a")
    events = csv_data.read_table(prepared.files[prepared.log.events.path])
    assert "p2" not in csv_data.reference_ids(events.values("playerId"))


def test_unresolved_import_fails_before_database_creation_or_catalog_access() -> None:
    upload, options = _case()
    obj = ObjectRef("cc1fda4d-abbe-4a88-95e1-875a964c9a01", "Example", contributions.KIND,
                    CreatedBy("importer", "oced_importer.csv", "oced_importer"))
    # No graph/catalog implementations are needed: strict preparation must reject before either is touched.
    importer = contributions.OcedImporter(None, None)
    with pytest.raises(ValidationError, match="missing referenced IDs"):
        importer.import_(upload, obj, options, None)


def test_warning_samples_are_bounded_and_unknown_strategies_are_rejected() -> None:
    upload = Upload.from_bytes("events.csv", (
        b'id,eventName,eventDatetime,playerId\n'
        b'e1,pass,2020-01-01T00:00:00,"p0,p1,p2,p3,p4,p5,p6"\n'
    ))
    options = {"entities": {"playerId": {"file": _file("wyId\np0\n")}}}
    prepared = csv_data.prepare(upload, options, "preview", preview=True)
    assert prepared.missing_references[0]["count"] == 6
    assert len(prepared.missing_references[0]["samples"]) == 5
    with pytest.raises(ValidationError, match="Choose strict validation"):
        csv_data.prepare(upload, {**options, "missing_reference_strategy": "ignore"}, "dataset-a")


@pytest.mark.parametrize("strategy", ["discard", "placeholders"])
def test_empty_object_table_preserves_every_event(strategy: str) -> None:
    upload, options = _case()
    options["entities"]["playerId"]["file"] = _file("source_id,name,age,enabled,joined\n")
    prepared = csv_data.prepare(upload, {**options, "missing_reference_strategy": strategy}, "dataset-a")
    events = csv_data.read_table(prepared.files[prepared.log.events.path])
    assert events.values("id") == ["e1", "e2", "e3"]
    players = csv_data.read_table(prepared.files[prepared.log.entities["playerId"].path])
    if strategy == "discard":
        assert not players.rows
        assert events.values("playerId") == ["", "", ""]
    else:
        assert players.values("wyId") == ["p1", "p2", "p3"]
        assert all(row[1:] == ["", "", "", ""] for row in players.rows)
