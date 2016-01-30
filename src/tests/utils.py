from btce.utils import u


def use_dataproviders(cls):
    methods = _get_test_methods(cls)
    if not methods:
        raise Exception('no dataproviders used on {}'.format(cls))
    for name, method in methods:
        data_func = getattr(method, 'dataprovider')
        for i, params in enumerate(data_func()):
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


def test_stream(subjects, stream, data):
    if not isinstance(subjects, tuple):
        subjects = (subjects,)
    result = []
    subscription = stream.subscribe(u(
        lambda *args: result.append(args)
    ))
    for item in data:
        if isinstance(item, dict):
            for i, subject in enumerate(subjects):
                if i in item:
                    subject.on_next(item[i])
        else:
            subjects[0].on_next(item)
    subscription.dispose()
    return tuple(result)
