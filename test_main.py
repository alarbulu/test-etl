import pytest
import main
import types
import json
import pathlib


class MockResponse:
    def __init__(self, json_data):
        self.json_data = json_data

    def __str__(self):
        return json.dumps(self.json_data)

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
    page_1 = MockResponse([{"name": "active_repo"}, {"name": "abandoned_repo"}])
    page_2 = MockResponse([{"name": "empty_repo"}])
    return iter([page_1, page_2])


@pytest.fixture
def active_repo_workflow_run_pages(workflow_run_template):
    template = workflow_run_template | {"repository": {"name": "active_repo"}}
    run_1 = template | {"id": 1}
    run_2 = template | {"id": 2}
    run_3 = template | {"id": 3}

    pages = [
        MockResponse({"total_count": 3, "workflow_runs": [run_1, run_2]}),
        MockResponse({"total_count": 3, "workflow_runs": [run_3]}),
    ]
    return iter(pages)


def test_get_repo_names(repos_pages):
    repo_names = main.get_repo_names(repos_pages)
    assert isinstance(repo_names, types.GeneratorType)
    assert list(repo_names) == ["active_repo", "abandoned_repo", "empty_repo"]


def test_get_workflow_runs(active_repo_workflow_run_pages):
    workflow_runs = main.get_workflow_runs(active_repo_workflow_run_pages)
    assert isinstance(workflow_runs, types.GeneratorType)
    runs_list = list(workflow_runs)
    assert len(runs_list) == 3
    run_1, run_2, run_3 = runs_list
    assert run_1["repository"]["name"] == "active_repo"
    assert run_1["id"] == 1
    assert run_2["id"] == 2
    assert run_3["id"] == 3


def test_write_workflow_run(workflow_run_template):
    mock_file_system = {}

    def mock_writer(obj, f_path):
        mock_file_system[f_path] = obj

    run = workflow_run_template | {"id": 1, "repository": {"name": "test_repo"}}
    main.write_workflow_run(run, pathlib.Path("test_dir"), mock_writer)

    assert mock_file_system[pathlib.Path("test_dir/runs/1.json")] == run
