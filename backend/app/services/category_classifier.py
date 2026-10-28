"""Second opinion on Plaid categories Plaid itself isn't sure of.

Plaid tags every transaction with a confidence_level. VERY_HIGH/HIGH rows
are usually a known merchant and its category is fine. LOW/UNKNOWN rows are
a guess from the merchant's name alone -- "Moongoat Greenhouse", a coffee
shop, came back as HOME_IMPROVEMENT_OTHER_HOME_IMPROVEMENT, LOW. Those rows,
and only those, get a second opinion, once per merchant:

1. Search the web for the merchant (Parallel through OpenRouter's web
   plugin). The query is the bank's own text in quotes, plus the city only
   when Plaid returned one, plus "yelp" for in-store purchases -- never a
   guessed city, and never yelp for an online one (an app's web address).
2. Ask Jev (TypeSafe AI's typed decision model) whether the results describe
   this same business, not another one sharing part of its name. If not,
   retry once with a looser query; if that fails too, drop the results.
3. Ask Jev to pick one of Bankr's spending categories, each with a short
   description, from the merchant's profile (bank text, visits, amounts,
   channel, place, card terminal) and whatever results survived step 2.
   The answer is one of our labels or an error, never prose to parse.

Answers are cached per merchant in MerchantCategoryGuess, with Jev's
confidence; only answers at or above settings.jev_min_confidence replace
Plaid's category. Precedence on a transaction, highest first: the user's own
pick (category_overridden), the user's rules, a trusted cached guess here,
Plaid's mapping. Income and transfers are never a choice: those stay with
the sign and account-type logic in category_mapper.py, and a merchant
category_mapper already knows (Software) is never asked about.

Built and tuned on an eval of 41 real low-confidence merchants
(backend/tests/evals/category_jev_*.csv): 30/30 labeled right, against
Plaid's 25. Small sample, the same one it was tuned on, and run against
the choices from before groups were split into "Other ..." subcategories.
"""

import logging
import re
import statistics
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Protocol

import httpx
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Category, MerchantCategoryGuess, Transaction
from app.db.seed_categories import DEFAULT_CATEGORIES
from app.integrations.bank_aggregator import AggregatorTransaction
from app.integrations.web_search import OpenRouterSearchClient, WebSearchClient
from app.services.category_mapper import merchant_category

logger = logging.getLogger(__name__)

LOW_CONFIDENCE = {"LOW", "UNKNOWN"}
DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"

# Expense categories a merchant's name can't tell you about: a loan payment
# is recognized from Plaid's LOAN_PAYMENTS_* tags, not the payee's name, and
# cash or a Zelle to a person from Plaid's TRANSFER_OUT_* ones. Naming the
# group excludes its subcategories too. Rows Plaid put in one of these are
# never sent either: there's no merchant to look up.
_NOT_CHOICES = {"Loan Payments", "Cash & ATM", "Payments to People"}
_NEVER_ASKED = {name for name, _, parent in DEFAULT_CATEGORIES if {name, parent} & _NOT_CHOICES}

