from typing import Any

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from starlette.responses import Response


def ok(data: Any, message: str = "Ok") -> JSONResponse:
    return JSONResponse(
        status_code=200,
        content={"success": True, "code": 200, "message": message, "data": jsonable_encoder(data)},
    )


def created(data: Any, message: str = "Created") -> JSONResponse:
    return JSONResponse(
        status_code=201,
        content={"success": True, "code": 201, "message": message, "data": jsonable_encoder(data)},
    )


def no_content() -> Response:
    return Response(status_code=204)
