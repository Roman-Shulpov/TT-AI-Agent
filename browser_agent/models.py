"""Tool arguments are small, strict models; the LLM never supplies executable code."""

import hashlib
import json
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

ShortText = Annotated[str, Field(min_length=1, max_length=1500)]
ElementId = Annotated[str, Field(pattern=r"^s\d+-e\d+$", max_length=32)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Navigate(StrictModel):
    url: Annotated[str, Field(min_length=1, max_length=2048)]

    @field_validator("url")
    @classmethod
    def web_url(cls, value: str) -> str:
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            raise ValueError("Only absolute http(s) URLs are allowed")
        if parts.username or parts.password or any(ord(c) < 32 for c in value):
            raise ValueError("Credentials and control characters are not allowed in URLs")
        return value


class Target(StrictModel):
    element_id: ElementId


class Click(Target):
    risk: Literal["read_only", "reversible", "sensitive", "unknown"]


class TypeText(Target):
    text: Annotated[str, Field(max_length=4000)]


class SelectOption(Target):
    value: Annotated[str, Field(max_length=500)]


class Scroll(StrictModel):
    direction: Literal["up", "down"]
    amount: Annotated[int, Field(ge=100, le=1500)]


class GoBack(StrictModel):
    pass


class Wait(StrictModel):
    milliseconds: Annotated[int, Field(ge=100, le=2000)]


class PressKey(Target):
    key: Literal["Enter", "Tab", "Escape", "ArrowDown", "ArrowUp", "Space"]
    risk: Literal["read_only", "reversible", "sensitive", "unknown"]


class SwitchTab(StrictModel):
    tab_id: Annotated[str, Field(pattern=r"^t\d+$", max_length=20)]


class AskUser(StrictModel):
    question: ShortText


class Finish(StrictModel):
    summary: ShortText
    evidence: ShortText


class RecordFact(StrictModel):
    quote: Annotated[str, Field(min_length=1, max_length=500)]


class Verification(StrictModel):
    complete: bool
    evidence: ShortText
    feedback: ShortText


TOOL_MODELS: dict[str, type[StrictModel]] = {
    "navigate": Navigate,
    "click": Click,
    "type_text": TypeText,
    "select_option": SelectOption,
    "scroll": Scroll,
    "go_back": GoBack,
    "wait": Wait,
    "press_key": PressKey,
    "switch_tab": SwitchTab,
    "ask_user": AskUser,
    "finish": Finish,
    "record_fact": RecordFact,
}


class Action(StrictModel):
    name: str
    arguments: StrictModel

    @classmethod
    def parse(cls, name: str, arguments_json: str) -> "Action":
        if name not in TOOL_MODELS:
            raise ValueError("Unknown tool name")
        return cls(name=name, arguments=TOOL_MODELS[name].model_validate_json(arguments_json))


class BrowserElement(BaseModel):
    id: str
    tag: str
    role: str = ""
    name: str = ""
    context: str = ""
    text: str = ""
    placeholder: str = ""
    type: str = ""
    value: str = ""
    checked: bool = False
    disabled: bool = False
    href: str = ""
    form_role: str = ""
    options: list[dict[str, str]] = Field(default_factory=list)
    frame: str = ""


class Observation(BaseModel):
    snapshot_id: str
    url: str
    title: str
    text: str
    elements: list[BrowserElement] = Field(default_factory=list)
    tabs: dict[str, str] = Field(default_factory=dict)
    scroll_y: int = 0
    warnings: list[str] = Field(default_factory=list)

    def fingerprint(self) -> str:
        # Snapshot IDs change each turn; exclude them from progress detection.
        data = [
            self.url,
            self.text,
            self.scroll_y,
            self.tabs,
            [e.model_dump(exclude={"id"}) for e in self.elements],
        ]
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:20]

    def element(self, element_id: str) -> BrowserElement | None:
        return next((e for e in self.elements if e.id == element_id), None)


class ToolResult(BaseModel):
    ok: bool
    message: str
    error: str | None = None


class RunResult(BaseModel):
    status: Literal["completed", "needs_input", "stopped"]
    summary: str
    steps: int
