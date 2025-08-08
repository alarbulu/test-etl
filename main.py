def get_repo_names(repos_pages):
    return (repo["name"] for page in repos_pages for repo in page)


def main():
    pass


if __name__ == "__main__":
    main()
