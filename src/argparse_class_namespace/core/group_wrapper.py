from typing import (
    TypeVar, Generic, Protocol, runtime_checkable,
    Callable, Sequence,
    Union, Literal, Unpack, Concatenate,
    TypedDict, DefaultDict,
    Self, Any, overload
)
import argparse
from .base_wrapper import (
    _return_bool,
    BaseWrapper, AddWrapperKwargs,
    WrapperOptions, WrapperOptionsPartial
)

_NS = TypeVar('_NS', bound=object)
_NS_co = TypeVar('_NS_co', covariant=True, bound=object)

_O = TypeVar('_O', bound=object)

class AddArgumentGroupKwargs(AddWrapperKwargs, total=False):
    title: str | None
    description: str | None

class AddArgumentGroupDefaults(TypedDict, Generic[_NS]):
    _argument_group_wrapper_bind_name: str | None
    _argument_group_wrapper_instance: 'GroupWrapper[_NS]'

class GroupWrapperOptions(WrapperOptions):
    pass
class GroupWrapperOptionsPartial(WrapperOptionsPartial, total=False):
    pass

def _resolve_group_wrapper_options(
    full: GroupWrapperOptions,
    partial: GroupWrapperOptionsPartial
) -> GroupWrapperOptions:
    options = full.copy()
    options.update(partial)
    return options

class GroupWithOptions(Protocol):
    @overload
    def __call__(
        self,
        ns_type: type[_NS],
        /
        ) -> 'GroupWrapper[_NS]': ...
    @overload
    def __call__(
        self,
        /,
        **partial_options: Unpack[GroupWrapperOptionsPartial]
        ) -> 'GroupWithOptions': ...
    def __call__(
        self,
        ns_type: type[_NS] | None = None,
        /,
        **partial_options: Unpack[GroupWrapperOptionsPartial]
        ):
        """
        Decorator or factory function to create a GroupWrapper for a class type.
        """
        raise NotImplementedError("GroupWithOptions must be implemented by a class.")

class GroupWrapper(BaseWrapper[_NS_co]):

    @classmethod
    def _from_argument_group(
        cls,
        ag: argparse._ArgumentGroup
        ) -> 'GroupWrapper[_NS_co]':
        if not isinstance(ag, argparse._ArgumentGroup):
            raise TypeError(f'Expected an instance of argparse._ArgumentGroup, got {type(ag)}')
        return ag.get_default('_argument_group_wrapper_instance')

    def _bind(self, bindname: str, parent: BaseWrapper):
        self._bind_base(bindname, parent)
        self._options['container'] = parent._options['container']
        for args, kwargs in self._dummy_container.args_kwargs:
            self.container.add_argument(*args, **kwargs)
        self.container.set_defaults(
            _argument_group_wrapper_bind_name=bindname,
            _argument_group_wrapper_instance=self
        )

    def _prepare_subwrapper(
        self,
        attrname: str,
        inst: BaseWrapper[_NS_co]
        ) -> tuple[list[str], AddArgumentGroupKwargs]:
        inst._bind(attrname, self)
        return ([attrname], AddArgumentGroupKwargs({
            'title': attrname,
            'description': None,
        }))

    def __init__(
        self,
        ns_co_type: type[_NS_co],
        options: GroupWrapperOptions
        ):
        super().__init__(ns_co_type, options)

    def add_wrapper(
        self,
        target: BaseWrapper,
        *args: str,
        **kwargs: Unpack[AddArgumentGroupKwargs]
        ):
        argument_group = target.container.add_argument_group(**kwargs)
        attrname, *_ = args
        target._argument_groups[attrname] = argument_group

    @property
    def container(self) -> argparse.ArgumentParser | argparse._ArgumentGroup:
        container =  self._options['container']
        if container is None:
            raise ValueError("Container is not set")
        return container

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
        instance: type[_NS] | _O | None,
        owner: type[_O] | None = None
        ):
        if instance is None:
            return self

        # Fallback to None if not set via setattr
        if _return_bool(False):
            # never called, but needed for type checking
            return self._ns_co_type()
        else:
            return None
