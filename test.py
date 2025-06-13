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