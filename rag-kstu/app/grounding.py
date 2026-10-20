"""Scope policy and evidence validation, independent of HTTP transport."""
import json
import re
from pathlib import Path
from urllib.parse import urlsplit
from .groq import InvalidOutput, ServiceUnavailable
from scripts.build_chunks import token_count
from .models import ChatRequest, ChatResponse, Citation, Grounding, Proposal, Verification

FALLBACK = 'I could not find enough reviewed source information to answer this question. Please specify the programme or rule you mean.'
PROMPT_VERSION = 'kstu-grounding-v2'
PROMPTS = Path(__file__).resolve().parent / 'prompts'
GENERATION_PROMPT = (PROMPTS / 'generate.txt').read_text(encoding='utf-8')
VERIFICATION_PROMPT = (PROMPTS / 'verify.txt').read_text(encoding='utf-8')
SCOPE_PATTERNS = [
    ('logistics_tuition', r'logistic|логист'),
    ('railway_tuition', r'railway|railroad|железнодорож|ижс\b|автомобильные дороги'),
    ('tokmok_admissions', r'tokmok|токмок'),
    ('calendar_fulltime_bachelor_specialist', r'calendar|календар|registration|регистрац|exam|экзамен|holiday|праздник|nooruz|нооруз|new year|новый год'),
    ('masters_admissions', r'master|магистр'),
]



def refusal_message(question, reason):
    russian = bool(re.search(r'[а-яё]', question.lower()))
    messages = {
        'unsupported_year': ('В базе проверены материалы для 2026–2027 учебного года. Для запрошенного года подтверждённых сведений нет.', 'The reviewed dataset covers 2026–2027. I do not have verified information for the requested year.'),
        'archive_only_policy': ('В этой базе есть только архивные сведения об этом правиле. По ним нельзя подтвердить действующие условия.', 'This dataset has only archived information about this rule, so I cannot confirm the current conditions.'),
        'archive_only_gpa': ('В этой базе нет проверенного правила расчёта GPA для действующих студентов. Условия поступления в магистратуру не заменяют это правило.', 'This dataset has no reviewed GPA calculation rule for enrolled students. Master’s admission requirements do not establish that rule.'),
        'unsupported_programme': ('Для указанной программы нет проверенных условий в выбранных таблицах. Уточните институт и точное название программы.', 'The selected tables do not establish conditions for this programme. Please specify the institute and exact programme name.'),
        'unsupported_audience': ('Для этой категории обучающихся в базе нет проверенных сведений по вопросу. Уточните уровень и форму обучения.', 'I have no reviewed information for this student group on this question. Please specify the degree level and study mode.'),
        'unsupported_university_wide_rule': ('Проверенные документы не подтверждают единое правило для всего университета. Уточните институт и программу.', 'The reviewed documents do not establish a university-wide rule. Please specify the institute and programme.'),
        'unsupported_bachelor_rule': ('В проверенных материалах нет подтверждения этого условия поступления на бакалавриат на 2026–2027 год. Уточните категорию поступления и конкретное условие.', 'The reviewed sources do not confirm this bachelor admission condition for 2026–2027. Please specify your applicant category and the condition you need.'),
        'unsupported_calendar_audience': ('В базе нет проверенного календаря для указанного уровня или формы обучения. Календарь очного бакалавриата нельзя применить к другой категории.', 'There is no reviewed calendar for this degree level or study mode. The full-time bachelor calendar cannot establish dates for another group.'),
        'unreviewed_bachelor_threshold_or_quota': ('Проверенный порог ОРТ или число грантовых мест на 2026–2027 год в базе отсутствует. Список документов не подтверждает эти значения.', 'The dataset has no reviewed ORT threshold or grant quota for 2026–2027. The document checklist does not establish these values.'),
        'unsupported_railway_audience': ('Проверенная таблица железнодорожного института не подтверждает стоимость для указанной категории иностранных студентов.', 'The reviewed railway institute table does not establish tuition for this category of foreign students.'),
        'support_check_failed': ('Не удалось подтвердить ответ целиком по найденным источникам. Уточните конкретную программу или задайте отдельно один вопрос о правиле.', 'I could not verify the complete answer against the retrieved sources. Please specify the programme or ask about one part of the rule at a time.'),
    }
    if reason in ('unsupported_or_invalid_proposal', 'invalid_clarification'):
        reason = 'support_check_failed'
    default = ('В проверенных источниках не удалось найти достаточно сведений для ответа. Уточните программу или правило, которое вас интересует.', FALLBACK)
    return messages.get(reason, default)[0 if russian else 1]

