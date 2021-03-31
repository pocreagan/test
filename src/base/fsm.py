from enum import IntEnum
from time import time


class FSM:
    """
    override class States in subclass.
    to set state = x, call FSM.x().
    bool(FSM.x) returns True if current state == x.
    FSM.next() rolls over to 0th state when it reaches the end.
    """

    class States:
        RESET = 0

    class _State:

        def __init__(self, state, parent: 'FSM') -> None:
            self._state, self._parent = state, parent

        def __bool__(self) -> bool:
            return self._parent.state == self._state

        @property
        def name(self) -> str:
            return self._state.name

        def __call__(self, is_super: bool = False) -> None:
            self._parent._set(self._state)

    def __init__(self, debug: bool = True) -> None:
        self.last_t, self._debug, self.name = time(), debug, f'FSM ( {self.__class__.__name__} )'
        self.States = IntEnum('States',  # type: ignore
                              {k: v for k, v in self.States.__dict__.items() if not k.startswith('_')})
        self._value_to_member_map = getattr(self.States, '_value2member_map_')
        assert self._membership(0), f'{self.name} must have a 0th state.'
        self.states = {k.name: self._State(k, self) for k in self.States}  # type: ignore
        self._alignment, self.state = max([len(n.name) for n in self.States]), None  # type: ignore
        self._reset()

    def _dbg_pnt(self, previous: '_State', new: '_State') -> None:
        last_t, self.last_t = self.last_t, time()
        te = round(self.last_t - last_t, 1)
        print(
            f'{self.name} {getattr(previous, "name", "").rjust(self._alignment)}\
            {f"{te}s".rjust(7)} -> {new.name}'
        )

    def _membership(self, n: int) -> bool:
        return n in self._value_to_member_map

    def __repr__(self) -> str:
        return f'{self.name} @ {self.state}'

    def __getattr__(self, k: str) -> '_State':
        if k in self.states:
            return self.states[k]
        return object.__getattribute__(self, k)

    def _reset(self) -> None:
        self._set(self.States(0))  # type: ignore

    def on_change_callback(self, *args) -> None:
        """
        set this in parent
        """

    def _on_change_callback(self, *args):
        self.on_change_callback(*args)
        if self._debug:
            self._dbg_pnt(*args)

    def _set(self, state: '_State') -> None:
        previous, self.state = self.state, state
        self._on_change_callback(previous, self.state)

    def next(self) -> None:
        new = self.state + 1  # type: ignore
        if not self._membership(new):
            return self._reset()
        return self._set(self.States(new))  # type: ignore

    def __iter__(self):
        if not self.state == 0:
            self._reset()
        return self

    def __next__(self):
        self.next()
        return self.state
