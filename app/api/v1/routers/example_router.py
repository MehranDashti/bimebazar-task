from fastapi import APIRouter, Depends

from app.core.dependencies import get_current_user, get_example_service
from app.core.response import created, no_content, ok
from app.db.pagination import Page, PaginationParams
from app.filters.example_filter import ExampleFilterParams
from app.models.user import User
from app.schemas.example import ExampleCreate, ExampleResponse, ExampleUpdate
from app.services.example_service import ExampleService

router = APIRouter(prefix="/examples", tags=["Examples"])


@router.get("", summary="List examples with filtering, sorting, and pagination")
async def list_examples(
    filters: ExampleFilterParams = Depends(),
    pagination: PaginationParams = Depends(),
    service: ExampleService = Depends(get_example_service),
    _: User = Depends(get_current_user),
):
    items, total = await service.get_paginated(
        filters=filters.to_dict(),
        sort_by=filters.sort_by,
        sort_order=filters.sort_order,
        pagination=pagination,
    )
    page = Page.create([ExampleResponse.model_validate(e) for e in items], total, pagination)
    return ok(page)


@router.get("/{example_id}", summary="Get a single example by ID")
async def get_example(
    example_id: int,
    service: ExampleService = Depends(get_example_service),
    _: User = Depends(get_current_user),
):
    example = await service.get_by_id(example_id)
    return ok(ExampleResponse.model_validate(example))


@router.post("", summary="Create an example")
async def create_example(
    body: ExampleCreate,
    service: ExampleService = Depends(get_example_service),
    _: User = Depends(get_current_user),
):
    example = await service.create(name=body.name, description=body.description)
    return created(ExampleResponse.model_validate(example))


@router.patch("/{example_id}", summary="Update an example")
async def update_example(
    example_id: int,
    body: ExampleUpdate,
    service: ExampleService = Depends(get_example_service),
    _: User = Depends(get_current_user),
):
    example = await service.update(example_id, name=body.name, description=body.description)
    return ok(ExampleResponse.model_validate(example))


@router.delete("/{example_id}", summary="Delete an example")
async def delete_example(
    example_id: int,
    service: ExampleService = Depends(get_example_service),
    _: User = Depends(get_current_user),
):
    await service.delete(example_id)
    return no_content()
