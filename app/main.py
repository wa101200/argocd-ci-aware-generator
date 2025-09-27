import logging
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, model_validator

from github_utils import commit_passed_checks
from state import create_application, get_application, update_application

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
async def lifespan(_app: FastAPI) -> None:
    """Sets up the database and yields the application."""
    import os

    from state import setup_db

    db_file = os.getenv("DB_FILE", "db.json")
    setup_db(db_file)
    yield


app = FastAPI(lifespan=lifespan)


@app.post("/api/v1/getparams.execute")
async def process_argocd_param(request: GetParamsRequest) -> GetParamsResponse:
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

    application_data = await get_application(application_set_name, repository, branch)

    checks_result = await commit_passed_checks(
        checks_regex=checks_regex,
        repo=f"{organization}/{repository}",
        commit_sha=sha,
    )

    if checks_result:
        if application_data is None:
            logger.info(
                f"Application not found for {application_set_name}, {repository}, {branch}"  # noqa: E501
            )
            logger.info("Creating new application")
            await create_application(application_set_name, repository, branch, state)
            logger.info("Application created")

        else:
            logger.info(
                f"Application found for {application_set_name}, {repository}, {branch}"
            )
            await update_application(application_set_name, repository, branch, state)
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
