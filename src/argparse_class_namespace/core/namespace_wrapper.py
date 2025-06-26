from typing import (
    TypeVar, Generic, Protocol, ParamSpec, runtime_checkable,
    Callable, Sequence,
    Union, Literal, Unpack, Concatenate,
    TypedDict, DefaultDict,
    Self, Any, overload
)
from types import UnionType
from itertools import chain
import argparse
import argcomplete

from .base_wrapper import (
    BaseWrapper,
    AddArgumentKwargs, AddWrapperKwargs,
    WrapperOptions, WrapperOptionsPartial,
    ParseResult
)
from .variable_docstring import get_variable_docstrings

_NS = TypeVar('_NS', bound=object)
_NS_co = TypeVar('_NS_co', covariant=True, bound=object)

_O = TypeVar('_O', bound=object)
_P = ParamSpec('_P')
_R = TypeVar('_R')

class AddParserKwargs(AddWrapperKwargs, total=False):
    add_help: Literal[False]
    parents: list[argparse.ArgumentParser]
    help: str | None

class AddArgumentDefaults(TypedDict, Generic[_NS]):
    pass

class AddParserDefaults(TypedDict, Generic[_NS]):
    _namespace_wrapper_bind_name: str | None
    _namespace_wrapper_instance: 'NamespaceWrapper[_NS]'

class NamespaceOptions(WrapperOptions):
    parser: argparse.ArgumentParser
class NamespaceOptionsPartial(WrapperOptionsPartial, total=False):
    parser: argparse.ArgumentParser
def _resolve_namespace_options(full: NamespaceOptions, partial: NamespaceOptionsPartial) -> NamespaceOptions:
    options = full.copy()
    options.update(partial)
    return options

class CallbackOptions(TypedDict):
    name: str | None
class CallbackOptionsPartial(TypedDict, total=False):
    name: str | None
def _resolve_callback_options(full: CallbackOptions, partial: CallbackOptionsPartial) -> CallbackOptions:
    options = full.copy()
    options.update(partial)
    return options

def _return_bool(value: bool) -> bool:
    return value

class NamespaceWithOptions(Protocol):
    @overload
    def __call__(
        self,
        ns_type: type[_NS],
        /
        ) -> 'NamespaceWrapper[_NS]': ...
    @overload
    def __call__(
        self,
        /,
        **partial_options: Unpack[NamespaceOptionsPartial]
        ) -> 'NamespaceWithOptions': ...
    def __call__(
        self,
        ns_type: type[_NS] | None = None,
        /,
        **partial_options: Unpack[NamespaceOptionsPartial]
        ) -> 'NamespaceWrapper[_NS] | NamespaceWithOptions':
        """
        Decorator or factory function to create a NamespaceWrapper for a class type.
        """
        raise NotImplementedError("This method should be implemented by the concrete class.")

class CallbackWithOptions(Protocol):
    def __call__(
        self,
        func: Callable[Concatenate[_NS, _P], _R]
        ) -> Callable[Concatenate[_NS, _P], _R]: ...