def scope_hint(text):
    for scope, pattern in SCOPE_PATTERNS:
        if re.search(pattern, text.lower()):
            return scope
    return None


def expanded_scope(text, available_scopes):
    q = text.lower()
    admissions = bool(re.search(r'admission|applicant|прием|приём|поступ|абитуриент', q))
    current_gpa = bool(re.search(r'\bgpa\b|средн.{0,12}балл', q)) and (bool(re.search(r'enrolled|current.student|обучающ|успеваем', q)) or not (admissions or re.search(r'master|магистр', q)))
    policy = bool(re.search(r'retake|re-sit|resit|пересда|академическ.{0,12}отпуск|academic leave|апелляц|appeal', q))
    if 'general_academic_policy' in available_scopes and (policy or current_gpa):
        return 'general_academic_policy'
    if re.search(r'master|магистр|tokmok|токмок|doctoral|докторант', q):
        return None
    programmes = bool(re.search(r'программ|направлени|специальност|program(?:me)?s?|degrees?|после школы|after school', q))
    listing = bool(re.search(r'каки|доступ|есть|предлага|which|what|available|offer|список|list', q))
    documents = bool(re.search(r'document|checklist|документ|аттестат|фото|photo', q))
    school = bool(re.search(r'bachelor|бакалавр|после школы|after school|11.{0,8}(?:класс|grade)|school.leaver', q))
    if 'bachelor_admissions' in available_scopes and documents and (school or admissions):
        return 'bachelor_admissions'
    if 'bachelor_programmes' in available_scopes and programmes and listing and not re.search(r'tuition|стоимост|оплат|стоит|сом|fee', q):
        return 'bachelor_programmes'
    return None


def resolve_request(request: ChatRequest, available_scopes=frozenset()):
    question = request.question.lower()
    explicit = expanded_scope(question, available_scopes) or scope_hint(question)
    # Calendar language about masters/doctoral audiences must not become a bachelor filter.
    if re.search(r'master|магистр', question) and explicit == 'calendar_fulltime_bachelor_specialist':
        explicit = 'masters_admissions'
    scope = explicit or request.scope
    prior_users = [message.content for message in request.history if message.role == 'user']
    if scope is None:
        scope = next((hint for text in reversed(prior_users) if (hint := expanded_scope(text, available_scopes) or scope_hint(text))), None)
    year_match = re.search(r'\b(20\d{2})[\s/–-]+(20\d{2})\b', question)
    year = '-'.join(year_match.groups()) if year_match else request.academic_year
    # Recent user turns resolve pronouns; assistant text never supplies scope or facts.
    context = '\n'.join(prior_users[-3:] + [request.question])
    return scope, year, context


