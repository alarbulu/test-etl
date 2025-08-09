import json
import pathlib
import types

import pytest

import main


class MockResponse:
    def __init__(self, json_data, next_url=None):
        self.links = {"next": {"url": next_url}} if next_url else {}
        self.json_data = json_data

    def __str__(self):
        return json.dumps(self.json_data)

    @property
    def text(self):
        return self.__str__()

    def json(self):
        return self.json_data


@pytest.fixture
def workflow_run_template():
    return {
        "id": None,  # Placeholder
        "name": "My Workflow",
        "head_sha": 12345678,
        "status": "pending",
        "conclusion": None,
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-01T00:00:00Z",
        "run_started_at": "2025-01-01T00:00:00Z",
        "repository": {
            "name": None  # Placeholder
        },
    }


@pytest.fixture
def repos_pages():
    page_1 = MockResponse(
        [{"name": "active_repo"}, {"name": "abandoned_repo"}], next_url="repos?page=2"
    )
    page_2 = MockResponse([{"name": "empty_repo"}])
    return iter([page_1, page_2])


@pytest.fixture
def active_repo_workflow_run_pages(workflow_run_template):
    template = workflow_run_template | {"repository": {"name": "active_repo"}}
    run_1 = template | {"id": 1}
    run_2 = template | {"id": 2}
    run_3 = template | {"id": 3}

    pages = [
        MockResponse(
            {"total_count": 3, "workflow_runs": [run_1, run_2]},
            next_url="active_repo/runs?page=2",
        ),
        MockResponse({"total_count": 3, "workflow_runs": [run_3]}),
    ]
    return iter(pages)


def test_get_pages():
    session = {
        "repos?page=1": MockResponse(["page", "1", "data"], next_url="repos?page=2"),
        "repos?page=2": MockResponse(["page", "2", "data"]),
    }
    pages = main.get_pages(session, "repos?page=1")

    assert isinstance(pages, types.GeneratorType)
    page_1, page_2 = list(pages)
    assert page_1.json_data == ["page", "1", "data"]
    assert page_2.json_data == ["page", "2", "data"]


def test_get_repo_names(repos_pages):
    repo_names = main.get_repo_names(repos_pages)
    assert isinstance(repo_names, types.GeneratorType)
    assert list(repo_names) == ["active_repo", "abandoned_repo", "empty_repo"]


def test_get_workflow_runs(active_repo_workflow_run_pages):
    workflow_runs = main.get_workflow_runs(active_repo_workflow_run_pages)
    run_1, run_2, run_3 = list(workflow_runs)

    assert isinstance(workflow_runs, types.GeneratorType)
    assert run_1["repository"]["name"] == "active_repo"
    assert run_1["id"] == 1
    assert run_2["id"] == 2
    assert run_3["id"] == 3


def test_write_pages():
    mock_file_system = {}

    def mock_write(obj, f_path):
        mock_file_system[str(f_path)] = obj

    pages = iter(
        [
            MockResponse(["data_1", "data_2"]),
            MockResponse(["data_3", "data_4"]),
        ]
    )
    main.write_pages(pages, pathlib.Path("test_dir"), mock_write)
    assert mock_file_system == {
        "test_dir/pages/1.json": '["data_1", "data_2"]',
        "test_dir/pages/2.json": '["data_3", "data_4"]',
    }


def test_write_workflow_run(workflow_run_template):
    mock_file_system = {}

    def mock_write(obj, f_path):
        mock_file_system[str(f_path)] = obj

    run = workflow_run_template | {"id": 1, "repository": {"name": "test_repo"}}
    main.write_workflow_run(run, pathlib.Path("test_dir"), mock_write)

    assert mock_file_system == {"test_dir/runs/1.json": run}
