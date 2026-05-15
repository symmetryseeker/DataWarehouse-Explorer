"""Smoke tests for web API endpoints against the real E:\ warehouse."""

from __future__ import annotations

from pathlib import Path

import pytest

from datawarehouse.web import create_app


@pytest.fixture
def client():
    app = create_app(warehouse_root=Path("E:/DataWarehouse"))
    return app.test_client()


def test_api_repos(client):
    r = client.get("/api/repos")
    assert r.status_code == 200
    data = r.get_json()
    assert len(data) >= 1


def test_api_repo_detail(client):
    r = client.get("/api/repo/fivethirtyeight_data")
    assert r.status_code == 200
    data = r.get_json()
    assert "files" in data
    assert data["meta"]["repo_name"] == "fivethirtyeight/data"


def test_api_file_csv(client):
    r = client.get("/api/file/fivethirtyeight_data/undefeated-boxers/undefeated.csv")
    assert r.status_code == 200
    data = r.get_json()
    assert data["type"] == "csv"
    assert len(data["headers"]) == 4


def test_api_file_stats(client):
    r = client.get("/api/file/fivethirtyeight_data/undefeated-boxers/undefeated.csv/stats")
    assert r.status_code == 200


def test_api_file_rows(client):
    r = client.get("/api/file/fivethirtyeight_data/undefeated-boxers/undefeated.csv/rows?sort=name&limit=5")
    assert r.status_code == 200


def test_api_export_csv(client):
    r = client.get("/api/export/fivethirtyeight_data/undefeated-boxers/undefeated.csv?format=csv")
    assert r.status_code == 200


def test_api_search(client):
    r = client.get("/api/search?q=weather")
    assert r.status_code == 200


def test_api_licenses(client):
    r = client.get("/api/licenses")
    assert r.status_code == 200
