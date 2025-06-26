from typing import (
    TypeVar, Generic, Protocol, runtime_checkable,
    Callable, Sequence,
    Union, Literal, Unpack, Concatenate,
    TypedDict, DefaultDict,
    Self, Any, overload
)
from types import UnionType
from itertools import chain
import argparse

from .variable_docstring import get_variable_docstrings

_NS = TypeVar('_NS', bound=object)
_NS_co = TypeVar('_NS_co', covariant=True, bound=object)

_O = TypeVar('_O', bound=object)

class AddArgumentKwargs(TypedDict, total=False):
    default: object
    dest: str
    nargs: int | str
    choices: list[object]
    action: str
    type: type | Callable[[str], object]
    help: str | None

class AddWrapperKwargs(TypedDict, total=False):
    pass

class WrapperOptions(TypedDict):
    container: argparse.ArgumentParser | argparse._ArgumentGroup
    defaults: dict[str, object]
class WrapperOptionsPartial(TypedDict, total=False):
    container: argparse.ArgumentParser | argparse._ArgumentGroup
    defaults: dict[str, object]

class _SubWrapperProtocol(Protocol[_NS_co]):
    def add_wrapper(self, *args, **kwargs): ...

@runtime_checkable
class SupportsOriginAndArgs(Protocol):
    __origin__: type
    __args__: tuple['type | SupportsOriginAndArgs', ...]

class BaseWrapper(Generic[_NS_co]):

    class _Sentinel:
        def __eq__(self, other): return True
    _allow_any_value = _Sentinel()

    @staticmethod
    def _is_dunder(attrname: str) -> bool:
        return attrname.startswith('__') and attrname.endswith('__')

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
            (k for k in annotations_keys | dict_keys if not BaseWrapper._is_dunder(k)),
            key=lambda k: ordered_keys[k]
        )

    def _bind(self, bindname: str, parent: 'BaseWrapper'):
        self._bindname = bindname
        self._parent = parent
        self.container.set_defaults(
            _namespace_wrapper_bind_name=bindname,
            _namespace_wrapper_instance=self
        )

    def _prepare_subwrapper(
        self,
        attrname: str,
        inst: 'BaseWrapper'
        ) -> tuple[list[str], AddWrapperKwargs]:
        raise NotImplementedError(
            f"{self.__class__.__name__} does not implement _prepare_subwrapper"
        )

    def _prepare_arg(
        self: 'BaseWrapper[_NS_co]',
        attrname: str
        ) -> tuple[list[str], AddArgumentKwargs]:

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

        kwargs['help'] = self._docstrings.get(attrname, None)

        return [_name_or_flag], kwargs

    def __init__(
        self,
        ns_type: type[_NS_co],
        options: WrapperOptions
        ):

        self._options = options

        self._ns_co_type = ns_type
        self._attrnames = self._get_attrnames(ns_type)
        self._docstrings = get_variable_docstrings(ns_type)

        self._parent: 'BaseWrapper | None' = None
        self._bindname: str | None = None

        self._subparsers = None
        self._argument_groups = None

        self._register_namespace(ns_type)

    def _register_namespace(self, ns_type: type): # call once

        add_argument_args: list[tuple[list[str], AddArgumentKwargs]] = []
        add_wrapper_args: dict[
            type['BaseWrapper'],
            list[tuple['BaseWrapper', list[str], AddWrapperKwargs]]
        ] = {
            wrapper_type: [] for wrapper_type in self._wrapper_types
        }

        for attrname in self._attrnames:
            if self._is_dunder(attrname):
                continue

            inst = getattr(self._ns_co_type, attrname, None)
            for w_type, w_args in add_wrapper_args.items():
                if isinstance(inst, w_type):
                    w_args.append((
                        inst,
                        *w_type._prepare_subwrapper(self, attrname, inst),
                    ))
            else:
                add_argument_args.append(
                    self._prepare_arg(attrname)
                )

        for w_type, w_args in add_wrapper_args.items():
            for inst, args, kwargs in w_args:
                inst.add_wrapper_to_subwrappers(
                    self, *args, **kwargs
                )
        for args, kwargs in add_argument_args:
            self.container.add_argument(*args, **kwargs)

    def add_wrapper_to_subwrappers(self, *args, **kwargs):
        raise NotImplementedError(
            f"{self.__class__.__name__} does not implement add_wrapper_to_subwrappers"
        )

    _wrapper_types = set[type['BaseWrapper']]()

    def __init_subclass__(cls) -> None:
        cls._wrapper_types.add(cls)

    @property
    def ns_type(self) -> type[_NS_co]:
        return self._ns_co_type
    @property
    def T(self) -> type[_NS_co]:
        return self._ns_co_type
    @property
    def attrnames(self) -> list[str]:
        return self._attrnames
    @property
    def container(self) -> argparse.ArgumentParser | argparse._ArgumentGroup:
        return self._options['container']
    @property
    def defaults(self) -> dict[str, Any]:
        return self._options['defaults']

    @overload
    def __get__(
        self,
        instance: _O,
        owner: type[_O] | None = None
        ) -> _NS_co | None: ...
    @overload
    def __get__(
        self,
        instance: None,
        owner: type | None = None
        ) -> Self: ...
    def __get__(
        self,
        instance: _O | None,
        owner: type[_O] | None = None
        ):
        raise NotImplementedError(
            f"{self.__class__.__name__} does not implement __get__"
        )

    def set_defaults(self, **kwargs: object):
        return self.container.set_defaults(**kwargs)

class ParseResult(Generic[_NS_co], argparse.Namespace):
    _namespace_wrapper_bind_name: str
    _namespace_wrapper_instance: BaseWrapper[_NS_co]