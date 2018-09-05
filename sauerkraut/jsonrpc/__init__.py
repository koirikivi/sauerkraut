import json
from abc import abstractmethod, ABCMeta
from functools import update_wrapper
from typing import TypeVar, Type, Dict, Any, Callable

import jsonrpc
import requests
from werkzeug.serving import run_simple
from werkzeug.wrappers import Request, Response

from .. import get_service_config

T = TypeVar('T')


class JsonRpcRequestClient(metaclass=ABCMeta):
    @abstractmethod
    def make_request(self, url: str, method: str, params: Dict) -> Dict:
        pass


class JsonRpcSerializer(metaclass=ABCMeta):
    @abstractmethod
    def serialize(self, method: str, data: Any) -> Any:
        pass

    @abstractmethod
    def deserialize(self, method: str, data: Any) -> Any:
        pass


class StandardJsonRpcRequestClient(JsonRpcRequestClient):
    def make_request(self, url: str, method: str, params: Dict) -> Any:
        headers = {'content-type': 'application/json'}
        request_id = 1
        payload = {
            'method': method,
            'params': params,
            'jsonrpc': '2.0',
            'id': request_id,
        }
        json_payload = json.dumps(payload)

        response = requests.post(url, data=json_payload, headers=headers)

        # TODO: better validation, throw errors instead of assert, map jsonrpc errors to python errors
        response.raise_for_status()

        json_response = response.json()
        assert 'result' in json_response
        assert json_response['jsonrpc'] == '2.0'
        assert json_response['id'] == request_id
        return json_response['result']


class StandardJsonRpcSerializer(JsonRpcSerializer):
    def serialize(self, method: str, data: Any) -> Any:
        return data

    def deserialize(self, method: str, data: Any) -> Any:
        return data


def create_jsonrpc_client_factory(service_cls: T, service_url: str, *,
                                  bases=(object,),
                                  generated_class_name=None,
                                  request_client_factory: Type[JsonRpcRequestClient] = StandardJsonRpcRequestClient,
                                  serialize_factory: Type[JsonRpcSerializer] = StandardJsonRpcSerializer) -> T:
    service_config = get_service_config(service_cls)

    def __init__(self):
        self._request_client = request_client_factory()
        self._serializer = serialize_factory()

    method_map = {'__init__': __init__}

    for method_config in service_config.method_configs:
        def method_func(self, *args, **kwargs):
            bound_args = method_config.signature.bind(self, *args, **kwargs)
            bound_args.apply_defaults()
            method_name = method_config.name
            unserialized_params = dict(bound_args.arguments)
            unserialized_params.pop('self')

            jsonrpc_params = self._serializer.serialize(method_name, unserialized_params)
            unserialized_response = self._request_client.make_request(
                service_url,
                method_name,
                jsonrpc_params
            )

            return self._serializer.deserialize(method_name, unserialized_response)

        update_wrapper(method_func, method_config.func)  # TODO: not sure if necessary
        method_func.__name__ = method_config.name
        method_map[method_config.name] = method_func

    if generated_class_name is None:
        generated_class_name = f'{service_config.name}JsonRpcClient'
    return type(generated_class_name, bases, method_map)


# TODO: the server part is very much todo. We should abstract out the backend stuff


class JsonRpcServer:
    def __init__(self, service, serializer, method_names):
        self._service = service
        self._serializer = serializer
        self._dispatcher = jsonrpc.Dispatcher()
        for method_name in method_names:
            wrapped_method = getattr(self._service, method_name)
            def wrapper(*args, **kwargs):
                # TODO: the deserialization is a bit silly
                deserialized_args = self._serializer.deserialize(method_name, args)
                deserialized_kwargs = self._serializer.deserialize(method_name, kwargs)
                result = wrapped_method(*deserialized_args, **deserialized_kwargs)
                return self._serializer.serialize(method_name, result)
            update_wrapper(wrapper, wrapped_method)
            self._dispatcher[method_name] = wrapper

        @Request.application
        def application(request):
            response = jsonrpc.JSONRPCResponseManager.handle(request.data, self._dispatcher)
            return Response(response.json, mimetype='application/json')

        self._application = application

    def run(self, hostname, port):
        run_simple(hostname, port, self._application)


def create_jsonrpc_server(service_cls: Callable, *,
                          serialize_factory: Type[JsonRpcSerializer] = StandardJsonRpcSerializer):
    service_config = get_service_config(service_cls)
    service = service_cls()
    serializer = serialize_factory()
    method_names = [c.name for c in service_config.method_configs]
    return JsonRpcServer(service, serializer, method_names)
