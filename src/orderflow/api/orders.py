"""Order HTTP endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from orderflow.db.session import get_db_session
from orderflow.orders.schemas import OrderCreate, OrderResponse
from orderflow.orders.service import confirm_order, create_order, get_order

router = APIRouter(prefix="/api/v1/orders", tags=["orders"])


@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
def create_order_endpoint(
    payload: OrderCreate,
    session: Annotated[Session, Depends(get_db_session)],
) -> OrderResponse:
    """Create one complete pending order."""

    return OrderResponse.from_order(create_order(session, payload))


@router.get("/{order_id}", response_model=OrderResponse)
def get_order_endpoint(
    order_id: UUID,
    session: Annotated[Session, Depends(get_db_session)],
) -> OrderResponse:
    """Get one order and its items."""

    return OrderResponse.from_order(get_order(session, order_id))


@router.post("/{order_id}/confirm", response_model=OrderResponse)
def confirm_order_endpoint(
    order_id: UUID,
    session: Annotated[Session, Depends(get_db_session)],
) -> OrderResponse:
    """Confirm an order with sequential transactional stock debit."""

    return OrderResponse.from_order(confirm_order(session, order_id))
