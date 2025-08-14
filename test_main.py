import datetime
import json
import pathlib
import types


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


def test_github_api_session_init(monkeypatch):
    monkeypatch.setenv("GITHUB_WORKFLOW_RUNS_TOKEN", "test_token")
    session = main.GitHubAPISession()

    assert session.headers["Authorization"] == "Bearer test_token"
    assert session.params == {"per_page": 100, "format": "json"}

    session.close()


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
    main.extract(session, output_dir, datetime.datetime(2025, 1, 1), mock_write)

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


def test_load_latest_workflow_runs(tmpdir):
    repo_dir = pathlib.Path(tmpdir) / "repo_1"
    older_dir = repo_dir / "20250101-000000Z" / "runs"
    older_dir.mkdir(parents=True)
    newer_dir = repo_dir / "20250102-000000Z" / "runs"
    newer_dir.mkdir(parents=True)

    (older_dir / "1.json").write_text('{"id": 1,"status": "completed"}')
    (older_dir / "2.json").write_text('{"id": 2, "status": "running"}')
    (newer_dir / "2.json").write_text('{"id": 2, "status": "completed"}')
    (newer_dir / "3.json").write_text('{"id": 3, "status": "running"}')

    runs = main.load_latest_workflow_runs(repo_dir)

    assert isinstance(runs, types.GeneratorType)
    assert list(runs) == [
        {"id": 3, "status": "running"},
        {"id": 2, "status": "completed"},
        {"id": 1, "status": "completed"},
    ]


def test_get_records(tmpdir):
    template = {
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
    # Timestamp handling is tested elsewhere so only one timestamp per repo here
    workflows_dir = pathlib.Path(tmpdir)
    repo_1_dir = workflows_dir / "repo_1" / "20250101-000000Z" / "runs"
    repo_2_dir = workflows_dir / "repo_2" / "20250101-000000Z" / "runs"
    repo_1_dir.mkdir(parents=True)
    repo_2_dir.mkdir(parents=True)

    repo_1_run_1 = template | {"id": 1, "repository": {"name": "repo_1"}}
    (repo_1_dir / "1.json").write_text(json.dumps(repo_1_run_1))
    repo_1_run_2 = template | {"id": 2, "repository": {"name": "repo_1"}}
    (repo_1_dir / "2.json").write_text(json.dumps(repo_1_run_2))
    repo_2_run_3 = template | {"id": 3, "repository": {"name": "repo_2"}}
    (repo_2_dir / "3.json").write_text(json.dumps(repo_2_run_3))

    records = main.get_records(workflows_dir)
    record_1, record_2, record_3 = sorted(records, key=lambda r: r.id)

    assert isinstance(records, types.GeneratorType)
    assert record_1._fields == main.Record._fields
    assert record_1.id == 1
    assert record_1.repo == "repo_1"
    assert record_2.id == 2
    assert record_2.repo == "repo_1"
    assert record_3.id == 3
    assert record_3.repo == "repo_2"


def test_main(tmpdir):
    # Run through pipeline for a single workflow run
    output_dir = pathlib.Path(tmpdir)

    def mock_now():
        return datetime.datetime(2025, 1, 1)

    run = {
        "id": 1,
        "name": "My Workflow",
        "head_sha": 12345678,
        "status": "pending",
        "conclusion": None,
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-01T00:00:00Z",
        "run_started_at": "2025-01-01T00:00:00Z",
        "repository": {"name": "test_repo"},
    }

    repos_page = MockResponse([{"name": "test_repo"}])
    repo_1_runs_page = MockResponse({"total_count": 1, "workflow_runs": [run]})

    session = {
        f"https://api.github.com/orgs/{main.GITHUB_ORG}/repos": repos_page,
        f"https://api.github.com/repos/{main.GITHUB_ORG}/test_repo/actions/runs": repo_1_runs_page,
    }

    main.main(session, output_dir, now_function=mock_now)

    with open(output_dir / "repos" / "20250101-000000Z" / "pages" / "1.json") as f:
        repo_page = json.load(f)

    with open(output_dir / "test_repo" / "20250101-000000Z" / "pages" / "1.json") as f:
        run_page = json.load(f)

    with open(output_dir / "test_repo" / "20250101-000000Z" / "runs" / "1.json") as f:
        run_file = json.load(f)

    with open(output_dir / "workflow_runs.csv") as f:
        csv_file = f.read()

    assert repo_page == [{"name": "test_repo"}]
    assert run_page == {"total_count": 1, "workflow_runs": [run]}
    assert run_file == run
    assert csv_file == (
        "id,repo,name,head_sha,status,conclusion,created_at,updated_at,run_started_at\n"
        "1,test_repo,My Workflow,12345678,pending,,2025-01-01T00:00:00Z,2025-01-01T00:00:00Z,2025-01-01T00:00:00Z\n"
    )
