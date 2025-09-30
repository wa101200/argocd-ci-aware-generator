from typing import Any

from tinydb import Query, TinyDB


class DatabaseService:
    """A service to interact with the TinyDB database."""

    def __init__(self, db_file: str) -> None:
        self._db = TinyDB(db_file, indent=4, sort_keys=True)
        self._application_table = self._db.table("application")

    def create_application(
        self,
        application_set_name: str,
        repo: str,
        branch: str,
        state: dict[str, Any],
        last_known_good_sha: str | None = None,
    ) -> int:
        """Creates a new application entry in the database."""
        application = Query()
        items = self._application_table.search(
            application.fragment(
                {
                    "application_set_name": application_set_name,
                    "repo": repo,
                    "branch": branch,
                }
            )
        )

        if len(items) > 0:
            raise Exception(
                f"Application already exists for {application_set_name}, {repo}, {branch}"  # noqa: E501
            )

        return self._application_table.insert(
            {
                "application_set_name": application_set_name,
                "repo": repo,
                "branch": branch,
                "state": state,
                "last_known_good_sha": last_known_good_sha,
            }
        )

    def get_application(
        self, application_set_name: str, repo: str, branch: str
    ) -> dict[str, Any] | None:
        """Retrieves the state of an existing application."""
        application = Query()
        items = self._application_table.search(
            application.fragment(
                {
                    "application_set_name": application_set_name,
                    "repo": repo,
                    "branch": branch,
                }
            )
        )
        if len(items) == 0:
            return None

        if len(items) > 1:
            raise Exception(
                f"Multiple applications found for {application_set_name}, {repo}, {branch}"  # noqa: E501
            )

        return items[0]

    def update_application(
        self,
        application_set_name: str,
        repo: str,
        branch: str,
        state: dict[str, Any],
        last_known_good_sha: str | None = None,
    ) -> int:
        """Updates the state of an existing application."""
        application = Query()
        items = self._application_table.update(
            {"state": state, "last_known_good_sha": last_known_good_sha},
            application.fragment(
                {
                    "application_set_name": application_set_name,
                    "repo": repo,
                    "branch": branch,
                }
            ),
        )

        if len(items) == 0:
            raise Exception(
                f"Application not found for {application_set_name}, {repo}, {branch}"
            )
        if len(items) > 1:
            raise Exception(
                f"Multiple applications found for {application_set_name}, {repo}, {branch}"  # noqa: E501
            )

        return items[0]

    def close(self) -> None:
        """Closes the database connection."""
        self._db.close()
