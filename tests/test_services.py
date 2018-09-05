from abc import ABCMeta, abstractmethod
from contextlib import contextmanager
from multiprocessing import Process

from sauerkraut import service, service_method
from sauerkraut.jsonrpc import create_jsonrpc_client_factory, create_jsonrpc_server


class FooService(metaclass=ABCMeta):
    @abstractmethod
    @service_method
    def bar(self):
        pass


@service
class FooServiceImpl(FooService):
    @service_method
    def bar(self):
        return 123


@contextmanager
def launch_process(target, *args, **kwargs):
    p = Process(target=target, args=args, kwargs=kwargs)
    p.start()
    try:
        yield
    finally:
        p.terminate()


def test_basic():
    foo_service = FooServiceImpl()
    assert foo_service.bar() == 123


def test_jsonrpc():
    foo_server = create_jsonrpc_server(FooServiceImpl)
    foo_service_factory = create_jsonrpc_client_factory(FooService, 'http://localhost:4000/jsonrpc')
    foo_service = foo_service_factory()
    with launch_process(foo_server.run, 'localhost', 4000):
        assert foo_service.bar() == 123
