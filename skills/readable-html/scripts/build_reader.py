#!/usr/bin/env python3
"""Build a portable reader from UTF-8 TXT or validated document JSON (stdlib only)."""
import argparse
import hashlib
import html
import json
import re
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parents[1] / 'assets' / 'reader-template.html'
DATA_PATTERN = re.compile(r'(<script type="application/json" id="reader-data">)(.*?)(</script>)', re.S)


def nonempty(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{label} must be a nonempty string')
    return value


def paragraphs(value, label):
    if not isinstance(value, list) or not value:
        raise ValueError(f'{label} must be a nonempty paragraph array')
    for i, item in enumerate(value):
        nonempty(item, f'{label}[{i}]')


def validate_document(raw, number):
    if not isinstance(raw, dict):
        raise ValueError(f'Document {number} must be an object')
    doc = dict(raw)
    nonempty(doc.get('title'), f'Document {number} title')
    if 'subtitle' in doc and not isinstance(doc['subtitle'], str):
        raise ValueError('subtitle must be a string')
    if 'lang' in doc and (not isinstance(doc['lang'], str) or not re.fullmatch(r'[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*', doc['lang'])):
        raise ValueError('lang must be a language tag such as fa, en, or ar')
    if 'dir' in doc and doc['dir'] not in ('rtl', 'ltr'):
        raise ValueError('dir must be rtl or ltr')
    bodies = [key for key in ('chapters', 'paragraphs', 'text') if key in doc]
    if len(bodies) != 1:
        raise ValueError('Choose exactly one body: chapters, paragraphs, or text')
    if bodies[0] == 'text':
        nonempty(doc['text'], 'text')
    elif bodies[0] == 'paragraphs':
        paragraphs(doc['paragraphs'], 'paragraphs')
    else:
        if not isinstance(doc['chapters'], list) or not doc['chapters']:
            raise ValueError('chapters must be a nonempty array')
        for i, chapter in enumerate(doc['chapters']):
            if not isinstance(chapter, dict):
                raise ValueError(f'Chapter {i} must be an object')
            nonempty(chapter.get('title'), f'Chapter {i} title')
            paragraphs(chapter.get('paragraphs'), f'Chapter {i} paragraphs')
            if 'pageStarts' in chapter:
                starts = chapter['pageStarts']
                if (not isinstance(starts, list) or not starts
                        or any(type(n) is not int for n in starts)
                        or starts[0] != 0 or starts != sorted(set(starts))
                        or starts[-1] >= len(chapter['paragraphs'])):
                    raise ValueError(f'Chapter {i} pageStarts must be ascending unique paragraph indices beginning at 0')
    if 'id' in doc:
        nonempty(doc['id'], 'id')
    else:
        serialized = json.dumps(doc, ensure_ascii=False, sort_keys=True).encode('utf-8')
        doc['id'] = 'book-' + hashlib.sha256(serialized).hexdigest()[:20]
    return doc


def build(input_path, output_path, title=None, lang=None, direction=None):
    input_path, output_path = Path(input_path), Path(output_path)
    if output_path.resolve() in (input_path.resolve(), TEMPLATE.resolve()):
        raise ValueError('Output must not overwrite the input or skill template')
    raw = input_path.read_text(encoding='utf-8-sig')
    if input_path.suffix.lower() == '.json':
        parsed = json.loads(raw)
        documents = parsed if isinstance(parsed, list) else [parsed]
    elif input_path.suffix.lower() == '.txt':
        documents = [{'title': title or input_path.stem, 'text': raw}]
    else:
        raise ValueError('Use .txt or structured .json; extract other formats first')
    if not documents:
        raise ValueError('At least one document is required')
    if any((title, lang, direction)):
        if len(documents) != 1:
            raise ValueError('CLI title/language overrides apply only to one document')
        if not isinstance(documents[0], dict):
            raise ValueError('Document must be an object')
        documents[0] = dict(documents[0])
        for key, value in (('title', title), ('lang', lang), ('dir', direction)):
            if value is not None:
                documents[0][key] = value
    documents = [validate_document(doc, i) for i, doc in enumerate(documents)]
    ids = [doc['id'] for doc in documents]
    if len(set(ids)) != len(ids):
        raise ValueError('Document IDs must be unique')
    data = json.dumps(documents, ensure_ascii=False, separators=(',', ':'))
    for old, escaped in (('&', '\\u0026'), ('<', '\\u003c'), ('>', '\\u003e'), ('\u2028', '\\u2028'), ('\u2029', '\\u2029')):
        data = data.replace(old, escaped)
    template = TEMPLATE.read_text(encoding='utf-8')
    if len(DATA_PATTERN.findall(template)) != 1:
        raise ValueError('Template must have exactly one reader-data block')
    result = DATA_PATTERN.sub(lambda m: m[1] + data + m[3], template)
    result = re.sub(r'<title>.*?</title>', lambda m: '<title>' + html.escape(documents[0]['title']) + '</title>', result, count=1)
    namespace = hashlib.sha256(json.dumps(ids, ensure_ascii=False).encode('utf-8')).hexdigest()[:20]
    for key in ('prefs', 'positions', 'marks'):
        result = result.replace(f'darang-{key}-v1', f'reader-{namespace}-{key}-v1')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(result, encoding='utf-8')
    return documents


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--title')
    parser.add_argument('--lang')
    parser.add_argument('--dir', choices=('rtl', 'ltr'))
    args = parser.parse_args()
    try:
        docs = build(args.input, args.output, args.title, args.lang, args.dir)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(f'Created {args.output} ({args.output.stat().st_size:,} bytes; {len(docs)} document(s))')


if __name__ == '__main__':
    main()
