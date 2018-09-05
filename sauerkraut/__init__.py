import inspect
from typing import Callable, Type, NamedTuple, Dict, List
from functools import partial


_SERVICE = '__service__'
_SERVICE_METHOD = '__service_method__'


def service(service_cls: Type = None, **kwargs):
    if service_cls is None:
        return partial(service, **kwargs)
    setattr(service_cls, _SERVICE, kwargs)
    return service_cls


def service_method(func: Callable = None, **kwargs):
    if func is None:
        return partial(service_method, **kwargs)
    setattr(func, _SERVICE_METHOD, kwargs)
    return func


def is_service_method(func: Callable):
    return hasattr(func, _SERVICE_METHOD)


class ServiceMethodConfig(NamedTuple):
    name: str
    func: Callable
    config: Dict
    signature: inspect.Signature


class ServiceConfig(NamedTuple):
    name: str
    config: Dict
    method_configs: List[ServiceMethodConfig]


def get_service_config(service_cls) -> ServiceConfig:
    service_config = getattr(service_cls, _SERVICE, {})
    methods = inspect.getmembers(service_cls, predicate=is_service_method)
    return ServiceConfig(
        name=service_config.get('name', service_cls.__name__),
        config=service_config,
        method_configs=[
            ServiceMethodConfig(
                name=attr_name,
                func=func,
                config=getattr(func, _SERVICE_METHOD),
                signature=inspect.Signature.from_callable(func)
            )
            for (attr_name, func) in methods
        ]
    )
