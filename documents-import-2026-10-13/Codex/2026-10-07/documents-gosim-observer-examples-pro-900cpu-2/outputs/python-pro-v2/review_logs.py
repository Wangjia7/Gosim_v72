#!/usr/bin/env python3
"""Read a bounded tail of agent/audit logs; --send explicitly calls the configured LLM."""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path
from llm_client import LLMClient, api_key, load_dotenv
from review import REVIEW_SYSTEM, validate_review


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log', type=Path)
    parser.add_argument('--send', action='store_true', help='send log excerpt to the configured model')
    parser.add_argument('--out', type=Path)
    parser.add_argument('--max-bytes', type=int, default=48000)
    args = parser.parse_args()
    if not 1 <= args.max_bytes <= 256000:
        parser.error('--max-bytes must be 1..256000')
    load_dotenv(str(Path(__file__).parent / '.env'))
    with args.log.open('rb') as f:
        f.seek(0, 2)
        length = f.tell()
        f.seek(max(0, length - args.max_bytes))
        excerpt = f.read(args.max_bytes).decode('utf-8', errors='replace')
    if api_key():
        excerpt = excerpt.replace(api_key(), '[REDACTED]')
    excerpt = re.sub(r'(?i)(authorization\s*[:=]\s*|api[_-]?key\s*[:=]\s*)[^\s,]+', r'\1[REDACTED]', excerpt)
    evidence = {'source_name': args.log.name, 'truncated': length > args.max_bytes, 'log_excerpt': excerpt}
    output = {'mode': 'preview', 'evidence': evidence}
    if args.send:
        if not api_key():
            parser.error('missing API key: set OPENAI_API_KEY')
        client = LLMClient(call_timeout=45, max_calls=1, max_retries=1)
        call = client.submit('log_review', REVIEW_SYSTEM, evidence, 90)
        call.wait(46)
        answer = validate_review(client.collect(call))
        if answer is None:
            raise SystemExit('log review failed, timed out, or returned invalid JSON; log unchanged')
        output = {'mode': 'llm', 'answer': answer}
    text = json.dumps(output, ensure_ascii=False, indent=2) + '\n'
    if args.out:
        args.out.write_text(text, encoding='utf-8')
    else:
        print(text, end='')


if __name__ == '__main__':
    main()
