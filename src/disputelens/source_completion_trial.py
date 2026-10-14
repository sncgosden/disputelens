"""Offline, development-only linked-evidence completion; no search or model calls."""
import copy
import argparse
import hashlib
import json
import re
from pathlib import Path

from .client import ModelError
from .context_pack import render_context
from .section_scope import classify_section, section_applicable

PUBLISHER_HEADINGS = {
    'normalized_path': 'data/indexes/section-hierarchy/71bf6051f48778a5e9ca12c1/documents.json',
    'normalized_sha256': 'c18ca242aa54b0cb8e2307c7364f7f9d3ed3f121a4425d95a926fa78b58507fb',
    'manifest_path': 'data/indexes/section-hierarchy/71bf6051f48778a5e9ca12c1/experiment.json',
    'manifest_sha256': '640ea7c8636e2ecaaded3b91e48fcad3e6b60f0fc962d28ca282c95f146a1729',
}

def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def render_diagnostic(groups):
    # Empty ranks belong only to the separately added diagnostic group. Keep the
    # frozen production renderer unchanged, so its saved identity remains valid.
    text = render_context(groups)
    return re.sub(r'EXTRACT GROUP FROM (SOURCE\d+); retrieval ranks: (?=\n|$)',
                  r'DIAGNOSTIC SOURCE COMPLETION FROM \1; not retrieved evidence', text)


