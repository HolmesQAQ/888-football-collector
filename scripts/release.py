"""Publish a tested commit; token is supplied only by GitHub Actions."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def main():
    version = Path('VERSION').read_text('utf-8').strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Invalid VERSION')
    tag = 'v' + version
    notes = Path('releases', tag + '.md').read_text('utf-8')
    repo, commit = os.environ['GITHUB_REPOSITORY'], os.environ['GITHUB_SHA']
    token = os.environ['GH_TOKEN']
    base = 'https://api.github.com/repos/' + repo

    def request(url, data=None, method=None, content_type='application/json'):
        body = json.dumps(data).encode() if isinstance(data, dict) else data
        headers = {'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
                   'Content-Type': content_type, 'X-GitHub-Api-Version': '2022-11-28'}
        with urlopen(Request(url, data=body, headers=headers, method=method), timeout=90) as response:
            return json.load(response)

    try:
        existing = request(base + '/releases/tags/' + tag)
    except HTTPError as error:
        if error.code != 404:
            raise
    else:
        if existing['draft']:
            raise RuntimeError('An incomplete draft exists; inspect it before resuming publication')
        print('Version already published; existing release and tag are unchanged:', existing['html_url'])
        return

    archive = '888-football-collector-' + tag + '.zip'
    subprocess.run(['git', 'archive', '--format=zip', '--prefix=888-football-collector-' + tag + '/',
                    '--output=' + archive, commit], check=True)
    checksum = Path('SHA256SUMS.txt')
    checksum.write_text(hashlib.sha256(Path(archive).read_bytes()).hexdigest() + '  ' + archive + '\n', encoding='utf-8')
    release = request(base + '/releases', dict(tag_name=tag, target_commitish=commit,
        name='888 足球数据采集器 ' + tag, body=notes, draft=True, prerelease=False))
    upload = release['upload_url'].split('{')[0]
    for path in (Path(archive), checksum):
        request(upload + '?name=' + path.name, path.read_bytes(), 'POST', 'application/octet-stream')
    published = request(base + '/releases/' + str(release['id']), {'draft': False}, 'PATCH')
    print('Published:', published['html_url'])


if __name__ == '__main__':
    main()
