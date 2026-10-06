"""100 client routing uses no speech model; it does NOT accept100 phone calls."""
import asyncio
import gc
import json
import time
import weakref
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from packages.contracts.providers import ProviderUnavailable
from services.providers.replica_pool import ReplicaPool
from services.stt.http_provider import HttpSTTProvider
from services.tts.http_provider import HttpTTSProvider


def test_100_live_independent_clients_do_not_all_hit_first_replica():
    providers = [HttpSTTProvider('http://start-a:9101,http://start-b:9101') for _ in range(100)]
    with ThreadPoolExecutor(max_workers=16) as threads:
        first = list(threads.map(lambda p: p._pool.order()[0], providers))
    assert Counter(first) == {'http://start-a:9101': 50, 'http://start-b:9101': 50}


def test_tts_clients_share_distribution_without_changing_retry_order():
    clients = [HttpTTSProvider('http://voice-a:9102,http://voice-b:9102') for _ in range(4)]
    assert [p._pool.order() for p in clients] == [
        ['http://voice-a:9102', 'http://voice-b:9102'],
        ['http://voice-b:9102', 'http://voice-a:9102'],
        ['http://voice-a:9102', 'http://voice-b:9102'],
        ['http://voice-b:9102', 'http://voice-a:9102'],
    ]


def test_distinct_configs_and_single_endpoint_preserve_independent_behavior():
    a = ReplicaPool(['independent-a', 'independent-b'])
    b = ReplicaPool(['independent-c', 'independent-d'])
    assert a.order()[0] == 'independent-a'
    assert b.order()[0] == 'independent-c'
    one = ReplicaPool(['single'])
    assert one.order() == one.order() == ['single']


def test_concurrent_pool_creation_and_expired_configs_release_cursor():
    with ThreadPoolExecutor(max_workers=16) as threads:
        pools = list(threads.map(
            lambda _: ReplicaPool(['construction-a', 'construction-b']), range(100)))
        first = list(threads.map(lambda pool: pool.order()[0], pools))
    assert Counter(first) == {'construction-a': 50, 'construction-b': 50}
    ref = weakref.ref(pools[0]._cursor)
    pools.clear()
    gc.collect()
    assert ref() is None


def test_100_independent_http_clients_keep_call_identity_and_balanced_requests():
    # Genuine adapter requests with controlled HTTP responses. No model/SIP capacity claim.
    async def scenario():
        bodies = []

        async def respond(request):
            await asyncio.sleep(0)
            body = json.loads(request.content)
            bodies.append((request.url.host, body))
            return httpx.Response(200, json={
                'text': 'Я выспалась.', 'asr_quality': 'GOOD', 'is_final': True})

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            providers = [HttpSTTProvider('http://http-a,http://http-b', client=client)
                         for _ in range(100)]
            results = await asyncio.gather(*[
                p.transcribe_final(b'\x00\x00' * 320, 16000, call_id=f'call-{i}',
                                   turn_id=1, utterance_id=f'u-{i}',
                                   deadline=time.monotonic() + 5)
                for i, p in enumerate(providers)
            ])
        assert Counter(host for host, _ in bodies) == {'http-a': 50, 'http-b': 50}
        assert {body['call_id'] for _, body in bodies} == {f'call-{i}' for i in range(100)}
        assert len({body['request_id'] for _, body in bodies}) == 100
        assert all(body['utterance_id'] == 'u-' + body['call_id'].removeprefix('call-')
                   for _, body in bodies)
        assert all(r.text == 'Я выспалась.' and r.is_final for r in results)

    asyncio.run(scenario())


def test_optional_prefixes_rotate_once_without_retry_on_busy_replica():
    async def scenario():
        hosts = []

        def busy(request):
            hosts.append(request.url.host)
            assert request.url.path == '/v1/preview'
            return httpx.Response(503, json={'error': 'busy'})

        async with httpx.AsyncClient(transport=httpx.MockTransport(busy)) as client:
            providers = [HttpSTTProvider('http://prefix-a,http://prefix-b', client=client,
                                         prefix_previews=True) for _ in range(4)]
            for i, provider in enumerate(providers):
                with pytest.raises(ProviderUnavailable, match='503'):
                    await provider.transcribe_partial(b'\x00\x00' * 16000, 16000,
                                                      call_id=f'p-{i}', partial_id='preview')
        assert hosts == ['prefix-a', 'prefix-b', 'prefix-a', 'prefix-b']

    asyncio.run(scenario())
