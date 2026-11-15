import contextlib
import importlib.util
import io
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, PropertyMock, patch


SCRIPT = Path(__file__).with_name('http-status.py')
SPEC = importlib.util.spec_from_file_location('http_status', SCRIPT)
http_status = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(http_status)


class URLValidationTests(unittest.TestCase):
    def test_normalizes_common_addresses(self):
        examples = {
            ' example.com ': 'https://example.com',
            'HTTP://example.com/path': 'HTTP://example.com/path',
            '//example.com': 'https://example.com',
            'localhost:8080/path': 'https://localhost:8080/path',
            'example.com:443': 'https://example.com:443',
            '[::1]:8080': 'https://[::1]:8080',
            'example.com/?next=http://other.test':
                'https://example.com/?next=http://other.test',
        }
        for supplied, expected in examples.items():
            with self.subTest(url=supplied):
                self.assertEqual(http_status.validate_url(supplied), expected)

    def test_rejects_invalid_addresses(self):
        for url in ('', ' ', 'ftp://example.com', 'mailto:user@example.com',
                    'http:example.com', 'https://', 'https://:443',
                    'https://example.com:abc', 'https://example.com:65536',
                    'https://[::1', 'https://exam ple.com',
                    'https://exam\nple.com', 'https://example.com/\x00'):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    http_status.validate_url(url)


class CLITests(unittest.TestCase):
    def run_cli(self, arguments, results=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(http_status, 'init'), \
                patch.object(http_status.time, 'sleep'), \
                patch.object(http_status, 'check_status_code') as check, \
                patch.object(http_status, 'format_result', return_value='result'), \
                contextlib.redirect_stdout(stdout), \
                contextlib.redirect_stderr(stderr):
            check.side_effect = results
            status = http_status.main(arguments)
        return status, stdout.getvalue(), stderr.getvalue(), check

    def test_network_failure_returns_nonzero(self):
        status, _, _, _ = self.run_cli(
            ['-u', 'example.com'], [{'success': False}])
        self.assertEqual(status, 1)

    def test_http_error_is_still_a_received_response(self):
        status, _, _, _ = self.run_cli(
            ['-u', 'example.com'], [{'success': True, 'status_code': 503}])
        self.assertEqual(status, 0)

    def test_invalid_url_does_not_make_a_request(self):
        for url in ('', 'ftp://example.com'):
            with self.subTest(url=url):
                status, _, stderr, check = self.run_cli(['-u', url])
                self.assertEqual(status, 1)
                self.assertIn('Invalid URL:', stderr)
                check.assert_not_called()

    def test_invalid_timeouts_are_argument_errors(self):
        for timeout in ('0', '-1', 'abc', '1.5'):
            with self.subTest(timeout=timeout), \
                    patch.object(http_status, 'check_status_code') as check, \
                    contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    http_status.main(['-u', 'example.com', '-t', timeout])
                self.assertEqual(error.exception.code, 2)
                check.assert_not_called()

    def test_passes_request_options(self):
        status, _, _, check = self.run_cli(
            ['-u', 'example.com', '-t', '5', '--no-redirect',
             '--user-agent', 'test-agent'], [{'success': True}])
        self.assertEqual(status, 0)
        check.assert_called_once_with(
            'https://example.com', timeout=5, follow_redirects=False,
            user_agent='test-agent')

    def test_batch_continues_and_preserves_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, 'urls.txt')
            path.write_text(
                'example.com\nftp://example.com\n\nother.test\nlast.test\n',
                encoding='utf-8-sig')
            status, stdout, stderr, check = self.run_cli(
                ['-f', str(path)],
                [{'success': True}, {'success': False}, {'success': True}])
        self.assertEqual(status, 1)
        self.assertEqual(check.call_count, 3)
        self.assertEqual(check.call_args_list[0][0][0], 'https://example.com')
        self.assertEqual(check.call_args_list[-1][0][0], 'https://last.test')
        self.assertIn('Checking 4 URLs', stdout)
        self.assertIn('Invalid URL:', stderr)

    def test_empty_and_missing_files_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, 'urls.txt')
            path.write_text('\n  \n', encoding='utf-8')
            status, _, stderr, check = self.run_cli(['-f', str(path)])
            self.assertEqual(status, 1)
            self.assertIn('empty', stderr)
            check.assert_not_called()
            status, _, stderr, check = self.run_cli(['-f', str(path) + '.missing'])
            self.assertEqual(status, 1)
            self.assertIn('Error reading file', stderr)
            check.assert_not_called()

    def test_invalid_utf8_file_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, 'urls.txt')
            path.write_bytes(b'\xff')
            status, _, stderr, check = self.run_cli(['-f', str(path)])
        self.assertEqual(status, 1)
        self.assertIn('Error reading file', stderr)
        check.assert_not_called()

    def test_keyboard_interrupt_returns_130(self):
        status, _, stderr, _ = self.run_cli(
            ['-u', 'example.com'], KeyboardInterrupt())
        self.assertEqual(status, 130)
        self.assertIn('cancelled', stderr)