def preflight(request, scope, year, context, available_scopes=frozenset()):
    q = request.question.lower()
    if year != '2026-2027':
        return 'refused', refusal_message(request.question, 'unsupported_year'), 'unsupported_year'
    if 'general_academic_policy' not in available_scopes and re.search(r'retake|re-sit|resit|пересда|академическ.{0,12}отпуск|academic leave', q):
        return 'refused', refusal_message(request.question, 'archive_only_policy'), 'archive_only_policy'
    if 'general_academic_policy' not in available_scopes and re.search(r'\bgpa\b|средн.{0,12}балл', q) and (re.search(r'enrolled|current.student|failed|repeated|обучающ|успеваем', q) or not re.search(r'master|магистр|admission|прием|приём', q + ' ' + context.lower())):
        return 'refused', refusal_message(request.question, 'archive_only_gpa'), 'archive_only_gpa'
    if re.search(r'outside.{0,50}(?:table|programme|program)|unlisted.{0,20}(?:programme|program)|не (?:входит|указан).{0,30}(?:таблиц|программ)', q):
        return 'refused', refusal_message(request.question, 'unsupported_programme'), 'unsupported_programme'
    if re.search(r'doctoral|ph\.?d|докторант|аспирант', q):
        return 'refused', refusal_message(request.question, 'unsupported_audience'), 'unsupported_audience'
    if scope not in ('bachelor_programmes', 'bachelor_admissions', 'general_academic_policy') and re.search(r'university.wide|всех.{0,12}бакалавр|общеуниверситет', q):
        return 'refused', refusal_message(request.question, 'unsupported_university_wide_rule'), 'unsupported_university_wide_rule'
    programme_question = bool(re.search(r'программ|направлени|специальност|program(?:me)?s?|degrees?|после школы|after school', q))
    if programme_question and re.search(r'каки|доступ|есть|предлага|which|what|available|offer', q) and scope is None:
        text = 'Какой институт или филиал вас интересует? В проверенных материалах есть отдельные сведения по Токмоку, логистике и железнодорожным направлениям; полного каталога программ пока нет.' if re.search(r'[а-яё]', q) else 'Which institute or branch interests you? The reviewed sources cover selected Tokmok, logistics and railway programmes; a complete programme catalogue is not available here.'
        return 'needs_clarification', text, 'programme_institute_missing'
    admissions = bool(re.search(r'admission|applicant|checklist|прием|приём|поступ|абитуриент|\bort\b|\bорт\b|grant|грант', q))
    bachelor = bool(re.search(r'bachelor|бакалавр', q))
    if admissions and bachelor and scope not in ('tokmok_admissions', 'bachelor_admissions'):
        return 'refused', refusal_message(request.question, 'unsupported_bachelor_rule'), 'unsupported_bachelor_rule'
    calendar = bool(re.search(r'calendar|календар|registration|регистрац|examin|экзамен|holiday|праздник', q))
    if calendar and re.search(r'master|магистр|part.time|заочн', q):
        return 'refused', refusal_message(request.question, 'unsupported_calendar_audience'), 'unsupported_calendar_audience'
    if scope == 'bachelor_admissions' and re.search(r'threshold|minimum.{0,15}score|порог|проходн|квот|quota|число.{0,15}грант', q):
        return 'refused', refusal_message(request.question, 'unreviewed_bachelor_threshold_or_quota'), 'unreviewed_bachelor_threshold_or_quota'
    if admissions and scope is None:
        return 'needs_clarification', 'Do you mean master’s admission or admission at the Tokmok branch?', 'admissions_audience_missing'
    fee = bool(re.search(r'tuition|per.credit|стоимост|обучени.{0,12}стоит|кредит.{0,12}сом|сколько.{0,15}обучен', q))
    fee = fee or scope in ('logistics_tuition', 'railway_tuition')
    if fee:
        if scope not in ('logistics_tuition', 'railway_tuition'):
            return 'needs_clarification', 'Which institute, programme, course, nationality group and study mode do you mean?', 'tuition_audience_missing'
        all_text = context.lower()
        if scope == 'railway_tuition' and re.search(r'foreign|иностран|не граждан|not.{0,12}kyrgyz', q):
            return 'refused', refusal_message(request.question, 'unsupported_railway_audience'), 'unsupported_railway_audience'
        has_country = re.search(r'kyrgyz|kyrgyzstan|кыргыз|киргиз|\bкр\b|near.foreign|ближн.{0,12}зарубеж|intergovernment|межправ', all_text)
        has_mode = re.search(r'full.time|очно|очная|extramural|distance|заоч|дот|\bdot\b', all_text)
        has_course = re.search(r'first|second|third|fourth|fifth|sixth|[1-6].{0,8}(?:year|course|курс)|перв|втор|трет|четвер|пят|шест|все.{0,6}курс', all_text)
        if not (has_country and has_mode and has_course):
            return 'needs_clarification', 'Which nationality group, course and study mode should I use for this institute?', 'tuition_qualifiers_missing'
    return None


