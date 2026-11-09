#!/usr/bin/env python3
"""Explicit hook installation. Default: print a proposal, write nothing."""
import argparse
import json
import os
import sys
import tomllib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from doska_flow.config import codex_home
from doska_flow.model import FlowError

EVENTS=('SessionStart','UserPromptSubmit','PreToolUse','PostToolUse','Stop','Interrupt','SessionEnd')

def template():
    code="import os,pathlib,runpy;runpy.run_path(str(pathlib.Path(os.environ.get('CODEX_HOME',str(pathlib.Path.home()/'.codex')))/'skills/doska-workflow/scripts/doska_flow.py'),run_name='__main__')"
    suffix=' -c '+json.dumps(code)+' hook'
    return {'description':'Doska tracking: requires explicit activation and hook trust on each machine.', 'hooks':{event:[{'hooks':[{'type':'command','command':'python3'+suffix,'commandWindows':'python'+suffix,'timeout':3 if event in ('Interrupt','SessionEnd') else 10,'statusMessage':'Doska '+event}]}] for event in EVENTS}}

def merge(existing,proposed):
    if not isinstance(existing,dict) or not isinstance(existing.get('hooks',{}),dict):raise FlowError('Existing hooks.json is malformed')
    result={**existing,'hooks':dict(existing.get('hooks',{}))}
    for event,groups in proposed['hooks'].items():
        old=result['hooks'].get(event,[])
        if not isinstance(old,list):raise FlowError('Existing hook event must be an array')
        result['hooks'][event]=old+[group for group in groups if group not in old]
    return result

def apply(home,proposed):
    path=Path(home)/'hooks.json'
    config=Path(home)/'config.toml'
    if config.exists() and 'hooks' in tomllib.loads(config.read_text()):raise FlowError('Inline hooks already exist in config.toml; merge the template there explicitly to avoid duplicate sources')
    merged=merge(json.loads(path.read_text()) if path.exists() else {},proposed)
    Path(home).mkdir(parents=True,exist_ok=True)
    temp=path.with_name('hooks.json.doska.tmp')
    fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        with os.fdopen(fd,'w') as f:json.dump(merged,f,indent=2);f.write('\n')
        os.replace(temp,path)
    finally:
        if temp.exists():temp.unlink()
    return path

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--home',type=Path,default=codex_home());p.add_argument('--apply',action='store_true');a=p.parse_args()
    proposed=template()
    if a.apply:
        # The command inherits this machine's CODEX_HOME. Targeting a different
        # directory is useful for a sandboxed trial, not implicit global activation.
        print('Wrote '+str(apply(a.home,proposed))+'. Review/trust the hooks in Codex; installation does not trust them.')
    else:print(json.dumps(proposed,indent=2));print('Dry run only; no files changed.',file=sys.stderr)
if __name__=='__main__':
    try:main()
    except (FlowError,OSError,ValueError) as exc:print(str(exc),file=sys.stderr);raise SystemExit(2)
