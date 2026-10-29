"""Entry model: one ledger record, stored as TOML frontmatter + markdown body."""
from dataclasses import dataclass, field
from datetime import date
import tomllib

DELIM = "+++"

KINDS = {"project", "commitment", "thread", "recurring"}
AREAS = {"software", "money", "home", "family", "faith", "health"}
STATES = {"active", "waiting", "idling", "seasonal", "dead", "done"}


class EntryParseError(Exception):
    """A ledger file could not be read. Carries the entry id."""


@dataclass
class Entry:
    id: str
    name: str
    kind: str
    area: str
    last_touched: date
    state: str = "active"
    next_action: str | None = None
    cadence_days: int = 7
    repo: str | None = None
    due: date | None = None
    wake: str | None = None
    waiting_on: str | None = None
    waiting_since: date | None = None
    links: list[str] = field(default_factory=list)
    body: str = ""
    repo_is_git: bool = True  # runtime only; set by gitscan, never serialized

    def to_text(self) -> str:
        lines = [DELIM]
        lines.append(f"name = {_toml(self.name)}")
        lines.append(f"kind = {_toml(self.kind)}")
        lines.append(f"area = {_toml(self.area)}")
        lines.append(f"state = {_toml(self.state)}")
        if self.next_action is not None:
            lines.append(f"next = {_toml(self.next_action)}")
        lines.append(f"cadence_days = {self.cadence_days}")
        lines.append(f"last_touched = {self.last_touched.isoformat()}")
        for key in ("repo", "wake", "waiting_on"):
            value = getattr(self, key)
            if value is not None:
                lines.append(f"{key} = {_toml(value)}")
        for key in ("due", "waiting_since"):
            value = getattr(self, key)
            if value is not None:
                lines.append(f"{key} = {value.isoformat()}")
        if self.links:
            lines.append(f"links = {_toml(self.links)}")
        lines.append(DELIM)
        text = "\n".join(lines) + "\n"
        if self.body:
            text += "\n" + self.body.rstrip("\n") + "\n"
        return text


def _toml(value) -> str:
    r"""Serialize a str or list[str] as a TOML value. stdlib has no writer.

    Escapes all control characters per TOML v1.0 spec for basic strings:
    \, ", and control chars U+0000–U+001F and U+007F.
    """
    if isinstance(value, list):
        return "[" + ", ".join(_toml(v) for v in value) + "]"

    result = []
    for char in value:
        if char == '\\':
            result.append('\\\\')
        elif char == '"':
            result.append('\\"')
        elif char == '\b':
            result.append('\\b')
        elif char == '\t':
            result.append('\\t')
        elif char == '\n':
            result.append('\\n')
        elif char == '\f':
            result.append('\\f')
        elif char == '\r':
            result.append('\\r')
        else:
            code = ord(char)
            # Escape remaining control characters: U+0000–U+001F and U+007F
            if code <= 0x1F or code == 0x7F:
                result.append(f"\\u{code:04x}")
            else:
                result.append(char)

    escaped = "".join(result)
    return f'"{escaped}"'


def parse_entry(text: str, entry_id: str) -> Entry:
    lines = text.split("\n")
    if not lines or lines[0].strip() != DELIM:
        raise EntryParseError(f"{entry_id}: file does not start with {DELIM}")
    try:
        closing = lines.index(DELIM, 1)
    except ValueError:
        raise EntryParseError(f"{entry_id}: no closing {DELIM}") from None

    try:
        meta = tomllib.loads("\n".join(lines[1:closing]))
    except tomllib.TOMLDecodeError as exc:
        raise EntryParseError(f"{entry_id}: bad TOML — {exc}") from None

    for key, allowed in (("kind", KINDS), ("area", AREAS), ("state", STATES)):
        value = meta.get(key)
        if value is not None and value not in allowed:
            raise EntryParseError(
                f"{entry_id}: {key} must be one of {sorted(allowed)}, got {value!r}"
            )

    for required in ("name", "kind", "area", "last_touched"):
        if required not in meta:
            raise EntryParseError(f"{entry_id}: missing required field {required!r}")

    return Entry(
        id=entry_id,
        name=meta["name"],
        kind=meta["kind"],
        area=meta["area"],
        last_touched=meta["last_touched"],
        state=meta.get("state", "active"),
        next_action=meta.get("next"),
        cadence_days=meta.get("cadence_days", 7),
        repo=meta.get("repo"),
        due=meta.get("due"),
        wake=meta.get("wake"),
        waiting_on=meta.get("waiting_on"),
        waiting_since=meta.get("waiting_since"),
        links=meta.get("links", []),
        body="\n".join(lines[closing + 1 :]).strip("\n"),
    )
