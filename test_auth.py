import auth


def test_github_api_session_init(monkeypatch):
    # Give a PAT without expiry date
    monkeypatch.setenv("GITHUB_WORKFLOW_RUNS_TOKEN", "test_token")
    monkeypatch.delenv("GITHUB_WORKFLOW_RUNS_TOKEN_EXPIRY")
    session = auth.GitHubAPISession()

    assert session.headers["Authorization"] == "Bearer test_token"

    session.close()
