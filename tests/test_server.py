"""Independent HTTP integration checks against a real loopback server.

Fixtures are synthetic files in a temporary directory. No user browser,
credentials, external service or private project file is accessed.
"""
from __future__ import annotations

import hashlib
import http.client
import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from independent_oracle import named_cases
from server import LocalServer
from vertice.codec import solve_json

HTTP_OBSERVATIONS = []


class LocalHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (ROOT / 'tmp').mkdir(exist_ok=True)
        cls.temporary = tempfile.TemporaryDirectory(prefix='http-audit-', dir=ROOT / 'tmp')
        cls.fixture_root = Path(cls.temporary.name)
        cls.web = cls.fixture_root / 'web'
        cls.web.mkdir()
        cls.video = bytes(range(256)) * 256
        (cls.web / 'index.html').write_text('<!doctype html><html lang="es"><title>Fixture</title></html>', encoding='utf-8')
        (cls.web / 'movie.mp4').write_bytes(cls.video)
        (cls.web / 'empty.bin').write_bytes(b'')
        (cls.web / 'runtime.wasm').write_bytes(b'\x00asm\x01\x00\x00\x00')
        (cls.web / 'engine.mjs').write_text('export const ready=true;', encoding='utf-8')
        (cls.web / 'captions.vtt').write_text('WEBVTT\n', encoding='utf-8')
        (cls.fixture_root / 'private.txt').write_text('PRIVATE_FIXTURE_MUST_NOT_BE_SERVED', encoding='utf-8')
        (cls.web / 'directory').mkdir()
        (cls.web / 'directory' / 'hidden.txt').write_text('directory listing forbidden', encoding='utf-8')
        cls.server = LocalServer(('127.0.0.1', 0), web_root=cls.web)
        cls.port = cls.server.server_port
        cls.thread = threading.Thread(target=cls.server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)
        cls.temporary.cleanup()

    def exchange(self, method='GET', path='/', body=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=7)
        request_headers = {'Connection': 'close', **(headers or {})}
        connection.request(method, path, body=body, headers=request_headers)
        response = connection.getresponse()
        status, response_headers, content = response.status, dict(response.getheaders()), response.read()
        connection.close()
        HTTP_OBSERVATIONS.append({'test': self.id(), 'method': method, 'path': path, 'status': status,
                                  'response_bytes': len(content),
                                  'content_type': response_headers.get('Content-Type'),
                                  'content_range': response_headers.get('Content-Range')})
        return status, response_headers, content

    def raw(self, method='GET', path='/', headers=(), body=b'', shutdown_write=False):
        wire = (f'{method} {path} HTTP/1.1\r\n' + '\r\n'.join(headers) +
                '\r\nConnection: close\r\n\r\n').encode('ascii') + body
        with socket.create_connection(('127.0.0.1', self.port), timeout=7) as client:
            client.settimeout(7)
            client.sendall(wire)
            if shutdown_write:
                client.shutdown(socket.SHUT_WR)
            chunks = []
            while True:
                chunk = client.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
        response = b''.join(chunks)
        head, content = response.split(b'\r\n\r\n', 1)
        status = int(head.split(b' ', 2)[1])
        HTTP_OBSERVATIONS.append({'test': self.id(), 'method': method, 'path': path, 'status': status,
                                  'response_bytes': len(content), 'raw_request': True})
        return status, head, content

    def post(self, text, headers=None):
        if isinstance(text, str):
            text = text.encode('utf-8')
        return self.exchange('POST', '/api/solve', text, {'Content-Type': 'application/json', **(headers or {})})

    def test_health_reports_actual_core_hashes_and_no_cors(self):
        status, headers, content = self.exchange(path='/api/health')
        self.assertEqual(status, 200)
        data = json.loads(content)
        self.assertEqual(data['project'], 'vertice-sdv')
        self.assertEqual(data['engine'], 'python')
        for name, digest in data['core'].items():
            self.assertEqual(digest, hashlib.sha256((ROOT / 'vertice' / name).read_bytes()).hexdigest())
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertNotIn('Access-Control-Allow-Origin', headers)

    def test_second_server_cannot_bind_the_same_listening_port(self):
        with self.assertRaises(OSError):
            duplicate = LocalServer(('127.0.0.1', self.port), web_root=self.web)
            duplicate.server_close()
        self.assertEqual(self.exchange(path='/api/health')[0], 200)

    def test_http_matches_python_for_shared_cases_and_both_trace_modes(self):
        for fixture in named_cases():
            for trace in (False, True):
                with self.subTest(case=fixture['id'], trace=trace):
                    payload = {**fixture['payload'], 'trace': trace}
                    encoded = json.dumps(payload, ensure_ascii=False)
                    status, _, content = self.post(encoded)
                    self.assertEqual(status, 200)
                    self.assertEqual(json.loads(content), json.loads(solve_json(encoded)))

    def test_trusted_hostnames_with_correct_port(self):
        for host in (f'127.0.0.1:{self.port}', f'localhost:{self.port}', f'LOCALHOST:{self.port}'):
            with self.subTest(host=host):
                self.assertEqual(self.exchange(headers={'Host': host})[0], 200)

    def test_wrong_missing_or_duplicate_host_rejected(self):
        for host in ('evil.example', '127.0.0.1', f'localhost:{self.port + 1}', f'127.0.0.1:{self.port}.evil.example'):
            with self.subTest(host=host):
                self.assertEqual(self.exchange(headers={'Host': host})[0], 403)
        self.assertEqual(self.raw(headers=())[0], 403)
        self.assertEqual(self.raw(headers=(f'Host: 127.0.0.1:{self.port}', f'Host: 127.0.0.1:{self.port}'))[0], 403)

    def test_cross_origin_is_rejected_and_same_origin_allowed(self):
        for origin in ('https://evil.example', 'null', f'https://localhost:{self.port}', 'http://localhost.evil.example'):
            with self.subTest(origin=origin):
                self.assertEqual(self.exchange(headers={'Origin': origin})[0], 403)
        self.assertEqual(self.exchange(headers={'Origin': f'http://127.0.0.1:{self.port}'})[0], 200)

    def test_duplicate_origin_is_not_silently_accepted(self):
        status, _, _ = self.raw(headers=(f'Host: 127.0.0.1:{self.port}',
                                        f'Origin: http://127.0.0.1:{self.port}', 'Origin: https://evil.example'))
        self.assertEqual(status, 403)

    def test_outside_paths_never_serve_private_file(self):
        for path in ('/../private.txt', '/%2e%2e/private.txt', '/%2E%2E%2Fprivate.txt',
                     '/..%5cprivate.txt', '/%00', '/%ff', '/C:/private.txt',
                     'http://evil.example/private.txt', '/api/../private.txt'):
            with self.subTest(path=path):
                status, _, content = self.exchange(path=path)
                self.assertIn(status, (403, 404))
                self.assertNotIn(b'PRIVATE_FIXTURE', content)

    def test_directory_listing_is_not_exposed(self):
        status, _, content = self.exchange(path='/directory/')
        self.assertEqual(status, 404)
        self.assertNotIn(b'hidden.txt', content)

    def test_expected_mime_and_security_headers(self):
        for path, content_type in [('/runtime.wasm', 'application/wasm'), ('/engine.mjs', 'text/javascript'),
                                   ('/captions.vtt', 'text/vtt; charset=utf-8'), ('/movie.mp4', 'video/mp4')]:
            with self.subTest(path=path):
                status, headers, _ = self.exchange(path=path)
                self.assertEqual(status, 200)
                self.assertEqual(headers['Content-Type'], content_type)
                self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
                self.assertEqual(headers['Cross-Origin-Resource-Policy'], 'same-origin')
                self.assertIn("frame-ancestors 'none'", headers['Content-Security-Policy'])

    def test_head_has_get_length_but_no_body(self):
        for path in ('/', '/movie.mp4', '/api/health', '/does-not-exist'):
            with self.subTest(path=path):
                get_status, get_headers, get_body = self.exchange(path=path)
                head_status, head_headers, head_body = self.exchange('HEAD', path)
                self.assertEqual(head_status, get_status)
                self.assertEqual(head_headers['Content-Length'], get_headers['Content-Length'])
                self.assertEqual(head_body, b'')
                self.assertEqual(len(get_body), int(get_headers['Content-Length']))

    def test_head_ignores_range_per_http_semantics(self):
        status, headers, content = self.exchange('HEAD', '/movie.mp4', headers={'Range': 'bytes=0-15'})
        self.assertEqual(status, 200)
        self.assertEqual(int(headers['Content-Length']), len(self.video))
        self.assertNotIn('Content-Range', headers)
        self.assertEqual(content, b'')

    def test_video_range_forward_suffix_open_and_clamped(self):
        for value, start, end in [('bytes=0-0', 0, 0), ('bytes=256-511', 256, 511),
                                  ('bytes=65530-', 65530, 65535), ('bytes=-7', 65529, 65535),
                                  ('bytes=65530-999999', 65530, 65535), ('bytes=-999999', 0, 65535)]:
            with self.subTest(value=value):
                status, headers, content = self.exchange(path='/movie.mp4', headers={'Range': value})
                self.assertEqual(status, 206)
                self.assertEqual(content, self.video[start:end + 1])
                self.assertEqual(headers['Content-Range'], f'bytes {start}-{end}/{len(self.video)}')
                self.assertEqual(int(headers['Content-Length']), end - start + 1)

    def test_invalid_or_unsatisfiable_ranges_have_no_body(self):
        for value in ('bytes=65536-', 'bytes=7-2', 'bytes=-0', 'bytes=-', 'bytes=0--2',
                      'bytes=0-1,4-5', 'bytes=' + '9' * 40 + '-', 'bytes=0-1,0-1,0-1'):
            with self.subTest(value=value):
                status, headers, content = self.exchange(path='/movie.mp4', headers={'Range': value})
                self.assertEqual(status, 416)
                self.assertEqual(headers['Content-Range'], f'bytes */{len(self.video)}')
                self.assertEqual(content, b'')

    def test_unknown_range_units_are_ignored(self):
        status, headers, content = self.exchange(path='/movie.mp4', headers={'Range': 'items=0-1'})
        self.assertEqual(status, 200)
        self.assertEqual(content, self.video)
        self.assertNotIn('Content-Range', headers)

    def test_if_range_mismatch_sends_complete_representation(self):
        for validator in ('"outdated-etag"', 'Wed, 01 Jan 2000 00:00:00 GMT'):
            with self.subTest(validator=validator):
                status, headers, content = self.exchange(path='/movie.mp4', headers={
                    'Range': 'bytes=0-15', 'If-Range': validator})
                self.assertEqual(status, 200)
                self.assertEqual(content, self.video)
                self.assertNotIn('Content-Range', headers)

    def test_empty_file_and_empty_range(self):
        status, headers, content = self.exchange(path='/empty.bin')
        self.assertEqual((status, headers['Content-Length'], content), (200, '0', b''))
        status, headers, content = self.exchange(path='/empty.bin', headers={'Range': 'bytes=0-0'})
        self.assertEqual((status, headers['Content-Range'], content), (416, 'bytes */0', b''))

    def test_post_body_framing_rejects_missing_duplicate_and_invalid_length(self):
        base = (f'Host: 127.0.0.1:{self.port}', 'Content-Type: application/json')
        for headers in [base, (*base, 'Content-Length: -2'), (*base, 'Content-Length: +2'),
                        (*base, 'Content-Length: 2', 'Content-Length: 2')]:
            self.assertEqual(self.raw('POST', '/api/solve', headers=headers, body=b'{}')[0], 411)
        self.assertEqual(self.raw('POST', '/api/solve', headers=(*base, 'Transfer-Encoding: chunked'),
                                  body=b'0\r\n\r\n')[0], 400)
        self.assertEqual(self.raw('POST', '/api/solve', headers=(*base, 'Content-Length: 2097153'))[0], 413)

    def test_truncated_post_is_a_controlled_client_error(self):
        headers = (f'Host: 127.0.0.1:{self.port}', 'Content-Type: application/json', 'Content-Length: 100')
        status, _, content = self.raw('POST', '/api/solve', headers=headers, body=b'{}', shutdown_write=True)
        self.assertEqual(status, 400)
        self.assertIn('incompleto', json.loads(content)['error'])

    def test_stalled_post_times_out_while_health_remains_available(self):
        headers = (f'POST /api/solve HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\n'
                   'Content-Type: application/json\r\nContent-Length: 100\r\nConnection: close\r\n\r\n{}')
        with socket.create_connection(('127.0.0.1', self.port), timeout=7) as client:
            client.settimeout(7)
            client.sendall(headers.encode())
            self.assertEqual(self.exchange(path='/api/health')[0], 200)
            # A read timeout is behavior being tested; no artificial waiting or CPU workload.
            started = time.monotonic()
            chunks = []
            while True:
                chunk = client.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
            response = b''.join(chunks)
            self.assertEqual(int(response.split(b' ', 2)[1]), 408)
            self.assertLess(time.monotonic() - started, 7)
            HTTP_OBSERVATIONS.append({'test': self.id(), 'method': 'POST', 'path': '/api/solve',
                                      'status': 408, 'stalled_body': True})

    def test_content_type_and_invalid_utf8_rejected(self):
        self.assertEqual(self.post(b'{}', {'Content-Type': 'text/plain'})[0], 415)
        self.assertEqual(self.post(b'\xff')[0], 400)
        valid = json.dumps(named_cases()[0]['payload'])
        self.assertEqual(self.post(valid, {'Content-Type': 'application/json; charset=utf-8'})[0], 200)

    def test_duplicate_content_type_is_not_ambiguous(self):
        body = json.dumps(named_cases()[0]['payload']).encode()
        status, _, _ = self.raw('POST', '/api/solve', headers=(f'Host: 127.0.0.1:{self.port}',
            f'Content-Length: {len(body)}', 'Content-Type: application/json', 'Content-Type: text/plain'), body=body)
        self.assertIn(status, (400, 415))

    def test_json_hostile_payloads_return_json_errors(self):
        base = json.dumps(named_cases()[1]['payload'])
        malformed = ['{}', '[]', 'null', '{', base + '{}',
                     base.replace('"trace": true', '"trace": true, "trace": false'),
                     base.replace('"weight": "2"', '"weight": 1e999999999999999999999999999999999'),
                     base.replace('"weight": "2"', '"weight": NaN'),
                     base[:-1] + ',"\\ud800":1}', '[' * 1200 + '0' + ']' * 1200]
        for text in malformed:
            with self.subTest(text=text[:80]):
                status, headers, content = self.post(text)
                self.assertEqual(status, 400)
                self.assertTrue(headers['Content-Type'].startswith('application/json'))
                self.assertIsInstance(json.loads(content)['error'], str)
        # The server must remain usable after rejected requests.
        self.assertEqual(self.exchange(path='/api/health')[0], 200)

    def test_unknown_endpoints_and_options_do_not_enable_remote_api(self):
        self.assertEqual(self.exchange(path='/api/solve')[0], 404)
        self.assertEqual(self.exchange('POST', '/wrong', '{}', {'Content-Type': 'application/json'})[0], 404)
        status, headers, _ = self.exchange('OPTIONS', '/api/solve')
        self.assertEqual(status, 405)
        self.assertNotIn('Access-Control-Allow-Origin', headers)

    def test_validate_endpoint_preserves_raw_numeric_precision(self):
        graph = named_cases()[1]['payload']['graph']
        encoded = json.dumps(graph)
        for token, expected_status, expected_weight in [('0.1', 200, '0.1'),
                                                       ('1000000000000.000001', 400, None),
                                                       ('1e-1000', 400, None)]:
            with self.subTest(token=token):
                text = encoded.replace('"weight": "2"', '"weight": ' + token)
                status, _, content = self.exchange('POST', '/api/validate', text.encode(), {'Content-Type': 'application/json'})
                self.assertEqual(status, expected_status)
                value = json.loads(content)
                if expected_weight is not None:
                    # Endpoint returns the canonical graph itself, without running a search.
                    self.assertEqual(next(edge for edge in value['edges'] if edge['id'] == 'e0')['weight'], expected_weight)
                else:
                    self.assertIsInstance(value['error'], str)

    def test_validate_endpoint_rejects_ambiguous_json_and_remote_origin(self):
        encoded = json.dumps(named_cases()[1]['payload']['graph'])
        duplicate = encoded.replace('"directed": false', '"directed": false, "directed": true')
        status, _, _ = self.exchange('POST', '/api/validate', duplicate.encode(), {'Content-Type': 'application/json'})
        self.assertEqual(status, 400)
        status, _, _ = self.exchange('POST', '/api/validate', encoded.encode(),
                                     {'Content-Type': 'application/json', 'Origin': 'https://evil.example'})
        self.assertEqual(status, 403)


if __name__ == '__main__':
    unittest.main(verbosity=2)
