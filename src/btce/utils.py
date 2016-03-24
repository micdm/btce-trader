from collections import namedtuple


def get_data_packed(*spec, **kwargs):
    if not spec:
        return _get_data_class(**kwargs)(is_packed=True, **kwargs)
    def _wrapper(*args):
        names = list(spec)
        params = list(args)
        kwargs = {}
        while names:
            name = names.pop(0)
            if not params:
                raise Exception('cannot match names and args: %s, %s' % (spec, args))
            arg = params.pop(0)
            if hasattr(arg, 'is_packed'):
                if hasattr(arg, name):
                    kwargs[name] = getattr(arg, name)
                    params.insert(0, arg)
                else:
                    names.insert(0, name)
            elif isinstance(arg, tuple):
                kwargs[name] = arg[0]
                params.insert(0, arg[1:])
            else:
                kwargs[name] = arg
        return get_data_packed(**kwargs)
    return _wrapper


def _get_data_class(**kwargs):
    properties = ('is_packed',) + tuple(sorted(kwargs.keys()))
    return namedtuple('Data', properties)
