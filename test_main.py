import pytest
import main
import types


@pytest.fixture
def repos_pages():
    page_1 = [{"name": "active_repo"}, {"name": "abandoned_repo"}]
    page_2 = [{"name": "empty_repo"}]
    return iter([page_1, page_2])


def test_get_repo_names(repos_pages):
    repo_names = main.get_repo_names(repos_pages)
    assert isinstance(repo_names, types.GeneratorType)
    assert list(repo_names) == ["active_repo", "abandoned_repo", "empty_repo"]
