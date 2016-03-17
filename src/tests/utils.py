
def use_dataproviders(cls):
    methods = _get_test_methods(cls)
    if not methods:
        raise Exception('no dataproviders used on {}'.format(cls))
    for name, method in methods:
        data_func = getattr(method, 'dataprovider')
        for i, params in enumerate(getattr(cls, data_func)()):
            setattr(cls, '{}_{}'.format(name, i), _get_new_test_method(method, params))
        delattr(cls, name)
    return cls


def _get_test_methods(cls):
    return [(key, value) for key, value in cls.__dict__.items() if hasattr(value, 'dataprovider')]


def _get_new_test_method(method, params):
    def wrapper(self):
        return method(self, *params)
    return wrapper


def dataprovider(data_func):
    def wrapper(func):
        setattr(func, 'dataprovider', data_func)
        return func
    return wrapper


def test_stream(stream, on_next, data):
    result = []
    subscription = stream.subscribe(result.append)
    for item in data:
        on_next(item)
    subscription.dispose()
    return result[-1] if result else None
