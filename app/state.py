from typing import Any

from tinydb import Query, TinyDB

db = None
application_table = None


def setup_db(db_file: str) -> TinyDB:
    """Initializes the global database instance."""
    global db, application_table
    db = TinyDB(db_file, indent=4, sort_keys=True)
    application_table = db.table("application")
    return db


async def create_application(
    application_set_name: str,
    repo: str,
    branch: str,
    state: dict[str, Any],
) -> int:
    """Creates a new application entry in the database."""
    application = Query()
    items = application_table.search(
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
            f"Application already exists for {application_set_name}, {repo}, {branch}"
        )

    return application_table.insert(
        {
            "application_set_name": application_set_name,
            "repo": repo,
            "branch": branch,
            "state": state,
        }
    )


async def get_application(
    application_set_name: str, repo: str, branch: str
) -> dict[str, Any] | None:
    """Retrieves the state of an existing application."""
    application = Query()
    items = application_table.search(
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
            f"Multiple applications found for {application_set_name}, {repo}, {branch}"
        )

    return items[0]


async def update_application(
    application_set_name: str, repo: str, branch: str, state: dict[str, Any]
) -> int:
    """Updates the state of an existing application."""
    application = Query()
    items = application_table.update(
        {"state": state},
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
            f"Multiple applications found for {application_set_name}, {repo}, {branch}"
        )

    return items[0]
