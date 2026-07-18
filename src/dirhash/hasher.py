from __future__ import annotations

import hashlib

try:
    import typing_extensions as t
except ImportError:
    import typing as t  # type: ignore[no-redef]

if t.TYPE_CHECKING:

    class HasherState(t.TypedDict):
        name: str
        data: bytes
        kwargs: dict[str, t.Any]


@t.runtime_checkable
class FactoryHasher(t.Protocol):
    """
    A runtime protocol to check for hashlib hasher objects.

    >>> import hashlib
    >>> isinstance(hashlib.new("md5-sha1"), FactoryHasher)
    True
    """

    def update(self, data: bytes) -> None: ...
    def hexdigest(self, **kwargs) -> str:
        """
        algorithms `shake_128` and `shake_256` require a `length` keyword argument.
        """
        ...


class PickableHasher(FactoryHasher):
    """
    A wrapper around hashlib hasher objects that makes them picklable.

    >>> import hashlib
    >>> isinstance(PickableHasher("md5-sha1"), FactoryHasher)
    True

    """

    algorithms: t.AbstractSet[str] = frozenset(
        hashlib.algorithms_available | hashlib.algorithms_guaranteed
    )
    """A set of all algorithms available in hashlib, including guaranteed ones."""

    def __init__(
        self,
        algorithm: str,
        data: bytes = b"",
        **kwargs,
    ) -> None:
        if algorithm not in self.algorithms:
            raise ValueError(f"Unknown hash algorithm: {algorithm!r}")

        self._state: HasherState = {
            "name": algorithm,
            "data": data,
            "kwargs": kwargs,
        }
        self._hash = hashlib.new(algorithm, data, **kwargs)

    @property
    def hash(self) -> hashlib._Hash:
        """wrapped hashlib.new() object"""
        return self._hash

    def update(self, data: bytes) -> None:
        """
        Update this hash object's state with the provided string.

        >>> hash = PickableHasher("md5")
        >>> hash.update(b"data")
        >>> hash.hexdigest() == hashlib.new("md5", b"data").hexdigest()
        True
        """
        self._hash.update(data)

    def hexdigest(self, length: int | None = None) -> str:  # type: ignore[override]
        """
        Return the digest value as a string of hexadecimal digits.

        >>> PickableHasher("shake_128", b"data").hexdigest()
        '6d5d29b8058bdf6517f2487f8dc537ab'
        >>> PickableHasher("shake_128", b"data").hexdigest(length=16)
        '6d5d29b8058bdf6517f2487f8dc537ab'
        """

        if self._hash.digest_size:
            return self._hash.hexdigest()

        def shake_digestsize() -> int:
            """return a default digest size for shake_128 and shake_256."""
            *_, bits = self._hash.name.split("_")
            return int(bits) // 8

        return self._hash.hexdigest(length or shake_digestsize())  # type: ignore[call-arg]

    def copy(self) -> t.Self:
        """
        Return a copy of the hash object.

        >>> hash = PickableHasher("md5", b"data")
        >>> copy = hash.copy()
        >>> id(hash) != id(copy)
        True
        """
        return self.__copy__()

    def __call__(self, data: bytes = b"") -> t.Self:
        self._state["data"] = data
        self._hash = hashlib.new(self._state["name"], data, **self._state["kwargs"])

        return self

    def __copy__(self) -> t.Self:
        obj = object.__new__(self.__class__)
        obj.__dict__.update(self.__dict__)
        obj._hash = self._hash.copy()

        return obj

    def __str__(self) -> str:
        return str(self._hash)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._state['name']!r})"

    def __getattr__(self, name: str) -> t.Any:
        return getattr(self._hash, name)

    def __getstate__(self) -> HasherState:
        return self._state

    def __setstate__(self, state: HasherState) -> None:
        self._state = state
        self._hash = hashlib.new(state["name"], state["data"], **state["kwargs"])


def new(algorithm: str, data: bytes = b"", **kwargs) -> PickableHasher:
    """
    Create a new picklable hasher object.

    >>> import hashlib, pickle
    >>> hash = new("md5", b"data")
    >>> hash.hexdigest() == hashlib.new("md5", b"data").hexdigest()
    True
    >>> pickled = pickle.loads(pickle.dumps(hash))
    >>> hash.hexdigest() == pickled.hexdigest()
    True
    """
    return PickableHasher(algorithm, data, **kwargs)


if __name__ == "__main__":
    import doctest

    doctest.testmod(exclude_empty=True)