# What each choice means, so Jev isn't matching bare labels. Kept generic on
# purpose: naming the eval's own merchants here would only flatter the eval.
# Groups aren't choices (see category_choices), so they have no entry.
CATEGORY_DESCRIPTIONS = {
    "Bank Fees": "Bank and card fees: overdraft, late, ATM, foreign transaction and annual fees.",
    "Entertainment": "Movies, concerts, live events, theaters, museums, sporting events, video games and music.",
    "Groceries": "Supermarkets and grocery stores, specialty and international markets, butchers, produce.",
    "Restaurants": "Eating out: restaurants, fast food, food trucks, bakeries, desserts, food delivery.",
    "Coffee": "Cafes, coffee and tea shops, boba.",
    "Alcohol & Bars": "Bars, pubs, breweries, wineries and liquor stores.",
    "Other Food & Drink": "Food and drink that fits no other choice, such as vending machines.",
    "Clothing": "Clothing, shoes and accessories stores.",
    "Electronics": "Electronics and computer stores.",
    "Online Marketplaces": "Online marketplaces selling many kinds of goods, such as Amazon, eBay and Etsy.",
    "Superstores": "Big-box stores selling groceries and general goods together, such as Target, Walmart, Costco.",
    "Pets": "Pet stores and supplies, veterinarians, grooming and boarding.",
    "Other Shopping": "Other retail: department, discount, convenience, thrift, gift, book and sporting goods stores.",
    "Home Improvement": "Hardware and garden stores, furniture and home furnishings, home repair and maintenance.",
    "Medical": "Doctors, dentists, eye care, hospitals, pharmacies, therapy and other healthcare for people.",
    "Personal Care": "Gyms and fitness, hair and beauty, spas, laundry and dry cleaning.",
    "Insurance": "Insurance premiums: car, home, renters, life and health insurance.",
    "Childcare": "Daycare, babysitting, nannies and after-school care.",
    "Education": "Tuition, schools, classes, tutoring and courses.",
    "Software": (
        "Apps, software and online services: SaaS, cloud storage, developer and productivity tools, "
        "whether billed monthly, yearly or once."
    ),
    "Other Services": "Other paid services: legal, accounting, postage and shipping, storage, cleaning.",
    "Taxes": "Tax payments to federal, state or local tax agencies.",
    "Donations": "Donations to charities, churches and non-profits.",
    "Government Fees": "Government agencies and fees: DMV, passports, permits, courts.",
    "Gas": "Fuel at gas stations.",
    "Car Maintenance": "Car repairs, oil changes, tires, car washes and auto parts.",
    "Rideshare & Taxis": "Uber, Lyft, taxis.",
    "Public Transit": "Buses, subways, trains and ferries.",
    "Parking & Tolls": "Parking lots, garages, meters and road tolls.",
    "Other Transportation": "Getting around in other ways, such as bike and scooter rentals.",
    "Travel": "Flights, hotels and lodging, rental cars, travel bookings.",
    "Rent": "Rent and property management payments.",
    "Utilities": "Electricity, gas, water, trash, sewer, internet, cable and phone bills.",
}

_SAME_BUSINESS_MIN = 0.4  # wrong-business results scored <= 0.10 in the eval, right ones 0.43+
_SAME_BUSINESS = (
    "Do these web search results clearly describe the same business as this bank transaction, so they can be "
    "trusted to say what kind of business it is? Different businesses that share part of a name do not count."
)
_PICK_CATEGORY = "Which spending category does this merchant belong to? Judge by what this business most likely is."

# Card-terminal prefixes ("SQ *", "TST*", "PAR*"), store numbers, dates and
# trailing state codes: noise to a search engine.
_PREFIX = re.compile(r"^[A-Z0-9]{2,6}\s?\*\s?", re.I)
_NOISE = re.compile(r"#\s*\d+|\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b|\b\d{3,}\b|PPD ID:.*", re.I)
_STATE_SUFFIX = re.compile(r"\s+-\s+[A-Z]{2}$")
_ONLINE = re.compile(r"\.(com|net|org|io|md|app|co|ai|tv)\b|\bwww\.|paypal|apple\.com/bill|\bamzn\b", re.I)


@dataclass(frozen=True)
class MerchantProfile:
    """Everything Jev and the search see about one merchant, summed up over
    the transactions at hand. No user, account or date: just the merchant."""

    merchant_key: str
    merchant_name: str
    bank_description: str | None
    channel: str | None
    city: str | None
    region: str | None
    payment_processor: str | None
    amounts: tuple[float, ...]  # money out, as positive numbers

    @property
    def place(self) -> str | None:
        return " ".join(p for p in (self.city, self.region) if p) or None

    @property
    def online(self) -> bool:
        return self.channel == "online" or bool(_ONLINE.search(self.bank_description or self.merchant_name))

    def search_queries(self) -> list[tuple[str, str]]:
        """(query, Parallel mode) to try in order: a tight keyword query
        first, then a looser one."""
        text = clean_bank_text(self.bank_description) or self.merchant_name
        if self.online:
            return [(f'"{text}"', "fast"), (self.merchant_name, "basic")]
        first = " ".join(p for p in (f'"{text}"', self.place, "yelp") if p)
        return [(first, "fast"), (" ".join(p for p in (self.merchant_name, self.place) if p), "basic")]

    def state(self) -> dict:
        state = {
            "merchant": self.merchant_name,
            "bank_description": self.bank_description,
            "visits": len(self.amounts),
            "median_amount_usd": round(statistics.median(self.amounts), 2) if self.amounts else None,
            "amount_range_usd": [min(self.amounts), max(self.amounts)] if self.amounts else None,
            "channel": self.channel,
        }
        if self.place:
            state["location"] = self.place
        if self.payment_processor:
            state["payment_processor"] = self.payment_processor
        return state


