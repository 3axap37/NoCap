import json

with open('evaluation.jsonl', encoding='utf-8') as f:
    expected_all = {}
    for line in f:
        r = json.loads(line)
        expected_all[r['document_id']] = [(sh['name'], sh['share_type'] or '', sh['share_count']) for sh in r['shareholders']]

with open('result_v2.jsonl', encoding='utf-8') as f:
    for line in f:
        r = json.loads(line)
        doc = r['document_id']
        actual = [(sh['name'], sh.get('share_type') or '', sh.get('share_count')) for sh in r['shareholders']]
        expected = expected_all.get(doc, [])
        missing = set(expected) - set(actual)
        extra = set(actual) - set(expected)
        if missing or extra:
            print(f'\n=== {doc} ===')
            for m in sorted(missing, key=lambda x: x[2]):
                print(f'  MISS: {repr(m[0])} | {m[1]} | {m[2]}')
            for e in sorted(extra, key=lambda x: x[2]):
                print(f'  XTRA: {repr(e[0])} | {e[1]} | {e[2]}')
        else:
            print(f'\n=== {doc} === PASS')
