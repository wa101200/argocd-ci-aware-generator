# Authentication is defined via github.Auth
import logging
import re

from github import Auth, Github

logging.basicConfig(level=logging.INFO)


logger = logging.getLogger(__name__)


class GithubService:
    """A service for interacting with the Github API."""

    def __init__(self, github_token: str) -> None:
        """Initializes the GithubService."""
        auth = Auth.Token(github_token)
        self._github_client = Github(auth=auth)

    async def health_check(self) -> bool:
        """Checks if the Github service is healthy."""
        try:
            rate = self._github_client.get_rate_limit()

            if rate.rate.remaining < 1:
                logger.error(
                    f"Github rate limit is reached, remaining: {rate.rate.remaining}"
                )
                return False
            logger.debug(f"Github rate limit: {self._github_client.get_rate_limit()}")
            return True
        except Exception as e:
            logger.error(f"Github service is not healthy: {e}")
            return False

    def commit_passed_checks(
        self,
        checks_regex: list[str],
        repo: str,
        commit_sha: str,
    ) -> bool:
        """Checks if the commit passed all the specified checks."""
        commit = self._github_client.get_repo(repo).get_commit(commit_sha)

        for check_regex in checks_regex:
            logger.info(f'Validating CI Check for regex "{check_regex}"')

            matched_runs = [
                i for i in commit.get_check_runs() if re.match(check_regex, i.name)
            ]

            if len(matched_runs) == 0:
                logger.info(f'No CI check run found for regex "{check_regex}"')

            for check_run in matched_runs:
                logger.info(
                    f'CI Check "{check_run.name}" matched "{check_regex}", validating...'  # noqa: E501
                )
                if not (
                    check_run.status == "completed"
                    and check_run.conclusion == "success"
                ):
                    logger.info(
                        f'CI Check "{check_run.name}" failed with conclusion "{check_run.conclusion}" and status "{check_run.status}" on regex "{check_regex}"'  # noqa: E501
                    )
                    return False
            logger.info(f'CI Check for regex "{check_regex}" passed')

        return True
