# test_main.py

import pytest
from httpx import AsyncClient

from containers import Container
from state import DatabaseService

# NOTE: These tests require a valid GITHUB_TOKEN environment variable.
# The tests run against a real, public GitHub repository and will fail without it.

# --- Test Constants ---
REPO_ORG = "wa101200"
REPO_NAME = "argocd-validate-ci-cheks-generators"
REPO_FULL_NAME = f"{REPO_ORG}/{REPO_NAME}"
APP_SET_NAME = "test-appset"
BRANCH = "main"

# A commit where all checks passed successfully.
# https://github.com/wa101200/argocd-validate-ci-cheks-generators/commit/de5e62e7eaf38691a62f806e16887b2620532594
SUCCESS_SHA = "de5e62e7eaf38691a62f806e16887b2620532594"

# A commit where the 'pre-commit' check failed.
# https://github.com/wa101200/argocd-validate-ci-cheks-generators/commit/4f18d12c487449ef5120b3ed0ecba268edf5dbb8
FAIL_SHA = "4f18d12c487449ef5120b3ed0ecba268edf5dbb8"

PASSING_CHECKS_REGEX = ["pre-commit"]
FAILING_CHECKS_REGEX = ["pre-commit"]


@pytest.fixture
def db_service(container: Container) -> DatabaseService:
    """A fixture that provides a database service for testing."""
    return container.db_service()


# --- Helper Function ---


def build_payload(
    generator_type: str, sha: str, checks_regex: list[str], repo_url: str | None = None
) -> dict:
    """Builds the ArgoCD request payload based on generator type and parameters."""
    data = {}
    if generator_type == "scm":
        data = {
            "organization": REPO_ORG,
            "repository": REPO_NAME,
            "branch": BRANCH,
            "sha": sha,
        }
    elif generator_type == "pr":
        if repo_url is None:
            repo_url = f"https://github.com/{REPO_FULL_NAME}.git"
        data = {
            "repoURL": repo_url,
            "branch": BRANCH,
            "head_sha": sha,
        }

    return {
        "applicationSetName": APP_SET_NAME,
        "input": {
            "parameters": {
                "sourceGeneratorType": generator_type,
                "checks_regex": checks_regex,
                "data": data,
            }
        },
    }


# --- Parameterized Test Configurations ---

# Configurations for SCM, PR (HTTPS), and PR (Git) generators
GENERATOR_CONFIGS = [
    ("scm", None),
    ("pr", f"https://github.com/{REPO_FULL_NAME}.git"),
    ("pr", f"git@github.com:{REPO_FULL_NAME}.git"),
]


# --- Refactored Tests ---