class NamespaceWrapper(BaseWrapper[_NS_co]):

    def _prepare_subparser(
        self: 'NamespaceWrapper[_NS]',
        attrname: str,
        inst: 'NamespaceWrapper'
        ) -> tuple[
            list[str], AddParserKwargs
        ]:
        inst._bind(attrname, self)
        return ([attrname.replace('_', '-')], AddParserKwargs({
            'add_help': False,
            'parents': [inst.parser],
            'help': self._docstrings.get(attrname, None)
        }))

    def __init__(self, ns_type: type[_NS_co], options: NamespaceOptions):

        options['container'].set_defaults(**options['defaults'], **AddParserDefaults({
            '_namespace_wrapper_bind_name': None,
            '_namespace_wrapper_instance': self
        }))

        super().__init__(ns_type, options)

    def _register_namespace(self, ns_type: type):

        add_argument_args: list[tuple[list[str], AddArgumentKwargs]] = []
        add_subparser_args: list[tuple[list[str], AddParserKwargs]] = []

        for attrname in self._attrnames:
            if self._is_dunder(attrname):
                continue

            inst = getattr(ns_type, attrname, None)
            if isinstance(inst, NamespaceWrapper):
                add_subparser_args.append(self._prepare_subparser(attrname, inst))
            else:
                add_argument_args.append(self._prepare_arg(attrname))

        for args, kwargs in add_subparser_args:
            self.add_wrapper_to_subwrappers(*args, **kwargs)

        for args, kwargs in add_argument_args:
            self.parser.add_argument(*args, **kwargs)

    def add_wrapper_to_subwrappers(self, *args: str, **kwargs: Unpack[AddParserKwargs]):
        if self._subparsers is None:
            self._subparsers = self.parser.add_subparsers()
        return self._subparsers.add_parser(*args, **kwargs)

    @property
    def ns_type(self) -> type[_NS_co]:
        return self._ns_co_type
    @property
    def T(self) -> type[_NS_co]:
        return self._ns_co_type
    @property
    def subparsers(self):
        return self._subparsers
    @property
    def attrnames(self) -> list[str]:
        return self._attrnames
    @property
    def parser(self) -> argparse.ArgumentParser:
        container = self._options['container']
        if isinstance(container, argparse.ArgumentParser):
            return container
        else:
            raise TypeError(
                f"Expected container to be an ArgumentParser, got {type(container).__name__}"
            )

    @overload
    def __get__(
        self,
        instance: _O,
        owner: type[_O] | None = None
        ) -> _NS_co | None: ...
    @overload
    def __get__(
        self,
        instance: ParseResult | None,
        owner: type[ParseResult] | None = None
        ) -> Self: ...

    def __get__(
        self,
        instance: ParseResult | None | _O,
        owner: type[_O] | None = None
        ):
        if instance is None or isinstance(instance, ParseResult):
            return self
        else:
            # Fallback to None if not set via setattr
            if _return_bool(False):
                # never called, but needed for type checking
                return self._ns_co_type()
            else:
                return None

    @overload
    def callback(
        self: 'NamespaceWrapper[_NS]',
        func: Callable[Concatenate[_NS, _P], _R],
        /
        ) -> Callable[Concatenate[_NS, _P], _R]: ...
    @overload
    def callback(
        self: 'NamespaceWrapper[_NS]',
        /,
        **kwargs: Unpack[CallbackOptionsPartial]
        ) -> CallbackWithOptions: ...
    def callback(
        self: 'NamespaceWrapper[_NS]',
        func: Callable[Concatenate[_NS, _P], _R] | None = None,
        /,
        **kwargs: Unpack[CallbackOptionsPartial]
        ):

        resolved_options = _resolve_callback_options(
            CallbackOptions({
                'name': None
            }),
            kwargs
        )

        def decorator(func: Callable[Concatenate[_NS, _P], _R]) -> Callable[Concatenate[_NS, _P], _R]:
            self.parser.set_defaults(**{
                resolved_options['name'] or func.__name__: func
            })
            return func

        if func is None:
            return decorator
        else:
            return decorator(func)

    def parse_args(self: 'NamespaceWrapper[_NS]', args: Sequence[str] | None = None) -> _NS:
        argcomplete.autocomplete(self.parser)
        parse_result = self.parser.parse_args(args, ParseResult[_NS]())
        ns_wrapper = parse_result._namespace_wrapper_instance
        bind_name = parse_result._namespace_wrapper_bind_name
        if not isinstance(ns_wrapper, NamespaceWrapper):
            # Never
            raise ValueError(
                "ParseResult does not contain a valid NamespaceWrapper instance."
            )
        ns: _NS = ns_wrapper._ns_co_type()
        for attrname in chain(ns_wrapper.attrnames, ns_wrapper.defaults.keys()):
            if (
                ns_wrapper is self
                and ns_wrapper.subparsers
                and (
                    any(
                        attrname.replace('_', pc) in ns_wrapper.subparsers.choices
                        for pc in ns_wrapper.parser.prefix_chars
                    )
                    or attrname in ns_wrapper.subparsers.choices
                    )
                ):
                continue
            setattr(ns, attrname, getattr(parse_result, attrname))
        while bind_name is not None and ns_wrapper._parent is not None:
            ns_wrapper = ns_wrapper._parent
            new_ns = ns_wrapper._ns_co_type()
            setattr(new_ns, bind_name, ns)
            bind_name = ns_wrapper.container.get_default('_namespace_wrapper_bind_name')
            ns = new_ns
        return ns

