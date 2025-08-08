def get_repo_names(repos_pages):
    decoded_pages = (page.json() for page in repos_pages)
    return (repo["name"] for page in decoded_pages for repo in page)


def get_workflow_runs(workflow_runs_pages):
    decoded_pages = (page.json() for page in workflow_runs_pages)
    return (run for page in decoded_pages for run in page["workflow_runs"])


def write_workflow_run(workflow_run, directory, writer):
    f_path = directory / "runs" / f"{workflow_run['id']}.json"
    writer(workflow_run, f_path)


def main():
    pass


if __name__ == "__main__":
    main()
