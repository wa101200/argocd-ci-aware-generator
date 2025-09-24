from fastapi import FastAPI
from pydantic import BaseModel
from typing import Any, Dict

app = FastAPI()


class GetParamsRequest(BaseModel):
    param1: str
    param2: int


class GetParamsResponse(BaseModel):
    success: bool
    data: Dict[str, Any]


@app.post("/api/v1/getparams.execute", response_model=GetParamsResponse)
async def get_params(request: GetParamsRequest):
    # Example logic
    result = {"received_param1": request.param1, "received_param2": request.param2}
    return GetParamsResponse(success=True, data=result)
