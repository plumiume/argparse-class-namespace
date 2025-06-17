from typing import (
    TypeVar, Generic, Protocol, ParamSpec, runtime_checkable,
    Callable, Sequence,
    Union, Literal, Unpack, Concatenate,
    TypedDict, DefaultDict,
    Any, overload
)
from types import UnionType
from itertools import chain
import argparse
import argcomplete

_NS = TypeVar('_NS', bound=object)
_NS_co = TypeVar('_NS_co', covariant=True, bound=object)

_O = TypeVar('_O', bound=object)
_P = ParamSpec('_P')
_R = TypeVar('_R')

class AddArgumentKwargs(TypedDict, total=False):
    default: object
    dest: str
    nargs: int | str
    choices: list[object]
    action: str
    type: type | Callable[[str], object]
class AddParserKwargs(TypedDict, total=False):
    add_help: Literal[False]
    parents: list[argparse.ArgumentParser]

class AddArgumentDefaults(TypedDict, Generic[_NS]):
    pass

class AddParserDefaults(TypedDict, Generic[_NS]):
    _namespace_wrapper_bind_name: str | None
    _namespace_wrapper_instance: 'NamespaceWrapper[_NS]'

class NamespaceOptions(TypedDict):
    parser: argparse.ArgumentParser
    defaults: dict[str, Any]
class NamespaceOptionsPartial(TypedDict, total=False):
    parser: argparse.ArgumentParser
    defaults: dict[str, Any]
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
    def __call__(self, ns_type: type[_NS]) -> 'NamespaceWrapper[_NS]': ...

class CallbackWithOptions(Protocol):
    def __call__(
        self,
        func: Callable[Concatenate[_NS, _P], _R]
        ) -> Callable[Concatenate[_NS, _P], _R]: ...

@runtime_checkable
class SupportsOriginAndArgs(Protocol):
    __origin__: type
    __args__: tuple['type | SupportsOriginAndArgs', ...]

class ParseResult(argparse.Namespace, Generic[_NS_co]):
    _namespace_wrapper_bind_name: str
    _namespace_wrapper_instance: 'NamespaceWrapper[_NS_co]'

class NamespaceWrapper(Generic[_NS_co]):

    class _Sentinel:
        def __eq__(self, other): return True
    _allow_any_value = _Sentinel()

    @staticmethod
    def _is_dunder(name: str) -> bool:
        return name.startswith('__') and name.endswith('__')

    @staticmethod
    def _get_attrnames(type_: type) -> list[str]:

        annotations_keys = type_.__annotations__.keys()
        dict_keys = type_.__dict__.keys()
        
        ordered_keys = {
            k: i for i, k in enumerate(annotations_keys)
        } | {
            k: i for i, k in enumerate(dict_keys, start=len(annotations_keys))
        }

        return sorted(
            (k for k in annotations_keys | dict_keys if not NamespaceWrapper._is_dunder(k)),
            key=lambda k: ordered_keys[k]
        )

    def _bind(self, bindname: str, parent: 'NamespaceWrapper'):
        self._bindname = bindname
        self._parent = parent
        self.parser.set_defaults(
            _namespace_wrapper_bind_name=bindname,
            _namespace_wrapper_instance=self
        )

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
        }))
    
    def _prepare_arg(
        self: 'NamespaceWrapper[_NS]',
        attrname: str
        ) -> tuple[
            list[str], AddArgumentKwargs
        ]:

        kwargs: AddArgumentKwargs = {}

        if attrname in self._ns_co_type.__dict__:
            _name_or_flag = '--' + attrname.replace('_', '-')
            kwargs['default'] = self._ns_co_type.__dict__[attrname]
            if _name_or_flag != attrname:
                kwargs['dest'] = attrname
        else:
            _name_or_flag = attrname.replace('-', '_')

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
        allowed = DefaultDict(list[object])

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
                    allowed[current].append(self._allow_any_value)
            elif isinstance(current, str | int | bool):
                allowed[type(current)].append(current)
            else:
                raise TypeError(f"Unsupported type annotation: {current}")

        choices = list(chain.from_iterable(allowed.values()))
        if bool_found:
            kwargs['action'] = 'store_false' if kwargs.get('default', None) else 'store_true'
            del kwargs['default']
        elif self._allow_any_value not in choices:
            kwargs['choices'] = choices
        elif allowed:
            def _type(value_string: str):
                errors: list[TypeError | ValueError] = []
                for t, a in allowed.items():
                    try:
                        value = t(value_string)
                    except (TypeError, ValueError) as e:
                        errors.append(e)
                        continue
                    if self._allow_any_value not in a or value in a:
                        return value
                raise TypeError(
                    f"Value '{value_string}' does not match any of the allowed types: "
                    f"{', '.join(str(t) for t in allowed.keys())}. Errors: {errors}"
                )
            kwargs['type'] = _type
        else:
            kwargs['type'] = str

        return [_name_or_flag], kwargs

    def __init__(self, ns_type: type[_NS_co], options: NamespaceOptions):

        self._ns_co_type = ns_type
        self._options = options
        options['parser'].set_defaults(**options['defaults'], **AddParserDefaults({
            '_namespace_wrapper_bind_name': None,
            '_namespace_wrapper_instance': self
        }))
        self._subparsers = None

        self._attrnames = self._get_attrnames(ns_type)
        
        self._parent: 'NamespaceWrapper | None' = None
        self._bindname: str | None = None

        self._register_namespace(ns_type)

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
        return self._options['parser']
    @property
    def defaults(self) -> dict[str, Any]:
        return self._options['defaults']

    @overload
    def __get__(self: 'NamespaceWrapper[_NS]', instance: ParseResult | None, owner: type[ParseResult] | None = None) -> 'NamespaceWrapper[_NS]': ...
    @overload
    def __get__(self: 'NamespaceWrapper[_NS]', instance: _O, owner: type[_O] | None = None) -> _NS | None: ...

    def __get__(self: 'NamespaceWrapper[_NS]', instance: _O | None, owner: type[_O] | None = None):
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
            name = resolved_options['name'] or func.__name__
            self.parser.set_defaults(**{
                name: func
            })
            return func

        if func is None:
            return decorator
        else:
            return decorator(func)

    def set_defaults(self, **kwargs: object):
        return self.parser.set_defaults(**kwargs)

    def parse_args(self: 'NamespaceWrapper[_NS]', args: Sequence[str] | None = None) -> _NS:
        argcomplete.autocomplete(self.parser)
        parse_result = self.parser.parse_args(args, ParseResult())
        ns_wrapper = parse_result._namespace_wrapper_instance
        bind_name = parse_result._namespace_wrapper_bind_name
        ns = ns_wrapper._ns_co_type()
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
            bind_name = ns_wrapper.parser.get_default('_namespace_wrapper_bind_name')
            ns = new_ns
        return ns

