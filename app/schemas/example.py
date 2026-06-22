from datetime import datetime

from pydantic import BaseModel, Field


class ExampleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, examples=["my-example"])
    description: str | None = Field(default=None, max_length=1000)


class ExampleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)


class ExampleResponse(BaseModel):
    id: int
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
