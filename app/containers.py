from dependency_injector import containers, providers

from github_utils import GithubService
from state import DatabaseService


class Container(containers.DeclarativeContainer):
    """A container for the application's dependencies."""

    config = providers.Configuration()

    db_service = providers.Singleton(
        DatabaseService,
        db_file=config.db_file,
    )

    github_service = providers.Singleton(
        GithubService, github_token=config.github_token
    )
