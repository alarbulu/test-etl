import json
import pathlib
import types

import pytest

import main


class MockResponse:
    def __init__(self, json_data, next_url=None):
        self.links = {"next": {"url": next_url}} if next_url else {}
        self.json_data = json_data
        self.status_code = 200

    @property
    def text(self):
        return json.dumps(self.json_data)

    def json(self):
        return self.json_data

    def raise_for_status(self):
        pass  # Response is valid


class MockErrorResponse:
    def __init__(self, error):
        self.error = error
        self.status_code = 400

    def raise_for_status(self):
        raise Exception(self.error)


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


def test_session_with_retry_when_successful(capsys):
    def sleep(seconds):
        return

    session = {"test_url": MockResponse(["data_1", "data_2"])}
    session_with_retry = main.SessionWithRetry(session, 3, 0.5, sleep_function=sleep)

    response = session_with_retry.get("test_url")
    assert response.json() == ["data_1", "data_2"]
    assert capsys.readouterr().out == ""


def test_session_with_retry_when_fail(capsys):
    def sleep(seconds):
        return

    session = {"invalid_url": MockErrorResponse("Network error")}
    session_with_retry = main.SessionWithRetry(session, 3, 0.5, sleep_function=sleep)
    response = session_with_retry.get("invalid_url")
    assert response.status_code == 400
    assert capsys.readouterr().out == (
        "Error fetching invalid_url: Network error\n"
        "Retrying in 0.5 seconds (retry attempt 1)...\n"
        "Error fetching invalid_url: Network error\n"
        "Retrying in 1.0 seconds (retry attempt 2)...\n"
        "Error fetching invalid_url: Network error\n"
        "Retrying in 2.0 seconds (retry attempt 3)...\n"
        "Error fetching invalid_url: Network error\n"
        "Maximum retries reached (3).\n"
    )


def test_session_with_retry_when_fail_then_succeed(capsys):
    def sleep(seconds):
        return

    responses = {
        "flaky_url": [
            MockErrorResponse("Temporary failure"),
            MockErrorResponse("Temporary failure"),
            MockErrorResponse("Temporary failure"),
            MockResponse(["data_1", "data_2"]),
        ]
    }

    class MockSession:
        def get(self, url):
            return responses[url].pop(0)

    session = MockSession()
    session_with_retry = main.SessionWithRetry(session, 3, 0.5, sleep_function=sleep)
    response = session_with_retry.get("flaky_url")

    assert response.json() == ["data_1", "data_2"]
    assert capsys.readouterr().out == (
        "Error fetching flaky_url: Temporary failure\nRetrying in 0.5 seconds (retry attempt 1)...\n"
        "Error fetching flaky_url: Temporary failure\nRetrying in 1.0 seconds (retry attempt 2)...\n"
        "Error fetching flaky_url: Temporary failure\nRetrying in 2.0 seconds (retry attempt 3)...\n"
    )


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


def test_get_repo_names():
    page_1 = MockResponse(
        [{"name": "active_repo"}, {"name": "abandoned_repo"}], next_url="repos?page=2"
    )
    page_2 = MockResponse([{"name": "empty_repo"}])
    session = {
        "https://api.github.com/orgs/opensafely/repos": page_1,
        "repos?page=2": page_2,
    }
    pages, repo_names = main.get_repo_names(session)

    assert list(pages) == [page_1, page_2]
    assert list(repo_names) == ["active_repo", "abandoned_repo", "empty_repo"]


def test_get_repo_workflow_runs():
    page_1 = MockResponse(
        {"total_count": 3, "workflow_runs": [{"id": 1}, {"id": 2}]},
        next_url="page_2_url",
    )
    page_2 = MockResponse({"total_count": 3, "workflow_runs": [{"id": 3}]})
    session = {
        "https://api.github.com/repos/opensafely/active_repo/actions/runs": page_1,
        "page_2_url": page_2,
    }
    pages, workflow_runs = main.get_repo_workflow_runs("active_repo", session)

    assert list(pages) == [page_1, page_2]
    assert list(workflow_runs) == [{"id": 1}, {"id": 2}, {"id": 3}]


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
