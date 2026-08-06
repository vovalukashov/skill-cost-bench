"""Cost computed from token counts, not taken from the agent's own report.

`total_cost_usd` in a session result is convenient and wrong to depend on. On a
subscription it can be zero or absent, because nothing was billed per token; the
work still happened and still had a price. A benchmark that reads that field
measures the billing arrangement of whoever ran it.

So the price is computed here, from the token counts the session does report,
against a dated table in the config. Two consequences worth the trouble: the
same run can be re-priced at different rates without re-running it, and a reader
who disagrees with the prices can recompute the whole report from the published
JSONL.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

PER_MILLION = 1_000_000


@dataclass(frozen=True)
class ModelPrice:
    """USD per million tokens."""

    input: float
    output: float
    cache_write_5m: float
    cache_write_1h: float
    cache_read: float

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ModelPrice":
        base_in = float(data["input"])
        return cls(
            input=base_in,
            output=float(data["output"]),
            # Published multipliers, used only when a rate is not given outright.
            cache_write_5m=float(data.get("cache_write_5m", base_in * 1.25)),
            cache_write_1h=float(data.get("cache_write_1h", base_in * 2.0)),
            cache_read=float(data.get("cache_read", base_in * 0.1)),
        )


def load_table(raw: Mapping[str, Any] | None) -> dict[str, ModelPrice]:
    table: dict[str, ModelPrice] = {}
    for key, value in (raw or {}).items():
        if key in ("source", "dated", "note"):
            continue
        if isinstance(value, Mapping) and "input" in value:
            table[str(key)] = ModelPrice.from_dict(value)
    return table


def _int(value: Any) -> int:
    return int(value) if isinstance(value, (int, float)) else 0


def split_cache_writes(usage: Mapping[str, Any]) -> tuple[int, int]:
    """Return (5-minute, 1-hour) cache-write tokens.

    The two TTLs are priced differently, and the session reports them separately
    under `cache_creation`. When only the total is present, all of it is charged
    at the cheaper 5-minute rate — an undercount is the safer way to be wrong
    about the arm that writes more cache.
    """
    detail = usage.get("cache_creation")
    if isinstance(detail, Mapping):
        five = _int(detail.get("ephemeral_5m_input_tokens"))
        hour = _int(detail.get("ephemeral_1h_input_tokens"))
        if five or hour:
            return five, hour
    return _int(usage.get("cache_creation_input_tokens")), 0


def price_usage(usage: Mapping[str, Any] | None, price: ModelPrice) -> float:
    if not usage:
        return 0.0
    five, hour = split_cache_writes(usage)
    total = (
        _int(usage.get("input_tokens")) * price.input
        + _int(usage.get("output_tokens")) * price.output
        + five * price.cache_write_5m
        + hour * price.cache_write_1h
        + _int(usage.get("cache_read_input_tokens")) * price.cache_read
    )
    return total / PER_MILLION


def price_run(usage: Mapping[str, Any] | None, model: str | None,
              table: Mapping[str, ModelPrice]) -> float | None:
    """Price one run, or None when the model has no entry in the table.

    None is deliberate: a silent zero would look like a free run and drag the
    arm's average down.
    """
    if not model or model not in table:
        return None
    return price_usage(usage, table[model])
