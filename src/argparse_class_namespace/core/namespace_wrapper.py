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
    _return_bool,
    BaseWrapper, AddWrapperKwargs,
    WrapperOptions, WrapperOptionsPartial,
)
from .group_wrapper import GroupWrapper
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

class ParseResult(Generic[_NS_co], argparse.Namespace):
    _namespace_wrapper_bind_name: str
    _namespace_wrapper_instance: BaseWrapper[_NS_co]

class NamespaceWrapper(BaseWrapper[_NS_co]):

    def _bind(self, bindname: str, parent: BaseWrapper):
        self._bind_base(bindname, parent)
        self.container.set_defaults(
            _namespace_wrapper_bind_name=bindname,
            _namespace_wrapper_instance=self
        )
    
    def _prepare_subwrapper(
        self,
        attrname: str,
        inst: BaseWrapper[_NS_co]
        ) -> tuple[
            list[str], AddParserKwargs
        ]:
        inst._bind(attrname, self)
        return ([attrname.replace('_', '-')], AddParserKwargs({
            'add_help': False,
            'parents': (
                [inst.container]
                if isinstance(inst.container, argparse.ArgumentParser)
                else []
            ),
            'help': self._docstrings.get(attrname, None)
        }))

    def __init__(self, ns_type: type[_NS_co], options: NamespaceOptions):

        container = options['container']
        if container is None:
            container = options['container'] = options['parser']

        container.set_defaults(**options['defaults'], **AddParserDefaults({
            '_namespace_wrapper_bind_name': None,
            '_namespace_wrapper_instance': self
        }))

        super().__init__(ns_type, options)

    def add_wrapper(self, target: BaseWrapper, *args: str, **kwargs: Unpack[AddParserKwargs]):
        if not isinstance(target.container, argparse.ArgumentParser):
            raise TypeError(
                f"Expected target.container to be an ArgumentParser, got {type(target.container).__name__}"
            )
        if target._subparsers is None:
            target._subparsers = target.container.add_subparsers()
        target._subparsers.add_parser(*args, **kwargs)

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
        return list(self._attrnames)
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
        instance: type | ParseResult | None,
        owner: Any = None
        ) -> Self: ...
    @overload
    def __get__(
        self,
        instance: _O,
        owner: type[_O] | None = None
        ) -> _NS_co | None: ...
    def __get__(
        self,
        instance: type | ParseResult | _O | None,
        owner: type[type | ParseResult | _O] | None = None
        ):
        if instance is None or isinstance(instance, type | ParseResult):
            return self

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
        ns_wrapper_instance = parse_result._namespace_wrapper_instance
        ns_wrapper_bind_name = parse_result._namespace_wrapper_bind_name
        if not isinstance(ns_wrapper_instance, NamespaceWrapper):
            # Never
            raise ValueError(
                "ParseResult does not contain a valid NamespaceWrapper instance."
            )

        ns: _NS = ns_wrapper_instance._ns_co_type()
        attrname_to_group = dict(chain.from_iterable(
            (
                (attrname, agname)
                for attrname in agwrapper.attrnames
            )
            for agname, agwrapper in ns_wrapper_instance._argument_groups.items()
        ))
        group_ns_instances = {
            agname: ag._ns_co_type()
            for agname, ag in ns_wrapper_instance._argument_groups.items()
        }

        for attrname in chain(ns_wrapper_instance.attrnames, ns_wrapper_instance.defaults.keys()):
            if (
                ns_wrapper_instance is self
                and ns_wrapper_instance.subparsers
                and (
                    any(
                        attrname.replace('_', pc) in ns_wrapper_instance.subparsers.choices
                        for pc in ns_wrapper_instance.parser.prefix_chars
                    )
                    or attrname in ns_wrapper_instance.subparsers.choices
                    )
                ):
                continue
            group = attrname_to_group.get(attrname, None)
            if not hasattr(parse_result, attrname):
                continue
            elif group is None:
                setattr(ns, attrname, getattr(parse_result, attrname))
            else:
                gns_inst = group_ns_instances[group]
                setattr(gns_inst, attrname, getattr(parse_result, attrname))

        while ns_wrapper_bind_name is not None and ns_wrapper_instance._parent is not None:
            ns_wrapper_instance = ns_wrapper_instance._parent
            new_ns = ns_wrapper_instance._ns_co_type()
            setattr(new_ns, ns_wrapper_bind_name, ns)
            ns_wrapper_bind_name = ns_wrapper_instance.container.get_default('_namespace_wrapper_bind_name')
            ns = new_ns

        return ns
