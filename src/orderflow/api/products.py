"""Product HTTP endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from orderflow.db.session import get_db_session
from orderflow.products.schemas import ProductCreate, ProductResponse
from orderflow.products.service import create_product, get_product

router = APIRouter(prefix="/api/v1/products", tags=["products"])


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def create_product_endpoint(
    payload: ProductCreate,
    session: Annotated[Session, Depends(get_db_session)],
) -> ProductResponse:
    """Create one product."""

    return ProductResponse.model_validate(create_product(session, payload))


@router.get("/{product_id}", response_model=ProductResponse)
def get_product_endpoint(
    product_id: UUID,
    session: Annotated[Session, Depends(get_db_session)],
) -> ProductResponse:
    """Get one product by identifier."""

    return ProductResponse.model_validate(get_product(session, product_id))