@pytest.mark.asyncio
@pytest.mark.parametrize("generator_type, repo_url", GENERATOR_CONFIGS)
async def test_checks_pass_no_existing_app(
    client: AsyncClient,
    generator_type: str,
    repo_url: str | None,
    db_service: DatabaseService,
) -> None:
    """Tests when checks pass and no application exists in the state.

    Expects a new application state to be created and returned.
    """
    payload = build_payload(generator_type, SUCCESS_SHA, PASSING_CHECKS_REGEX, repo_url)
    response = await client.post("/api/v1/getparams.execute", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert len(data["output"]["parameters"]) == 1

    sha_key = "sha" if generator_type == "scm" else "head_sha"
    assert data["output"]["parameters"][0][sha_key] == SUCCESS_SHA

    db_app = db_service.get_application(APP_SET_NAME, REPO_NAME, BRANCH)
    assert db_app is not None
    assert db_app["state"][sha_key] == SUCCESS_SHA


@pytest.mark.asyncio
@pytest.mark.parametrize("generator_type, repo_url", GENERATOR_CONFIGS)
async def test_checks_fail_no_existing_app(
    client: AsyncClient,
    generator_type: str,
    repo_url: str | None,
    db_service: DatabaseService,
) -> None:
    """Tests when checks fail and no application exists.

    Expects an empty parameter list and no application state created.
    """
    payload = build_payload(generator_type, FAIL_SHA, FAILING_CHECKS_REGEX, repo_url)
    response = await client.post("/api/v1/getparams.execute", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["output"]["parameters"] == []

    db_app = db_service.get_application(APP_SET_NAME, REPO_NAME, BRANCH)
    assert db_app is None


@pytest.mark.asyncio
@pytest.mark.parametrize("generator_type, repo_url", GENERATOR_CONFIGS)
async def test_checks_fail_with_existing_app(
    client: AsyncClient,
    generator_type: str,
    repo_url: str | None,
    db_service: DatabaseService,
) -> None:
    """Tests when checks fail but an older application state exists.

    Expects the previous (existing) state to be returned.
    """
    sha_key = "sha" if generator_type == "scm" else "head_sha"
    previous_state = {
        "repoURL" if generator_type == "pr" else "repository": REPO_NAME,
        sha_key: "old-sha",
    }

    db_service.create_application(APP_SET_NAME, REPO_NAME, BRANCH, previous_state)

    payload = build_payload(generator_type, FAIL_SHA, FAILING_CHECKS_REGEX, repo_url)
    response = await client.post("/api/v1/getparams.execute", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert len(data["output"]["parameters"]) == 1
    assert data["output"]["parameters"][0] == previous_state


@pytest.mark.asyncio
@pytest.mark.parametrize("generator_type, repo_url", GENERATOR_CONFIGS)
async def test_checks_pass_with_existing_app_update(
    client: AsyncClient,
    generator_type: str,
    repo_url: str | None,
    db_service: DatabaseService,
) -> None:
    """Tests when checks pass and an application state already exists.

    Expects the state to be updated with the new commit SHA.
    """
    sha_key = "sha" if generator_type == "scm" else "head_sha"
    previous_state = {"repository": REPO_NAME, sha_key: "old-sha"}
    db_service.create_application(APP_SET_NAME, REPO_NAME, BRANCH, previous_state)

    payload = build_payload(generator_type, SUCCESS_SHA, PASSING_CHECKS_REGEX, repo_url)
    response = await client.post("/api/v1/getparams.execute", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert len(data["output"]["parameters"]) == 1
    assert data["output"]["parameters"][0][sha_key] == SUCCESS_SHA

    db_app = db_service.get_application(APP_SET_NAME, REPO_NAME, BRANCH)
    assert db_app is not None
    assert db_app["state"][sha_key] == SUCCESS_SHA


@pytest.mark.asyncio
@pytest.mark.parametrize("generator_type, repo_url", GENERATOR_CONFIGS)
async def test_cache_hit_returns_current_request_state(
    client: AsyncClient,
    generator_type: str,
    repo_url: str | None,
    db_service: DatabaseService,
) -> None:
    """Tests that a cache hit returns the state from the current request.

    When the `sha_check_fingerprint` matches an existing record, the endpoint
    should return the parameters from the current request payload, not the
    state stored in the database. The database should also not be updated.
    """
    checks_regex = PASSING_CHECKS_REGEX
    sha_check_fingerprint = "+".join([SUCCESS_SHA, *checks_regex])

    # 1. Create a pre-existing application with a specific state and fingerprint
    previous_state = {"this_is": "old_state"}
    db_service.create_application(
        APP_SET_NAME,
        REPO_NAME,
        BRANCH,
        previous_state,
        last_known_good_sha=sha_check_fingerprint,
    )

    # 2. Build a new payload that will cause a cache hit
    payload = build_payload(generator_type, SUCCESS_SHA, checks_regex, repo_url)
    current_state = payload["input"]["parameters"]["data"]

    # 3. Make the request
    response = await client.post("/api/v1/getparams.execute", json=payload)
    assert response.status_code == 200

    # 4. Assert the response contains the state from the new payload
    data = response.json()
    assert len(data["output"]["parameters"]) == 1
    assert data["output"]["parameters"][0] == current_state
    assert data["output"]["parameters"][0] != previous_state

    # 5. Verify the database state has not been updated
    db_app = db_service.get_application(APP_SET_NAME, REPO_NAME, BRANCH)
    assert db_app is not None
    assert db_app["state"] == previous_state
