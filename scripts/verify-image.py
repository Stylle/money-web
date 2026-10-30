"""Verify Docker Hub tags and both Linux platforms without printing credentials."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--image',default='stylle/money-web')
    p.add_argument('--tags',nargs='+',default=['0.2.0','latest'])
    p.add_argument('--docker-config',default='')
    p.add_argument('--output')
    args = p.parse_args()
    command = ['docker']+(['--config',args.docker_config] if args.docker_config else [])
    results = []
    for tag in args.tags:
        image = args.image+':'+tag
        run = subprocess.run(command+['buildx','imagetools','inspect',image],capture_output=True,text=True,check=True)
        match = re.search(r'^Digest:\s+(sha256:[0-9a-f]{64})',run.stdout,re.MULTILINE)
        if not match:raise RuntimeError('Registry digest was not returned')
        raw = subprocess.run(command+['buildx','imagetools','inspect','--raw',image],capture_output=True,text=True,check=True)
        manifest = json.loads(raw.stdout)
        platforms = sorted({m['platform']['os']+'/'+m['platform']['architecture'] for m in manifest.get('manifests',[]) if m.get('platform',{}).get('architecture')!='unknown'})
        if not {'linux/amd64','linux/arm64'} <= set(platforms):raise RuntimeError('Required platform missing')
        results.append({'tag':tag,'digest':match.group(1),'platforms':platforms})
    if len({r['digest'] for r in results})!=1:raise RuntimeError('Release tags refer to different manifests')
    report = {'checked_at':datetime.now(timezone.utc).isoformat(),'image':args.image,'registry_verified':True,'tags_match':True,'tags':results}
    if args.output:Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report),flush=True)


if __name__=='__main__':main()
