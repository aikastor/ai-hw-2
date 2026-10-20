#!/usr/bin/env python3
"""Evaluate chat over HTTP; gold labels are used only after a response arrives."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from urllib.parse import urldefrag
import httpx

ROOT = Path(__file__).resolve().parents[2]


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def check_response(case, body, chunks):
    expected = case.get('expected_status', 'refused' if case.get('refusal') else 'answered')
    expected_ids = case.get('expected_selection_ids', [case['selection_id']] if 'selection_id' in case else [])
    grounding = body.get('grounding', {})
    claims = grounding.get('claims', [])
    problems = []
    cited = set()
    for citation in body.get('citations', []):
        chunk = chunks.get(citation.get('chunk_id'))
        if chunk is None:
            problems.append('unknown citation chunk'); continue
        page = citation.get('page_number', citation.get('page'))
        title = citation.get('source_title', citation.get('title', citation.get('source')))
        official = citation.get('source_url', citation.get('official_url'))
        link = citation.get('url', citation.get('page_url'))
        pages = {c['page_number'] for c in chunk['citations']}
        if page not in pages or title != chunk['source']:
            problems.append('citation metadata mismatch')
        if official and urldefrag(official)[0] != urldefrag(chunk['source_url'])[0]:
            problems.append('citation official URL mismatch')
        target = chunk['source_url'] if page is None else urldefrag(chunk['source_url'])[0]+'#page='+str(page)
        if link and link != target:
            problems.append('citation target mismatch')
        cited.add(citation['chunk_id'])
    quote_checks = []
    for claim in claims:
        evidence = claim.get('evidence', [])
        valid = bool(evidence)
        for reference in evidence:
            chunk = chunks.get(reference.get('chunk_id'))
            quote = reference.get('quote', '')
            valid = valid and bool(chunk and quote and quote in chunk['text'])
        quote_checks.append(bool(valid))
        if not valid:problems.append('claim quotation not in supplied chunk')
    if body.get('status') != 'answered' and body.get('citations'):
        problems.append('nonanswer has citations')
    retrieved_ids = grounding.get('retrieved_chunk_ids', [])
    retrieved_selections = grounding.get('retrieved_selection_ids', [chunks[c]['selection_id'] for c in retrieved_ids if c in chunks])
    relevant = any(s in expected_ids for s in retrieved_selections)
    answer_cites_expected = any(chunks[c]['selection_id'] in expected_ids for c in cited)
    if body.get('status') == 'answered' and (not claims or not cited):
        problems.append('answer missing claims or citations')
    return {
        'expected_status':expected, 'status_correct':body.get('status') == expected,
        'grounded_refusal':body.get('status')=='refused' and bool(body.get('answer', '').strip()) and not body.get('citations') and bool(grounding.get('outcome')),
        'expected_evidence_retrieved':relevant, 'answer_cites_expected_selection':answer_cites_expected,
        'quote_checks':quote_checks, 'citation_correctness':not problems, 'local_support_errors':problems,
        'support_check_limit':'Quote and metadata checks are deterministic; entailment and completeness require a source audit. Provider verification is probabilistic.',
        'source_audit':'pending',
    }


def evaluate(base_url, output, datasets, limit=None, chunks_path=None, cases_path=None, delay=0.1):
    app=ROOT/'rag-kstu'
    chunks={c['chunk_id']:c for c in rows(chunks_path or app/'data/chunks.current.jsonl')}
    sources = {'handoff':app/'evaluation/questions.jsonl', 'regression':app/'evaluation/retrieval-heldout.jsonl', 'final':app/'evaluation/generation-final.jsonl'}
    if cases_path:
        sources['expanded'] = cases_path
        datasets = ['expanded']
    cases=[]
    calls=0
    with httpx.Client(base_url=base_url,timeout=300,trust_env=False) as client:
        health=client.get('/health').json()
        for dataset in datasets:
            for case in rows(sources[dataset]):
                if case.get('expected_empty'):continue
                if limit is not None and len(cases)>=limit:break
                request=case.get('request') if dataset in ('final', 'expanded') else {'question':case.get('question',case.get('query'))}
                if set(request) - {'question','history','category','academic_year','scope'}:
                    raise ValueError('Unexpected request fields; gold labels must not enter chat')
                response=client.post('/chat',json=request);calls+=1
                result={'dataset':dataset,'case_id':case['case_id'],'request':request,'http_status':response.status_code,'expected_status':case.get('expected_status','refused' if case.get('refusal') else 'answered'),
                        'expected_answer':case.get('expected_answer'),'expected_selection_ids':case.get('expected_selection_ids',[case.get('selection_id')])}
                if response.is_success:
                    result['response']=response.json()
                    result['checks']=check_response(case,result['response'],chunks)
                else:result['service_error']=response.json()
                cases.append(result)
                Path(output).write_text(json.dumps({'status':'running','cases':cases},ensure_ascii=False,indent=2)+'\n')
                print(dataset,case['case_id'],response.status_code,result.get('response',{}).get('status'),flush=True)
                time.sleep(delay)
    summary={}
    for dataset in datasets:
        subset=[r for r in cases if r['dataset']==dataset]
        supported=[r for r in subset if r['expected_status']=='answered']
        refusals=[r for r in subset if r['expected_status']=='refused']
        summary[dataset]={
            'cases':len(subset),'service_errors':sum(r['http_status']!=200 for r in subset),
            'supported_cases':len(supported),'answered_with_expected_citation':sum(r.get('checks',{}).get('status_correct',False) and r['checks']['answer_cites_expected_selection'] and r['checks']['citation_correctness'] for r in supported),
            'grounded_refusal_count':sum(r.get('checks',{}).get('grounded_refusal',False) for r in refusals),'expected_refusals':len(refusals),
            'false_refusals':sum(r.get('response',{}).get('status')=='refused' for r in supported),
            'evidence_found_but_not_answered':[r['case_id'] for r in supported if r.get('checks',{}).get('expected_evidence_retrieved') and r.get('response',{}).get('status')!='answered'],
            'local_support_error_cases':[r['case_id'] for r in subset if r.get('checks',{}).get('local_support_errors')],
            'source_audit':'pending; automated quote/citation checks do not establish entailment',
        }
    result={'schema_version':1,'date':datetime.now(timezone.utc).isoformat(),'surface':'real POST /chat over HTTP',
            'health':health,'http_chat_requests':calls,'dataset_hashes':{k:hashlib.sha256(sources[k].read_bytes()).hexdigest() for k in datasets},
            'method':'Questions and user history only enter chat. Gold selections and expected answers are grading labels. Existing bilingual set is reused development evidence. Frozen final set stays untuned.',
            'summary':summary,'cases':cases}
    Path(output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,indent=2))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url',default='http://127.0.0.1:8000')
    parser.add_argument('--output',type=Path,default=ROOT/'rag-kstu/evaluation/chat-results.json')
    parser.add_argument('--datasets',nargs='+',choices=['handoff','regression','final'],default=['handoff','regression','final'])
    parser.add_argument('--limit',type=int)
    parser.add_argument('--chunks', type=Path)
    parser.add_argument('--cases', type=Path)
    parser.add_argument('--delay', type=float, default=0.1)
    args=parser.parse_args();evaluate(args.base_url,args.output,args.datasets,args.limit,args.chunks,args.cases,args.delay)