def build_profile(key: str, txns: list[AggregatorTransaction]) -> MerchantProfile:
    def most_common(values):
        values = [v for v in values if v]
        return Counter(values).most_common(1)[0][0] if values else None

    return MerchantProfile(
        merchant_key=key,
        merchant_name=most_common(t.merchant_name for t in txns) or key,
        bank_description=most_common(t.original_description for t in txns),
        channel=most_common(t.payment_channel for t in txns),
        city=most_common(t.location_city for t in txns),
        region=most_common(t.location_region for t in txns),
        payment_processor=most_common(t.payment_processor for t in txns),
        amounts=tuple(round(-t.amount, 2) for t in txns if t.amount < 0),
    )


def clean_bank_text(text: str | None) -> str | None:
    if not text:
        return None
    text = _STATE_SUFFIX.sub("", _NOISE.sub("", _PREFIX.sub("", text.strip())))
    return " ".join(text.split()) or None


@dataclass(frozen=True)
class CategoryAnswer:
    label: str  # one of the choice labels, e.g. "Food & Drink > Coffee"
    confidence: float | None


class CategoryClassifier(Protocol):
    model: str

    def classify(self, profile: MerchantProfile, choices: dict[str, str]) -> CategoryAnswer:
        """`choices` is label -> description. Return one of the labels.
        Raise on any failure."""
        ...


def merchant_key(name: str | None) -> str | None:
    if not name:
        return None
    return re.sub(r"\s+", " ", name).strip().lower() or None


def category_choices(categories: dict[str, Category]) -> dict[str, str]:
    """Choice label -> category name. Subcategories carry their parent
    ("Food & Drink > Coffee") so the model sees the hierarchy. A group is
    never a choice: its "Other ..." subcategory is there for when no other
    one fits."""
    by_id = {c.id: c for c in categories.values()}
    groups = {c.parent_category_id for c in categories.values() if c.parent_category_id}
    choices = {}
    for name, category in categories.items():
        parent = by_id.get(category.parent_category_id)
        if category.type != "expense" or category.id in groups or {name, parent and parent.name} & _NOT_CHOICES:
            continue
        choices[f"{parent.name} > {name}" if parent else name] = name
    return choices


def needs_second_opinion(txn: Transaction, mapped: Category) -> bool:
    return (
        (txn.aggregator_category_confidence or "").upper() in LOW_CONFIDENCE
        and mapped.type == "expense"
        and mapped.name not in _NEVER_ASKED
        and float(txn.amount) < 0
        and not txn.category_overridden
        and not txn.is_split
        and txn.split_parent_id is None
        and merchant_key(txn.original_merchant_name) is not None
        and merchant_category(txn.original_merchant_name) is None  # already known, e.g. Software
    )


def trusted(guess: MerchantCategoryGuess) -> bool:
    """Whether a cached guess may replace Plaid's category. A guess from
    before confidences were stored has none, and is trusted as it was."""
    return guess.confidence is None or guess.confidence >= settings.jev_min_confidence


def cached_guesses(db: Session, keys: set[str]) -> dict[str, MerchantCategoryGuess]:
    if not keys:
        return {}
    rows = db.query(MerchantCategoryGuess).filter(MerchantCategoryGuess.merchant_key.in_(keys))
    return {row.merchant_key: row for row in rows}


