from argparse import FileType, Action, HelpFormatter

class DestAndTypeHelpFormatter(HelpFormatter):

    def _get_type_repr(self, action: Action) -> str:
        if action.type is None:
            return 'str'
        elif isinstance(action.type, str):
            return (action.type)
        elif isinstance(action.type, FileType):
            return 'file'
        return f'{action.type.__name__}'

    def _get_default_metavar_for_optional(self, action: Action) -> str:
        return f'{action.dest}: {self._get_type_repr(action)}'

    def _get_default_metavar_for_positional(self, action: Action) -> str:
        return f'{action.dest}: {self._get_type_repr(action)}'
