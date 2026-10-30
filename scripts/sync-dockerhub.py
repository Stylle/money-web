"""Update this project's Docker Hub Overview; PAT comes from hidden stdin only."""
import getpass
import json
from pathlib import Path
import sys
import urllib.request


def main():
    secret = getpass.getpass('Docker Hub token: ') if sys.stdin.isatty() else sys.stdin.readline().strip()
    overview = (Path(__file__).resolve().parents[1]/'docs/dockerhub-description.md').read_text(encoding='utf-8')
    short = 'Single-container investment watch: stocks, ETFs, crypto, news, portfolios and optional AI.'
    def request(url, data=None, token=None, method=None):
        headers = {'Content-Type':'application/json'}
        if token:
            headers['Authorization'] = 'Bearer '+token
        req = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None,
                                     headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            print('Docker Hub request failed: HTTP '+str(exc.code)+' ('+(method or ('POST' if data else 'GET'))+')')
            raise
    auth = request('https://hub.docker.com/v2/auth/token', {'identifier':'stylle','secret':secret})
    secret = None
    token = auth['access_token']
    url = 'https://hub.docker.com/v2/repositories/stylle/money-web/'
    request(url, {'description':short,'full_description':overview}, token, 'PATCH')
    result = request(url, token=token)
    if result.get('full_description') != overview:
        raise RuntimeError('Overview verification failed')
    print('Docker Hub Overview updated and verified')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # Never log headers, credentials, response bodies, or request URLs.
        print('Docker Hub Overview sync failed: '+type(exc).__name__)
        sys.exit(1)
