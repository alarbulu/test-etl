import pytest
import main
import types


@pytest.fixture
def repos_pages():
    def _repos_pages():
        page_1 = [{"name": "active_repo"}, {"name": "abandoned_repo"}]
        page_2 = [{"name": "empty_repo"}]
        yield page_1
        yield page_2

    return _repos_pages()


def test_get_repo_names(repos_pages):
    repo_names = main.get_repo_names(repos_pages)
    assert isinstance(repo_names, types.GeneratorType)
    assert list(repo_names) == ["active_repo", "abandoned_repo", "empty_repo"]
