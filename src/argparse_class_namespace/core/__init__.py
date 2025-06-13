from typing import (
    TypeVar, Generic, Protocol, runtime_checkable,
    TypedDict,
    Literal, Union,
    overload, Callable,
    Sequence, Unpack
)
from types import UnionType
import argparse
import argcomplete

_NS = TypeVar('_NS', bound=object)
_NS_co = TypeVar('_NS_co', covariant=True, bound=object)

class AddArgumentKwargs(TypedDict, total=False):
    default: object
    dest: str
    nargs: int | str
    choices: list[str | int]
    action: str
    type: type | Callable[[str], object]
class AddParserKwargs(TypedDict, total=False):
    dest: str
    parents: list[argparse.ArgumentParser]

@runtime_checkable
class SupportsOriginAndArgs(Protocol):
    __origin__: type
    __args__: tuple['type | SupportsOriginAndArgs', ...]

class NamespaceOptions(TypedDict):
    parser: argparse.ArgumentParser
class NamespaceOptionsPartial(TypedDict, total=False):
    parser: argparse.ArgumentParser
def _resolve_namespace_options(full: NamespaceOptions, partial: NamespaceOptionsPartial) -> NamespaceOptions:
    options = full.copy()
    options.update(partial)
    return options

def _is_dunder(name: str) -> bool:
    return name.startswith('__') and name.endswith('__')

class NamespaceWrapper(Generic[_NS_co]):

    def _get_attrnames(self, ns_type: type[_NS]) -> list[str]:
        
        annotations_keys = ns_type.__annotations__.keys()
        dict_keys = ns_type.__dict__.keys()
        
        ordered_keys = {
            k: i for i, k in enumerate(annotations_keys)
        } | {k: i for i, k in enumerate(dict_keys, start=len(annotations_keys))}

        return sorted(
            annotations_keys | dict_keys,
            key=lambda k: ordered_keys[k]
        )

    def _prepare_subparser(self, attrname: str, inst: 'NamespaceWrapper'):
        return ([attrname.replace('_', '-')], AddParserKwargs({
            'dest': attrname,
            'parents': [inst.parser],
        }))
    
    def _prepare_arg(self, attrname: str) -> tuple[list[str], AddArgumentKwargs]:

        kwargs: AddArgumentKwargs = {}

        if attrname in self._ns_co_type.__dict__:
            _name_or_flag = '--' + attrname.replace('_', '-')
            kwargs['default'] = self._ns_co_type.__dict__[attrname]
            if _name_or_flag != attrname:
                kwargs['dest'] = attrname
        else:
            _name_or_flag = attrname.replace('_', '-')

        ann = self._ns_co_type.__annotations__.get(attrname, str)

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
        choices: list[str | int | bool] = []
        types: list[type] = []

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
                if issubclass(current, bool):
                    bool_found = True
                else:
                    types.append(current)
            elif isinstance(current, str | int | bool):
                choices.append(current)
            else:
                raise TypeError(f"Unsupported type annotation: {current}")

        if bool_found:
            kwargs['action'] = 'store_false' if kwargs.get('default', None) else 'store_true'
            del kwargs['default']
        elif not types and choices:
            kwargs['choices'] = choices
        elif types:
            def _type(value: str):
                errors = []
                for t in types:
                    try:
                        return t(value)
                    except (ValueError, TypeError) as e:
                        errors.append(e)
                        continue
                for v in choices:
                    try:
                        ret = v.__class__(value)
                    except (ValueError, TypeError) as e:
                        errors.append(e)
                        continue
                    if ret not in choices:
                        continue
                raise TypeError(
                    f"Cannot convert '{value}' to any of the types: {', '.join(str(t) for t in types)}. "
                    f"Errors: {', '.join(str(e) for e in errors)}"
                )
            kwargs['type'] = _type
        else:
            kwargs['type'] = str

        return [_name_or_flag], kwargs
        
    def __init__(self, ns_type: type[_NS_co], options: NamespaceOptions):

        self._ns_co_type = ns_type
        self._options = options
        self._subparsers = None

        attrnames = self._get_attrnames(ns_type)

        add_argument_args: list[tuple[list[str], AddArgumentKwargs]] = []
        add_subparser_args: list[tuple[list[str], AddParserKwargs]] = []

        for attrname in attrnames:
            if _is_dunder(attrname):
                continue

            inst = getattr(ns_type, attrname, None)
            if isinstance(inst, NamespaceWrapper):
                add_subparser_args.append(self._prepare_subparser(attrname, inst))
            else:
                add_argument_args.append(self._prepare_arg(attrname))

        for args, kwargs in add_subparser_args:
            self.get_or_create_subparsers().add_parser(*args, **kwargs)

        for args, kwargs in add_argument_args:
            self.parser.add_argument(*args, **kwargs)

    def get_or_create_subparsers(self):
        if self._subparsers is None:
            self._subparsers = self.parser.add_subparsers()
        return self._subparsers

    @property
    def ns_type(self) -> type[_NS_co]:
        return self._ns_co_type
    @property
    def subparsers(self):
        return self._subparsers
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
    """
    Decorator or factory function to wrap a class with a NamespaceWrapper for argparse integration.
    This function can be used as a decorator or called directly to create a NamespaceWrapper
    for a given class type, enabling advanced argparse namespace handling.

    Args:
        ns_type (`type[_NS_co] | None`, optional): The class type to wrap. If None, the function
            returns a decorator that can be applied to a class. If a type is provided, the function
            returns a NamespaceWrapper instance for that type. Defaults to None.
        **partial_options (`*NamespaceOptionsPartial`): Partial options to customize the
            namespace behavior. These options are merged with defaults.

    Returns:
        out (`NamespaceWrapper[_NS_co] | (ns_type: type[_NS_co]) -> NamespaceWrapper[_NS_co]`): 
            If `ns_type` is provided, returns a NamespaceWrapper instance for the given type.
            If `ns_type` is None, returns a decorator that wraps a class with NamespaceWrapper.

    Examples:
        ```python
            @namespace
            class MyNamespaceAsDecorator:
                ...

            class MyNamespaceAsFactory:
                ...
            wrapper = namespace(MyNamespaceAsFactory)
        ```
    """

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
