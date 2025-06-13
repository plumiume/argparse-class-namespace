from .namespace_wrapper import NamespaceWrapper

class Repr:
    def __repr__(self):
        attrnames = NamespaceWrapper._get_attrnames(self.__class__)
        return (
            f'{self.__class__.__name__}('
            + ', '.join(f'{name}={getattr(self, name)}' for name in attrnames)
            + ')'
        )
