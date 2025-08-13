import datetime
import pathlib
import requests
import json
import itertools
import time

import collections

File = collections.namedtuple("File", ["filepath", "content"])

GITHUB_ORG = "alartest"


def write_file(content, filepath):
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w") as f:
        f.write(content)


class SessionWithRetry:
    def __init__(
        self, session, max_retries=3, base_delay_seconds=0.5, sleep_function=time.sleep
    ):
        self.session = session
        self.max_retries = max_retries
        self.base_delay_seconds = base_delay_seconds
        self.sleep = sleep_function

    def get(self, url):
        retry_count = 0
        while True:
            try:
                response = self.session.get(url)
                response.raise_for_status()
                return response
            except Exception as error:
                print(f"Error fetching {url}: {error}")
                if retry_count < self.max_retries:
                    delay_seconds = self.base_delay_seconds * (2**retry_count)
                    print(
                        f"Retrying in {delay_seconds} seconds (retry attempt {retry_count + 1})..."
                    )
                    retry_count += 1
                    self.sleep(delay_seconds)
                else:
                    print(f"Maximum retries reached ({self.max_retries}).")
                    return response


def get_pages(session, first_page_url):
    url = first_page_url
    while True:
        response = session.get(url)
        yield response
        if next_link := response.links.get("next"):
            url = next_link["url"]
        else:
            break


def _extract_repo_names_from_pages(repos_pages):
    decoded_pages = (page.json() for page in repos_pages)
    return (repo["name"] for page in decoded_pages for repo in page)


def get_repo_names(session):
    url = f"https://api.github.com/orgs/{GITHUB_ORG}/repos"
    pages_1, pages_2 = itertools.tee(get_pages(session, url))
    return pages_1, _extract_repo_names_from_pages(pages_2)


def _extract_workflow_runs_from_pages(workflow_runs_pages):
    decoded_pages = (page.json() for page in workflow_runs_pages)
    return (run for page in decoded_pages for run in page["workflow_runs"])


def get_repo_workflow_runs(repo_name, session):
    url = f"https://api.github.com/repos/{GITHUB_ORG}/{repo_name}/actions/runs"
    pages_1, pages_2 = itertools.tee(get_pages(session, url))
    return pages_1, _extract_workflow_runs_from_pages(pages_2)


def get_page_files(pages, output_dir):
    for page_number, page in enumerate(pages, start=1):
        yield File(output_dir / "pages" / f"{page_number}.json", page.text)


def get_run_files(workflow_runs, output_dir):
    for run in workflow_runs:
        yield File(output_dir / "runs" / f"{run['id']}.json", json.dumps(run))


def extract(session, output_dir, write_function, now_function=datetime.datetime.now):
    timestamp = now_function().strftime("%Y%m%d-%H%M%SZ")
    repo_pages, repo_names = get_repo_names(session)
    repo_files = get_page_files(repo_pages, output_dir / "repos" / timestamp)

    file_iterables = [repo_files]
    for repo_name in repo_names:
        run_pages, runs = get_repo_workflow_runs(repo_name, session)
        page_files = get_page_files(run_pages, output_dir / repo_name / timestamp)
        run_files = get_run_files(runs, output_dir / repo_name / timestamp)
        file_iterables.extend([page_files, run_files])

    for file in itertools.chain(*file_iterables):
        write_function(file.content, file.filepath)


def main():  # pragma: no cover
    session = SessionWithRetry(session=requests.Session())
    output_dir = pathlib.Path("data")

    extract(session, output_dir, write_file)


if __name__ == "__main__":
    main()
