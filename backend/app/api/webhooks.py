"""Inbound webhooks from bank aggregators.

Unlike every other route in this API, the caller here is Plaid, not a
Bankr user -- there's no session token, and the request is authenticated
by verifying Plaid's own signature over the raw body instead (see
PlaidClient.verify_webhook_signature). That's also why this reads
`request.body()` directly rather than taking a Pydantic model: the
signature covers the exact bytes Plaid sent, and re-serializing a parsed
model wouldn't reliably reproduce them.
"""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_aggregator
from app.db.base import get_db
from app.integrations.bank_aggregator import BankAggregatorClient
from app.services.webhook_service import handle_plaid_webhook

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/plaid", status_code=status.HTTP_200_OK)
async def plaid_webhook(
    request: Request,
    db: Session = Depends(get_db),
    aggregator: BankAggregatorClient = Depends(get_aggregator),
) -> dict:
    raw_body = await request.body()
    verification_header = request.headers.get("plaid-verification")

    if not verification_header or not aggregator.verify_webhook_signature(raw_body, verification_header):
        # Deliberately vague: Plaid doesn't retry a 401 (it's not a
        # transient failure), and there's nothing here worth telling a
        # forged or replayed request about.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid webhook signature")

    try:
        payload = json.loads(raw_body)
    except ValueError:
        # Passed signature verification (which itself hashes this exact
        # body) but isn't valid JSON -- shouldn't happen; log and 200 it so
        # Plaid doesn't retry something that will never parse.
        logger.error("plaid webhook: verified body is not valid JSON")
        return {"acknowledged": True}

    handle_plaid_webhook(db, payload, aggregator)
    return {"acknowledged": True}
