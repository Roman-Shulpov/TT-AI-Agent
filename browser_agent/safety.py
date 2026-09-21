"""Human confirmation policy; heuristics are defense in depth, not a security sandbox."""

import re
from typing import Literal
from urllib.parse import urljoin, urlsplit

from .models import Action, Observation

SENSITIVE = re.compile(
    r"pay|purchase|place.?order|confirm.?order|send|submit|delete|remove|erase|unsubscribe|"
    r"transfer|publish|оплат|купить|подтверд|отправ|удал|перевести|опубликов",
    re.I,
)


def classify(
    action: Action, observation: Observation, mode: str = "conservative"
) -> tuple[Literal["allow", "confirm", "block"], str]:
    args = action.arguments.model_dump()
    element = observation.element(args.get("element_id", ""))
    if "element_id" in args and element is None:
        return "block", "Target is absent from current observation; re-observe"
    if element and element.value == "[redacted]":
        return "block", "Fill credentials manually in the browser, then continue"
    if action.name == "navigate":
        if SENSITIVE.search(args["url"]):
            return "confirm", "Navigation URL may trigger a sensitive operation"
        return "allow", "HTTP(S) navigation"
    if action.name in {"click", "press_key", "select_option"}:
        label = f"{element.name} {element.text} {element.href}"
        if args.get("risk") in {"sensitive", "unknown"} or SENSITIVE.search(label):
            return "confirm", "Potential submission, deletion or other sensitive action"
        if action.name == "press_key" and args["key"] in {"Tab", "Escape", "ArrowDown", "ArrowUp"}:
            return "allow", "Non-submitting keyboard navigation"
        if element.role in {"checkbox", "radio"}:
            return "allow", "Toggle a form choice"
        if element.role == "link" and element.href and action.name == "click":
            destination = urlsplit(urljoin(observation.url, element.href))
            if destination.scheme in {"http", "https"}:
                return "allow", "Ordinary web link"
            return "confirm", "Link uses a non-HTTP destination"
        if element.role == "searchbox" or element.form_role == "search":
            return "allow", "Search control"
        if mode == "conservative":
            return "confirm", "Effect of this control cannot be proven from DOM metadata"
    return "allow", "No sensitive effect identified by current policy"


def confirmation_text(action: Action, observation: Observation, reason: str) -> str:
    element = observation.element(getattr(action.arguments, "element_id", ""))
    target = element.name if element else getattr(action.arguments, "url", "")
    return (
        f"Подтвердить {action.name}: {target[:240]}?\n"
        f"Страница: {observation.url[:300]}\nПричина: {reason}\nВведите YES для одного действия: "
    )
