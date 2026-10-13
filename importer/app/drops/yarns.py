"""Reading the YARN section of a DROPS pattern."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_COMPONENT_RE = re.compile(
    r"^(?P<name>.+?)\s+from\s+Garnstudio(?:\s*\(belongs to yarn group\s+(?P<group>[A-F])\))?\s*$",
    re.IGNORECASE,
)
_COLOUR_LINE_RE = re.compile(
    r"^(?P<amounts>\d+(?:[.,]\d+)?(?:\s*[-–/]\s*\d+(?:[.,]\d+)?)*)\s*(?P<unit>g|m|skeins?|balls?)\s+"
    r"(?P<label>colou?r|shade)\s*:?\s*(?P<number>[^,]+?)(?:\s*,\s*(?P<cname>.+?))?\s*$",
    re.IGNORECASE,
)
_PLAIN_AMOUNT_RE = re.compile(
    r"^(?P<amounts>\d+(?:[.,]\d+)?(?:\s*[-–/]\s*\d+(?:[.,]\d+)?)*)\s*(?P<unit>g|m|skeins?|balls?)\b(?P<rest>.*)$",
    re.IGNORECASE,
)
_AND_RE = re.compile(r"^and\s+use\s*:?$", re.IGNORECASE)
_OR_RE = re.compile(r"^or\s+use\s*:?$", re.IGNORECASE)


@dataclass
class YarnColour:
    number: str
    name: str = ""
    amounts: list[float] = field(default_factory=list)
    unit: str = "g"

    @property
    def label(self) -> str:
        return f"{self.number} {self.name}".strip()


@dataclass
class YarnComponent:
    name: str
    group: str = ""
    colours: list[YarnColour] = field(default_factory=list)

    @property
    def slug(self) -> str:
        return slugify_yarn(self.name)


@dataclass
class YarnOption:
    components: list[YarnComponent] = field(default_factory=list)


def tidy_yarn_name(raw: str) -> str:
    """DROPS ALPACA -> DROPS Alpaca, DROPS KID-SILK -> DROPS Kid-Silk."""
    words = []
    for word in raw.strip().split():
        if word.upper() == "DROPS":
            words.append("DROPS")
        else:
            words.append("-".join(part.capitalize() for part in word.split("-")))
    return " ".join(words)


def slugify_yarn(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _numbers(text: str) -> list[float]:
    values = []
    for part in re.split(r"\s*[-–/]\s*", text.strip()):
        try:
            values.append(float(part.replace(",", ".")))
        except ValueError:
            return []
    return values


def parse_yarn_section(lines: list[str]) -> tuple[list[YarnOption], list[str]]:
    """Return (options, warnings). Never raises: unreadable lines become warnings."""
    options: list[YarnOption] = []
    warnings: list[str] = []
    current_option: YarnOption | None = None
    current: YarnComponent | None = None

    def start_option() -> YarnOption:
        opt = YarnOption()
        options.append(opt)
        return opt

    for line in (ln.strip() for ln in lines):
        if not line:
            continue
        if _OR_RE.match(line):
            current_option = start_option()
            current = None
            continue
        if _AND_RE.match(line):
            current = None
            continue
        m = _COMPONENT_RE.match(line)
        if m:
            if current_option is None:
                current_option = start_option()
            current = YarnComponent(name=tidy_yarn_name(m.group("name")), group=(m.group("group") or "").upper())
            current_option.components.append(current)
            continue
        m = _COLOUR_LINE_RE.match(line)
        if m and current is not None:
            current.colours.append(
                YarnColour(
                    number=m.group("number").strip(),
                    name=(m.group("cname") or "").strip(),
                    amounts=_numbers(m.group("amounts")),
                    unit=m.group("unit").lower(),
                )
            )
            continue
        m = _PLAIN_AMOUNT_RE.match(line)
        if m and current is not None:
            current.colours.append(
                YarnColour(number="", name=m.group("rest").strip(" ,:"), amounts=_numbers(m.group("amounts")), unit=m.group("unit").lower())
            )
            continue
        warnings.append(f"Could not read this yarn line: {line}")
    return options, warnings
