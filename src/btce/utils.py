class _Result(tuple):
    pass


def u(func):
    def _wrapper(*args):
        return func(*_get_args(args))
    return _wrapper


def _get_args(args):
    result = []
    for arg in args:
        if isinstance(arg, _Result):
            result += _get_args(arg)
        else:
            result.append(arg)
    return result


def r(*args):
    return _Result(args)