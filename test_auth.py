import auth


def test_github_api_session_init(monkeypatch):
    monkeypatch.setenv("GITHUB_WORKFLOW_RUNS_TOKEN", "test_token")
    session = auth.GitHubAPISession()

    assert session.headers["Authorization"] == "Bearer test_token"

    session.close()
