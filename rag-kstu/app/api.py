"""Run one Uvicorn worker. The retriever never leaves its owner thread."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from .config import Settings
from .groq import GroqClient, ServiceUnavailable
from .grounding import PROMPT_VERSION, answer
from .models import ChatRequest, ChatResponse


class RetrievalOwner:
    def __init__(self, factory):
        self.factory = factory
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='kstu-retrieval')
        self.retriever = None
        self.available_scopes = frozenset()
        self.queue = asyncio.Semaphore(8)

    async def _run(self, function):
        try:
            async with asyncio.timeout(90):
                async with self.queue:
                    return await asyncio.get_running_loop().run_in_executor(self.executor, function)
        except TimeoutError as error:
            raise ServiceUnavailable('retrieval_timeout') from error

    async def open(self):
        def construct():
            self.retriever = self.factory()
            from scripts.retrieval import scope_for
            self.available_scopes = frozenset(scope_for(chunk) for chunk in getattr(self.retriever, 'chunks', []))
        await self._run(construct)

    async def search(self, query, **filters):
        return await self._run(lambda: self.retriever.search(query, **filters))

    async def ready(self):
        def check():
            self.retriever._check_corpus()
            self.retriever.embedder._verify_identity()
        await self._run(check)

    async def close(self):
        if self.retriever is not None:
            await asyncio.get_running_loop().run_in_executor(self.executor, self.retriever.close)
        self.executor.shutdown(wait=True, cancel_futures=True)


def default_retriever(settings):
    from scripts.retrieval import Retriever
    return Retriever(settings.index, settings.embedding_config)


def create_app(settings=None, retriever_factory=None, provider_factory=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.error = None
        app.state.owner = None
        app.state.provider = None
        try:
            app.state.settings = settings or Settings.from_env()
            app.state.provider = (provider_factory or GroqClient)(app.state.settings)
            app.state.owner = RetrievalOwner(retriever_factory or (lambda: default_retriever(app.state.settings)))
            await app.state.owner.open()
        except (ValueError, OSError, ServiceUnavailable):
            app.state.error = 'configuration_or_retrieval_unavailable'
        try:
            yield
        finally:
            if app.state.owner is not None:
                await app.state.owner.close()
            if app.state.provider is not None:
                await app.state.provider.close()

    app = FastAPI(title='KSTU reviewed-source chat', lifespan=lifespan)

    def require_ready():
        if app.state.error:
            raise HTTPException(503, detail={'code': app.state.error, 'retryable': True})

    @app.get('/health')
    async def health():
        require_ready()
        try:
            await app.state.owner.ready()
            await app.state.provider.ready()
        except (ValueError, OSError, ServiceUnavailable):
            return JSONResponse(status_code=503, content={'ready': False, 'code': 'dependency_unavailable'})
        return {'ready': True, 'model': app.state.settings.model, 'prompt_version': PROMPT_VERSION,
                'provider_requests': getattr(app.state.provider, 'request_count', 0),
                'provider_usage': getattr(app.state.provider, 'usage', [])}

    @app.post('/chat', response_model=ChatResponse)
    async def chat(request: ChatRequest):
        require_ready()
        try:
            return await answer(request, app.state.owner, app.state.provider, app.state.settings)
        except ServiceUnavailable as error:
            headers = {'Retry-After': error.retry_after} if error.retry_after else None
            raise HTTPException(503, detail={'code': error.code, 'retryable': True}, headers=headers) from error
        except (ValueError, OSError) as error:
            raise HTTPException(503, detail={'code': 'retrieval_unavailable', 'retryable': True}) from error

    return app


app = create_app()
