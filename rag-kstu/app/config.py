"""Server-only configuration. Secrets are never included in health responses."""
from dataclasses import dataclass, field
import os
from pathlib import Path
from dotenv import load_dotenv

APP_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL = 'openai/gpt-oss-120b'


@dataclass(frozen=True)
class Settings:
    api_key: str = field(repr=False)
    model: str = DEFAULT_MODEL
    index: Path = APP_ROOT / 'data/retrieval'
    embedding_config: Path = APP_ROOT / 'models/ollama-embedding.json'
    context_chars: int = 12000
    provider_concurrency: int = 2
    request_timeout: float = 60.0

    def __post_init__(self):
        if not self.api_key.strip():
            raise ValueError('GROQ_API_KEY is missing')
        if self.model not in {DEFAULT_MODEL, 'openai/gpt-oss-20b'}:
            raise ValueError('GROQ_MODEL is not supported by the verified strict-schema configuration')
        if not 5000 <= self.context_chars <= 100000:
            raise ValueError('Invalid context size')
        if not 1 <= self.provider_concurrency <= 4 or not 5 <= self.request_timeout <= 120:
            raise ValueError('Invalid provider limits')

    @classmethod
    def from_env(cls):
        load_dotenv(APP_ROOT / '.env', override=False)
        return cls(api_key=os.getenv('GROQ_API_KEY', ''), model=os.getenv('GROQ_MODEL', DEFAULT_MODEL),
                   index=Path(os.getenv('KSTU_INDEX', str(APP_ROOT / 'data/retrieval'))),
                   embedding_config=Path(os.getenv('KSTU_EMBEDDING_CONFIG', str(APP_ROOT / 'models/ollama-embedding.json'))))
