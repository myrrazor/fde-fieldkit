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
from itertools import accumulate
from typing import Any

_installed = False
_original_random_elements: Any = None
_CACHE_MAX = 128
# id() alone is not a stable key: a freed dict can be replaced by another at
# the same id. Holding the dict keeps that id reserved for this mapping.
_weight_cache: dict[int, tuple[Any, tuple[Any, ...], list[float]]] = {}
_key_cache: dict[int, tuple[Any, tuple[Any, ...]]] = {}


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
    from faker.providers.internet import Provider as InternetProvider
    from faker.providers.lorem import Provider as LoremProvider

    InternetProvider._random_ipv4_address_from_subnets = _ipv4_from_subnets  # type: ignore[method-assign]
    LoremProvider.get_words_list = _get_words_list  # type: ignore[method-assign]
    LoremProvider.word = _word  # type: ignore[method-assign]
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
        return self.generator.random.sample(_sequence(elements), length)
    choices = _sequence(elements)
    if length == 1:
        return [self.generator.random.choice(choices)]
    return self.generator.random.choices(choices, k=length)


def _sequence(elements: Any) -> Any:
    if isinstance(elements, (list, tuple, str)):
        return elements
    return tuple(elements)


def _cumulative(elements: dict[Any, Any]) -> tuple[tuple[Any, ...], list[float]]:
    ident = id(elements)
    cached = _weight_cache.get(ident)
    if cached is not None and cached[0] is elements:
        return cached[1], cached[2]
    keys = tuple(elements)
    cumulative = list(accumulate(float(weight) for weight in elements.values()))
    if ident in _weight_cache or len(_weight_cache) < _CACHE_MAX:
        _weight_cache[ident] = (elements, keys, cumulative)
    return keys, cumulative


def _keys(elements: dict[Any, Any]) -> tuple[Any, ...]:
    ident = id(elements)
    cached = _key_cache.get(ident)
    if cached is not None and cached[0] is elements:
        return cached[1]
    keys = tuple(elements)
    if ident in _key_cache or len(_key_cache) < _CACHE_MAX:
        _key_cache[ident] = (elements, keys)
    return keys


def _word(self: Any, part_of_speech: str | None = None, ext_word_list: Any = None) -> str:
    # Same draw as Faker's word(): one choice from the locale list, via _randbelow.
    return self.generator.random.choice(_get_words_list(self, part_of_speech, ext_word_list))


def _numerify(self: Any, text: str = "###") -> str:
    # Placeholder passes stay in Faker's order so the RNG stream does not move.
    if not any(char in text for char in "#%$!@"):
        return text
    chars = list(text)
    rand = self.generator.random.randint
    if "#" in text:
        for index, char in enumerate(chars):
            if char == "#":
                chars[index] = str(rand(0, 9))
    if "%" in text:
        for index, char in enumerate(chars):
            if char == "%":
                chars[index] = str(rand(1, 9))
    if "$" in text:
        for index, char in enumerate(chars):
            if char == "$":
                chars[index] = str(rand(2, 9))
    if "!" in text:
        for index, char in enumerate(chars):
            if char == "!":
                chars[index] = str(rand(0, 9)) if rand(0, 1) else ""
    if "@" in text:
        for index, char in enumerate(chars):
            if char == "@":
                chars[index] = str(rand(1, 9)) if rand(0, 1) else ""
    return "".join(chars)


def _get_words_list(
    self: Any,
    part_of_speech: str | None = None,
    ext_word_list: Any = None,
) -> Any:
    # Faker copies the locale word list on every word(). Callers only read it.
    if ext_word_list is not None:
        return ext_word_list
    if part_of_speech:
        if part_of_speech not in self.parts_of_speech:
            raise ValueError(f"{part_of_speech} is not recognized as a part of speech.")
        return self.parts_of_speech[part_of_speech]
    cached = getattr(self, "_fk_words", None)
    if cached is None:
        words = self.word_list
        cached = words if isinstance(words, list) else list(words)
        self._fk_words = cached
    return cached


def _ipv4_from_subnets(
    self: Any,
    subnets: Any,
    weights: Any = None,
    network: bool = False,
) -> str:
    if not subnets:
        raise ValueError("No subnets to choose from")
    usable = (
        isinstance(weights, list)
        and len(subnets) == len(weights)
        and weights
    )
    subnet = None
    if usable:
        cache = getattr(self, "_fk_ipv4_cdf", None)
        key = (id(subnets), len(subnets), id(weights), len(weights))
        if cache is not None and cache[0] == key:
            subnet = self.generator.random.choices(subnets, cum_weights=cache[1], k=1)[0]
        elif all(isinstance(weight, (float, int)) for weight in weights):
            cdf = list(accumulate(float(weight) for weight in weights))
            self._fk_ipv4_cdf = (key, cdf)
            subnet = self.generator.random.choices(subnets, cum_weights=cdf, k=1)[0]
    if subnet is None:
        subnet = self.generator.random.choice(subnets)

    address = str(
        subnet[self.generator.random.randint(0, subnet.num_addresses - 1)]
    )
    if network:
        from ipaddress import IPv4Network

        address += "/" + str(
            self.generator.random.randint(subnet.prefixlen, subnet.max_prefixlen)
        )
        address = str(IPv4Network(address, strict=False))
    return address


def _lexify(self: Any, text: str = "????", letters: str = string.ascii_letters) -> str:
    if "?" not in text:
        return text
    rand = self.generator.random
    return "".join(rand.choice(letters) if char == "?" else char for char in text)
