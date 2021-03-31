from typing import Optional

from src.base.general import setdefault_attr_from_factory

__all__ = [
    'StatusBit',
    'BitField',
]

_status_bits_list_key = '_status_bits_list_key_'
_word_val_key = 'word_value'


def add_self_to_map(owner, map_key: str, name: str, index: Optional[int], value) -> int:
    d = setdefault_attr_from_factory(owner, map_key, dict)
    if index is not None:
        if (index in d) or (d and (max(d.keys()) > index)):
            raise ValueError(f'cannot assign {name} to {index}')
        index = index
    elif d:
        index = max(d.keys()) + 1
    else:
        index = 0
    d[index] = value
    return index  # type: ignore


class StatusBit:
    def __init__(self, bit: int = None) -> None:
        self.bit = bit

    def __set_name__(self, owner, name):
        bit = add_self_to_map(owner, _status_bits_list_key, name, self.bit, name)
        setattr(owner, _word_val_key, getattr(owner, _word_val_key, 0) + 1 << bit)
        setattr(owner, name, None)


class BitField:
    class _Base:
        def _convert_input(self, value) -> int:
            raise NotImplementedError

        def __post_init__(self, value: str = '') -> None:
            self._value = self._convert_input(value)
            bits = getattr(self, _status_bits_list_key)
            [setattr(self, k, bool((self._value >> bit) & 1)) for bit, k in bits.items()]

        def __bool__(self) -> bool:
            return bool(self._value)

    class FromBase10(_Base):
        _conversion_base = 10

        def _convert_input(self, value) -> int:
            return int(value, self._conversion_base)

    class FromBinary(FromBase10):
        _conversion_base = 2
