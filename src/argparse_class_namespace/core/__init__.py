from typing import TypeVar, overload, Unpack, Callable
import argparse

from .namespace_wrapper import (
    NamespaceWrapper,
    _resolve_namespace_options, NamespaceOptions, NamespaceOptionsPartial,
    NamespaceWithOptions
)
from .group_wrapper import (
    GroupWrapper,
    _resolve_group_wrapper_options, GroupWrapperOptions, GroupWrapperOptionsPartial,
    GroupWithOptions
)

_NS_co = TypeVar('_NS_co', covariant=True, bound=object)

@overload
def namespace(
    ns_type: type[_NS_co],
    /
    ) -> NamespaceWrapper[_NS_co]: ...
@overload
def namespace(
    **partial_options: Unpack[NamespaceOptionsPartial]
    ) -> NamespaceWithOptions: ...

def namespace(
    ns_type: type[_NS_co] | None = None,
    /,
    **partial_options: Unpack[NamespaceOptionsPartial]
    ):
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

    parser = argparse.ArgumentParser(add_help=False)
    parser._add_action(argparse._HelpAction(['-h', '--help']))

    if ns_type is not None:
        return NamespaceWrapper(ns_type, _resolve_namespace_options(
        NamespaceOptions(
            container=parser,
            parser=parser,
            defaults={}
        ),
        partial_options
    ))

    parent_options = partial_options

    @overload
    def decorator(
        ns_type: type[_NS_co],
        /,
        ) -> NamespaceWrapper[_NS_co]: ...
    @overload
    def decorator(
        **partial_options: Unpack[NamespaceOptionsPartial]
        ) -> NamespaceWithOptions: ...
    def decorator(
        ns_type: type[_NS_co] | None = None,
        /,
        **partial_options: Unpack[NamespaceOptionsPartial]
        ):

        options = parent_options | partial_options

        if ns_type is not None:
            return NamespaceWrapper(ns_type, _resolve_namespace_options(
                NamespaceOptions(
                    container=parser,
                    parser=parser,
                    defaults={}
                ),
                options
            ))

        return namespace(**options)

    return decorator

@overload
def group(
    ns_type: type[_NS_co],
    /
    ) -> GroupWrapper[_NS_co]: ...
@overload
def group(
    **partial_options: Unpack[GroupWrapperOptionsPartial]
    ) -> GroupWithOptions: ...
def group(
    ns_type: type[_NS_co] | None = None,
    /,
    **partial_options: Unpack[GroupWrapperOptionsPartial]
    ):

    if ns_type is not None:
        return GroupWrapper(ns_type, _resolve_group_wrapper_options(
            GroupWrapperOptions(
                container=None,
                defaults={}
            ),
            partial_options
        ))

    parent_options = partial_options

    @overload
    def decorator(
        ns_type: type[_NS_co],
        /,
    ) -> GroupWrapper[_NS_co]: ...
    @overload
    def decorator(
        **partial_options: Unpack[GroupWrapperOptionsPartial]
    ) -> GroupWithOptions: ...
    def decorator(
        ns_type: type[_NS_co] | None = None,
        /,
        **partial_options: Unpack[GroupWrapperOptionsPartial]
    ):

        options = parent_options | partial_options

        if ns_type is not None:
            return GroupWrapper(ns_type, _resolve_group_wrapper_options(
                GroupWrapperOptions(
                    container=None,
                    defaults={}
                ),
                options
            ))

        return group(**options)

    return decorator
