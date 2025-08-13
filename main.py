import json
import itertools
import time

import collections

File = collections.namedtuple("File", ["filepath", "content"])


class SessionWithRetry:
    def __init__(
        self, session, max_retries, base_delay_seconds, sleep_function=time.sleep
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
    url = "https://api.github.com/orgs/opensafely/repos"
    pages_1, pages_2 = itertools.tee(get_pages(session, url))
    return pages_1, _extract_repo_names_from_pages(pages_2)


def _extract_workflow_runs_from_pages(workflow_runs_pages):
    decoded_pages = (page.json() for page in workflow_runs_pages)
    return (run for page in decoded_pages for run in page["workflow_runs"])


def get_repo_workflow_runs(repo_name, session):
    url = f"https://api.github.com/repos/opensafely/{repo_name}/actions/runs"
    pages_1, pages_2 = itertools.tee(get_pages(session, url))
    return pages_1, _extract_workflow_runs_from_pages(pages_2)


def get_page_files(pages, output_dir):
    for page_number, page in enumerate(pages, start=1):
        yield File(output_dir / "pages" / f"{page_number}.json", page.text)


def get_run_files(workflow_runs, output_dir):
    for run in workflow_runs:
        yield File(output_dir / "runs" / f"{run['id']}.json", json.dumps(run))


def extract(session, output_dir, writer):
    repo_names_pages, repo_names = get_repo_names(session)
    repo_names_files = get_page_files(repo_names_pages, output_dir / "repos")

    file_iterables = [repo_names_files]
    for repo_name in repo_names:
        workflow_run_pages, workflow_runs = get_repo_workflow_runs(repo_name, session)
        page_files = get_page_files(workflow_run_pages, output_dir / repo_name)
        run_files = get_run_files(workflow_runs, output_dir / repo_name)
        file_iterables.extend([page_files, run_files])

    for file in itertools.chain(*file_iterables):
        writer(file.content, file.filepath)


def main():
    pass


if __name__ == "__main__":
    main()
