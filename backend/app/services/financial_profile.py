"""Onboarding answers → financial_profile.md, which every chat turn reads first."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.models import User

OCCUPATIONS = {
    "salaried": "Salaried",
    "contractor": "Contractor — income varies",
    "student": "Student / part-time",
}

KNOWLEDGE = {
    "nothing": (
        "Nothing",
        "I'm starting from scratch. Keep it plain and explain the why.",
    ),
    "somewhat": (
        "Somewhat",
        "I know the basics — budgets, emergency funds, paying down debt. Fill in the gaps.",
    ),
    "expert": (
        "Expert",
        "I already speak this language. Skip the intro course; be direct.",
    ),
}

LIFESTYLES = {
    "strict": (
        "Strict",
        "FIRE, high savings rate, invest first. Cut the fat.",
    ),
    "balanced": (
        "Balanced",
        "Save with a plan, still live a little.",
    ),
    "ball": (
        "Let's Ball Out",
        "I want sick experiences. Don't lecture me out of the trip.",
    ),
}

HOUSING = {
    "rent": "Rent",
    "mortgage": "Mortgage",
    "none": "Neither",
}

MAX_STORY_CHARS = 4000
MAX_LIST = 20


class ProfileError(ValueError):
    pass


def _money(amount: float) -> str:
    if abs(amount - round(amount)) < 0.005:
        return f"${amount:,.0f}"
    return f"${amount:,.2f}"


def render_markdown(payload: dict) -> str:
    path = payload.get("path")
    lines = ["# financial_profile.md", ""]
    if path == "story":
        story = (payload.get("story") or "").strip()
        lines += ["Path: story", "", "## In their words", story]
        return "\n".join(lines).rstrip() + "\n"

    answers = payload.get("answers") or {}
    occ = OCCUPATIONS.get(answers.get("occupation", ""), answers.get("occupation", ""))
    know_label, know_blurb = KNOWLEDGE.get(answers.get("knowledge", ""), ("", ""))
    life_label, life_blurb = LIFESTYLES.get(answers.get("lifestyle", ""), ("", ""))
    lines += [
        "Path: questions",
        "",
        "## About",
        f"- Age: {answers.get('age')}",
        f"- Occupation: {occ}",
        f"- Typical monthly income: {_money(float(answers.get('monthly_income') or 0))}",
        f"- Cash on hand: {_money(float(answers.get('cash') or 0))}",
        f"- Emergency fund: {_money(float(answers.get('emergency_fund') or 0))}",
        _housing_line(answers),
        "",
        "## Debts",
    ]
    debts = answers.get("debts") or []
    if not debts:
        lines.append("- None listed")
    else:
        for d in debts:
            lines.append(
                f"- {d['name']}: still owed {_money(float(d['owed']))}, paid off {_money(float(d['paid_off']))}"
            )
    lines += ["", "## Investments"]
    inv = answers.get("investments") or []
    if not inv:
        lines.append("- None listed")
    else:
        for i in inv:
            lines.append(f"- {i['name']}: {_money(float(i['amount']))}")
    lines += ["", "## Goals"]
    goals = answers.get("goals") or []
    if not goals:
        lines.append("- None listed yet")
    else:
        for g in goals:
            target = g.get("target")
            saved = g.get("saved")
            if target and saved:
                lines.append(f"- {g['name']}: {_money(float(saved))} of {_money(float(target))}")
            elif target:
                lines.append(f"- {g['name']} ({_money(float(target))})")
            elif saved:
                lines.append(f"- {g['name']}: {_money(float(saved))} in so far")
            else:
                lines.append(f"- {g['name']}")
    lines += [
        "",
        "## Knowledge",
        f"{know_label} — {know_blurb}" if know_label else "",
        "",
        "## Lifestyle",
        f"{life_label} — {life_blurb}" if life_label else "",
    ]
    return "\n".join(line for line in lines if line is not None).rstrip() + "\n"


def _housing_line(answers: dict) -> str:
    kind = answers.get("housing") or "none"
    label = HOUSING.get(kind, "Neither")
    pay = float(answers.get("housing_payment") or 0)
    if kind in ("rent", "mortgage") and pay > 0:
        return f"- Housing: {label} {_money(pay)} / month"
    return f"- Housing: {label}"


def _clean_name(raw: str, label: str) -> str:
    name = (raw or "").strip()[:80]
    if not name:
        raise ProfileError(f"{label} needs a name")
    return name


def save_profile(db: Session, user: User, path: str, story: str | None, answers: dict | None) -> User:
    if path == "story":
        text = (story or "").strip()
        if len(text) < 8:
            raise ProfileError("Write a bit more about what's going on")
        if len(text) > MAX_STORY_CHARS:
            raise ProfileError("That's a bit long — trim it down")
        payload = {"path": "story", "story": text[:MAX_STORY_CHARS]}
    elif path == "questions":
        if not answers:
            raise ProfileError("Answers are missing")
        payload = {"path": "questions", "answers": _normalize_answers(answers)}
    else:
        raise ProfileError("Pick questions or a story")
    user.financial_profile = payload
    user.financial_profile_md = render_markdown(payload)
    user.onboarding_completed_at = datetime.now(timezone.utc)
    db.add(user)
    return user


def _normalize_answers(answers: dict) -> dict:
    occ = answers.get("occupation")
    if occ not in OCCUPATIONS:
        raise ProfileError("Pick how you earn")
    knowledge = answers.get("knowledge")
    if knowledge not in KNOWLEDGE:
        raise ProfileError("Pick how much you know")
    lifestyle = answers.get("lifestyle")
    if lifestyle not in LIFESTYLES:
        raise ProfileError("Pick a lifestyle")
    try:
        age = int(answers["age"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ProfileError("Enter your age") from exc
    if age < 16 or age > 120:
        raise ProfileError("Age looks off")
    try:
        income = float(answers["monthly_income"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ProfileError("Enter what you usually make in a month") from exc
    if income <= 0 or income >= 1_000_000_000:
        raise ProfileError("Monthly income looks off")
    try:
        cash = float(answers.get("cash") or 0)
    except (TypeError, ValueError) as exc:
        raise ProfileError("Enter how much cash you have") from exc
    if cash < 0 or cash >= 1_000_000_000:
        raise ProfileError("Cash amount looks off")
    try:
        emergency_fund = float(answers.get("emergency_fund") or 0)
    except (TypeError, ValueError) as exc:
        raise ProfileError("Enter the emergency fund") from exc
    if emergency_fund < 0 or emergency_fund >= 1_000_000_000:
        raise ProfileError("Emergency fund looks off")

    housing = answers.get("housing") or "none"
    if housing not in HOUSING:
        raise ProfileError("Pick rent, mortgage, or neither")
    try:
        housing_payment = float(answers.get("housing_payment") or 0)
    except (TypeError, ValueError) as exc:
        raise ProfileError("Enter the monthly housing amount") from exc
    if housing_payment < 0 or housing_payment >= 1_000_000_000:
        raise ProfileError("Housing amount looks off")
    if housing == "none":
        housing_payment = 0

    debts = []
    for row in answers.get("debts") or []:
        owed = float(row.get("owed") or 0)
        paid = float(row.get("paid_off") or 0)
        if owed < 0 or paid < 0:
            raise ProfileError("Debt amounts can't be negative")
        debts.append({"name": _clean_name(row.get("name", ""), "Debt"), "owed": owed, "paid_off": paid})
        if len(debts) > MAX_LIST:
            raise ProfileError("That's too many debts")

    investments = []
    for row in answers.get("investments") or []:
        amount = float(row.get("amount") or 0)
        if amount < 0:
            raise ProfileError("Investment amounts can't be negative")
        investments.append({"name": _clean_name(row.get("name", ""), "Investment"), "amount": amount})
        if len(investments) > MAX_LIST:
            raise ProfileError("That's too many investments")

    goals = []
    for row in answers.get("goals") or []:
        target = row.get("target")
        goal = {"name": _clean_name(row.get("name", ""), "Goal")}
        if target is not None and str(target).strip() != "":
            value = float(target)
            if value < 0:
                raise ProfileError("Goal targets can't be negative")
            goal["target"] = value
        saved = row.get("saved")
        if saved is not None and str(saved).strip() != "":
            put = float(saved)
            if put < 0:
                raise ProfileError("Goal progress can't be negative")
            goal["saved"] = put
        goals.append(goal)
        if len(goals) > MAX_LIST:
            raise ProfileError("That's too many goals")

    return {
        "age": age,
        "occupation": occ,
        "monthly_income": income,
        "cash": cash,
        "emergency_fund": emergency_fund,
        "housing": housing,
        "housing_payment": housing_payment,
        "debts": debts,
        "investments": investments,
        "goals": goals,
        "knowledge": knowledge,
        "lifestyle": lifestyle,
    }
