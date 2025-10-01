import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Literal

from dependency_injector.wiring import Provide, inject
from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, model_validator

from containers import Container
from github_utils import GithubService
from state import DatabaseService

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class ParamsScmData(BaseModel):
    """Parameters schema for the ArgoCD getparams request."""

    organization: str
    repository: str
    branch: str
    sha: str

    model_config = ConfigDict(extra="allow")


class ParamsPrData(BaseModel):
    """Parameters schema for the ArgoCD getparams request."""

    # ruff: noqa: N815
    repoURL: str
    branch: str
    head_sha: str

    model_config = ConfigDict(extra="allow")


class Params(BaseModel):
    """Parameters schema for the ArgoCD getparams request."""

    sourceGeneratorType: Literal["scm", "pr"]
    checks_regex: list[str]

    data: ParamsScmData | ParamsPrData

    @model_validator(mode="before")
    @classmethod
    def validate_data_type(cls, data: dict) -> dict:
        """Validates the data field based on the sourceGeneratorType."""
        if not isinstance(data, dict):
            return data

        generator_type: str = data.get("sourceGeneratorType")
        data_field = data.get("data")

        if generator_type == "scm":
            validated_data = ParamsScmData.model_validate(data_field)
            data["data"] = validated_data.model_dump()
        elif generator_type == "pr":
            validated_data = ParamsPrData.model_validate(data_field)
            data["data"] = validated_data.model_dump()

        return data


class Input(BaseModel):
    """Input schema for the ArgoCD getparams request."""

    parameters: Params


class GetParamsRequest(BaseModel):
    """Request schema for the ArgoCD getparams request."""

    applicationSetName: str
    input: Input


class GetParamsResponse(BaseModel):
    """Response schema for the ArgoCD getparams request."""

    output: dict[str, Any]


@asynccontextmanager
async def lifespan(_app: FastAPI):  # noqa: ANN201 TODO
    """Initializes the container and sets up the database connection."""
    container = Container()
    db_file = os.getenv("DB_FILE", "db.json")
    github_token = os.getenv("GITHUB_TOKEN")
    container.config.from_dict({"db_file": db_file, "github_token": github_token})
    container.wire(modules=[__name__])
    _app.container = container
    yield
    container.unwire()


app = FastAPI(lifespan=lifespan)


@app.post("/api/v1/getparams.execute")
@inject
async def process_argocd_param(
    request: GetParamsRequest,
    db_service: DatabaseService = Depends(Provide[Container.db_service]),  # noqa: B008 TODO
    github_service: GithubService = Depends(Provide[Container.github_service]),  # noqa: B008 TODO
) -> GetParamsResponse:
    """Processes the ArgoCD getparams request."""
    application_set_name = request.applicationSetName

    checks_regex: list[str] = request.input.parameters.checks_regex

    if request.input.parameters.sourceGeneratorType == "scm":
        d = ParamsScmData.model_validate(request.input.parameters.data)
        organization = d.organization
        repository: str = d.repository
        branch: str = d.branch
        sha: str = d.sha
        state = d.model_dump()

    if request.input.parameters.sourceGeneratorType == "pr":
        d = ParamsPrData.model_validate(request.input.parameters.data)

        if d.repoURL.startswith("https://github.com/"):
            organization = d.repoURL.split("/")[-2]
            repository = d.repoURL.split("/")[-1].removesuffix(".git")
        else:
            organization = d.repoURL.removeprefix("git@github.com:").split("/")[0]
            repository = d.repoURL.split("/")[-1].removesuffix(".git")

        branch: str = d.branch
        sha: str = d.head_sha

        state = d.model_dump()

    sha_check_fingerprint = "+".join([sha, *checks_regex])

    application_data = db_service.get_application(
        application_set_name, repository, branch
    )

    logger.debug(f"Application data: {application_data}")

    if (
        application_data is not None
        and application_data["last_known_good_sha"] == sha_check_fingerprint
    ):
        logger.debug(
            f"CACHE HIT: Application found for {application_set_name}, {repository}, {branch} with last known good sha {sha_check_fingerprint} matching current SHA"  # noqa: E501
        )

        resp = {"output": {"parameters": [state]}}
        return GetParamsResponse(**resp)

    checks_result = github_service.commit_passed_checks(
        checks_regex=checks_regex,
        repo=f"{organization}/{repository}",
        commit_sha=sha,
    )

    if checks_result:
        if application_data is None:
            logger.info(
                f"Application not found for {application_set_name}, {repository}, {branch}"  # noqa: E501
            )
            logger.info(
                f"Creating new application with last known good sha {sha_check_fingerprint}"  # noqa: E501
            )
            db_service.create_application(
                application_set_name,
                repository,
                branch,
                state,
                last_known_good_sha=sha_check_fingerprint,
            )
            logger.info("Application created")

        else:
            logger.info(
                f"Application found for {application_set_name}, {repository}, {branch}"
            )
            logger.info(
                f"Updating application with last known good sha {sha_check_fingerprint}"
            )
            db_service.update_application(
                application_set_name,
                repository,
                branch,
                state,
                last_known_good_sha=sha_check_fingerprint,
            )
        resp = {"output": {"parameters": [state]}}
        return GetParamsResponse(**resp)

    else:
        if application_data is None:
            logger.info(
                f"GH checks on {repository} failed, no application found for {application_set_name}, {repository}, {branch}, and no application is found, returning empty state"  # noqa: E501
            )
            return GetParamsResponse(**{"output": {"parameters": []}})
        else:
            logger.info(
                f"GH checks on {repository} failed, application found for {application_set_name}, {repository}, {branch}, returning previous state"  # noqa: E501
            )
            return GetParamsResponse(
                **{"output": {"parameters": [application_data["state"]]}}
            )


@app.get("/health")
@inject
async def health_check(
    db_service: DatabaseService = Depends(Provide[Container.db_service]),  # noqa: B008 TODO
    github_service: GithubService = Depends(Provide[Container.github_service]),  # noqa: B008 TODO
) -> JSONResponse:
    """Health check endpoint."""
    db_healthy, github_healthy = await asyncio.gather(
        db_service.health_check(), github_service.health_check()
    )

    health_status = {
        "database": db_healthy,
        "github": github_healthy,
    }

    overall_status = all(health_status.values())

    status_code = 200 if overall_status else 503

    return JSONResponse(content=health_status, status_code=status_code)
