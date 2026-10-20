#!/usr/bin/env python3
"""Build and verify source-bound additions without changing the frozen base corpus."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

import build_chunks as base
import validate_chunks as validator

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = 'rag-kstu/data/expanded/source-manifest.json'
SCOPES = {'bachelor_programmes', 'bachelor_admissions', 'general_academic_policy'}
SETTINGS = {'tokenizer': base.TOKENIZER, 'tokenizer_version': base.TOKENIZER_VERSION,
            'target_min_tokens': 500, 'preferred_tokens': 800, 'target_max_tokens': 1000}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def safe_path(value):
    path = Path(value)
    require('..' not in path.parts, 'Path traversal is forbidden')
    candidate = path if path.is_absolute() else ROOT / path
    require(candidate.is_relative_to(ROOT), 'Source path must be inside the workspace')
    relative = candidate.relative_to(ROOT)
    current = ROOT
    for part in relative.parts:
        current = current / part
        require(not current.is_symlink(), f'Symlink source path is forbidden: {value}')
    require(candidate.resolve().is_relative_to(ROOT.resolve()), 'Source path escapes workspace')
    return candidate


def pinned(value, expected):
    path = safe_path(value)
    require(isinstance(expected, str) and len(expected) == 64, f'Missing SHA256: {value}')
    require(base.sha256(path.read_bytes()) == expected, f'Hash drift: {value}')
    return path


def read(value):
    return json.loads(safe_path(value).read_text(encoding='utf-8'))


def extract_programmes(raw_path):
    """Keep each connected rowspan group with its actual page heading and columns."""
    from lxml import html
    document = html.fromstring(Path(raw_path).read_text(encoding='utf-8'))
    frames = document.xpath('//*[@id="cc11982"]')
    require(len(frames) == 1, 'Programme HTML requires its reviewed content frame')
    tables = frames[0].xpath('.//table')
    require(bool(tables), 'Programme HTML has no content tables')
    titles = document.xpath('//h1')
    require(len(titles) == 1, 'Programme HTML requires one page title')
    clean = lambda node: ' '.join(node.text_content().split())
    title = clean(titles[0])
    first_container = tables[0].getparent()
    first_container = first_container if first_container.tag == 'figure' else tables[0]
    intro_nodes = first_container.xpath('preceding-sibling::p')
    require(len(intro_nodes) >= 2, 'Programme HTML lacks year and institute context')
    intro = '\n\n'.join(clean(node) for node in intro_nodes[:-1] if clean(node))
    require(bool(intro), 'Programme HTML lacks admission year context')
    passages = []
    for table_index, table in enumerate(tables, 1):
        container = table.getparent() if table.getparent().tag == 'figure' else table
        institutes = container.xpath('preceding-sibling::*[self::p or self::h2 or self::h3][1]')
        require(bool(institutes), 'Programme table lacks institute heading')
        institute = clean(institutes[0])
        grid, rows, group_end = {}, [], {}
        html_rows = table.xpath('./tr|./thead/tr|./tbody/tr|./tfoot/tr')
        for row_index, tr in enumerate(html_rows):
            column = 0
            for cell in tr.xpath('./td|./th'):
                while (row_index, column) in grid:
                    column += 1
                height, width = int(cell.get('rowspan', '1')), int(cell.get('colspan', '1'))
                require(1 <= height <= len(html_rows) and 1 <= width <= 32,
                        'Invalid programme table span')
                require(row_index + height <= len(html_rows), 'Programme rowspan exceeds table')
                value = clean(cell)
                group_end[row_index] = max(group_end.get(row_index, row_index), row_index + height - 1)
                for dr in range(height):
                    for dc in range(width):
                        key = (row_index + dr, column + dc)
                        require(key not in grid, 'Overlapping programme table spans')
                        grid[key] = value
                column += width
            rows.append([grid.get((row_index, c), '') for c in range(3)])
        require(len(rows) >= 2 and all(rows[0]), 'Programme table requires three column headers')
        require(not any(column > 2 for _, column in grid), 'Unexpected programme table columns')
        escape = lambda value: value.replace('|', '\\|').replace('\n', ' ')
        render = lambda cells: '| ' + ' | '.join(escape(cell) for cell in cells) + ' |'
        header = render(rows[0]) + '\n| --- | --- | --- |'
        start = 1
        while start < len(rows):
            end, cursor = group_end.get(start, start), start
            while cursor <= end:
                end = max(end, group_end.get(cursor, cursor))
                cursor += 1
            group = rows[start:end + 1]
            text = '\n\n'.join([title, intro, institute, header + '\n' + '\n'.join(map(render, group))])
            passages.append({'id': f'programmes-table-{table_index}-rows-{start + 1}-{end + 1}',
                             'text': text, 'page_number': None, 'institute': institute,
                             'locator': {'html_table': table_index, 'first_html_row': start + 1,
                                         'last_html_row': end + 1}, 'rows': group})
            start = end + 1
    return passages


def extract_requirements(raw_path):
    """Preserve each applicant heading and its complete published checklist."""
    from lxml import html
    document = html.fromstring(Path(raw_path).read_text(encoding='utf-8'))
    frames = document.xpath('//*[@id="c4011"]')
    require(len(frames) == 1, 'Requirements HTML lacks its reviewed content frame')
    clean = lambda node: ' '.join(' '.join(node.itertext()).split())
    passages = []
    for index, listing in enumerate(frames[0].xpath('./ul'), 1):
        headings = listing.xpath('preceding-sibling::*[self::p or self::h2 or self::h3][1]')
        require(len(headings) == 1 and clean(headings[0]), 'Requirements checklist lacks audience heading')
        heading = clean(headings[0])
        items = []
        for item in listing.xpath('./li'):
            paragraphs = item.xpath('./p')
            if paragraphs:
                selected = [p for p in paragraphs if 'text-center' not in p.get('class', '').split()]
                items.append(' '.join(clean(p) for p in selected))
            else:
                items.append(clean(item))
        require(bool(items) and all(items), 'Empty requirements checklist')
        passages.append({'id': f'requirements-section-{index}', 'page_number': None,
                         'text': heading + '\n\n' + '\n'.join('- ' + item for item in items),
                         'locator': {'html_frame': 'c4011', 'list_number': index}, 'audience_heading': heading})
    require(bool(passages), 'Requirements HTML has no checklists')
    return passages


def _base_records(manifest):
    paths = {}
    for key in ('base_manifest', 'base_current', 'base_archive'):
        paths[key] = pinned(manifest[key + '_path'], manifest[key + '_sha256'])
    frozen = json.loads(paths['base_manifest'].read_text(encoding='utf-8'))
    require(frozen.get('target_academic_year') == manifest['target_academic_year'], 'Base academic year mismatch')
    for path, expected in frozen['inputs'].items():
        pinned(path, expected)
    for source in frozen['sources']:
        pinned(source['original_path'], source['source_sha256'])
        for prefix in ('extraction', 'selected_text'):
            if source.get(prefix + '_path'):
                pinned(source[prefix + '_path'], source[prefix + '_sha256'])
    current = [json.loads(line) for line in paths['base_current'].read_text().splitlines()]
    archive = [json.loads(line) for line in paths['base_archive'].read_text().splitlines()]
    validator.validate_records(frozen, current + archive)
    coverage_path = paths['base_current'].parent / 'coverage.json'
    safe_path(coverage_path)
    validator.validate_coverage(frozen, json.loads(coverage_path.read_text()))
    require(all(c['eligibility'] == 'current' for c in current), 'Base current eligibility mismatch')
    require(all(c['eligibility'] == 'archive' for c in archive), 'Base archive eligibility mismatch')
    return paths, current, archive


def _reference(ref, source):
    pinned(ref['artifact_path'], ref['artifact_sha256'])
    require('start' not in ref and 'end' not in ref, 'Expansion references must retain complete semantic units')
    require(ref.get('reader') in {'passage', 'block', 'text'}, 'Unknown reference reader')
    pdf = Path(source['raw_path']).suffix.lower() == '.pdf'
    page = ref.get('page_number')
    require(type(page) is int and page >= 1 if pdf else page is None, 'Invalid physical PDF/HTML page')
    if pdf and ref['reader'] != 'text':
        require(read(ref['artifact_path']).get('source_sha256') == source['source_sha256'], 'PDF extraction belongs to a different raw source')
    if not pdf:
        require(source.get('format') in {'html_programmes', 'html_requirements'}, 'Unknown HTML extraction format')
    text = validator.reference_text(ref)
    if source.get('format') in {'html_programmes', 'html_requirements'}:
        require(ref['reader'] == 'passage', 'HTML must use reproducible passages')
        artifact = read(ref['artifact_path'])
        extractor = extract_programmes if source['format'] == 'html_programmes' else extract_requirements
        expected = extractor(safe_path(source['raw_path']))
        require(artifact.get('passages') == expected, 'HTML passages differ from independently parsed raw source')
        require(artifact.get('source_sha256', source['source_sha256']) == source['source_sha256'], 'HTML artifact source hash mismatch')
        require(artifact.get('source_url', source['source_url']) == source['source_url'], 'HTML artifact source URL mismatch')
    return text


def _supplement(selection, settings):
    require(selection.get('scope') in SCOPES, 'Unknown reviewed expansion scope')
    require(selection.get('current_answer_eligible') is True, 'Expansion requires explicit current eligibility')
    require(selection.get('review_decision') == 'approved', 'Missing approved review decision')
    require(selection.get('academic_year', '2026-2027') == '2026-2027', 'Selection query cohort mismatch')
    source = selection['source']
    pinned(source['raw_path'], source['source_sha256'])
    url = urlsplit(source.get('source_url', ''))
    require(url.scheme == 'https' and url.hostname in {'kstu.kg', 'www.kstu.kg'}, 'Official HTTPS KSTU source required')
    require(isinstance(source.get('title'), str) and source['title'].strip(), 'Missing reviewed source title')
    authority = selection.get('review_ref')
    require(isinstance(authority, dict), 'Missing independent review authority')
    require(authority.get('selection_id') == selection['selection_id'], 'Review authority selection ID mismatch')
    review_path = pinned(authority['artifact_path'], authority['artifact_sha256'])
    reviews = json.loads(review_path.read_text(encoding='utf-8')).get('selections', [])
    approved = [row for row in reviews if row.get('selection_id') == selection['selection_id']]
    expected = {key: value for key, value in selection.items() if key != 'review_ref'}
    require(len(approved) == 1 and approved[0] == expected, 'Selection differs from independent review authority')
    units = selection.get('units')
    if units is None:
        units = [{'unit_id': f"{selection['selection_id']}-unit-{i}", 'kind': 'paragraph', 'parts': [ref]}
                 for i, ref in enumerate(selection.get('refs', []), 1)]
    require(bool(units), 'Selection requires complete reviewed semantic units')
    context = selection.get('context', [])
    for ref in context + [ref for unit in units for ref in unit['parts']]:
        _reference(ref, source)
    normalized = dict(selection, units=units, context=context, eligibility='current', academic_year='2026-2027',
                      review_evidence={'decision': 'approved', 'authority': authority},
                      recognition_status=selection.get('recognition_status', 'reviewed_source_text'))
    normalized_source = dict(source, source=source['title'], original_path=source['raw_path'])
    chunks = base.chunk_selection(normalized, normalized_source, settings)
    for chunk in chunks:
        chunk['scope'] = selection['scope']
        chunk['corpus_kind'] = 'reviewed_expansion'
        chunk['chunk_id'] = 'kstu-expanded-' + base.sha256(base.canonical({key: value for key, value in chunk.items() if key != 'chunk_id'}).encode())
    for i, chunk in enumerate(chunks):
        if i:
            chunk['overlap']['previous_chunk_id'] = chunks[i - 1]['chunk_id']
            chunk['chunk_id'] = 'kstu-expanded-' + base.sha256(base.canonical({key: value for key, value in chunk.items() if key != 'chunk_id'}).encode())
    return chunks


def _reconstruct(manifest_path):
    manifest = read(manifest_path)
    require(manifest.get('kind') == 'reviewed_expansion' and manifest.get('university_id') == 'kstu', 'Unknown expansion manifest')
    require(manifest.get('target_academic_year') == '2026-2027', 'Expansion target academic year mismatch')
    paths, current, archive = _base_records(manifest)
    supplements = manifest.get('supplements', [])
    require(bool(supplements), 'Expansion has no reviewed supplements')
    require(len({s['selection_id'] for s in supplements}) == len(supplements), 'Duplicate supplement selection IDs')
    additional = [chunk for selection in supplements for chunk in _supplement(selection, SETTINGS)]
    records = current + archive + additional
    require(len({chunk['chunk_id'] for chunk in records}) == len(records), 'Duplicate chunk IDs')
    require(not ({c['selection_id'] for c in current + archive} & {s['selection_id'] for s in supplements}), 'Expansion selection collides with frozen base')
    return manifest, paths, current, archive, additional


def validate_expansion(chunks_path):
    chunks_path = safe_path(chunks_path)
    metadata = read(chunks_path.parent / 'build-stats.json')
    manifest_path = metadata['manifest_path']
    pinned(manifest_path, metadata['manifest_sha256'])
    manifest, paths, base_current, archive, additional = _reconstruct(manifest_path)
    expected_current = paths['base_current'].read_bytes() + ''.join(base.canonical(c) + '\n' for c in additional).encode()
    require(chunks_path.read_bytes() == expected_current, 'Expansion differs from exact source reconstruction or frozen base')
    require(safe_path(chunks_path.parent / 'chunks.archive.jsonl').read_bytes() == paths['base_archive'].read_bytes(), 'Expansion changed frozen archive')
    current = [json.loads(line) for line in chunks_path.read_text().splitlines()]
    require(len({c['chunk_id'] for c in current + archive}) == len(current + archive), 'Duplicate corpus chunk ID')
    return current


def build(manifest_path=DEFAULT_MANIFEST, output='rag-kstu/data/expanded'):
    manifest_path = safe_path(manifest_path)
    manifest, paths, current, archive, additional = _reconstruct(manifest_path)
    output = safe_path(output)
    protected = set(paths.values()) | {manifest_path}
    protected.update(safe_path(path) for path in read(paths['base_manifest'])['inputs'])
    for selection in manifest['supplements']:
        protected.add(safe_path(selection['source']['raw_path']))
        protected.add(safe_path(selection['review_ref']['artifact_path']))
        refs = selection.get('context', []) + selection.get('refs', [])
        refs += [ref for unit in selection.get('units', []) for ref in unit['parts']]
        protected.update(safe_path(ref['artifact_path']) for ref in refs)
    require(not any(output / name in protected for name in ('chunks.current.jsonl', 'chunks.archive.jsonl', 'build-stats.json', 'validation.json')), 'Output overlaps protected expansion inputs')
    output.mkdir(parents=True, exist_ok=True)
    for filename in ('chunks.current.jsonl', 'chunks.archive.jsonl', 'build-stats.json', 'validation.json'):
        safe_path(output / filename)
    (output / 'chunks.current.jsonl').write_bytes(paths['base_current'].read_bytes() + ''.join(base.canonical(c) + '\n' for c in additional).encode())
    (output / 'chunks.archive.jsonl').write_bytes(paths['base_archive'].read_bytes())
    stats = {'kind': 'reviewed_expansion', 'manifest_path': str(manifest_path.relative_to(ROOT)),
             'manifest_sha256': base.sha256(manifest_path.read_bytes()), 'target_academic_year': manifest['target_academic_year'],
             'base_current_count': len(current), 'additional_chunk_count': len(additional),
             'chunk_counts': {'current': len(current) + len(additional), 'archive': len(archive)},
             'supplement_selection_count': len(manifest['supplements']),
             'tokenizer': {'name': base.TOKENIZER, 'version': base.TOKENIZER_VERSION},
             'settings': SETTINGS}
    (output / 'build-stats.json').write_text(json.dumps(stats, ensure_ascii=False, indent=2, sort_keys=True) + '\n')
    validated = validate_expansion(output / 'chunks.current.jsonl')
    report = {'status': 'valid', 'kind': 'reviewed_expansion', 'current_count': len(validated),
              'frozen_base_preserved': True, 'archive_preserved': True,
              'manifest_sha256': stats['manifest_sha256']}
    (output / 'validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + '\n')
    return validated + archive, stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['build', 'validate'])
    parser.add_argument('--manifest', default=DEFAULT_MANIFEST)
    parser.add_argument('--output', default='rag-kstu/data/expanded')
    parser.add_argument('--chunks', default='rag-kstu/data/expanded/chunks.current.jsonl')
    args = parser.parse_args()
    result = build(args.manifest, args.output)[1] if args.command == 'build' else {'current_count': len(validate_expansion(args.chunks)), 'status': 'valid'}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