def retrieval_query(request, context):
    q = request.question
    lower = q.lower()
    terms = []
    vocabulary = [
        (r'программ|направлени|после школы|program|after school', 'бакалавр специалитет направления подготовки профиль'),
        (r'\bgpa\b|средн.{0,12}балл', 'GPA средний балл кредиты формула'),
        (r'confirm|подтверд', 'подтвердить согласие на зачисление договор оплата'),
        (r'foreign|иностран', 'граждане иностранных государств исключением международными договорами'),
        (r'winter|зимн', 'зимняя экзаменационная сессия январь'),
        (r'summer|летн', 'летняя экзаменационная сессия июнь'),
        (r'grant|грант', 'образовательный грант конкурс'),
        (r'photo|medical|фото|медицин', 'фотографии медицинская справка'),
        (r'nooruz', 'Нооруз'),
        (r'new year', 'Новый год'),
    ]
    for pattern, translation in vocabulary:
        if re.search(pattern, lower):
            terms.append(translation)
    if re.search(r'\bthat\b|\bit\b|\bthose\b|эт(?:а|от|ой|ого|ом|и)|там', lower):
        user_context = context.rsplit('\n', 1)[0]
        q = user_context[-3000:] + '\n' + q
    return q + '\n' + ' '.join(terms) if terms else q


def select_context(hits, request, scope, year, limit):
    selected, size, tokens = [], 0, 0
    for hit in hits:
        if (hit.get('eligibility') != 'current' or hit.get('current_answer_eligible') is not True
                or hit.get('university_id') != 'kstu' or hit.get('academic_year') != year
                or (scope is not None and hit.get('scope') != scope)
                or (request.category is not None and request.category not in
                    [hit.get('category')] + hit.get('additional_categories', []))):
            continue
        item = {key: hit[key] for key in ('chunk_id', 'selection_id', 'scope', 'source', 'source_url',
                                          'academic_year', 'audience_restrictions', 'limitations', 'text', 'topic')}
        publication_year = hit.get('effective_date_evidence', {}).get('publication_year')
        if type(publication_year) is int:
            item['publication_year'] = publication_year
        item['pages'] = sorted({reference['page_number'] for reference in hit['citations']})
        amount = len(json.dumps(item, ensure_ascii=False))
        item_tokens = token_count(json.dumps(item, ensure_ascii=False))
        if size + amount <= limit and tokens + item_tokens <= 2500:
            selected.append(item)
            size += amount
            tokens += item_tokens
    return selected


def numbers(text):
    values = set()
    # Grouped monetary values normalize to the literal numbers printed in tables.
    text = re.sub(r'\b\d{1,3}(?:[,\s]\d{3})+\b', lambda match: re.sub(r'\D', '', match[0]), text)
    text = re.sub(r'(?<=\d),(?=\d{1,2}\b)', '.', text)
    for value in re.findall(r'\d+(?:\.\d+)?', text):
        if '.' in value and len(value.rsplit('.', 1)[1]) != 2:
            values.update(str(int(piece)) for piece in value.split('.'))
        else:
            values.add(value.lstrip('0') or '0')
    # Dates such as 11.01.2027 must also support translated day/month/year forms.
    for day, month, year in re.findall(r'\b(\d{1,2})\.(\d{1,2})\.(20\d{2})\b', text):
        values.update((str(int(day)), str(int(month)), year))
    return values


def validate_proposal(proposal, selected):
    if proposal.decision != 'answered' or not proposal.claims or proposal.clarification:
        return False
    by_id = {row['chunk_id']: row for row in selected}
    for claim in proposal.claims:
        if re.search(r'<[^>]*>|https?://|\]\(', claim.text):
            return False
        supported_numbers = set()
        for ref in claim.evidence:
            chunk = by_id.get(ref.chunk_id)
            if chunk is None or not ref.quote.strip():
                return False
            if ref.quote not in chunk['text']:
                pattern = r'\s+'.join(re.escape(part) for part in ref.quote.split())
                match = re.search(pattern, chunk['text'])
                if match is None:
                    return False
                ref.quote = match.group(0)
            supported_numbers.update(numbers(chunk['text'] + ' ' + chunk['academic_year']))
            if type(chunk.get('publication_year')) is int:
                supported_numbers.add(str(chunk['publication_year']))
        if not numbers(claim.text).issubset(supported_numbers):
            return False
    return True


def verification_passed(verdict, count):
    return (verdict.answers_question and verdict.audience_applicable and verdict.complete and verdict.injection_free
            and sorted(row.claim_index for row in verdict.claims) == list(range(count))
            and all(row.entailed and row.audience_preserved and row.qualifiers_preserved for row in verdict.claims))


