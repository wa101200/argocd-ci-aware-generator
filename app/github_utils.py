# Authentication is defined via github.Auth
import logging
import os
import re

from github import Auth, Github

logging.basicConfig(level=logging.INFO)


logger = logging.getLogger(__name__)

# using an access token
auth = Auth.Token(os.environ["GITHUB_TOKEN"])
enable_caching = os.getenv("ENABLE_GITHUB_CACHING", "true").lower() == "true"

githubClient = Github(auth=auth)  # noqa: N816


async def commit_passed_checks(
    checks_regex: list[str],
    repo: str,
    commit_sha: str,
    github_client: Github = githubClient,
) -> bool:
    """Checks if the commit passed all the specified checks."""
    commit = github_client.get_repo(repo).get_commit(commit_sha)

    for check_regex in checks_regex:
        logger.info(f'Validating Check for regex "{check_regex}"')

        matched_runs = [
            i for i in commit.get_check_runs() if re.match(check_regex, i.name)
        ]

        if len(matched_runs) == 0:
            logger.info(f'No check run found for regex "{check_regex}"')

        for check_run in matched_runs:
            logger.info(
                f'Check "{check_run.name}" matched "{check_regex}", validating...'
            )
            if not (
                check_run.status == "completed" and check_run.conclusion == "success"
            ):
                logger.info(
                    f'Check "{check_run.name}" failed with conclusion "{check_run.conclusion}" and status "{check_run.status}" on regex "{check_regex}"'  # noqa: E501
                )
                return False
        logger.info(f'Check for regex "{check_regex}" passed')

    return True
