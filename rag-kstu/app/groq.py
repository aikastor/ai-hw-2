"""One bounded Groq client without tools or model substitution."""
import asyncio
import json
import math
import re
import httpx
from pydantic import ValidationError
from scripts.build_chunks import token_count
from .config import Settings


class ServiceUnavailable(Exception):
    def __init__(self, code='provider_unavailable', retry_after=None):
        self.code = code
        self.retry_after = retry_after
        super().__init__(code)


class InvalidOutput(Exception):
    pass


class GroqClient:
    def __init__(self, settings: Settings, transport=None):
        self.settings = settings
        self.semaphore = asyncio.Semaphore(settings.provider_concurrency)
        self.request_count = 0
        self.usage = {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}
        self.client = httpx.AsyncClient(
            base_url='https://api.groq.com/openai/v1',
            headers={'Authorization': 'Bearer ' + settings.api_key},
            timeout=httpx.Timeout(settings.request_timeout, connect=5.0, pool=5.0),
            limits=httpx.Limits(max_connections=settings.provider_concurrency, max_keepalive_connections=2),
            follow_redirects=False, trust_env=False, transport=transport)

    async def close(self):
        await self.client.aclose()

    async def _request(self, method, path, **kwargs):
        try:
            async with asyncio.timeout(130):
                async with self.semaphore:
                    for attempt in range(2):
                        self.request_count += 1
                        response = await self.client.request(method, path, **kwargs)
                        if response.status_code != 429:
                            break
                        try:
                            retry_after = response.headers.get('retry-after')
                            if retry_after is not None:
                                delay = float(retry_after)
                            else:
                                reset = response.headers.get('x-ratelimit-reset-tokens', '')
                                parts = re.findall(r'(\d+(?:\.\d+)?)(ms|s|m|h)', reset)
                                if parts and ''.join(value + unit for value, unit in parts) == reset:
                                    scales = {'ms': 0.001, 's': 1, 'm': 60, 'h': 3600}
                                    delay = sum(float(value) * scales[unit] for value, unit in parts)
                                else:
                                    delay = 60.0
                        except ValueError:
                            delay = 60.0
                        if attempt or not math.isfinite(delay) or not 0 <= delay <= 60:
                            retry = str(min(60, max(1, delay))) if math.isfinite(delay) else None
                            raise ServiceUnavailable('provider_rate_limited', retry)
                        await asyncio.sleep(max(0.1, delay))
        except (httpx.RequestError, TimeoutError) as error:
            raise ServiceUnavailable('provider_timeout') from error
        if not response.is_success:
            if response.status_code == 400:
                try:
                    error = response.json().get('error', {})
                    code = error.get('code')
                    if code == 'json_validate_failed':
                        raise InvalidOutput('provider_schema_generation_failed')
                except (ValueError, AttributeError):
                    pass
            raise ServiceUnavailable('provider_configuration' if response.status_code in (400, 401, 403, 404)
                                     else 'provider_unavailable')
        try:
            return response.json()
        except (ValueError, UnicodeDecodeError) as error:
            raise ServiceUnavailable('provider_protocol') from error

    async def ready(self):
        data = await self._request('GET', '/models')
        if not isinstance(data, dict) or self.settings.model not in {
            row.get('id') for row in data.get('data', []) if isinstance(row, dict)
        }:
            raise ServiceUnavailable('provider_model_unavailable')

    async def complete(self, instruction, payload, model_type):
        schema = model_type.model_json_schema()
        quote_options = {}
        if model_type.__name__ == 'Proposal' and payload.get('evidence'):
            references = schema['$defs']['EvidenceRef']['properties']
            del references['chunk_id']
            schema['$defs']['EvidenceRef']['required'] = ['quote']
            evidence = []
            for row in payload['evidence']:
                options = []
                for line in dict.fromkeys(line.strip() for line in row['text'].splitlines() if line.strip()):
                    handle = 'Q' + str(len(quote_options))
                    quote_options[handle] = {'id': handle, 'chunk_id': row['chunk_id'], 'quote': line}
                    options.append({'id': handle, 'quote': line})
                evidence.append(dict({key: value for key, value in row.items() if key != 'text'}, quote_options=options))
            if not quote_options:
                raise InvalidOutput('no_quote_options')
            references['quote']['enum'] = list(quote_options)
            references['quote']['description'] = 'The id of one supplied quote option, such as Q0.'
            payload = dict(payload, evidence=evidence)
        body = {
            'model': self.settings.model, 'temperature': 0, 'max_completion_tokens': 2000,
            'reasoning_effort': 'low',
            'messages': [{'role': 'system', 'content': instruction},
                         {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}],
            'response_format': {'type': 'json_schema', 'json_schema': {
                'name': model_type.__name__.lower(), 'strict': True,
                'schema': schema}}}
        # cl100k is a conservative reproducible input budget, not the provider tokenizer.
        if token_count(json.dumps(body, ensure_ascii=False)) > 6500:
            raise InvalidOutput('provider_input_budget_exceeded')
        response = await self._request('POST', '/chat/completions', json=body)
        try:
            choice = response['choices'][0]
            if choice.get('finish_reason') != 'stop':
                raise InvalidOutput('incomplete_provider_output')
            content = json.loads(choice['message']['content'])
            if quote_options:
                for claim in content['claims']:
                    for reference in claim['evidence']:
                        if not isinstance(reference, dict) or set(reference) != {'quote'}:
                            raise InvalidOutput('invalid_quote_reference_shape')
                        option = quote_options.get(reference['quote'])
                        if option is None:
                            raise InvalidOutput('invalid_quote_handle')
                        reference.update(chunk_id=option['chunk_id'], quote=option['quote'])
            parsed = model_type.model_validate(content)
            usage = response.get('usage', {})
            for key in self.usage:
                value = usage.get(key, 0)
                if type(value) is int and value >= 0:
                    self.usage[key] += value
            return parsed, usage
        except (KeyError, IndexError, TypeError, ValidationError, ValueError) as error:
            raise InvalidOutput('malformed_provider_output') from error
