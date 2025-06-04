from typing import (
    TypeVar, Generic, Protocol, runtime_checkable,
    TypedDict,
    Literal, Union,
    overload, 
    Sequence, Unpack
)
from types import UnionType
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

            kwargs = {}

            if _is_dunder(attrname):
                continue

            if attrname in ns_type.__dict__:
                _name_or_flag = '--' + attrname.replace('_', '-')
                kwargs['default'] = ns_type.__dict__[attrname]
                kwargs['dest'] = attrname
            else:
                _name_or_flag = attrname.replace('_', '-')

            ann = ns_type.__annotations__.get(attrname, str)

            stack: list[object | type | SupportsOriginAndArgs] 
            if isinstance(ann, SupportsOriginAndArgs):
                if ann.__origin__ is list:
                    stack = list(ann.__args__)
                    kwargs['nargs'] = '*'
                elif ann.__origin__ is tuple:
                    stack = list(ann.__args__)
                    kwargs['nargs'] = len(ann.__args__)
                else:
                    stack = [ann]
            else:
                stack = [ann]

            bool_found = False
            choises = []
            types = []

            while stack:
                current = stack.pop(0)

                if isinstance(current, SupportsOriginAndArgs):
                    if current.__origin__ is Union or current.__origin__ is Literal:
                        stack.extend(current.__args__)

                    else:
                        stack.append(current.__origin__)
                elif isinstance(current, UnionType):
                    stack.extend(current.__args__)
                elif isinstance(current, type):
                    types.append(current)
                elif isinstance(current, str | int):
                    choises.append(current)
                elif isinstance(current, bool):
                    bool_found = True
                else:
                    raise TypeError(f"Unsupported type annotation: {current}")

            if bool_found:
                kwargs['action'] = 'store_false' if kwargs.get('default', None) else 'store_true'
                del kwargs['default']
            elif choises:
                kwargs['choices'] = choises
            elif types:
                def _type(value: str):
                    errors = []
                    for t in types:
                        try:
                            return t(value)
                        except (ValueError, TypeError) as e:
                            errors.append(e)
                            continue
                    raise TypeError(
                        f"Cannot convert '{value}' to any of the types: {', '.join(str(t) for t in types)}. "
                        f"Errors: {', '.join(str(e) for e in errors)}"
                    )
                kwargs['type'] = _type
            else:
                kwargs['type'] = str

            print(_name_or_flag, kwargs)

            self.parser.add_argument(
                _name_or_flag,
                **kwargs
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
