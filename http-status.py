#!/usr/bin/env python3

import argparse
import re
import sys
import time
from urllib.parse import urlparse

import requests
from colorama import Fore, Style, init


def check_status_code(url, timeout=10, follow_redirects=True, user_agent=None):
    try:
        headers = {}
        if user_agent:
            headers['User-Agent'] = user_agent
        
        start_time = time.perf_counter()
        with requests.get(
            url,
            timeout=timeout,
            allow_redirects=follow_redirects,
            headers=headers,
            stream=True
        ) as response:
            elapsed_time = (time.perf_counter() - start_time) * 1000
            try:
                content_length = int(response.headers.get('Content-Length', ''))
                if content_length < 0:
                    content_length = None
            except ValueError:
                content_length = None

            return {
                'success': True,
                'status_code': response.status_code,
                'reason': response.reason,
                'response_time': elapsed_time,
                'url': url,
                'final_url': response.url,
                'redirected': bool(response.history),
                'content_length': content_length,
                'headers': dict(response.headers)
            }

    except requests.exceptions.RequestException as e:
        return {
            'success': False,
            'error': str(e),
            'error_type': type(e).__name__
        }


def get_status_color(status_code):
    if 100 <= status_code < 200:
        return Fore.BLUE + Style.BRIGHT    # Informational
    elif 200 <= status_code < 300:
        return Fore.GREEN + Style.BRIGHT   # Success
    elif 300 <= status_code < 400:
        return Fore.CYAN + Style.BRIGHT    # Redirection
    elif 400 <= status_code < 500:
        return Fore.YELLOW + Style.BRIGHT  # Client Error
    else:
        return Fore.RED + Style.BRIGHT     # Server Error


def format_result(result, verbose=False):
    if not result['success']:
        error_color = Fore.RED + Style.BRIGHT
        return f"{error_color}● {Fore.WHITE}Error ({result['error_type']}): {result['error']}"
    
    color = get_status_color(result['status_code'])
    status_display = f"{color}● {Fore.WHITE}{result['status_code']} {result['reason']}"
    time_display = f"{Fore.WHITE}- {result['response_time']:.0f}ms"
    
    base_output = f"{status_display} {time_display}"
    
    if verbose:
        content_size = (f"{result['content_length']} bytes"
                        if result['content_length'] is not None else 'unknown')
        verbose_info = [
            f"{Fore.CYAN}URL:{Fore.WHITE} {result['url']}",
            f"{Fore.CYAN}Redirected:{Fore.WHITE} {result['redirected']}",
            f"{Fore.CYAN}Content-Length:{Fore.WHITE} {content_size}",
            f"{Fore.CYAN}Final URL:{Fore.WHITE} {result['final_url']}"
        ]
        return base_output + "\n" + "\n".join(verbose_info)
    
    return base_output


def validate_url(url):
    url = url.strip()
    if not url:
        raise ValueError("URL must not be empty")
    if any(character.isspace() or ord(character) < 32 or ord(character) == 127
           for character in url):
        raise ValueError("URL must not contain whitespace or control characters")

    scheme = re.match(r'^([a-z][a-z0-9+.-]*):', url, re.IGNORECASE)
    if url.startswith('//'):
        url = 'https:' + url
    elif scheme and scheme.group(1).lower() in ('http', 'https'):
        pass
    elif scheme and not re.match(r'^[^/?#]+:[0-9]+(?:[/?#]|$)', url):
        raise ValueError("Only HTTP and HTTPS URLs are supported")
    else:
        url = 'https://' + url

    try:
        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname:
            raise ValueError("HTTP(S) URL must include a hostname")
        # Accessing .port validates both its syntax and range.
        parsed.port
        return url
    except ValueError as e:
        raise ValueError(f"Invalid URL: {e}")


def positive_timeout(value):
    try:
        timeout = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("Timeout must be a positive integer")
    if timeout <= 0:
        raise argparse.ArgumentTypeError("Timeout must be a positive integer")
    return timeout


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Check HTTP status code of URLs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s -u example.com
  %(prog)s -u https://example.com -v
  %(prog)s -u example.com -t 5 --no-redirect
  %(prog)s -f urls.txt
        """
    )
    
    url_group = parser.add_mutually_exclusive_group(required=True)
    url_group.add_argument('-u', '--url', help="URL to check (e.g., example.com or https://example.com)")
    url_group.add_argument('-f', '--file', help="File containing URLs to check (one per line)")
    
    parser.add_argument('-t', '--timeout', type=positive_timeout, default=10,
                       help="Request timeout in seconds (default: 10)")
    parser.add_argument('--no-redirect', action='store_true',
                       help="Do not follow redirects")
    parser.add_argument('-v', '--verbose', action='store_true',
                       help="Verbose output")
    parser.add_argument('--user-agent', 
                       help="Custom User-Agent string")
    
    args = parser.parse_args(argv)
    init(autoreset=True)
    
    try:
        batch = args.file is not None
        if batch:
            try:
                with open(args.file, 'r', encoding='utf-8-sig') as f:
                    urls = [line.strip() for line in f if line.strip()]
            except (OSError, UnicodeError) as e:
                print(f"{Fore.RED}Error reading file '{args.file}': {e}", file=sys.stderr)
                return 1
            if not urls:
                print(f"{Fore.RED}Error: URL file is empty", file=sys.stderr)
                return 1
            print(f"{Fore.CYAN}Checking {len(urls)} URLs...{Style.RESET_ALL}\n")
        else:
            urls = [args.url]

        exit_code = 0
        for i, url in enumerate(urls, 1):
            try:
                valid_url = validate_url(url)
            except ValueError as e:
                prefix = f"{i:3d}. " if batch else ''
                print(f"{prefix}{Fore.RED}Invalid URL: {url} - {e}", file=sys.stderr)
                exit_code = 1
            else:
                result = check_status_code(
                    valid_url,
                    timeout=args.timeout,
                    follow_redirects=not args.no_redirect,
                    user_agent=args.user_agent
                )
                prefix = f"{i:3d}. [{valid_url}] " if batch else ''
                print(prefix + format_result(result, args.verbose))
                if not result['success']:
                    exit_code = 1
            if i < len(urls):
                time.sleep(0.1)
        return exit_code

    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Operation cancelled by user", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
