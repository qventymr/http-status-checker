#!/usr/bin/env python3

import requests
from colorama import init, Fore, Style
import argparse
import sys
from urllib.parse import urlparse
import time


init(autoreset=True)

def check_status_code(url, timeout=10, follow_redirects=True, user_agent=None):
    try:
        headers = {}
        if user_agent:
            headers['User-Agent'] = user_agent
        
        start_time = time.time()
        response = requests.get(
            url, 
            timeout=timeout, 
            allow_redirects=follow_redirects,
            headers=headers
        )
        elapsed_time = (time.time() - start_time) * 1000
        
        result = {
            'success': True,
            'status_code': response.status_code,
            'reason': response.reason,
            'response_time': elapsed_time,
            'final_url': response.url,
            'redirected': response.history != [],
            'content_length': len(response.content),
            'headers': dict(response.headers)
        }
        
        return result
        
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
        verbose_info = [
            f"{Fore.CYAN}URL:{Fore.WHITE} {result['final_url']}",
            f"{Fore.CYAN}Redirected:{Fore.WHITE} {result['redirected']}",
            f"{Fore.CYAN}Content Size:{Fore.WHITE} {result['content_length']} bytes",
            f"{Fore.CYAN}Final URL:{Fore.WHITE} {result['final_url']}"
        ]
        return base_output + "\n" + "\n".join(verbose_info)
    
    return base_output

def validate_url(url):
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    try:
        parsed = urlparse(url)
        if not parsed.netloc:
            raise ValueError("Invalid URL: no network location")
        return url
    except Exception as e:
        raise ValueError(f"Invalid URL: {e}")

def main():
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
    
    parser.add_argument('-t', '--timeout', type=int, default=10, 
                       help="Request timeout in seconds (default: 10)")
    parser.add_argument('--no-redirect', action='store_true',
                       help="Do not follow redirects")
    parser.add_argument('-v', '--verbose', action='store_true',
                       help="Verbose output")
    parser.add_argument('--user-agent', 
                       help="Custom User-Agent string")
    
    args = parser.parse_args()
    
    try:
        if args.url:
            url = validate_url(args.url)
            result = check_status_code(
                url, 
                timeout=args.timeout,
                follow_redirects=not args.no_redirect,
                user_agent=args.user_agent
            )
            print(format_result(result, args.verbose))
        
        elif args.file:
            try:
                with open(args.file, 'r', encoding='utf-8') as f:
                    urls = [line.strip() for line in f if line.strip()]
                
                print(f"{Fore.CYAN}Checking {len(urls)} URLs...{Style.RESET_ALL}\n")
                
                for i, url in enumerate(urls, 1):
                    try:
                        valid_url = validate_url(url)
                        result = check_status_code(
                            valid_url,
                            timeout=args.timeout,
                            follow_redirects=not args.no_redirect,
                            user_agent=args.user_agent
                        )
                        print(f"{i:3d}. [{validate_url(url)}] {format_result(result, args.verbose)}")
                    except ValueError as e:
                        error_color = Fore.RED + Style.BRIGHT
                        print(f"{i:3d}. {error_color}● {Fore.WHITE}Invalid URL: {url} - {e}")
    
                    if i < len(urls):
                        time.sleep(0.1)
                        
            except FileNotFoundError:
                print(f"{Fore.RED}Error: File '{args.file}' not found")
                sys.exit(1)
            except Exception as e:
                print(f"{Fore.RED}Error reading file: {e}")
                sys.exit(1)
    
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"{Fore.RED}Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
