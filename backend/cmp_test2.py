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
        if doc != 'Test2':
            continue
        actual = [(sh['name'], sh.get('share_type') or '', sh.get('share_count')) for sh in r['shareholders']]
        expected = expected_all.get(doc, [])
        missing = set(expected) - set(actual)
        extra = set(actual) - set(expected)
        print('Missing:')
        for m in missing:
            print(f'  {m[0]!r} | {m[2]}')
        print('Extra:')
        for e in extra:
            print(f'  {e[0]!r} | {e[2]}')
