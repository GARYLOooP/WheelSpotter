# WheelSpotter

<div align="center">

**A wheel-spotting scout that finds reusable solutions before you build from scratch.**

[![Version](https://img.shields.io/badge/version-3.0.0-blue.svg)](https://github.com/GARYLOooP/wheelspotter)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8+-yellow.svg)](https://www.python.org/)

*Gets smarter with every use, but never stops exploring.*

</div>

---

## Overview

WheelSpotter helps you find existing libraries, frameworks, and tools instead of reinventing the wheel. It features:

- **🧠 Self-Learning**: Learns from your feedback to improve future searches
- **🎯 Intent-Aware**: Understands whether you need a library, service, or tool
- **⚡ Cost-Controlled**: Smart budget management prevents over-searching
- **🔄 Anti-Filter-Bubble**: Never stops exploring new options

---

## Quick Start

### Prerequisites

- **Python 3.8+** (stdlib only, no external dependencies)
- **GitHub Token** (recommended)

> ⚠️ **Important**: Without a GitHub token, you're limited to 60 API requests/hour. With a token, you get 5000 requests/hour.

### Set Up GitHub Token

```bash
# Linux/macOS
export GITHUB_TOKEN=your_github_token_here

# Windows CMD
set GITHUB_TOKEN=your_github_token_here

# Windows PowerShell
$env:GITHUB_TOKEN="your_github_token_here"
```

### Basic Usage

```bash
# Search for a library
python scripts/search.py -q "python pdf parser" -c L2 -i library

# Search multiple platforms
python scripts/search.py -q "react charting" -c L2 -i library -p github,npm

# Record feedback for learning
python scripts/search.py --learn -q "python pdf" --chose "pypdf2" --rating 4
```

---

## How It Works

```
Your Query
    ↓
[Complexity Grading] → L1/L2/L3 (determines budget)
    ↓
[Intent Classification] → library/service/tool/reference
    ↓
[Platform Selection] → GitHub, PyPI, npm, Maven, Crates.io...
    ↓
[Parallel Search] → Concurrent API calls
    ↓
[Smart Filter + Sort] → Quality signals + learned preferences
    ↓
Recommendations with install commands
```

---

## Learning System

WheelSpotter gets smarter over time:

1. **Search Recording**: Every search is logged
2. **Feedback Collection**: Ask users which package they chose
3. **Platform Weights**: Frequently chosen platforms get priority
4. **Keyword Expansion**: Learns associations (e.g., "excel" → "spreadsheet")

```bash
# Record feedback
python scripts/search.py --learn -q "excel parser" --chose "openpyxl" --rating 5

# Analyze feedback
python scripts/search.py --teach

# View statistics
python scripts/search.py --stats

# Reset learning data
python scripts/search.py --forget
```

---

## CLI Reference

| Parameter | Short | Description | Default |
|-----------|-------|-------------|---------|
| `--query` | `-q` | Search keywords | (required) |
| `--complexity` | `-c` | L1/L2/L3 | L2 |
| `--intent` | `-i` | library/service/tool/reference | library |
| `--platforms` | `-p` | Comma-separated: github,pypi,npm,maven,crates | github |
| `--limit` | `-l` | Max results per platform | 20 |
| `--token` | `-t` | GitHub token | $GITHUB_TOKEN |
| `--output` | `-o` | Output file | stdout |
| `--no-memory` | | Disable learning | false |
| `--learn` | | Record feedback mode | false |
| `--chose` | | Chosen package (for --learn) | - |
| `--rating` | | Rating 1-5 (for --learn) | 3 |
| `--teach` | | Run learning engine | false |
| `--stats` | | Show statistics | false |
| `--forget` | | Reset learning data | false |

---

## Example Output

```json
{
  "status": "found",
  "recommendations": [
    {
      "name": "openpyxl",
      "source": "pypi",
      "url": "https://openpyxl.readthedocs.io/",
      "match_score": 0.92,
      "action": "pip install openpyxl",
      "license": "MIT",
      "stars": 1200
    }
  ],
  "cost": {
    "time_seconds": 3.2,
    "memory_enabled": true
  }
}
```

---

## Anti-Filter-Bubble Guarantees

| Mechanism | Effect |
|-----------|--------|
| **Exploration floor (20%)** | No platform weight drops below 20% of base |
| **90-day decay** | Old feedback loses influence over time |
| **Diversity boost (1.3x)** | New query domains get priority |
| **70/30 blending** | Learned preferences never fully dominate |

---

## Project Structure

```
wheelspotter/
├── SKILL.md              # Full skill documentation
├── README.md             # This file
├── scripts/
│   ├── search.py         # Main search script
│   └── wheel_memory.json # Learning data (auto-created)
└── requirements.txt      # Empty (stdlib only)
```

---

## Contributing

Contributions welcome! Please open an issue or PR on GitHub.

---

## License

MIT License - see [LICENSE](LICENSE) for details.

---

## Changelog

| Version | Changes |
|---------|---------|
| **3.0.0** | Self-learning feedback system, anti-filter-bubble mechanisms |
| **2.0.0** | Concurrent search, npm fixes, GitHub noise filtering |
| **1.1.0** | Zero external deps, PyPI/npm fixes |
| **1.0.0** | Initial release |

---

<div align="center">

**Don't reinvent the wheel — spot it!**

</div>
