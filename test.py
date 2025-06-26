def test_namespace():

    from typing import Literal
    import argparse
    from argparse_class_namespace import namespace

    @namespace(parser=argparse.ArgumentParser(add_help=True, exit_on_error=False))
    class Namespace:
        # positionals
        str_pos: str
        int_pos: int
        float_pos: float
        # optionals
        str_opt: str = 'default'
        int_opt: int = 42
        float_opt: float = 3.14
        # choices
        choice: Literal['a', 'b', 'c'] = 'a'
        choise_any: Literal['a', 'b', 'c'] | int = 0
        # nargs
        str_nargs: list[str] = []
        choise_nargs: list[Literal['a', 'b', 'c']] = []

    ns = Namespace.parse_args([
        'hello', '123', '3.14',
        '--str-opt', 'world',
        '--int-opt', '100',
        '--float-opt', '2.71',
        '--choice', 'b',
        '--choise-any', 'c',
        '--str-nargs', 'one', 'two', 'three',
        '--choise-nargs', 'a', 'b', 'c'
    ])

def test_namespace_subnamespace():

    import argparse
    from argparse_class_namespace import namespace

    @namespace
    class SubNamespace:
        sub_str: str = 'default'
        sub_int: int = 42

    @namespace
    class NamespaceWithSubNamespace:
        sub_ns = SubNamespace

    ns = NamespaceWithSubNamespace.parse_args([
        'sub-ns',
        '--sub-str', 'world',
        '--sub-int', '100'
    ])

    ret = (ns.sub_ns and ns.sub_ns.sub_str and ns.sub_ns.sub_int)

    ns = NamespaceWithSubNamespace.parse_args([])

    assert ret, "SubNamespace parsing failed"

def test_nested_namespace():

    from argparse_class_namespace import namespace

    @namespace
    class L2Namespace:
        inner_str: str
        inner_int: int = 42

    @namespace
    class L1Namespace:
        l2 = L2Namespace

    @namespace
    class L0Namespace:
        l1 = L1Namespace

    l0 = L0Namespace.parse_args([
        'l1', 'l2', 'this-is-inner', '--inner-int', '100'
    ])

    ret = (l0.l1 and l0.l1.l2 and l0.l1.l2.inner_str and l0.l1.l2.inner_int)

    assert ret, "Nested Namespace parsing failed"

def test_namespace_with_subclass():

    from argparse_class_namespace import namespace

    @namespace
    class ParentNamespace:

        @namespace
        class command:
            child_str: str = 'default'
            child_int: int = 42

    parent_ns = ParentNamespace.parse_args([
        'command',
        '--child-str', 'hello',
        '--child-int', '100'
    ])

    ret = (parent_ns.command and
           parent_ns.command.child_str == 'hello' and
           parent_ns.command.child_int == 100)

    assert ret, "Namespace with subclass parsing failed"

def test_namespace_with_variable_docstrings():

    from argparse_class_namespace import namespace

    @namespace
    class DocstringNamespace:
        """This is a test namespace."""
        str_var: str = "default"
        """This is a string variable."""
        int_var: int = 42
        """This is an integer variable."""

    ns = DocstringNamespace.parse_args([
        '--str-var', 'hello',
        '--int-var', '100'
    ])

    ret = (ns.str_var == 'hello' and ns.int_var == 100)

def test_namespace_group():

    from argparse_class_namespace import namespace, group, mixin

    @namespace
    class GroupedNamespace(mixin.Repr):

        @group
        class group1(mixin.Repr):
            group1_str: str = 'default'
            group1_int: int = 42

    ns = GroupedNamespace.parse_args([
        '--group1', '0',
    ])

    ret = (
        ns.group1
        and ns.group1.group1_str == 'default'
        and ns.group1.group1_int == 42
    )