def complete_context(baseline, supplement, publisher_headings=None):
    """Verify whole source blocks, preserve citation IDs, evict intact other groups.

    This manually selected development diagnostic cannot estimate retrieval quality
    or establish merchant scope. Its new prompt must never reuse baseline answers.
    """
    if supplement.get('status') != 'separate_diagnostic_evidence_not_baseline':
        raise ModelError('Only separate diagnostic supplements are supported.')
    if file_hash(supplement['source_path']) != supplement['source_sha256']:
        raise ModelError('Supplement source changed.')
    docs = json.loads(Path(supplement['source_path']).read_text())
    blocks = {b['passage_id']: b for d in docs['documents'] for b in d['blocks']}
    pieces = supplement['pieces']
    if not pieces or len({p['passage_id'] for p in pieces}) != len(pieces):
        raise ModelError('Supplement needs unique whole source blocks.')
    for p in pieces:
        b = blocks.get(p['passage_id'])
        if (b is None or p['start'] != 0 or p['end'] != len(b['text'])
                or p['text'] != b['text'] or p['locator'] != b['locator']
                or p['headings'] != b['headings']
                or hashlib.sha256(b['text'].encode()).hexdigest() != p['source_text_sha256']):
            raise ModelError('Supplement source span/provenance mismatch.')
    pack = copy.deepcopy(baseline)
    groups = pack['groups']
    requested = {p['passage_id'] for p in pieces}
    anchors = [g for g in groups if any(e['passage_id'] in requested for e in g['evidence'])]
    if not anchors:
        raise ModelError('Supplement must link to evidence in the frozen context.')
    anchor = anchors[0]
    if any(g['metadata'] != anchor['metadata'] or g['source_sha256'] != anchor['source_sha256'] for g in anchors):
        raise ModelError('Linked context sources disagree.')
    source_id = anchor['metadata']['source_id']
    if source_id == 'mastercard-chargeback-guide' and publisher_headings is None:
        raise ModelError('Publisher headings required for Mastercard completion.')
    heading_blocks = None
    if publisher_headings is not None:
        for name in ('normalized', 'manifest'):
            if file_hash(publisher_headings[name + '_path']) != publisher_headings[name + '_sha256']:
                raise ModelError('Publisher heading provenance changed.')
        manifest = json.loads(Path(publisher_headings['manifest_path']).read_text())
        if (manifest['identity']['baseline_normalized_sha256'] != supplement['source_sha256']
                or manifest['identity']['source_sha256'] != anchor['source_sha256']
                or manifest['normalized_path'] != publisher_headings['normalized_path']
                or not manifest['evidence_and_scope_unchanged']):
            raise ModelError('Publisher headings belong to a different source experiment.')
        transformed = json.loads(Path(publisher_headings['normalized_path']).read_text())
        heading_blocks = {b['passage_id']: b for d in transformed['documents'] for b in d['blocks']}
    present = {e['passage_id']: e for g in groups for e in g['evidence']}
    new = []
    for p in pieces:
        if not p['passage_id'].startswith(source_id + ':'):
            raise ModelError('Supplement crosses document scope.')
        b = blocks[p['passage_id']]
        if heading_blocks is not None:
            corrected = heading_blocks.get(p['passage_id'])
            if (corrected is None or corrected['text'] != b['text']
                    or corrected['locator'] != b['locator']
                    or not corrected['headings']
                    or any(not isinstance(h, str) or not h.strip() for h in corrected['headings'])):
                raise ModelError('Publisher heading transformation changed source evidence.')
            b = {**b, 'headings': list(corrected['headings'])}
        unit = {'metadata': anchor['metadata'], 'passage_ids': [p['passage_id']]}
        scope = {p['passage_id']: classify_section(b['headings'])}
        if not section_applicable(unit, pack['trusted_settings'], scope):
            raise ModelError('Supplement failed existing section applicability.')
        if p['passage_id'] in present:
            old = present[p['passage_id']]
            start, end = old['evidence_character_start'], old['evidence_character_end']
            if old['locator'] != b['locator'] or old['text'] != b['text'][start:end]:
                raise ModelError('Frozen evidence disagrees with linked source.')
            if not old['complete_evidence']:
                raise ModelError('Partial baseline span needs a separate reviewed expansion policy.')
            continue
        e = copy.deepcopy(b)
        e.update(evidence_character_start=0, evidence_character_end=len(b['text']),
                 original_evidence_characters=len(b['text']), complete_evidence=True)
        new.append(e)
    if not new:
        raise ModelError('No missing evidence to complete.')
    maximum = pack['budget']['maximum']
    if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum < 1:
        raise ModelError('Invalid context word budget.')
    labels = [e['citation_id'] for g in groups for e in g['evidence']]
    if len(labels) != len(set(labels)):
        raise ModelError('Duplicate frozen citation labels.')
    next_id = max(int(label[1:]) for label in labels) + 1
    for number, e in enumerate(new, next_id):
        e['citation_id'] = f'S{number:03d}'
    completion = {'parent_chunk_ids': [], 'unit_ids': [], 'retrieval_ranks': [],
                  'metadata': copy.deepcopy(anchor['metadata']), 'source_sha256': anchor['source_sha256'],
                  'evidence_origin': 'diagnostic_source_completion', 'evidence': new}
    groups.insert(groups.index(anchor) + 1, completion)
    removed = []
    while len(render_diagnostic(groups).split()) > maximum:
        removable = [g for g in groups if g is not completion and g not in anchors]
        if not removable:
            raise ModelError('Required linked evidence exceeds context budget; no partial trimming.')
        victim = max(removable, key=lambda g: max(g['retrieval_ranks']))
        groups.remove(victim)
        removed.append({'unit_ids': victim['unit_ids'], 'retrieval_ranks': victim['retrieval_ranks'],
                        'reason': 'intact group displaced by required diagnostic source completion'})
    pack['text'] = render_diagnostic(groups)
    pack['citations'] = {e['citation_id']: {'passage_id': e['passage_id'], 'locator': e['locator'],
        'source_sha256': g['source_sha256'], 'character_start': e['evidence_character_start'],
        'character_end': e['evidence_character_end'], 'complete_evidence': e['complete_evidence']}
        for g in groups for e in g['evidence']}
    pack['budget'].update(used=len(pack['text'].split()), model_token_check_pending=True)
    pack['included_units'] = sum(len(g['unit_ids']) for g in groups)
    pack['omitted_groups'].extend(removed)
    pack.pop('evaluation_identity', None)
    pack['diagnostic_completion'] = {'case_id': supplement['case_id'],
        'added_passage_ids': [e['passage_id'] for e in new], 'removed_group_count': len(removed),
        'source_selection': 'manual development review, not query-only retrieval',
        'baseline_attempt_reuse_allowed': False, 'production_integration': False,
        'applicability': 'Existing document/section guards only; complete merchant scope not established'}
    if publisher_headings is not None:
        pack['diagnostic_completion']['publisher_heading_provenance'] = {
            **publisher_headings, 'evidence_text_and_locators_unchanged': True,
            'review_status': 'publisher-derived; not independent mapping review'}
    pack['limitations'] = 'Development diagnostic only; no measured answer improvement or complete scope/answerability claim.'
    return pack


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case-id', choices=('E18', 'E23'), default='E18')
    args = parser.parse_args()
    case_id = args.case_id
    baseline_path = Path('data/indexes/context-eval/9588eef5a0cd81e960abe04c/packs') / (case_id + '.json')
    supplement_name = ('E18-complete-linked-evidence.json' if case_id == 'E18'
                       else 'E23-whole-block-completion.json')
    supplement_path = Path('eval/experiments/applicability-v1') / supplement_name
    supplement = json.loads(supplement_path.read_text())
    before = file_hash(baseline_path)
    if before != supplement['frozen_context_pack_sha256']:
        raise ModelError('Frozen development context changed.')
    baseline = json.loads(baseline_path.read_text())
    candidate = complete_context(baseline, supplement, publisher_headings=PUBLISHER_HEADINGS)
    from .grounded_answer import build_answer_prompt
    prompt = build_answer_prompt(baseline['question'], candidate)
    identity = hashlib.sha256((before + file_hash(supplement_path) + file_hash(__file__)
        + json.dumps(candidate, sort_keys=True, ensure_ascii=False)).encode()).hexdigest()[:24]
    candidate['diagnostic_identity'] = identity
    out = Path('data/indexes/source-completion-trials') / identity
    out.mkdir(parents=True, exist_ok=True)
    (out / (case_id + '-context.json')).write_text(json.dumps(candidate, indent=2, ensure_ascii=False) + '\n')
    (out / (case_id + '-prompt.json')).write_text(prompt + '\n')
    report = {'identity': identity, 'case_id': case_id, 'baseline_words': baseline['budget']['used'],
        'candidate_words': candidate['budget']['used'], 'maximum_words': candidate['budget']['maximum'],
        **candidate['diagnostic_completion'], 'model_token_check': 'pending authorized model runner',
        'model_calls': 0, 'answer_quality': 'not measured', 'runner_sha256': file_hash(__file__),
        'baseline_sha256': before, 'supplement_sha256': file_hash(supplement_path)}
    if file_hash(baseline_path) != before:
        raise ModelError('Frozen context was modified.')
    (out / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    print('SAVED: ' + str(out))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
