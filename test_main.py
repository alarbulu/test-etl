import datetime
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
        "flaky_url": [MockErrorResponse("Temporary failure")] * 3
        + [MockResponse(["data_1", "data_2"])]
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
    page_1 = MockResponse([{"name": "repo_1"}], next_url="repos?page=2")
    page_2 = MockResponse([{"name": "repo_2"}])
    session = {
        f"https://api.github.com/orgs/{main.GITHUB_ORG}/repos": page_1,
        "repos?page=2": page_2,
    }
    pages, repo_names = main.get_repo_names(session)

    assert list(pages) == [page_1, page_2]
    assert list(repo_names) == ["repo_1", "repo_2"]


def test_get_repo_workflow_runs():
    page_1 = MockResponse(
        {"total_count": 2, "workflow_runs": [{"id": 1}]}, next_url="page_2_url"
    )
    page_2 = MockResponse({"total_count": 2, "workflow_runs": [{"id": 2}]})
    session = {
        f"https://api.github.com/repos/{main.GITHUB_ORG}/repo_1/actions/runs": page_1,
        "page_2_url": page_2,
    }
    pages, workflow_runs = main.get_repo_workflow_runs("repo_1", session)

    assert list(pages) == [page_1, page_2]
    assert list(workflow_runs) == [{"id": 1}, {"id": 2}]


def test_get_page_files():
    pages = iter([MockResponse(["data_1"]), MockResponse(["data_2"])])
    files = main.get_page_files(pages, pathlib.Path("test_dir"))

    assert list(files) == [
        main.File(pathlib.Path("test_dir/pages/1.json"), '["data_1"]'),
        main.File(pathlib.Path("test_dir/pages/2.json"), '["data_2"]'),
    ]


def test_get_run_files():
    files = main.get_run_files([{"id": 1}, {"id": 2}], pathlib.Path("test_dir"))

    assert list(files) == [
        main.File(pathlib.Path("test_dir/runs/1.json"), '{"id": 1}'),
        main.File(pathlib.Path("test_dir/runs/2.json"), '{"id": 2}'),
    ]


def test_extract():
    mock_file_system = {}

    def mock_write(obj, f_path):
        mock_file_system[str(f_path)] = obj

    def mock_now():
        return datetime.datetime(2025, 1, 1)

    repos_page_1 = MockResponse([{"name": "repo_1"}], next_url="repos?page=2")
    repos_page_2 = MockResponse([{"name": "repo_2"}])
    repo_1_runs_page = MockResponse(
        {"total_count": 2, "workflow_runs": [{"id": 1}, {"id": 2}]}
    )
    repo_2_runs_page = MockResponse({"total_count": 0, "workflow_runs": []})
    session = {
        f"https://api.github.com/orgs/{main.GITHUB_ORG}/repos": repos_page_1,
        "repos?page=2": repos_page_2,
        f"https://api.github.com/repos/{main.GITHUB_ORG}/repo_1/actions/runs": repo_1_runs_page,
        f"https://api.github.com/repos/{main.GITHUB_ORG}/repo_2/actions/runs": repo_2_runs_page,
    }
    output_dir = pathlib.Path("test_dir")
    main.extract(session, output_dir, mock_write, now_function=mock_now)

    assert mock_file_system == {
        "test_dir/repos/20250101-000000Z/pages/1.json": '[{"name": "repo_1"}]',
        "test_dir/repos/20250101-000000Z/pages/2.json": '[{"name": "repo_2"}]',
        "test_dir/repo_1/20250101-000000Z/pages/1.json": '{"total_count": 2, "workflow_runs": [{"id": 1}, {"id": 2}]}',
        "test_dir/repo_1/20250101-000000Z/runs/1.json": '{"id": 1}',
        "test_dir/repo_1/20250101-000000Z/runs/2.json": '{"id": 2}',
        "test_dir/repo_2/20250101-000000Z/pages/1.json": '{"total_count": 0, "workflow_runs": []}',
    }


def test_get_names_of_extracted_repos(tmpdir):
    workflows_dir = pathlib.Path(tmpdir)
    (workflows_dir / "repo_1").mkdir(parents=True)
    (workflows_dir / "repo_2").mkdir(parents=True)

    extracted_repos = main.get_names_of_extracted_repos(workflows_dir)

    assert list(extracted_repos) == ["repo_1", "repo_2"]


def test_get_all_extracted_run_filepaths(tmpdir):
    workflows_dir = pathlib.Path(tmpdir)
    timestamp_dir_1 = workflows_dir / "repo_1" / "20250101-000000Z" / "runs"
    (timestamp_dir_1).mkdir(parents=True)
    (timestamp_dir_1 / "1.json").touch()
    (timestamp_dir_1 / "2.json").touch()
    timestamp_dir_2 = workflows_dir / "repo_1" / "20250102-000000Z" / "runs"
    (timestamp_dir_2).mkdir(parents=True)
    (timestamp_dir_2 / "1.json").touch()
    (timestamp_dir_2 / "2.json").touch()

    run_files = main.get_all_extracted_run_filepaths(workflows_dir, "repo_1")

    assert run_files == [
        workflows_dir / "repo_1" / "20250102-000000Z" / "runs" / "2.json",
        workflows_dir / "repo_1" / "20250102-000000Z" / "runs" / "1.json",
        workflows_dir / "repo_1" / "20250101-000000Z" / "runs" / "2.json",
        workflows_dir / "repo_1" / "20250101-000000Z" / "runs" / "1.json",
    ]