def compile_citations(claims, hits):
    by_id = {hit['chunk_id']: hit for hit in hits}
    citations = {}
    for claim in claims:
        for ref in claim.evidence:
            hit = by_id[ref.chunk_id]
            for source in hit['citations']:
                base = source['source_url'] if source['page_number'] is None else source['source_url'].split('#', 1)[0]
                parsed = urlsplit(base)
                if parsed.scheme != 'https' or parsed.hostname not in ('kstu.kg', 'www.kstu.kg'):
                    raise ValueError('Invalid official citation URL')
                key = (base, source['page_number'])
                if key not in citations:
                    citations[key] = Citation(chunk_id=ref.chunk_id, chunk_ids=[ref.chunk_id], source_title=hit['source'],
                                              source_url=base, page_number=source['page_number'],
                                              url=base if source['page_number'] is None else base + '#page=' + str(source['page_number']))
                elif ref.chunk_id not in citations[key].chunk_ids:
                    citations[key].chunk_ids.append(ref.chunk_id)
    return list(citations.values())


async def answer(request, retriever, provider, settings):
    available_scopes = getattr(retriever, 'available_scopes', frozenset())
    scope, year, context = resolve_request(request, available_scopes)
    grounding = Grounding(outcome='pending')

    def respond(status, text, outcome, citations=None):
        grounding.outcome = outcome
        if status == 'refused':
            text = refusal_message(request.question, outcome)
        elif status == 'needs_clarification' and re.search(r'[а-яё]', request.question.lower()):
            text = {
                'admissions_audience_missing': 'Вы спрашиваете о поступлении в магистратуру или в Токмокский филиал?',
                'tuition_audience_missing': 'Уточните институт, программу, курс, гражданство и форму обучения.',
                'tuition_qualifiers_missing': 'Уточните гражданство, курс и форму обучения для этого института.',
            }.get(outcome, text)
        return ChatResponse(status=status, answer=text, citations=citations or [], scope=scope,
                            academic_year=year, grounding=grounding)

    gate = preflight(request, scope, year, context, available_scopes)
    if gate:
        return respond(*gate)
    result = await retriever.search(retrieval_query(request, context), category=request.category,
                                    academic_year=year, scope=scope, top_k=8, mode='hybrid')
    selected = select_context(result['hits'], request, scope, year, settings.context_chars)
    grounding.retrieved = selected
    grounding.retrieved_chunk_ids = [row['chunk_id'] for row in selected]
    grounding.retrieved_selection_ids = list(dict.fromkeys(row['selection_id'] for row in selected))
    if not selected:
        return respond('refused', FALLBACK, 'no_eligible_evidence')
    payload = {'question': request.question, 'prior_user_messages': [message.content[-1000:] for message in request.history if message.role == 'user'][-3:],
               'academic_year': year, 'scope': scope, 'evidence': selected}
    try:
        grounding.provider_calls += 1
        proposal, usage = await provider.complete(GENERATION_PROMPT, payload, Proposal)
        grounding.usage.append(usage)
        if proposal.decision == 'needs_clarification' and not proposal.claims and proposal.clarification.strip():
            if re.search(r'https?://|<[^>]*>|\d', proposal.clarification):
                return respond('refused', FALLBACK, 'invalid_clarification')
            return respond('needs_clarification', proposal.clarification, 'provider_clarification')
        grounding.claims = proposal.claims
        if not validate_proposal(proposal, selected):
            return respond('refused', FALLBACK, 'unsupported_or_invalid_proposal')
        grounding.claims = proposal.claims
        grounding.provider_calls += 1
        verdict, usage = await provider.complete(VERIFICATION_PROMPT, dict(payload, evidence=[row for row in selected if row['chunk_id'] in {ref.chunk_id for claim in proposal.claims for ref in claim.evidence}], proposed_claims=[claim.model_dump() for claim in proposal.claims]), Verification)
        grounding.usage.append(usage)
        grounding.support_check = verdict
        if not verification_passed(verdict, len(proposal.claims)):
            return respond('refused', FALLBACK, 'support_check_failed')
        citations = compile_citations(proposal.claims, result['hits'])
        return respond('answered', '\n\n'.join(claim.text for claim in proposal.claims), 'validated', citations)
    except InvalidOutput as error:
        raise ServiceUnavailable('provider_invalid_output') from error
