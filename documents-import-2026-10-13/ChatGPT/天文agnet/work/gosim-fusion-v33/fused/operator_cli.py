#!/usr/bin/env python3
"""Side adapter for a real human note; it does not modify the website protocol.

Input JSON: now_utc, known_target_ids, active_requests, operator_messages,
forecast_tonight, bulletin_now. Output is a validated internal preference.
"""
import argparse
import json
import sys
from pathlib import Path
from advisor import Advisor
from llm_client import LLMClient, api_key
from skymath import parse_utc


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    args=parser.parse_args()
    if not api_key():raise SystemExit('set OPENAI_API_KEY for the operator adapter')
    data=json.loads(args.input.read_text())
    advisor=Advisor(LLMClient(log=lambda t:print(t,file=sys.stderr),max_calls=2,max_retries=1))
    advisor.now=parse_utc(data['now_utc']).timestamp()
    advisor.valid_until=advisor.now+900
    advisor.known_targets=set(data.get('known_target_ids',[]))
    advisor.active_requests={r['request_id']:r for r in data.get('active_requests',[])}
    advisor.texts=[{'source_id':str(x['message_id']),'text':str(x['text'])[:2000]}
                  for x in data.get('operator_messages',[])[:16]]
    plan,_=advisor.start_night(data['now_utc'][:10],data.get('forecast_tonight',[]),
                              data.get('bulletin_now',[]),{'rows':[]},60,8)
    if plan is None:raise SystemExit('no valid operator interpretation returned')
    print(json.dumps(plan,ensure_ascii=False))

if __name__=='__main__':main()
