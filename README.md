# HTTP Status Checker

A command-line Python tool to check HTTP status codes with colored terminal output.
The status marker falls back to `*` when the output encoding cannot display `●`.

## Features

- **Clear status output** — Color-coded HTTP status codes for quick scanning.
- **Response insights** — Response times, redirects, and server-declared content length.
- **Batch checking** — Check multiple URLs from a text file.
- **Configurable requests** — Set timeouts, custom User-Agent headers, and redirect behavior.
- **Minimal dependencies** — Lightweight Python CLI built with `requests` and `colorama`.

## Installation

### Prerequisites

- Python 3.6 or higher
- pip package manager

### Step 1: Install Dependencies

```bash
pip install requests colorama
```

### Step 2: Download the script

```bash
git clone https://github.com/qventymr/http-status-checker.git
cd http-status-checker
mv http-status.py http-status
```

### Step 3: Make Executable

```bash
chmod +x http-status
```

## Adding to PATH

For a system-wide installation:

```bash
sudo mv http-status /usr/local/bin/
```

Or install it for your user without `sudo`:

```bash
mkdir -p ~/.local/bin
mv http-status ~/.local/bin/
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

## Command Line Options

```text
usage: http-status [-h] (-u URL | -f FILE) [-t TIMEOUT] [--no-redirect] [-v] [--user-agent USER_AGENT]

Check HTTP status code of URLs

options:
  -h, --help            show this help message and exit
  -u URL, --url URL     URL to check (e.g., example.com or https://example.com)
  -f FILE, --file FILE  File containing URLs to check (one per line)
  -t TIMEOUT, --timeout TIMEOUT
                        Request timeout in seconds (default: 10)
  --no-redirect         Do not follow redirects
  -v, --verbose         Verbose output
  --user-agent USER_AGENT
                        Custom User-Agent string

```

## Examples

```bash
http-status -u example.com
http-status -u https://example.com -v
http-status -u example.com -t 5 --no-redirect
http-status -f urls.txt
```

URLs without a scheme use HTTPS. Explicit schemes must be HTTP or HTTPS.
Timeouts must be positive integers. URL files are UTF-8 (an optional BOM is
accepted), with blank lines ignored; an empty file is an error. Batch checks
continue after invalid URLs or failed requests.

The checker sends a GET request and closes the final response after receiving
its headers, without downloading its body. Verbose output shows the original
and final URLs. `Content-Length` is the server-declared transfer size, which may
differ from the decoded body size; it is shown as `unknown` when absent or
invalid. Response time uses a monotonic clock and measures time until the final
headers arrive, including redirects. The timeout applies to connecting and
waiting for socket data, rather than a total deadline for the entire check.

## Exit Codes

- `0`: Every URL returned an HTTP response, including 4xx and 5xx responses.
- `1`: An invalid URL, a failed request, or an unreadable or empty URL file.
- `2`: Invalid command-line arguments, including a non-positive timeout.
- `130`: Interrupted with Ctrl+C.

## Tests

Run from a fresh clone, before renaming or moving the script:

```bash
python -m unittest discover -v
```
