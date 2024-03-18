import os
import aiohttp
import sys
from cachetools import TTLCache
from wrapt import decorator
from collections.abc import Awaitable, Callable, Mapping
from fastapi import status
from fastapi.responses import Response as FastAPIResponse


__cache = TTLCache(sys.maxsize, ttl=1200)


def with_authorization(auth_check: Callable[[aiohttp.ClientResponse], bool]):
    """
    Accesses auth endpoint and invokes auth_check agains the response.
    Requires wrapped method to declare the access_token and response params.

    To disable authorization set the AUTH_ENABLED env var to 0.
    AUTH_ENDPOINT env var should contain a valid access token validation end point.
    """

    @decorator
    async def authorization(
        func,
        instance,
        args,
        kwargs: Mapping,
    ) -> Awaitable:
        if not int(os.environ.get('AUTH_ENABLED', 1)):
            return await func(*args, **kwargs)

        access_token = kwargs.get('access_token', '')
        if not access_token:
            __forbid_access(kwargs)
            return

        async def next(response: aiohttp.ClientResponse):
            if auth_check(response):
                return await func(*args, **kwargs)
            __forbid_access(kwargs)

        try:
            response = __cache[access_token]
            return await next(response)
        except KeyError:
            pass

        async with aiohttp.ClientSession() as session:
            async with session.get(
                os.environ['AUTH_ENDPOINT'],
                headers={'Authorization': access_token},
            ) as response:
                __cache[access_token] = response
                return await next(response)

    return authorization


def __forbid_access(kwargs: Mapping):
    resp: FastAPIResponse = kwargs.get('response', None)
    if resp:
        resp.status_code = status.HTTP_403_FORBIDDEN
