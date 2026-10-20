"""Validated HTTP and provider boundaries."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Scope = Literal['masters_admissions', 'tokmok_admissions', 'logistics_tuition',
                'railway_tuition', 'calendar_fulltime_bachelor_specialist',
                'bachelor_programmes', 'bachelor_admissions', 'general_academic_policy']
Category = Literal['prospective student', 'current student', 'calendar']
Status = Literal['answered', 'refused', 'needs_clarification']


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Message(StrictModel):
    role: Literal['user', 'assistant']
    content: str = Field(min_length=1, max_length=6000)


class ChatRequest(StrictModel):
    question: str = Field(min_length=1, max_length=2000)
    history: list[Message] = Field(default_factory=list, max_length=12)
    category: Category | None = None
    academic_year: str = Field(default='2026-2027', pattern=r'^20\d{2}-20\d{2}$')
    scope: Scope | None = None

    @field_validator('question')
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError('Question must contain text')
        return value.strip()

    @model_validator(mode='after')
    def bound_history(self):
        if sum(len(message.content) for message in self.history) > 20000:
            raise ValueError('Conversation history is too long')
        return self


class EvidenceRef(StrictModel):
    chunk_id: str = Field(min_length=1, max_length=200)
    quote: str = Field(min_length=1, max_length=12000)


class Claim(StrictModel):
    text: str = Field(min_length=1, max_length=1800)
    evidence: list[EvidenceRef] = Field(min_length=1, max_length=5)


class Proposal(StrictModel):
    decision: Status
    clarification: str = Field(max_length=300)
    claims: list[Claim] = Field(max_length=8)


class ClaimVerdict(StrictModel):
    claim_index: int = Field(ge=0, le=7)
    entailed: bool
    audience_preserved: bool
    qualifiers_preserved: bool


class Verification(StrictModel):
    answers_question: bool
    audience_applicable: bool
    complete: bool
    injection_free: bool
    claims: list[ClaimVerdict] = Field(max_length=8)


class Citation(StrictModel):
    chunk_id: str
    chunk_ids: list[str]
    source_title: str
    source_url: str
    page_number: int | None
    url: str


class Grounding(StrictModel):
    prompt_version: str = 'kstu-grounding-v2'
    outcome: str
    provider_error: str | None = None
    retrieved: list[dict] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    retrieved_chunk_ids: list[str] = Field(default_factory=list)
    retrieved_selection_ids: list[str] = Field(default_factory=list)
    support_check: Verification | None = None
    provider_calls: int = 0
    usage: list[dict] = Field(default_factory=list)


class ChatResponse(StrictModel):
    status: Status
    answer: str
    citations: list[Citation]
    scope: Scope | None
    academic_year: str
    grounding: Grounding
