#!/usr/bin/env python3
"""Freeze the independently reviewed KSTU source additions alongside the base corpus."""
import hashlib
import json
from pathlib import Path
import re
from expanded_sources import extract_programmes, extract_requirements
from validate_chunks import reference_text

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'rag-kstu/data/expanded'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def relative(path):
    return str(path.relative_to(ROOT))


def passage_ref(path,passage):
    return {'reader':'passage','artifact_path':relative(path),'artifact_sha256':sha(path),
            'passage_id':passage['id'],'page_number':passage['page_number'],
            'text_sha256':hashlib.sha256(passage['text'].encode()).hexdigest()}


def prepare():
    base_path=ROOT/'rag-kstu/data/source-manifest.json'
    frozen=json.loads(base_path.read_text())
    reviewed=json.loads((OUT/'review/policies.json').read_text())
    supplements=[]
    programme_institutes = 0
    common={'current_answer_eligible':True,'review_decision':'approved','additional_categories':[]}
    for filename,kind,url,title,extractor in [
        ('programmes','html_programmes','https://kstu.kg/abiturientu/1/napravlenija-podgotovki/bakalavr-i-magistratura#cc11982','Бакалавр и Специалитет: направления подготовки КГТУ, 2026–2027',extract_programmes),
        ('admissions-documents','html_requirements','https://kstu.kg/abiturientu/4/dokumenty#c4011','Документы для поступления: официальный перечень КГТУ',extract_requirements),
    ]:
        raw=OUT/'sources'/f'{filename}.html'
        passages=extractor(raw)
        artifact=OUT/f'{filename}-passages.json'
        save(artifact,{'source_sha256':sha(raw),'source_url':url,'passages':passages})
        source={'title':title,'source_url':url,'raw_path':relative(raw),'source_sha256':sha(raw),'format':kind}
        groups={}
        for p in passages:
            group=p.get('institute') if kind=='html_programmes' else p['id']
            groups.setdefault(group,[]).append(p)
        if kind == 'html_programmes':
            programme_institutes = len(groups)
        for index,(label,items) in enumerate(groups.items(),1):
            programme=kind=='html_programmes'
            supplements.append(dict(common,selection_id=f"{'programmes' if programme else 'bachelor-documents'}-{index:02}",source=source,
                scope='bachelor_programmes' if programme else 'bachelor_admissions',category='prospective student',
                topic=['programmes'] if programme else ['admissions_documents'],
                audience_restrictions=[label if programme else items[0]['audience_heading']],
                effective_date_evidence={'status':'explicit_2026_2027_intake' if programme else 'currently_published_undated_checklist','review_date':'2026-10-20','source_year':2026 if programme else None},
                limitations=['The page title includes bachelor and specialist programmes. Do not classify every specialization row as bachelor. This selection covers one institute; do not claim a complete university list.'] if programme else ['The central checklist prints no intake year. Describe the currently published checklist, without asserting an explicit 2026-2027 date. Other applicant groups have different lists.'],
                context=[],refs=[passage_ref(artifact,p) for p in items],recognition_status='reviewed_html_tables' if programme else 'reviewed_html_checklist'))
    sources={s['source_sha256']:s for s in frozen['sources']}
    policy_sources={s['source_sha256']:s for s in reviewed['sources']}
    for selected in reviewed['selections']:
        h=selected['source_sha256'];source=sources[h];review=policy_sources[h]
        units=[]
        for ref in selected['references']:
            text=reference_text(ref)
            if not units or re.match(r'^\s*\d+\.\d+\.',text):
                units.append({'unit_id':selected['id']+'-unit-'+str(len(units)+1),'kind':'paragraph','parts':[]})
            units[-1]['parts'].append(ref)
        supplements.append(dict(common,selection_id='published-'+selected['id'],
            source={'title':source.get('source',source['title']),'source_url':review['url'],'raw_path':source['original_path'],'source_sha256':h,'format':'pdf'},
            scope='general_academic_policy',category='current student',topic=[selected['topic']],
            audience_restrictions=[selected['scope']],context=review.get('authority_refs',[])[:7],units=units,
            effective_date_evidence={'status':'officially_published_policy_2025','publication_year':2025,'review_date':'2026-10-20','publication_indexes':reviewed['publication_indexes'],'applicability':'Published-policy explanation. Query cohort is 2026-2027; explicit non-repeal and individual eligibility are not established.'},
            limitations=[selected['eligible_use'],'Preserve all exceptions. Do not invent rector order dates or correct the printed amendment-sheet inconsistency.','The old appeal deadline in clause 3.4 is excluded because a separately published 2026 appeals policy differs.'],recognition_status='reviewed_selected_pdf_passage'))
    appeal=OUT/'appeals-passages.json'
    if appeal.exists():
        record=json.loads(appeal.read_text());raw=OUT/'sources/appeals-2026.pdf'
        supplements.append(dict(common,selection_id='published-appeal-deadline-2026',
            source={'title':'Положение об апелляции результатов итоговых государственных испытаний и промежуточной аттестации обучающихся ВПО и СПО КГТУ, 2026','source_url':'https://kstu.kg/fileadmin/user_upload/polozhenie_ob_apelljacii_rezultatov_itogovykh_gosudarstvennykh_ispytanii_i_promezhutochnoi_attestacii_obuchajushchikhsja_vpo_i_spo_v_kgtu_im_compressed.pdf','raw_path':relative(raw),'source_sha256':sha(raw),'format':'pdf'},
            scope='general_academic_policy',category='current student',topic=['appeals'],audience_restrictions=['KSTU higher and secondary professional education students; final state examinations and intermediate attestation.'],
            context=[],refs=[passage_ref(appeal,p) for p in record['passages']],
            effective_date_evidence={'status':'officially_published_policy_2026','publication_year':2026,'review_date':'2026-10-20'},
            limitations=['Physical PDF page 4, clause 2.4. Do not use the conflicting older 2025 clause 3.4. This selection establishes the filing deadline, not the entire appeals procedure.'],recognition_status='visually_reviewed_manual_transcription'))
    ledger=OUT/'review/approved-selections.json'
    save(ledger,{'review_date':'2026-10-20','method':'Source research and visual policy review recorded in sibling policies.json and programmes-research.md; source text is reconstructed independently.','selections':supplements})
    manifest={'schema_version':1,'kind':'reviewed_expansion','university_id':'kstu','target_academic_year':'2026-2027'}
    for key,path in [('base_manifest',base_path),('base_current',ROOT/'rag-kstu/data/chunks.current.jsonl'),('base_archive',ROOT/'rag-kstu/data/chunks.archive.jsonl')]:
        manifest[key+'_path']=relative(path);manifest[key+'_sha256']=sha(path)
    manifest['supplements']=[dict(s,review_ref={'artifact_path':relative(ledger),'artifact_sha256':sha(ledger),'selection_id':s['selection_id']}) for s in supplements]
    save(OUT/'source-manifest.json',manifest)
    print(json.dumps({'reviewed_supplements':len(supplements),'programme_institutes':programme_institutes,'manifest':relative(OUT/'source-manifest.json')}))


if __name__=='__main__':prepare()