class JevCategoryClassifier:
    """Jev through OpenRouter's Decisions API, over plain httpx: TypeSafe's
    own SDK needs a newer pydantic than the mcp package works with. About
    $0.001-0.006 per merchant, nearly all of it the search."""

    def __init__(
        self,
        api_key: str,
        model: str,
        http: httpx.Client | None = None,
        searches: dict[str, WebSearchClient] | None = None,
    ):
        self.model = model
        self._http = http or httpx.Client(
            timeout=15.0,
            headers={"Authorization": f"Bearer {api_key}", "X-Title": settings.openrouter_app_name},
        )
        self._searches = searches or {
            mode: OpenRouterSearchClient(
                api_key=api_key,
                model=settings.openrouter_model,
                app_name=settings.openrouter_app_name,
                engine="parallel",
                mode=mode,
            )
            for mode in ("fast", "basic")
        }

    def _decide(self, state: dict, question: dict) -> dict:
        response = self._http.post(
            DECISIONS_URL, json={"model": self.model, "state": state, "questions": {"q": question}}
        )
        response.raise_for_status()
        return response.json()["answers"]["q"]

    def web_context(self, profile: MerchantProfile) -> str | None:
        """Search results Jev agrees describe this merchant, or None."""
        for query, mode in profile.search_queries():
            try:
                results = self._searches[mode].search(query, max_results=3)
            except httpx.HTTPError:
                logger.warning("merchant search failed for %r", query, exc_info=True)
                continue
            text = " | ".join(f"{r.title}: {r.snippet[:200]}" for r in results)[:700]
            if not text:
                continue
            transaction = {"merchant": profile.merchant_name, "bank_description": profile.bank_description}
            if profile.place:
                transaction["place"] = profile.place
            same = self._decide(
                {"bank_transaction": transaction, "web_search_results": text},
                {"type": "noul", "instructions": _SAME_BUSINESS},
            )
            if same.get("noul", 0) >= _SAME_BUSINESS_MIN:
                return text
        return None

    def classify(self, profile: MerchantProfile, choices: dict[str, str]) -> CategoryAnswer:
        state = profile.state()
        if context := self.web_context(profile):
            state["web_search_results"] = context
        answer = self._decide(state, {"type": "choice", "instructions": _PICK_CATEGORY, "criteria": choices})
        return CategoryAnswer(label=answer["choice"], confidence=answer.get("confidence"))


def get_classifier() -> CategoryClassifier | None:
    if not settings.jev_categorization_enabled or not settings.openrouter_api_key:
        return None
    return JevCategoryClassifier(settings.openrouter_api_key, settings.jev_model)


def classify_merchants(
    db: Session,
    pending: dict[str, tuple[MerchantProfile, list[Transaction]]],
    categories: dict[str, Category],
    classifier: CategoryClassifier,
    limit: int,
) -> int:
    """Ask `classifier` about each uncached merchant in `pending` (at most
    `limit`), cache the answer and recategorize that merchant's rows when
    the answer is confident enough. Failures are logged and leave Plaid's
    mapping in place. Returns the number of transactions recategorized."""
    labels = category_choices(categories)
    choices = {label: CATEGORY_DESCRIPTIONS.get(name) for label, name in labels.items()}
    batch = list(pending.items())[:limit]

    def ask(profile: MerchantProfile) -> CategoryAnswer | None:
        try:
            return classifier.classify(profile, choices)
        except Exception:
            logger.warning("category classifier failed for merchant %r", profile.merchant_name, exc_info=True)
            return None

    # The calls are network-bound and independent; the database writes below
    # stay on this thread, since a Session isn't thread-safe.
    with ThreadPoolExecutor(max_workers=8) as pool:
        answers = list(pool.map(ask, [profile for _, (profile, _) in batch]))

    changed = 0
    for (key, (_, txns)), answer in zip(batch, answers):
        if answer is None:
            continue
        name = labels.get(answer.label)
        if name is None:
            logger.warning("category classifier returned %r, not one of the choices", answer.label)
            continue
        category = categories[name]
        # Another sync may have cached this merchant meanwhile; first answer wins.
        db.execute(
            insert(MerchantCategoryGuess)
            .values(
                merchant_key=key,
                category_id=category.id,
                source="jev",
                model=classifier.model,
                confidence=answer.confidence,
            )
            .on_conflict_do_nothing(index_elements=["merchant_key"])
        )
        if answer.confidence is not None and answer.confidence < settings.jev_min_confidence:
            continue
        for txn in txns:
            txn.bankr_category_id = category.id
            changed += 1
    if len(pending) > limit:
        logger.info("category classifier: %d merchants left for a later sync", len(pending) - limit)
    db.flush()
    return changed
