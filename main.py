import json
import itertools
import time


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


def write_pages(pages, directory, writer):
    for page_number, page in enumerate(pages, start=1):
        f_path = directory / "pages" / f"{page_number}.json"
        writer(page.text, f_path)


def write_workflow_run(workflow_run, directory, writer):
    # We can only serialize the JSON right before writing since we need the ID
    f_path = directory / "runs" / f"{workflow_run['id']}.json"
    writer(json.dumps(workflow_run), f_path)


def extract(session, output_dir, writer):
    repos_pages, repo_names = get_repo_names(session)
    write_pages(repos_pages, output_dir / "repos", writer)

    for repo in repo_names:
        workflow_runs_pages, workflow_runs = get_repo_workflow_runs(repo, session)
        write_pages(workflow_runs_pages, output_dir / repo, writer)
        for workflow_run in workflow_runs:
            write_workflow_run(workflow_run, output_dir / repo, writer)


def main():
    pass


if __name__ == "__main__":
    main()
