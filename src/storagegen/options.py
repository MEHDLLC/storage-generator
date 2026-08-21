"""A tiny declarative option system shared by every generator.

Each generator declares its options once.  That single declaration drives
CLI parsing, validation, the manifest written next to the models, and the
"Options used" table in the listing, so those four can never drift apart.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence


class OptionError(ValueError):
    """Raised when a supplied option value cannot be used."""


@dataclass(frozen=True)
class Option:
    name: str
    default: Any
    help: str
    kind: str = "float"          # float | int | bool | choice | str
    choices: tuple[str, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    unit: str = ""
    group: str = "General"
    listed: bool = True          # show in the listing's options table

    @property
    def flag(self) -> str:
        return "--" + self.name.replace("_", "-")

    def coerce(self, value: Any) -> Any:
        if self.kind == "bool":
            return _as_bool(self.name, value)
        if self.kind == "int":
            return int(_as_number(self.name, value))
        if self.kind == "float":
            return float(_as_number(self.name, value))
        if self.kind == "choice":
            text = str(value)
            if text not in self.choices:
                raise OptionError(
                    f"{self.name}: {text!r} is not one of "
                    + ", ".join(self.choices)
                )
            return text
        return str(value)

    def check_range(self, value: Any) -> None:
        if self.kind not in ("int", "float"):
            return
        if self.minimum is not None and value < self.minimum:
            raise OptionError(
                f"{self.name}: {value:g}{self.unit} is below the minimum "
                f"{self.minimum:g}{self.unit}"
            )
        if self.maximum is not None and value > self.maximum:
            raise OptionError(
                f"{self.name}: {value:g}{self.unit} is above the maximum "
                f"{self.maximum:g}{self.unit}"
            )

    def describe_default(self) -> str:
        if self.default is None:
            return "from preset"
        if self.kind == "bool":
            return "yes" if self.default else "no"
        if self.kind in ("int", "float"):
            return f"{self.default:g}{self.unit}"
        return str(self.default)


class OptionSet:
    """An ordered collection of `Option`s."""

    def __init__(self, options: Iterable[Option]):
        self._options: tuple[Option, ...] = tuple(options)
        seen: set[str] = set()
        for option in self._options:
            if option.name in seen:
                raise ValueError(f"duplicate option {option.name!r}")
            seen.add(option.name)

    def __iter__(self):
        return iter(self._options)

    def __len__(self):
        return len(self._options)

    def __contains__(self, name: str) -> bool:
        return any(o.name == name for o in self._options)

    def get(self, name: str) -> Option:
        for option in self._options:
            if option.name == name:
                return option
        raise KeyError(name)

    def defaults(self) -> dict[str, Any]:
        return {o.name: o.default for o in self._options}

    def groups(self) -> dict[str, list[Option]]:
        grouped: dict[str, list[Option]] = {}
        for option in self._options:
            grouped.setdefault(option.group, []).append(option)
        return grouped

    def resolve(self, supplied: dict[str, Any] | None = None) -> dict[str, Any]:
        """Merge supplied values over the defaults, coercing and range-checking."""
        supplied = dict(supplied or {})
        unknown = sorted(set(supplied) - {o.name for o in self._options})
        if unknown:
            raise OptionError(
                "unknown option(s): "
                + ", ".join(unknown)
                + ". Run `storagegen options <generator>` to see what's available."
            )
        resolved: dict[str, Any] = {}
        for option in self._options:
            value = supplied.get(option.name, option.default)
            if value is None:
                resolved[option.name] = None
                continue
            value = option.coerce(value)
            option.check_range(value)
            resolved[option.name] = value
        return resolved

    def add_to_parser(self, parser: argparse.ArgumentParser) -> None:
        for group_name, options in self.groups().items():
            group = parser.add_argument_group(group_name)
            for option in options:
                self._add_one(group, option)

    @staticmethod
    def _add_one(group, option: Option) -> None:
        help_text = f"{option.help} (default: {option.describe_default()})"
        if option.kind == "bool":
            group.add_argument(
                option.flag,
                dest=option.name,
                nargs="?",
                const=True,
                default=argparse.SUPPRESS,
                type=lambda v: _as_bool(option.name, v),
                metavar="yes|no",
                help=help_text,
            )
            group.add_argument(
                "--no-" + option.name.replace("_", "-"),
                dest=option.name,
                action="store_const",
                const=False,
                default=argparse.SUPPRESS,
                help=argparse.SUPPRESS,
            )
            return
        kwargs: dict[str, Any] = {
            "dest": option.name,
            "default": argparse.SUPPRESS,
            "help": help_text,
        }
        if option.kind == "choice":
            kwargs["choices"] = list(option.choices)
            kwargs["metavar"] = "{" + ",".join(option.choices) + "}"
        elif option.kind == "int":
            kwargs["type"] = int
            kwargs["metavar"] = "N"
        elif option.kind == "float":
            kwargs["type"] = float
            kwargs["metavar"] = option.unit.strip() or "X"
        else:
            kwargs["metavar"] = "TEXT"
        group.add_argument(option.flag, **kwargs)


@dataclass
class Report:
    """Validation feedback that is not fatal, plus notes worth surfacing."""

    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)

    def note(self, message: str) -> None:
        if message not in self.notes:
            self.notes.append(message)


def _as_bool(name: str, value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "y", "on"):
        return True
    if text in ("0", "false", "no", "n", "off"):
        return False
    raise OptionError(f"{name}: expected yes/no, got {value!r}")


def _as_number(name: str, value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise OptionError(f"{name}: expected a number, got {value!r}") from exc


def merge_sequence(pairs: Sequence[str]) -> dict[str, str]:
    """Turn `name=value` strings (from `--set`) into a dict."""
    out: dict[str, str] = {}
    for pair in pairs:
        if "=" not in pair:
            raise OptionError(f"expected name=value, got {pair!r}")
        key, _, value = pair.partition("=")
        out[key.strip()] = value.strip()
    return out
