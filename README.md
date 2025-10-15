# HTTP Status Checker

A command-line Python tool to check HTTP status codes with colored terminal output.

## Features

- 🎨 **Color-coded status responses** - Visual status code highlighting
- 📊 **Detailed information** - Response time, redirects, content size
- 📁 **Batch processing** - Check multiple URLs from a file
- ⚙️ **Flexible options** - Custom timeouts, User-Agents, redirect control
- 🚀 **Fast and lightweight** - Minimal dependencies

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
wget https://raw.githubusercontent.com/your-repo/http-status/main/http-status.py -O http-status
```

### Step 3: Make Executable

```bash
chmod +x http-status
```

## Adding to PATH

```bash
sudo mv http-status /usr/local/bin/
```

```bash
mkdir -p ~/.local/bin
mv http-status ~/.local/bin/
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

## Command Line Options

usage: status-checker [-h] (-u URL | -f FILE) [-t TIMEOUT] [--no-redirect] [-v] [--user-agent USER_AGENT]

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

Examples:
  status-checker -u example.com
  status-checker -u https://example.com -v
  status-checker -u example.com -t 5 --no-redirect
  status-checker -f urls.txt
