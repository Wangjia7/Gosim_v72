#!/usr/bin/env python3
"""Public-initialize selector. Retains one chosen agent's complete state."""
import json
import os
import sys
from pathlib import Path
from routing import initial_route

PROTOCOL='participant-agent-protocol-v4'

def log(message):
    print(message,file=sys.stderr,flush=True)

def main():
    # Same key/no-model startup contract as the official project.
    from llm_client import api_key,load_dotenv
    load_dotenv(str(Path(__file__).with_name('.env')))
    # Load optional local settings before importing the planner's tunable constants.
    for name in ('PRO_FULL_FIELD', 'PRO_BREAKPOINTS', 'PRO_CONSERVATIVE_REQUIRED', 'PRO_REQUEST_BATCH'):
        os.environ.setdefault(name, '0')
    rules_only=os.environ.get('OBSERVER_MODEL_DISABLED') == '1'
    if not rules_only and not api_key():
        log('missing API key: continuing with deterministic rules');rules_only=True
    agent=None;family=None;replies={}
    for line in sys.stdin:
        if not line.strip():continue
        message=json.loads(line);kind=message.get('message_type')
        if kind=='initialize':
            family,reasons=initial_route(message['payload'])
            if family=='fusion_core':
                from fusion_core.agent import ObserverAgent
            else:
                from enhanced_agent import ObserverAgent
            agent=ObserverAgent(message['payload'],rules_only=rules_only)
            log('initial router: '+json.dumps({'family':family,'public_reasons':reasons,
                'hidden_anomalies':'unknown; no initial classification claimed'}))
        elif kind=='decision_request':
            sequence=message['decision_sequence']
            if sequence in replies:
                print(replies[sequence],flush=True);continue
            try:action=agent.respond(message['payload'])
            except Exception as exc:
                log(f'error {type(exc).__name__}: {exc}; waiting one slot')
                action={'action':'wait','duration_seconds':900,'reason':'internal error'}
            action.setdefault('decision_source','rules' if rules_only else 'llm-advised')
            reply=json.dumps({'protocol_version':PROTOCOL,'message_type':'decision_response',
                 'decision_sequence':sequence,**action},separators=(',',':'))
            replies[sequence]=reply
            if len(replies)>16:replies.pop(next(iter(replies)))
            print(reply,flush=True)
        elif kind=='finish':
            log(f'router finished: family={family} termination={message.get("payload",{}).get("termination_reason")}')
    return 0

if __name__=='__main__':raise SystemExit(main())
