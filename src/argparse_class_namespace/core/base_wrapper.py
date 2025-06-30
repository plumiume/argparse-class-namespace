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

_T = TypeVar('_T', bound=object)
_O = TypeVar('_O', bound=object)

def _return_bool(value: bool) -> bool:
    return value

class ArgumentAddable(Protocol):
    def add_argument(self, *args, **kwargs) -> Any: ...

class DummyContainer(ArgumentAddable):
    def __init__(self):
        self.args_kwargs: list[tuple[tuple, dict]] = []
    def add_argument(self, *args, **kwargs):
        self.args_kwargs.append((args, kwargs))

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
    container: argparse.ArgumentParser | argparse._ArgumentGroup | None
    defaults: dict[str, object]
class WrapperOptionsPartial(TypedDict, total=False):
    container: argparse.ArgumentParser | argparse._ArgumentGroup | None
    defaults: dict[str, object]

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
        raise NotImplementedError(
            f"{self.__class__.__name__} does not implement _bind"
        )

    def _bind_base(self, bindname: str, parent: 'BaseWrapper'):
        self._bindname = bindname
        self._parent = parent

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
        self._dummy_container = DummyContainer()

        self._subparsers: argparse._SubParsersAction[argparse.ArgumentParser] | None = None
        self._argument_groups = dict[str, argparse._ArgumentGroup]()

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
            is_continue = False
            for w_type, w_args in add_wrapper_args.items():
                if isinstance(inst, w_type):
                    w_args.append((
                        inst,
                        *w_type._prepare_subwrapper(self, attrname, inst)
                    ))
                    is_continue = True
                    break
            if is_continue:
                continue
            else:
                add_argument_args.append(
                    self._prepare_arg(attrname)
                )

        for w_type, w_args in add_wrapper_args.items():
            for inst, args, kwargs in w_args:
                w_type.add_wrapper(
                    inst, self, *args, **kwargs
                )

        if not add_argument_args and self._subparsers:
            self._subparsers.required = True
                
        for args, kwargs in add_argument_args:
            self.argument_addable_object.add_argument(*args, **kwargs)

    def add_wrapper(self, target: 'BaseWrapper', *args, **kwargs):
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
        container = self._options['container']
        if container is None:
            raise ValueError("Container is not set")
        return container
    @property
    def argument_addable_object(self) -> ArgumentAddable:
        return self._options['container'] or self._dummy_container
    @property
    def defaults(self) -> dict[str, Any]:
        return self._options['defaults']

    @overload
    def __get__(
        self,
        instance: type | None,
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
        instance: type[_NS] |  _O | None,
        owner: type[type[_NS] | _O] | None = None
        ):
        raise NotImplementedError(
            f"{self.__class__.__name__} does not implement __get__"
        )

    def set_defaults(self, **kwargs: object):
        return self.container.set_defaults(**kwargs)
