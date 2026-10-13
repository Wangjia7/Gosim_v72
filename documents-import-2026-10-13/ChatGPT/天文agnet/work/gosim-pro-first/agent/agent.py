#!/usr/bin/env python3
"""Public-initialize selector. Retains one chosen agent's complete state."""
import json
import sys
from pathlib import Path
from routing import initial_route

PROTOCOL='participant-agent-protocol-v4'

def log(message):
    print(message,file=sys.stderr,flush=True)

def main():
    # Same key/no-model startup contract as the official project.
    from official_pro.llm_client import api_key,load_dotenv
    from official_pro.agent import model_disabled
    load_dotenv(str(Path(__file__).with_name('.env')))
    rules_only=model_disabled()
    if not rules_only and not api_key():
        log('missing API key: set OPENAI_API_KEY');return 2
    agent=None;family=None
    for line in sys.stdin:
        if not line.strip():continue
        message=json.loads(line);kind=message.get('message_type')
        if kind=='initialize':
            family,reasons=initial_route(message['payload'])
            if family=='official_pro':
                from official_pro.agent import ObserverAgent
            else:
                from enhanced_agent import ObserverAgent
            agent=ObserverAgent(message['payload'],rules_only=rules_only)
            log('initial router: '+json.dumps({'family':family,'public_reasons':reasons,
                'hidden_anomalies':'unknown; no initial classification claimed'}))
        elif kind=='decision_request':
            try:action=agent.respond(message['payload'])
            except Exception as exc:
                log(f'error {type(exc).__name__}: {exc}; waiting one slot')
                action={'action':'wait','duration_seconds':900,'reason':'internal error'}
            action.setdefault('decision_source','rules' if rules_only else 'llm-advised')
            print(json.dumps({'protocol_version':PROTOCOL,'message_type':'decision_response',
                 'decision_sequence':message['decision_sequence'],**action},separators=(',',':')),flush=True)
        elif kind=='finish':
            log(f'router finished: family={family} termination={message.get("payload",{}).get("termination_reason")}')
    return 0

if __name__=='__main__':raise SystemExit(main())
