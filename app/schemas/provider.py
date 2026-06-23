from pydantic import BaseModel


class ProviderSyncResponse(BaseModel):
    updated: int
    errors: list[str]
    message: str = ""
