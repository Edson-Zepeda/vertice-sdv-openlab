"""Verify a released ZIP anonymously against its local receipt and source revision.

The output belongs outside the source checkout, so recording delivery proof does
not change the revision identified inside the delivered ZIP. No credentials used.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.request
from urllib.parse import urlsplit, urlunsplit
import zipfile


def sha(data):
    return hashlib.sha256(data).hexdigest()


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "VERTICE-release-verification", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.status, response.read(), response.geturl()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    package = args.package.resolve()
    output = args.output.resolve()
    if output.suffix.lower() != '.json':
        parser.error("Save final verification as a .json file.")
    if output.is_relative_to(root):
        parser.error("Save final verification outside the source checkout.")
    protected = (package, package.with_suffix('.receipt.json'), package.with_suffix('.sha256'))
    if any(output == path.resolve() or
           (output.exists() and path.exists() and output.samefile(path)) for path in protected):
        parser.error("The verification output must not replace the ZIP, receipt or checksum.")
    receipt = json.loads(package.with_suffix('.receipt.json').read_text(encoding='utf8'))
    data = package.read_bytes()
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "checks": [], "authentication": "None", "errors": []}

    def check(name, passed, **details):
        report['checks'].append({'name': name, 'passed': bool(passed), **details})
        if not passed:
            raise AssertionError(name)

    try:
        check('Local receipt matches ZIP', receipt['sha256'] == sha(data) and receipt['bytes'] == len(data) and not receipt['source_dirty'])
        with zipfile.ZipFile(package) as archive:
            check('ZIP CRC is valid', archive.testzip() is None)
            manifest = json.loads(archive.read('VerticeSDV/MANIFEST.json'))
            check('Manifest identifies the clean source revision', manifest['source_revision'] == receipt['source_revision'] and manifest['release_ready'] and not manifest['source_dirty'])
            expected = {'VerticeSDV/' + row['path'] for row in manifest['files']} | {'VerticeSDV/MANIFEST.json'}
            check('No missing, duplicate or additional entries', set(archive.namelist()) == expected and len(archive.namelist()) == len(expected))
            mismatches = [row['path'] for row in manifest['files'] if sha(archive.read('VerticeSDV/' + row['path'])) != row['sha256'] or len(archive.read('VerticeSDV/' + row['path'])) != row['bytes']]
            check('Every archived file matches its manifest', not mismatches, files=len(manifest['files']), mismatches=mismatches)
            metadata = json.loads(archive.read('VerticeSDV/web/data/release.json'))
        api = 'https://api.github.com/repos/Edson-Zepeda/vertice-sdv-openlab'
        status, raw, url = fetch(api + '/releases/tags/v' + manifest['version'])
        release = json.loads(raw)
        check('Release is public and final', status == 200 and not release['draft'] and not release['prerelease'], url=release['html_url'])
        status, raw, _ = fetch(api + '/git/ref/tags/' + release['tag_name'])
        reference = json.loads(raw)['object']
        if reference['type'] == 'tag':
            _, raw, _ = fetch(reference['url']); reference = json.loads(raw)['object']
        check('Release tag points to the archived source', status == 200 and reference['type'] == 'commit' and reference['sha'] == manifest['source_revision'], revision=reference['sha'])
        assets = [asset for asset in release['assets'] if asset['name'] == package.name]
        check('Exactly one named download is available', len(assets) == 1)
        asset = assets[0]
        check('The project links to this release asset', metadata['published'] and metadata['package'] == asset['browser_download_url'])
        status, downloaded, final_url = fetch(asset['browser_download_url'])
        location = urlsplit(final_url)
        public_location = urlunsplit((location.scheme, location.netloc, location.path, '', ''))
        check('Anonymous download equals the local ZIP', status == 200 and downloaded == data, bytes=len(downloaded), sha256=sha(downloaded), final_url_without_query=public_location)
        report['source_revision'] = manifest['source_revision']
        report['package_sha256'] = sha(data)
        report['release_url'] = release['html_url']
    except Exception as error:
        report['errors'].append(f'{type(error).__name__}: {error}')
    report['finished_at'] = datetime.now(timezone.utc).isoformat()
    report['passed'] = not report['errors'] and all(row['passed'] for row in report['checks'])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'passed': report['passed'], 'checks': len(report['checks']), 'errors': report['errors']}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
