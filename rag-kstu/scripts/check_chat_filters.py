#!/usr/bin/env python3
"""Check the six explicit metadata negatives separately from answer generation."""
import argparse
import hashlib
import json
from pathlib import Path
from retrieval import Retriever, DEFAULT_INDEX

ROOT=Path(__file__).resolve().parents[2]


def check(index, output):
    path=ROOT/'rag-kstu/evaluation/retrieval-heldout.jsonl'
    cases=[json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    results=[]
    with Retriever(index_dir=index) as retriever:
        for case in cases:
            if not case.get('expected_empty'):continue
            result=retriever.search(case['query'],mode='hybrid',top_k=5,**case['request'])
            results.append({'case_id':case['case_id'],'request':case['request'],'status':result['status'],
                            'retrieved_chunk_ids':[hit['chunk_id'] for hit in result['hits']],'passed':not result['hits']})
    report={'status':'passed' if len(results)==6 and all(r['passed'] for r in results) else 'failed',
            'fixture_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'cases':results,
            'method':'Explicit metadata filters only, separate from unfiltered chat questions. Stop the API that owns this index before running.'}
    Path(output).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    if report['status']!='passed':raise ValueError('Metadata isolation failed')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index',type=Path,default=DEFAULT_INDEX)
    parser.add_argument('--output',type=Path,default=ROOT/'rag-kstu/evaluation/chat-filter-results.json')
    args=parser.parse_args();check(args.index,args.output)
