import contextlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


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


if __name__ == '__main__':
    unittest.main()
