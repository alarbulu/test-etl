def get_repo_names(repos_pages):
    return (repo["name"] for page in repos_pages for repo in page)


def get_workflow_runs(workflow_runs_pages):
    return (run for page in workflow_runs_pages for run in page["workflow_runs"])


def main():
    pass


if __name__ == "__main__":
    main()
