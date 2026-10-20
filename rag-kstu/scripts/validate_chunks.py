#!/usr/bin/env python3
"""Independently verify the KSTU corpus against its frozen source allowlist."""
import argparse
from collections import Counter
import hashlib
import json
import re
from datetime import date
from pathlib import Path
import sys
import tempfile
from urllib.parse import urldefrag, urlparse

ROOT = Path(__file__).resolve().parents[2] if (Path(__file__).resolve().parent.parent / 'UNIVERSITY.md').exists() else Path.cwd()
sys.path.insert(0, str(ROOT / 'rag-kstu/scripts'))
from build_chunks import token_count

FALLBACK = 'Unfortunately, I do not have accurate information on this question. Please contact the Student Office (room 101).'
TOPICS = {'retakes', 'gpa', 'academic_leave', 'admissions_documents', 'thresholds', 'tuition', 'grants', 'examination_periods', 'course_registration', 'holidays'}
CATEGORIES = {'prospective student', 'current student', 'calendar'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def path_for(path):
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def read(path):
    return json.loads(path_for(path).read_text(encoding='utf-8'))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def check_hash(path, expected):
    require(isinstance(expected, str) and len(expected) == 64, f'Missing hash: {path}')
    require(digest(path_for(path).read_bytes()) == expected, f'Hash drift: {path}')


def reference_text(ref):
    """Read the approved artifact independently of the chunk builder."""
    check_hash(ref['artifact_path'], ref['artifact_sha256'])
    p = path_for(ref['artifact_path'])
    page = ref.get('page_number')
    require(page is None or type(page) is int and page >= 1, 'Invalid physical page')
    if ref['reader'] == 'text':
        text = p.read_text(encoding='utf-8')
    elif ref['reader'] == 'passage':
        found = [r for r in read(p)['passages'] if r['id'] == ref['passage_id']]
        require(len(found) == 1 and found[0]['page_number'] == page, 'Passage/page mismatch')
        text = found[0]['text']
    elif ref['reader'] == 'block':
        found = [r for r in read(p)['pages'] if r['page_number'] == page]
        require(len(found) == 1, 'Missing or duplicate physical page')
        index = ref['block_index']
        require(type(index) is int and 0 <= index < len(found[0]['blocks']), 'Invalid source block')
        block = found[0]['blocks'][index]
        text = (block.get('markdown') if block.get('type') == 'table' else block.get('text')) or block.get('text') or block.get('markdown')
    else:
        raise ValueError('Unknown artifact reader')
    require(isinstance(text, str) and bool(text.strip()), 'Empty approved text')
    require(digest(text.encode()) == ref['text_sha256'], 'Source text hash mismatch')
    start, end = ref.get('start', 0), ref.get('end', len(text))
    require(type(start) is int and type(end) is int and 0 <= start < end <= len(text), 'Invalid source slice')
    return text[start:end]


def joined(parts):
    return '\n\n'.join(parts)


def load_chunks(output):
    chunks = []
    for eligibility in ('current', 'archive'):
        for line in (path_for(output) / f'chunks.{eligibility}.jsonl').read_text().splitlines():
            chunk = json.loads(line)
            require(chunk['eligibility'] == eligibility, 'Chunk in wrong eligibility file')
            chunks.append(chunk)
    return chunks


def validate_review_authority(manifest):
    """Check policy decisions against separate review packets, not self-declared flags."""
    base = 'rag-kstu/data/enrichment/'
    policies = read(base + 'policies/findings.json')
    policy_sources = {s['source_sha256'] for s in policies['sources']}
    policy_refs = {(e['source_sha256'], b['page_number'], b['block_order'], b['text_sha256']) for e in policies['evidence'] for b in e['source_blocks']}
    calendar = read(base + 'calendar/findings.json')
    tuition = {r['source_sha256']: r for r in read(base + 'tuition/findings.json')['records']}
    admissions = read(base + 'admissions/findings.json')['claims']
    masters = read(base + 'admissions/masters-passages.json')
    authority = next(p for p in masters['passages'] if p['id'] == 'masters-authority')
    known_sources = policy_sources | set(tuition) | {calendar['source_sha256']} | {a['source_sha256'] for a in admissions}
    require({s['source_sha256'] for s in manifest['sources']} == known_sources, 'Source allowlist differs from reviewed enrichment evidence')
    for selection in manifest['selections']:
        h = selection['source_sha256']
        refs = selection['context'] + [r for u in selection['units'] for r in u['parts']]
        if h in policy_sources:
            require(selection['eligibility'] == 'archive' and selection['current_answer_eligible'] is False and selection['category'] == 'current student', 'Unresolved policy applicability cannot be promoted to current answers')
            require(all((h, r['page_number'], r.get('block_index'), r['text_sha256']) in policy_refs for r in refs), 'Policy block outside reviewed evidence')
            require(all(not e['current_answer_eligible'] for e in policies['evidence'] if e['source_sha256'] == h), 'Policy review requires reconciliation')
        elif h == calendar['source_sha256']:
            require(selection['category'] == 'calendar' and selection['eligibility'] == 'current', 'Calendar category/currentness mismatch')
            association = selection.get('event_association')
            require(association in calendar['records'], 'Calendar event association not reviewed')
            require([r.get('block_index') for r in selection['context']] == list(range(4)), 'Calendar year/audience context omitted')
            require([r.get('block_index') for u in selection['units'] for r in u['parts']] == association['source_block_indices'], 'Calendar cell/caption references differ from reviewed event')
            require(selection['audience_restrictions'] == [calendar['audience']] and selection['topic'] == [association['topic']], 'Calendar audience/topic mismatch')
        elif h in tuition:
            review = tuition[h]
            require(selection['eligibility'] == 'current' and selection['category'] == 'prospective student' and selection['topic'] == ['tuition'], 'Tuition reviewed mapping mismatch')
            approved = {b['index']: b['block_sha256'] for b in review['block_refs']}
            blocks = read(review['extraction_path'])['pages'][0]['blocks']
            for ref in refs:
                idx = ref.get('block_index')
                require(ref['artifact_path'] == review['extraction_path'] and ref['page_number'] == 1 and idx in approved, 'Tuition reference outside reviewed table')
                actual = hashlib.sha256(json.dumps(blocks[idx], ensure_ascii=False, sort_keys=True).encode()).hexdigest()
                require(actual == approved[idx], 'Tuition reviewed block hash mismatch')
            records = read('data/knowledge/selection.json')['records']
            require(any(r['source_sha256'] == h and r['page_number'] == 1 and r['decision'] == 'current' for r in records), 'Tuition lacks prior current decision')
            audience = review['audience_restrictions']
            require(selection['audience_restrictions'] == (audience if isinstance(audience, list) else [audience]), 'Tuition audience differs from review')
        else:
            require(selection['eligibility'] == 'current' and selection['category'] == 'prospective student', 'Admission reviewed mapping mismatch')
            claims = [a for a in admissions if a['source_sha256'] == h]
            require(claims and all(a['status'] == 'selected_passage_verified_current_scoped' for a in claims), 'Admissions authority missing')
            if h == masters['source_sha256']:
                require(any(r.get('passage_id') == 'masters-authority' and r['page_number'] == 1 and 'start' not in r and r['text_sha256'] == digest(authority['text'].encode()) for r in selection['context']), 'Masters source requires complete year/audience authority context')
                require(all(r['artifact_path'] == base + 'admissions/masters-passages.json' and r.get('passage_id') in {p['id'] for p in masters['passages']} for r in refs), 'Masters reference outside reviewed passages')
                require('gpa' not in selection['topic'], 'Master admission GPA cannot promote general GPA')
            else:
                require(selection['audience_restrictions'] == [claims[0]['scope']] and all(r['artifact_path'] == claims[0]['extraction_ref'] and r['page_number'] == 1 for r in refs), 'Tokmok scope differs from reviewed branch evidence')


def validate_records(manifest, chunks):
    """Validate already loaded records; exposed for corruption-control tests."""
    require(manifest['university_id'] == 'kstu', 'Wrong university manifest')
    for path, expected in manifest['inputs'].items():
        check_hash(path, expected)
    validate_review_authority(manifest)
    sources = {s['source_sha256']: s for s in manifest['sources']}
    require(len(sources) == len(manifest['sources']), 'Duplicate source identity')
    for h, s in sources.items():
        check_hash(s['original_path'], h)
        for prefix in ('extraction', 'selected_text'):
            if s.get(prefix + '_path'):
                check_hash(s[prefix + '_path'], s[prefix + '_sha256'])
        require(bool((s.get('source') or s.get('title') or '').strip()), 'Missing source title')
        require(urlparse(s['source_url']).hostname in {'kstu.kg', 'www.kstu.kg'}, 'Unofficial source URL')
    selections = {s['selection_id']: s for s in manifest['selections']}
    require(len(selections) == len(manifest['selections']), 'Duplicate selection ID')
    ids = set()
    by_selection = {key: [] for key in selections}
    text_cache = {}
    def text(ref):
        key = canonical(ref)
        if key not in text_cache:
            text_cache[key] = reference_text(ref)
        return text_cache[key]
    for s in selections.values():
        require(s['source_sha256'] in sources, 'Selection source not allowlisted')
        require(s['category'] in CATEGORIES and s['eligibility'] in {'current', 'archive'}, 'Unapproved selection metadata')
        require(s['current_answer_eligible'] is (s['eligibility'] == 'current'), 'Selection currentness decision mismatch')
        require(bool(s['audience_restrictions']) and bool(s['effective_date_evidence']) and bool(s['review_evidence']), 'Missing reviewed scope')
        if s['eligibility'] == 'current':
            require(s['academic_year'] == manifest['target_academic_year'], 'Wrong current academic year')
        for ref in s['context'] + [r for u in s['units'] for r in u['parts']]:
            text(ref)
            require(ref['page_number'] in sources[s['source_sha256']]['selected_pages'], 'Unapproved source page')
            require(manifest['inputs'].get(ref['artifact_path']) == ref['artifact_sha256'], 'Reference artifact not pinned')
        require(len({u['unit_id'] for u in s['units']}) == len(s['units']), 'Duplicate selected unit')
    for c in chunks:
        cid = c['chunk_id']
        require(cid not in ids, 'Duplicate chunk ID')
        ids.add(cid)
        require(c['selection_id'] in selections, 'Unapproved/withheld selection emitted')
        s = selections[c['selection_id']]
        source = sources[s['source_sha256']]
        require(c['university_id'] == 'kstu', 'Foreign university emitted')
        for field in ('source_sha256', 'category', 'additional_categories', 'topic', 'academic_year', 'effective_date_evidence', 'audience_restrictions', 'eligibility', 'recognition_status', 'review_evidence'):
            require(c[field] == s.get(field), f'Chunk {field} differs from reviewed selection')
        require(c['category'] in CATEGORIES, 'Invalid category')
        if 'current_answer_eligible' in c:
            require(c['current_answer_eligible'] is s['current_answer_eligible'], 'Chunk current eligibility mismatch')
        require(c['eligibility'] != 'current' or s['current_answer_eligible'] is True, 'Withheld or archive text in current output')
        for field in ('source_url', 'original_path'):
            require(c[field] == source[field], f'Chunk {field} mismatch')
        require(c['source'] == (source.get('source') or source['title']), 'Chunk display title mismatch')
        units = {u['unit_id']: u for u in s['units']}
        require(bool(c['unit_ids']) and len(c['unit_ids']) == len(set(c['unit_ids'])), 'Missing/duplicate chunk units')
        require(all(uid in units for uid in c['unit_ids']), 'Unapproved unit emitted')
        body = [r for uid in c['unit_ids'] for r in units[uid]['parts']]
        require(c['extraction_provenance'] == {'context': s['context'], 'body': body}, 'Source provenance mismatch')
        context_values = [text(r) for r in s['context']]
        unit_values = [joined([text(r) for r in units[uid]['parts']]) for uid in c['unit_ids']]
        if all(units[uid]['kind'] == 'table_rows' for uid in c['unit_ids']):
            expected_text = joined(context_values[:-1] + [context_values[-1].rstrip('\n') + '\n' + '\n'.join(v.rstrip('\n') for v in unit_values)])
        else:
            expected_text = joined(context_values + unit_values)
        require(c['text'] == expected_text, 'Chunk text differs from exact approved units')
        require(c['token_count'] == token_count(c['text']), 'Incorrect measured token count')
        require(c['tokenizer'] == {'name': manifest['settings']['tokenizer'], 'version': manifest['settings']['tokenizer_version']}, 'Tokenizer metadata mismatch')
        all_refs = s['context'] + body
        pdf = Path(source['original_path']).suffix.lower() == '.pdf'
        require(all((type(r['page_number']) is int and r['page_number'] >= 1) if pdf else r['page_number'] is None for r in all_refs), 'Invalid physical PDF/HTML page')
        require(c['page_number'] == all_refs[0]['page_number'] and c['body_page_number'] == body[0]['page_number'], 'First contributing physical page mismatch')
        citations = []
        for role, refs in (('context', s['context']), ('body', body)):
            for ref in refs:
                page = ref['page_number']
                citations.append(dict(ref, role=role, source_sha256=source['source_sha256'], source_url=source['source_url'], url=urldefrag(source['source_url'])[0] + f'#page={page}' if page else source['source_url']))
        require(c['citations'] == citations, 'Incomplete or wrong physical-page citations')
        count = c['token_count']
        exception = c['size_exception']
        require(bool(exception) == (count < 500 or count > 1000), 'Size exception missing or spurious')
        if exception:
            require(bool(exception['reason']) and exception['measured_tokens'] == count, 'Size exception measurement mismatch')
        payload = {k: v for k, v in c.items() if k != 'chunk_id'}
        require(cid == 'kstu-' + digest(canonical({'chunk': payload, 'settings': manifest['settings']}).encode()), 'Unstable or invalid chunk ID')
        by_selection[c['selection_id']].append(c)
    for sid, group in by_selection.items():
        s = selections[sid]
        selected = [u['unit_id'] for u in s['units']]
        cursor = 0
        previous = None
        unit_text = {u['unit_id']: joined([text(r) for r in u['parts']]) for u in s['units']}
        for c in group:
            overlap = c['overlap']
            shared = overlap['shared_unit_ids']
            if previous:
                require(overlap['previous_chunk_id'] == previous['chunk_id'], 'Overlap predecessor mismatch')
                require(shared == previous['unit_ids'][-len(shared):] if shared else True, 'Overlap is not a complete trailing unit suffix')
                require(c['unit_ids'][:len(shared)] == shared, 'Shared units not at next chunk start')
                shared_values = [unit_text[u] for u in shared]
                table_rows = {u['unit_id'] for u in s['units'] if u['kind'] == 'table_rows'}
                overlap_text = '\n'.join(v.rstrip('\n') for v in shared_values) if shared and set(shared) <= table_rows else joined(shared_values)
                measured = token_count(overlap_text) if shared else 0
                denominator = previous['token_count']
                require(overlap['shared_tokens'] == measured and overlap['denominator_tokens'] == denominator and overlap['ratio'] == measured / denominator, 'Incorrect measured semantic overlap')
                require(overlap['repeated_context_tokens'] == (token_count(joined([text(r) for r in s['context']])) if s['context'] else 0), 'Repeated context counted as overlap or wrong context count')
                require(0.10 <= measured / denominator <= 0.15 or bool(overlap['exception']), 'Missing overlap exception')
            else:
                require(overlap['previous_chunk_id'] is None and not shared and overlap['shared_tokens'] == 0 and overlap['denominator_tokens'] is None and overlap['ratio'] is None and overlap['repeated_context_tokens'] == 0, 'First chunk has false overlap')
            fresh = c['unit_ids'][len(shared):]
            require(bool(fresh) and fresh == selected[cursor:cursor + len(fresh)], 'Selected unit omission, duplication, or ordering error')
            cursor += len(fresh)
            previous = c
        require(cursor == len(selected), f'Unaccounted selected units: {sid}')
    sizes = [c['token_count'] for c in chunks]
    return {'source_count': len(sources), 'selection_count': len(selections), 'selected_unit_count': sum(len(s['units']) for s in selections.values()), 'chunk_counts': dict(Counter(c['eligibility'] for c in chunks)), 'size_distribution': {'minimum': min(sizes), 'maximum': max(sizes), 'under_500': sum(n < 500 for n in sizes), '500_to_1000': sum(500 <= n <= 1000 for n in sizes), 'over_1000': sum(n > 1000 for n in sizes)}, 'size_exception_count': sum(bool(c['size_exception']) for c in chunks), 'overlap_pairs': [dict(chunk_id=c['chunk_id'], **c['overlap']) for c in chunks if c['overlap']['previous_chunk_id']], 'unaccounted_selected_units': 0}


def validate_coverage(manifest, coverage):
    require({r['topic'] for r in coverage['topics']} == TOPICS and len(coverage['topics']) == 10, 'Coverage must contain all ten topics exactly once')
    current_topics = set()
    for row in coverage['topics']:
        selected = [s for s in manifest['selections'] if row['topic'] in s['topic']]
        current = [s for s in selected if s['eligibility'] == 'current']
        if current:
            current_topics.add(row['topic'])
        require(row['current_scoped_support'] is bool(current), 'Coverage current support mismatch')
        require(row['status'] == ('partial' if selected else 'missing'), 'Coverage overstates unresolved audience gaps')
        require(bool(row['next_action']) and bool(row['fallback_question']) and bool(row['remaining_gap']), 'Missing coverage gap/action/fallback')
        expected = [{'selection_id': s['selection_id'], 'source_sha256': s['source_sha256'], 'eligibility': s['eligibility'], 'academic_year': s['academic_year'], 'audience': s['audience_restrictions'], 'effective_date_evidence': s['effective_date_evidence'], 'references': s['context'] + [r for u in s['units'] for r in u['parts']]} for s in current + [s for s in selected if s['eligibility'] == 'archive']]
        require(row['evidence'] == expected, 'Coverage evidence differs from selected source scopes')
    require(coverage['topics_with_current_scoped_evidence'] == len(current_topics), 'Coverage count mismatch')
    require(coverage['full_assignment_coverage'] is False and 'gpa' not in current_topics, 'Admission GPA must not fill general GPA gap')
    return {'topics_with_current_scoped_evidence': len(current_topics), 'current_topics': sorted(current_topics), 'full_assignment_coverage': False}


def validate_questions(path, chunks):
    if not path.exists():
        return {'status': 'not_present'}
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    require(len(rows) >= 20, 'At least 20 evaluation cases required')
    refusals = [r for r in rows if r.get('refusal') is True or r.get('type') == 'refusal']
    tables = [r for r in rows if r.get('type') == 'table_lookup']
    require(len(refusals) >= 5 and len(tables) >= 3, 'Insufficient refusal/table lookup cases')
    for row in rows:
        require(bool(row.get('question')), 'Empty evaluation question')
        answer = row.get('expected_answer', row.get('answer'))
        require(bool(answer), 'Missing verified answer')
        if row in refusals:
            require(answer == FALLBACK, 'Wrong assignment fallback')
            continue
        refs = row.get('expected_references', row.get('expected_sources', []))
        fragments = row.get('evidence_fragments', [])
        require(refs and fragments, 'Answerable question requires references and exact evidence fragments')
        candidates = []
        for ref in refs:
            matches = [c for c in chunks if c['eligibility'] == 'current' and c['source_sha256'] == ref['source_sha256'] and (not row.get('selection_id') or c['selection_id'] == row['selection_id']) and any(x['page_number'] == ref['page_number'] for x in c['citations'])]
            require(bool(matches), 'Evaluation reference is not current corpus evidence')
            candidates.extend(matches)
        evidence = '\n\n'.join(c['text'] for c in candidates)
        require(all(isinstance(fragment, str) and fragment and fragment in evidence for fragment in fragments), 'Evaluation answer evidence fragment missing')
        selection_id = row.get('selection_id')
        if selection_id:
            require(any(c['selection_id'] == selection_id for c in candidates), 'Question selection does not match cited evidence')
        # Calendar dates can be reviewed cell/label associations rather than literal OCR strings.
        associations = [c.get('event_association') for c in candidates if c.get('event_association') and (not selection_id or c['selection_id'] == selection_id)]
        if associations:
            require(row.get('reviewed_event_association') in associations, 'Question calendar association differs from reviewed evidence')
            association = row['reviewed_event_association']
            dates = [date.fromisoformat(association[k]) for k in ('date', 'start_date', 'end_date') if k in association]
            if not dates:
                dates = [date(int(y), int(m), int(d)) for d, m, y in re.findall(r'(\d{2})\.(\d{2})\.(\d{4})', association['source_label'])]
            answer_numbers = {int(n) for n in re.findall(r'\d+', answer)}
            require(dates and all(d.day in answer_numbers and d.year in answer_numbers and (d.strftime('%B').lower() in answer.lower() or d.month in answer_numbers) for d in dates), 'Calendar expected answer dates differ from reviewed association')
        if selection_id:
            sample = next(c for c in candidates if c['selection_id'] == selection_id)
            require(row.get('audience') == sample['audience_restrictions'] and row.get('academic_year') == sample['academic_year'] and row.get('topic') in sample['topic'], 'Question scope differs from reviewed chunk')
    return {'status': 'passed', 'cases': len(rows), 'refusal_cases': len(refusals), 'table_lookup_cases': len(tables)}


def validate(manifest_path='rag-kstu/data/source-manifest.json', output='rag-kstu/data', check_determinism=False):
    manifest = read(manifest_path)
    chunks = load_chunks(output)
    stats = validate_records(manifest, chunks)
    stats['coverage'] = validate_coverage(manifest, read(path_for(output) / 'coverage.json'))
    stats['questions'] = validate_questions(ROOT / 'rag-kstu/evaluation/questions.jsonl', chunks)
    exclusions = read(path_for(output) / 'exclusions.json')['records']
    require(bool(exclusions) and all(bool(r['reason']) for r in exclusions), 'Missing exclusion accounting')
    stats['exclusion_records'] = len(exclusions)
    if check_determinism:
        from build_chunks import build
        with tempfile.TemporaryDirectory(prefix='kstu-determinism-') as first, tempfile.TemporaryDirectory(prefix='kstu-determinism-') as second:
            build(manifest_path, first)
            build(manifest_path, second)
            for name in ('chunks.current.jsonl', 'chunks.archive.jsonl', 'build-stats.json'):
                require((Path(first) / name).read_bytes() == (Path(second) / name).read_bytes() == (path_for(output) / name).read_bytes(), f'Determinism/output drift: {name}')
        stats['determinism'] = 'Two fresh builds and saved corpus are byte-identical, including ordered IDs and content.'
    else:
        stats['determinism'] = 'not_requested'
    return stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', default='rag-kstu/data/source-manifest.json')
    parser.add_argument('--output', default='rag-kstu/data')
    parser.add_argument('--check-determinism', action='store_true')
    args = parser.parse_args()
    try:
        stats = validate(args.manifest, args.output, args.check_determinism)
        report = {'schema_version': 1, 'status': 'passed', 'manifest_sha256': digest(path_for(args.manifest).read_bytes()), **stats}
    except (ValueError, KeyError, IndexError, OSError) as error:
        report = {'schema_version': 1, 'status': 'failed', 'error': str(error)}
    (path_for(args.output) / 'validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False))
    raise SystemExit(0 if report['status'] == 'passed' else 1)


if __name__ == '__main__':
    main()