class RequestTests(unittest.TestCase):
    def make_response(self, headers=None):
        response = MagicMock()
        response.__enter__.return_value = response
        response.status_code = 200
        response.reason = 'OK'
        response.url = 'https://other.test/'
        response.history = [object()]
        response.headers = headers or {}
        type(response).content = PropertyMock(
            side_effect=AssertionError('Response body must not be read'))
        return response

    def test_streams_response_closes_it_and_uses_monotonic_time(self):
        response = self.make_response({'Content-Length': '123'})
        with patch.object(http_status.requests, 'get', return_value=response) as get, \
                patch.object(http_status.time, 'perf_counter', side_effect=[10, 10.25]):
            result = http_status.check_status_code(
                'https://example.com/', timeout=5, follow_redirects=False,
                user_agent='test-agent')
        self.assertTrue(result['success'])
        self.assertEqual(result['url'], 'https://example.com/')
        self.assertEqual(result['final_url'], 'https://other.test/')
        self.assertTrue(result['redirected'])
        self.assertEqual(result['content_length'], 123)
        self.assertEqual(result['response_time'], 250)
        get.assert_called_once_with(
            'https://example.com/', timeout=5, allow_redirects=False,
            headers={'User-Agent': 'test-agent'}, stream=True)
        response.__exit__.assert_called_once()

    def test_missing_or_invalid_lengths_are_unknown(self):
        for value in (None, '', '-1', 'invalid', '0', '42'):
            with self.subTest(value=value):
                headers = {} if value is None else {'Content-Length': value}
                response = self.make_response(headers)
                with patch.object(http_status.requests, 'get', return_value=response):
                    result = http_status.check_status_code('https://example.com/')
                expected = int(value) if value in ('0', '42') else None
                self.assertEqual(result['content_length'], expected)
                self.assertTrue(result['success'])

    def test_request_errors_are_returned(self):
        for error in (http_status.requests.exceptions.Timeout('timed out'),
                      http_status.requests.exceptions.ConnectionError('refused'),
                      http_status.requests.exceptions.TooManyRedirects('loop'),
                      http_status.requests.exceptions.InvalidHeader('bad header')):
            with self.subTest(error=type(error).__name__), \
                    patch.object(http_status.requests, 'get', side_effect=error):
                result = http_status.check_status_code('https://example.com/')
                self.assertFalse(result['success'])
                self.assertEqual(result['error_type'], type(error).__name__)

    def test_verbose_output_distinguishes_urls_and_unknown_length(self):
        response = self.make_response()
        with patch.object(http_status.requests, 'get', return_value=response):
            result = http_status.check_status_code('https://example.com/')
        output = http_status.format_result(result, verbose=True)
        self.assertIn('https://example.com/', output)
        self.assertIn('https://other.test/', output)
        self.assertIn('unknown', output)
        self.assertNotIn('None bytes', output)


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class HTTPIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == '/redirect':
                    self.send_response(302)
                    self.send_header('Location', '/ok')
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                elif self.path == '/headers-only':
                    self.send_response(200)
                    self.send_header('Content-Length', '1000000000')
                    self.end_headers()
                    # A body-reading client times out; a header-only check returns.
                    self.server.release_body.wait(5)
                else:
                    self.send_response(503 if self.path == '/error' else 200)
                    self.send_header('Content-Length', '2')
                    self.send_header('X-Seen-User-Agent', self.headers['User-Agent'])
                    self.end_headers()

            def log_message(self, *args):
                pass

        cls.server = ThreadedHTTPServer(('127.0.0.1', 0), Handler)
        cls.server.release_body = threading.Event()
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = 'http://127.0.0.1:{}'.format(cls.server.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.server.release_body.set()
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def check(self, path, **options):
        # Avoid proxy settings on the host affecting loopback tests.
        with patch.dict('os.environ', {'NO_PROXY': '127.0.0.1', 'no_proxy': '127.0.0.1'}):
            return http_status.check_status_code(self.base_url + path, timeout=1, **options)

    def test_returns_status_without_waiting_for_body(self):
        try:
            result = self.check('/headers-only')
            self.assertTrue(result['success'], result)
            self.assertEqual(result['status_code'], 200)
            self.assertEqual(result['content_length'], 1000000000)
        finally:
            self.server.release_body.set()

    def test_follows_redirects_and_sends_user_agent(self):
        result = self.check('/redirect', user_agent='integration-agent')
        self.assertTrue(result['success'], result)
        self.assertEqual(result['status_code'], 200)
        self.assertTrue(result['redirected'])
        self.assertEqual(result['url'], self.base_url + '/redirect')
        self.assertEqual(result['final_url'], self.base_url + '/ok')
        self.assertEqual(result['headers']['X-Seen-User-Agent'], 'integration-agent')

    def test_can_disable_redirects(self):
        result = self.check('/redirect', follow_redirects=False)
        self.assertTrue(result['success'], result)
        self.assertEqual(result['status_code'], 302)
        self.assertFalse(result['redirected'])
        self.assertEqual(result['final_url'], self.base_url + '/redirect')

    def test_http_error_remains_a_successful_check(self):
        result = self.check('/error')
        self.assertTrue(result['success'], result)
        self.assertEqual(result['status_code'], 503)


if __name__ == '__main__':
    unittest.main()
