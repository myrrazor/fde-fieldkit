"""Speed up Faker draws without changing seeded results.

Faker rebuilds a weighted-choice table on every draw, and ``numerify`` walks
placeholders with a regex substitution per character class. Both burn the same
RNG calls in the same order when done directly, so ``seed_instance`` output
stays identical. Installed on the provider class because ``company()`` and
``name()`` call back into it internally.
"""

from __future__ import annotations

import string
from collections import OrderedDict
from collections.abc import Sequence
from typing import Any

_installed = False
_original_random_elements: Any = None
_weight_cache: dict[int, tuple[tuple[Any, ...], list[float]]] = {}
_key_cache: dict[int, tuple[Any, ...]] = {}


def install_fast_faker() -> None:
    """Patch Faker's hot helpers once per process."""

    global _installed, _original_random_elements
    if _installed:
        return
    from faker.providers import BaseProvider

    _original_random_elements = BaseProvider.random_elements
    BaseProvider.random_elements = _random_elements  # type: ignore[method-assign]
    BaseProvider.numerify = _numerify  # type: ignore[method-assign]
    BaseProvider.lexify = _lexify  # type: ignore[method-assign]
    _installed = True


def _random_elements(
    self: Any,
    elements: Any = ("a", "b", "c"),
    length: int | None = None,
    unique: bool = False,
    use_weighting: bool | None = None,
) -> Sequence[Any]:
    use_weighting = self.__use_weighting__ if use_weighting is None else use_weighting
    if isinstance(elements, dict) and not isinstance(elements, OrderedDict):
        raise ValueError("Use OrderedDict only to avoid dependency on PYTHONHASHSEED (See #363).")
    if length is None:
        length = self.generator.random.randint(1, len(elements))
    if unique and length > len(elements):
        raise ValueError(
            "Sample length cannot be longer than the number of unique elements to pick from."
        )

    # Weighted sampling without replacement is rare and has its own algorithm.
    if isinstance(elements, dict) and unique and use_weighting:
        return _original_random_elements(self, elements, length, unique, use_weighting)

    if isinstance(elements, dict):
        if use_weighting:
            keys, cumulative = _cumulative(elements)
            return self.generator.random.choices(keys, cum_weights=cumulative, k=length)
        keys = _keys(elements)
        if unique:
            return self.generator.random.sample(keys, length)
        if length == 1:
            return [self.generator.random.choice(keys)]
        return self.generator.random.choices(keys, k=length)

    if unique:
        return self.generator.random.sample(elements, length)
    choices = elements if isinstance(elements, (tuple, str)) else tuple(elements)
    if length == 1:
        return [self.generator.random.choice(choices)]
    return self.generator.random.choices(choices, k=length)


def _cumulative(elements: dict[Any, Any]) -> tuple[tuple[Any, ...], list[float]]:
    cached = _weight_cache.get(id(elements))
    if cached is None:
        keys = tuple(elements)
        total = 0.0
        cumulative: list[float] = []
        for weight in elements.values():
            total += float(weight)
            cumulative.append(total)
        cached = (keys, cumulative)
        _weight_cache[id(elements)] = cached
    return cached


def _keys(elements: dict[Any, Any]) -> tuple[Any, ...]:
    cached = _key_cache.get(id(elements))
    if cached is None:
        cached = tuple(elements)
        _key_cache[id(elements)] = cached
    return cached


def _numerify(self: Any, text: str = "###") -> str:
    rand = self.generator.random
    if "#" in text:
        text = "".join(str(rand.randint(0, 9)) if char == "#" else char for char in text)
    if "%" in text:
        text = "".join(str(rand.randint(1, 9)) if char == "%" else char for char in text)
    if "$" in text:
        text = "".join(str(rand.randint(2, 9)) if char == "$" else char for char in text)
    if "!" in text:
        text = "".join(
            (str(rand.randint(0, 9)) if rand.randint(0, 1) else "") if char == "!" else char
            for char in text
        )
    if "@" in text:
        text = "".join(
            (str(rand.randint(1, 9)) if rand.randint(0, 1) else "") if char == "@" else char
            for char in text
        )
    return text


def _lexify(self: Any, text: str = "????", letters: str = string.ascii_letters) -> str:
    if "?" not in text:
        return text
    rand = self.generator.random
    return "".join(rand.choice(letters) if char == "?" else char for char in text)
