import ast
import inspect
import itertools
import textwrap

def _get_tree_from_class(cls: type) -> ast.Module:

    try:
        source = inspect.getsource(cls)
    except OSError as e:
        raise RuntimeError(
            f"Could not get source code for class"
            f" {cls.__name__}: {e}"
        )

    try:
        tree = ast.parse(textwrap.dedent(source))
    except SyntaxError as e:
        raise RuntimeError(
            f"Syntax error in source code of class {cls.__name__}: {e}"
        )

    return tree

def _get_var_name_from_assign(assign: ast.Assign) -> str | None:

    if len(assign.targets) != 1:
        return None

    target = assign.targets[0]

    if not isinstance(target, ast.Name):
        return None

    return target.id

def _get_var_name_from_annassign(assign: ast.AnnAssign) -> str | None:

    if not isinstance(assign.target, ast.Name):
        return None

    return assign.target.id

def _get_str_const_expr(expr: ast.Expr) -> str | None:

    if not isinstance(expr.value, ast.Constant):
        return None

    constant = expr.value

    if not isinstance(constant.value, str):
        return None

    return constant.value

def get_variable_docstrings(cls: type) -> dict[str, str]:
    """Extracts variable names and their associated docstrings from a class.
    Args:
        cls (type): The class from which to extract variable docstrings.
    Returns:
        dict[str, str]: A dictionary mapping variable names to their docstrings.
    Raises:
        TypeError: If the provided `cls` is not a class type.
        RuntimeError: If the class definition is not found or if it contains multiple definitions.
    """

    if not isinstance(cls, type):
        raise TypeError(f"Expected a class type, but got {type(cls).__name__}.")

    tree = _get_tree_from_class(cls)

    if len(tree.body) != 1:
        raise RuntimeError(
            f"Expected a single class definition in {cls.__name__}, "
            f"but found {len(tree.body)} definitions."
        )

    cls_def = tree.body[0]

    if not isinstance(cls_def, ast.ClassDef):
        raise RuntimeError(
            f"Expected a class definition in {cls.__name__}, "
            f"but found {type(cls_def).__name__}."
        )

    return {
        target_name: docstring
        for assign, expr in itertools.pairwise(cls_def.body)
        if (
            isinstance(assign, ast.Assign) and (target_name := _get_var_name_from_assign(assign)) is not None
            or isinstance(assign, ast.AnnAssign) and (target_name := _get_var_name_from_annassign(assign)) is not None
        )
        and isinstance(expr, ast.Expr) and (docstring := _get_str_const_expr(expr)) is not None
    }