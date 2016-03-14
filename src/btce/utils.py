from collections import namedtuple


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


def get_data_packed(*spec, **kwargs):
    if not spec:
        return namedtuple('Data', ('is_packed',) + tuple(kwargs.keys()))(is_packed=True, **kwargs)
    def _wrapper(*args):
        names = list(spec)
        args = list(args)
        kwargs = {}
        while names:
            name = names.pop(0)
            if not args:
                raise Exception('cannot match names and args')
            arg = args.pop(0)
            if hasattr(arg, 'is_packed'):
                if hasattr(arg, name):
                    kwargs[name] = getattr(arg, name)
                    args.insert(0, arg)
                else:
                    names.insert(0, name)
            else:
                kwargs[name] = arg
        return get_data_packed(**kwargs)
    return _wrapper
