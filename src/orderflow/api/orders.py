"""Order HTTP endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Response, status
from sqlalchemy.orm import Session

from orderflow.db.session import get_db_session
from orderflow.orders.schemas import OrderCreate, OrderResponse
from orderflow.orders.service import confirm_order, create_order, get_order

router = APIRouter(prefix="/api/v1/orders", tags=["orders"])

IdempotencyKey = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=1,
        max_length=128,
        pattern=r"^[!-~]+$",
    ),
]


@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
def create_order_endpoint(
    payload: OrderCreate,
    response: Response,
    idempotency_key: IdempotencyKey,
    session: Annotated[Session, Depends(get_db_session)],
) -> OrderResponse:
    """Create or replay one complete pending order by opaque request key."""

    result = create_order(session, payload, idempotency_key)
    response.status_code = (
        status.HTTP_200_OK if result.replayed else status.HTTP_201_CREATED
    )
    return OrderResponse.from_order(result.order)


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
    """Confirm an order with concurrency-safe transactional stock debit."""

    return OrderResponse.from_order(confirm_order(session, order_id))
