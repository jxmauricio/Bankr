"""Help with a subscription or a charge the user wants back: where to cancel,
and an email they can copy. Bankr never cancels or sends anything itself.

The cancel page comes from a short curated list first. A merchant it doesn't
know is looked up once with web search (only the merchant's name is ever
searched) and the answer, even "nothing found", is cached for every user in
MerchantCancelLink. Emails are plain templates filled with the user's own
numbers: no model, so nothing in them is made up.
"""

import logging
from datetime import date
from urllib.parse import urlparse

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import MerchantCancelLink
from app.integrations.web_search import WebSearchClient
from app.services.recurring_service import merchant_key

logger = logging.getLogger(__name__)

# merchant_key -> (name, page where the subscription is managed or cancelled).
CANCEL_PAGES: dict[str, tuple[str, str]] = {
    "netflix": ("Netflix", "https://www.netflix.com/cancelplan"),
    "spotify": ("Spotify", "https://www.spotify.com/account/subscription/"),
    "spotify usa": ("Spotify", "https://www.spotify.com/account/subscription/"),
    "hulu": ("Hulu", "https://secure.hulu.com/account"),
    "disney plus": ("Disney+", "https://www.disneyplus.com/account/subscription"),
    "disney": ("Disney+", "https://www.disneyplus.com/account/subscription"),
    "max": ("Max", "https://auth.max.com/subscription"),
    "hbo max": ("Max", "https://auth.max.com/subscription"),
    "youtube premium": ("YouTube Premium", "https://www.youtube.com/paid_memberships"),
    "google youtube": ("YouTube Premium", "https://www.youtube.com/paid_memberships"),
    "apple": ("Apple subscriptions", "https://support.apple.com/en-us/118428"),
    "apple com bill": ("Apple subscriptions", "https://support.apple.com/en-us/118428"),
    "amazon prime": ("Amazon Prime", "https://www.amazon.com/mc/manage"),
    "prime video": ("Amazon Prime", "https://www.amazon.com/mc/manage"),
    "audible": ("Audible", "https://www.audible.com/account/overview"),
    "paramount": ("Paramount+", "https://www.paramountplus.com/account/"),
    "peacock": ("Peacock", "https://www.peacocktv.com/account/plans"),
    "adobe": ("Adobe", "https://account.adobe.com/plans"),
    "dropbox": ("Dropbox", "https://www.dropbox.com/account/plan"),
    "microsoft": ("Microsoft", "https://account.microsoft.com/services"),
    "openai": ("ChatGPT", "https://help.openai.com/en/articles/7232927"),
    "chatgpt": ("ChatGPT", "https://help.openai.com/en/articles/7232927"),
    "nytimes": ("The New York Times", "https://myaccount.nytimes.com/seg/subscription"),
    "new york times": ("The New York Times", "https://myaccount.nytimes.com/seg/subscription"),
    "planet fitness": ("Planet Fitness", "https://www.planetfitness.com/about-planet-fitness/customer-service"),
    "duolingo": ("Duolingo", "https://support.duolingo.com/hc/en-us/articles/204830690"),
    "headspace": ("Headspace", "https://www.headspace.com/subscriptions"),
    "patreon": ("Patreon", "https://www.patreon.com/settings/memberships"),
}

# Search results from these hosts are someone else's opinion, not the merchant's page.
_NOT_A_CANCEL_PAGE = ("reddit.com", "quora.com", "youtube.com/watch", "facebook.com", "tiktok.com")


def cancel_link(db: Session, merchant: str, search: WebSearchClient | None) -> dict | None:
    """{"url", "title", "source": "curated" | "search"} for where to cancel, or
    None when neither the list nor a search knows."""
    key = merchant_key(merchant)
    if not key:
        return None
    if key in CANCEL_PAGES:
        name, url = CANCEL_PAGES[key]
        return {"url": url, "title": f"Manage your {name} subscription", "source": "curated"}

    cached = db.query(MerchantCancelLink).filter(MerchantCancelLink.merchant_key == key).one_or_none()
    if cached is None:
        if search is None:
            return None
        cached = _search(db, key, search)
        if cached is None:
            return None
    if not cached.url:
        return None
    return {"url": cached.url, "title": cached.title or "How to cancel", "source": "search"}


def _search(db: Session, key: str, search: WebSearchClient) -> MerchantCancelLink | None:
    try:
        results = search.search(f"how to cancel {key} subscription", max_results=5)
    except Exception:
        # Not cached: a provider outage shouldn't mean "no page" for good.
        logger.exception("cancel-page search failed for %s", key)
        return None
    best = next(
        (r for r in results if r.url.startswith("https://") and not any(h in r.url for h in _NOT_A_CANCEL_PAGE)),
        None,
    )
    row = MerchantCancelLink(merchant_key=key, url=best.url if best else None, title=(best.title or urlparse(best.url).netloc)[:200] if best else None)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        row = db.query(MerchantCancelLink).filter(MerchantCancelLink.merchant_key == key).one()
    return row


def _dollars(amount: float) -> str:
    return f"${abs(amount):,.2f}"


def _day(d: date | str) -> str:
    d = date.fromisoformat(d) if isinstance(d, str) else d
    return f"{d:%B} {d.day}, {d.year}"


def cancellation_email(merchant: str, amount: float | None = None, next_date: date | str | None = None) -> dict:
    """A request to cancel, for a merchant with no self-serve page or one the user would rather write to."""
    lines = [
        "Hello,",
        "",
        f"Please cancel my {merchant} subscription, effective immediately, and stop all future charges to my card.",
    ]
    if amount is not None and next_date is not None:
        lines.append(f"My next charge of {_dollars(amount)} is due on {_day(next_date)}; please make sure it doesn't go through.")
    lines += [
        "",
        "Please reply to confirm the cancellation and the date it takes effect.",
        "",
        "Thank you,",
        "[Your name]",
        "[The email or account number on the subscription]",
    ]
    return {"kind": "cancellation", "subject": f"Cancel my {merchant} subscription", "body": "\n".join(lines)}


def refund_email(merchant: str, charges: list[dict], reason: str) -> dict:
    """A refund request for one or more charges ({"amount", "date"}). `reason`
    is "duplicate" (charged twice), "price_change" (an increase the user
    wasn't told about) or "unrecognized"."""
    listed = [f"- {_dollars(c['amount'])} on {_day(c['date'])}" for c in charges]
    if reason == "duplicate":
        ask = "I was charged twice for the same purchase:"
        want = f"Please refund the duplicate charge of {_dollars(charges[-1]['amount'])}."
    elif reason == "price_change":
        ask = "My subscription went up in price without notice I could find:"
        want = "Please refund the difference, or let me know when and how the change was announced."
    else:
        ask = "I don't recognize this charge on my card:"
        want = "Please tell me what it was for, or refund it if it was made in error."
    lines = ["Hello,", "", ask, *listed, "", want, "", "Thank you,", "[Your name]", "[The email or account number you have on file]"]
    return {"kind": "refund", "subject": f"Refund request: {merchant} charge", "body": "\n".join(lines)}
