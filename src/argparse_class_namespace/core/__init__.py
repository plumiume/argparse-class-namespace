from typing import (
    TypeVar, Generic, Protocol, runtime_checkable,
    TypedDict,
    overload, 
    Sequence, Unpack
)
import argparse
import argcomplete

_NS = TypeVar('_NS', bound=object)
_NS_co = TypeVar('_NS_co', covariant=True, bound=object)

@runtime_checkable
class SupportsOriginAndArgs(Protocol):
    __origin__: type
    __args__: tuple['type | SupportsOriginAndArgs', ...]

class NamespaceOptions(TypedDict):
    parser: argparse.ArgumentParser
class NamespaceOptionsPartial(NamespaceOptions, total=False): ...
def _resolve_namespace_options(full: NamespaceOptions, partial: NamespaceOptionsPartial) -> NamespaceOptions:
    options = full.copy()
    options.update(partial)
    return options

def _is_dunder(name: str) -> bool:
    return name.startswith('__') and name.endswith('__')

class NamespaceWrapper(Generic[_NS_co]):
    def __init__(self, ns_type: type[_NS_co], options: NamespaceOptions):

        self._ns_co_type = ns_type
        self._options = options

        attrnames = (ns_type.__annotations__.keys() - ns_type.__dict__.keys()) | ns_type.__dict__.keys()

        for attrname in attrnames:

            _dest = attrname

            if _is_dunder(attrname):
                continue

            if attrname in ns_type.__dict__:
                _name_or_flag = '--' + attrname.replace('_', '-')
                _default = ns_type.__dict__[attrname]
            else:
                _name_or_flag = attrname.replace('_', '-')
                _default = ''

            _type = ns_type.__annotations__.get(attrname, str)

            self.parser.add_argument(
                _name_or_flag,
                type=_type,
                dest=_dest,
                default=_default,
            )

    @property
    def ns_type(self) -> type[_NS_co]:
        return self._ns_co_type
    @property
    def parser(self) -> argparse.ArgumentParser:
        return self._options['parser']
    def parse_args(self, args: Sequence[str] | None = None) -> _NS_co:
        argcomplete.autocomplete(self.parser)
        return self.parser.parse_args(args, namespace=self._ns_co_type())

class NamespaceWithOptions(Protocol[_NS]):
    def __call__(self, ns_type: type[_NS]) -> NamespaceWrapper[_NS]: ...

@overload
def namespace(ns_type: type[_NS_co], /) -> NamespaceWrapper[_NS_co]: ...
@overload
def namespace(**partial_options: Unpack[NamespaceOptionsPartial]) -> NamespaceWithOptions: ...

def namespace(ns_type: type[_NS_co] | None = None, /, **partial_options: Unpack[NamespaceOptionsPartial]): # type: ignore
    resolved_options = _resolve_namespace_options(
        NamespaceOptions(parser=argparse.ArgumentParser()),
        partial_options
    )
    if ns_type is None:
        def decorator(ns_type: type[_NS_co]) -> NamespaceWrapper[_NS_co]:
            return NamespaceWrapper(ns_type, resolved_options)
        return decorator
    else:
        return NamespaceWrapper[_NS_co](ns_type, resolved_options)
