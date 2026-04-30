---
name: WheelSpotter
version: 3.0.0
description: A wheel-spotting scout that finds reusable solutions before you build from scratch. Cost-controlled intelligent search with complexity-aware filtering, intent-based platform selection, self-learning feedback, and anti-filter-bubble mechanisms.
author: GARYLOooP
license: MIT
triggers:
  - "is there an existing"
  - "looking for library"
  - "any existing solution"
  - "before implementing"
  - "avoid reinventing"
  - "is there a library for"
  - "find a tool that"
  - "need a package for"
  - "spot a wheel"
  - "find wheels"
---

# WheelSpotter (v3.0)

> **WheelSpotter** — Your wheel-spotting scout. Spots reusable solutions before you build from scratch. **Gets smarter with every use, but never stops exploring.**

**Core principle**: Solutions must be directly integrable—not flashy but unusable toys.

---

## What's New in v3.0

### Self-Learning Feedback System

WheelSpotter now learns from usage to improve future searches:

1. **Automatic search recording**: Every search is logged with query, results, and metadata
2. **User feedback collection**: After presenting results, ask the user which they chose and how satisfied they are (1-5 rating)
3. **Learned platform weights**: Frequently chosen platforms get higher sort priority
4. **Keyword expansion patterns**: Discovers associations (e.g., "excel" → also try "spreadsheet")
5. **Anti-filter-bubble guarantees**: The system never stops exploring new options

### Anti-Filter-Bubble Mechanisms

| Mechanism | How It Works |
|-----------|-------------|
| **Exploration floor (20%)** | Every platform retains at least 20% of its base weight, regardless of learned preferences |
| **90-day decay half-life** | Old feedback exponentially decays — a preference from 6 months ago has only 25% influence |
| **Diversity boost (1.3x)** | Results from never-seen query domains get a 1.3x score multiplier |
| **70/30 blending** | Sort is 70% learned + 30% base signal, preventing total dominance |

### Feedback Collection Workflow

After presenting search results, the agent should ask:

> "Did any of these recommendations work for you? Which one did you choose? (Just tell me the package name, or say 'none of them')"

Then record feedback via:
```bash
python scripts/search.py --learn -q "original query" --chose "chosen_package_name" --rating 4
```

The learning engine runs automatically or can be triggered manually:
```bash
python scripts/search.py --teach   # Analyze accumulated feedback
python scripts/search.py --stats   # View learning statistics
python scripts/search.py --forget  # Reset all learning data
```

---

## When to Use

### Trigger Scenarios

Load this skill when the user expresses these intents:

| Pattern | Example |
|---------|---------|
| Looking for existing solutions | "Is there an existing PDF parsing library?" |
| Avoiding duplicate work | "I don't want to reinvent the wheel..." |
| Tech stack consultation | "What's a good Python data visualization library?" |
| Quick integration needs | "I need an OCR API I can use right away" |
| Pre-implementation research | "Implementing JWT auth—any existing solutions?" |
| Wheel spotting | "Spot any wheels for image processing?" |

**Keyword matches**: `is there`, `existing`, `wheel`, `library`, `framework`, `API`, `tool`, `solution`, `spot`

### Do NOT Trigger

| Scenario | Reason | Suggestion |
|----------|--------|------------|
| User wants to build themselves | "I want to write my own..." | Assist with coding directly |
| Highly customized requirements | "I need something that does X, Y, Z all at once..." | Suggest breaking down and searching separately |
| Learning purposes | "I want to learn how to implement..." | Provide tutorials instead |
| Tech stack already decided | "I'm using React to build..." | Move to development guidance |

---

## Design Principles

| Principle | Description | Implementation |
|-----------|-------------|----------------|
| **Problem-Oriented** | Precisely solve "finding integrable wheels" | Sources classified by output form, exclude chatbots |
| **Closed-Loop Delivery** | Clear "usable/unusable" conclusion with action | Results include `pip install` commands or self-build recommendation |
| **High Adaptability** | Dynamic strategy based on complexity and intent | Complexity grading + intent-adaptive source selection |
| **Progressive Improvement** | System gets smarter with each use | Feedback loops, learned weights, keyword expansion |
| **Anti-Filter-Bubble** | Never stops exploring new options | Exploration floor, time decay, diversity boost |
| **Cost Red Line** | Search cost must be lower than self-build cost | Budget caps, tiered abandonment, early termination |

---

## Prerequisites

**Environment**:
- Python 3.8+ (stdlib only, no external dependencies)
- Internet access for API calls
- **GitHub Token** (recommended, increases API limit from 60 to 5000 req/hour)

> ⚠️ **Note**: Without a GitHub token, you may hit API rate limits quickly. Set it via:
> ```bash
> export GITHUB_TOKEN=your_token_here  # Linux/macOS
> set GITHUB_TOKEN=your_token_here     # Windows CMD
> $env:GITHUB_TOKEN="your_token_here"  # Windows PowerShell
> ```

**Learning data**: Stored in `scripts/wheel_memory.json` alongside the script. No database or external service required.

---

## Input/Output Specification

### Input Format

```python
# Method 1: Natural language (parsed by agent)
user_input = "I need a Python library to process Excel files"

# Method 2: Structured input (optional)
{
    "requirement": "process Excel files",
    "tech_stack": ["Python"],
    "intent": "library",
    "constraints": {
        "license": "MIT",
        "min_stars": 100,
        "last_updated": "12m"
    }
}
```

### Output Format

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
        "memory_enabled": true,
        "query_expanded": false
    }
}
```

**Status values**:
- `found`: Suitable solutions found
- `not_found`: Recommend self-build
- `needs_clarification`: Requirement unclear, need follow-up
- `error`: Search failed, return error info

---

## Core Workflow

```
User Input
  |
[M0] Complexity Grading (~30 tokens)
  |
[M1] Intent Classification (~60 tokens)
  |
[Optional] Clarification (1-2 rounds if needed)
  |
[M2] Extract Keywords + Tech Entities (~150 tokens)
  |
[M2.5] Apply Learned Keyword Expansions (from feedback history)
  |
[Search] Activate platforms by intent, parallel API calls
  |
[Hard Filter] Deprecated/activity/form matching
  |
[Smart Sort] Base quality + learned platform weights + diversity boost
  |
[LLM Refinement] Multi-dimensional eval for <=5 candidates (~300 tokens)
  |
Output recommendations + action commands + cost report
  |
[Feedback] Ask user which they chose + satisfaction rating
  |
[Record] Save feedback to wheel_memory.json
```

---

## Implementation Details

### Step 1: Complexity Grading (M0)

**Prompt Template**:
```
You are a development complexity assessment expert. Evaluate the requirement:
- L1: Simple function/tool, solvable with dozens of lines
- L2: Medium module, requires interface design
- L3: Complex system, involves multiple components

Requirement: {requirement}
Output JSON only: { "complexity": "L2", "reason": "..." }
```

**Impact on Search Strategy**:

| Complexity | Token Cap | Time Cap | Sources | Star Threshold |
|------------|-----------|----------|---------|----------------|
| L1 Simple | 300 | 8s | 2-3 | >=10 |
| L2 Medium | 600 | 12s | 3-5 | >=50 |
| L3 Complex | 800 | 15s | Full | >=100 |

### Step 2: Intent Classification (M1)

**Prompt Template**:
```
Analyze the requirement, determine desired output form (multiple allowed):
- library: Library/framework integrable into code
- service: Callable external API/service
- tool: Standalone executable tool/CLI
- reference: Code template/example/architecture reference
- assistant: Conversational assistant (usually not a wheel, use cautiously)

Requirement: {requirement}
Output JSON only: { "intent": [...], "reason": "..." }
```

**Important**: If intent only contains `assistant`, return guidance without triggering search.

### Step 3: Platform Selection Matrix

| Intent | Activate Sources | Do NOT Search |
|--------|------------------|---------------|
| library | GitHub, PyPI, npm, Maven, Crates.io | Conversational skill marketplaces |
| service | MCP Hubs, HuggingFace API, RapidAPI | Pure code repos |
| tool | GitHub Releases, Docker Hub, npm -g | Pure library platforms |
| reference | Stack Overflow, GitHub Gist, Official docs | Distribution platforms |

> **Note**: PyPI has no keyword search JSON API; it supports exact/fuzzy package name lookup only. For keyword-level Python package discovery, always combine `github,pypi`. GitHub is the primary search source; PyPI supplements with package metadata when a name match is found.

### Step 4: Learned Keyword Expansion

If the user has previously found good results for similar queries, the system automatically expands keywords:

```
User query: "excel parser"
Learned expansion: "excel parser spreadsheet"  (+ "spreadsheet" from past feedback)
```

Only expansions validated by 2+ positive feedback entries are applied. This helps surface relevant packages that use different terminology.

### Step 5: Hard Filtering Rules

```python
def hard_filter(candidate, complexity, intent):
    # 1. Archived/Deprecated check
    if candidate.archived or candidate.deprecated:
        return False

    # 2. Dynamic star threshold
    thresholds = {"L1": 10, "L2": 50, "L3": 100}
    if candidate.stars < thresholds[complexity]:
        return False

    # 3. Update time check
    if months_since_update > 24:
        return False

    # 4. Form consistency check
    if intent == "library" and not has_package_indicator(candidate):
        return False

    return True
```

### Step 6: Learning-Aware Sorting

Results are sorted by a blend of quality signals and learned preferences:

```
Score = base_quality * learned_platform_weight * diversity_multiplier

Where:
- base_quality: stars/downloads/popularity from the platform
- learned_platform_weight: 70% learned + 30% base (from feedback history)
- diversity_multiplier: 1.3x for new domains, 1.1x for under-explored platforms

Exploration floor: no platform weight drops below 20% of its base value
```

### Step 7: Feedback Collection

**After presenting results, the agent MUST ask the user for feedback:**

> "Did any of these recommendations work for you? If you chose one, tell me the package name so I can record it for better future searches."

Then record via CLI:
```bash
python scripts/search.py --learn -q "original query keywords" --chose "chosen_package_name" --rating 4
```

| Rating | Meaning |
|--------|---------|
| 5 | Perfect match, installed and using |
| 4 | Good match, minor adjustments needed |
| 3 | Somewhat useful, but not ideal |
| 2 | Poor match, barely relevant |
| 1 | Completely wrong recommendation |

### Step 8: LLM Refinement

**Multi-dimensional Scoring**:
```
Final Score = Semantic Similarity * 0.5
            + Integration Feasibility * 0.3
            + Activity Normalization * 0.2
```

---

## Search Script

See [scripts/search.py](scripts/search.py) for the standalone implementation.

**Search Usage**:
```bash
# Basic usage
python scripts/search.py -q "python pdf parser" -c L2 -i library

# Multiple platforms
python scripts/search.py -q "python excel read write" -c L2 -i library -p github,pypi

# With GitHub token (recommended)
python scripts/search.py -q "react charting library" -c L3 -i library -t $GITHUB_TOKEN

# Disable learning for one-off searches
python scripts/search.py -q "rust web framework" --no-memory
```

**Learning Management**:
```bash
# Record feedback
python scripts/search.py --learn -q "python pdf" --chose "pypdf2" --rating 4
python scripts/search.py --learn -q "react chart" --chose "recharts" --rating 5 --notes "great API"

# Run learning engine
python scripts/search.py --teach

# View learning statistics
python scripts/search.py --stats

# Reset all learning data
python scripts/search.py --forget
```

**All Parameters**:
| Parameter | Short | Description | Default |
|-----------|-------|-------------|---------|
| `--query` | `-q` | Search keywords | - |
| `--complexity` | `-c` | L1/L2/L3 | L2 |
| `--intent` | `-i` | library/service/tool/reference | library |
| `--platforms` | `-p` | Comma-separated platforms | github |
| `--limit` | `-l` | Max results per platform | 20 |
| `--token` | `-t` | GitHub token (optional) | - |
| `--output` | `-o` | Output file (optional) | stdout |
| `--no-memory` | | Disable learning for this search | false |
| `--learn` | | Record feedback mode | false |
| `--chose` | | Package user chose (for --learn) | - |
| `--rating` | | Satisfaction 1-5 (for --learn) | 3 |
| `--notes` | | Optional notes (for --learn) | "" |
| `--teach` | | Run learning engine | false |
| `--stats` | | Show learning statistics | false |
| `--forget` | | Reset all learning data | false |

---

## Memory File Format

Learning data is stored in `scripts/wheel_memory.json`:

```json
{
  "version": "3.0.0",
  "created": "2026-04-30T...",
  "last_updated": "2026-04-30T...",
  "stats": {
    "total_searches": 42,
    "total_feedback": 15
  },
  "feedback": [
    {
      "query": "python pdf parser",
      "fingerprint": "a1b2c3d4e5f6",
      "timestamp": "2026-04-30T...",
      "recommendations": [
        {"name": "PyPDF2", "source": "github", "action": "pip install pypdf2"}
      ],
      "chosen": "PyPDF2",
      "rating": 4,
      "notes": "works well"
    }
  ],
  "platform_weights": {
    "github": 1.3,
    "pypi": 1.1,
    "npm": 0.9
  },
  "keyword_expansions": {
    "excel": ["spreadsheet", "xlsx"],
    "pdf": ["document", "portable"]
  },
  "seen_domains": ["a1b2c3d4e5f6", "f6e5d4c3b2a1"]
}
```

---

## Error Handling

| Error Condition | Strategy | User Message |
|-----------------|----------|--------------|
| GitHub API rate limit (403) | Fallback to web search or prompt for token | "GitHub API limit reached. Please retry later or configure a GitHub token." |
| Network timeout (>15s) | Retry once, return partial results on failure | "Some platforms timed out. Returning available results." |
| No matching intent | Don't trigger search, guide user to clarify | "Your requirement may need custom development. Continue searching?" |
| JSON parse failure | Log error, return raw response | "Failed to parse search results. Please check raw data." |
| All platforms failed | Return graceful degradation | "Search service temporarily unavailable. Please retry later or research manually." |
| Memory file corrupted | Reset to default, continue without learning | "Learning data reset due to corruption. This search will not benefit from past feedback." |

---

## Cost Control

### Three-Tier Budget System

| Level | Token Cap | Time Cap | Strategy |
|-------|-----------|----------|----------|
| L1 Simple | 300 | 8s | Quick abandonment, recommend self-build if not found |
| L2 Medium | 600 | 12s | Moderate resources |
| L3 Complex | 800 | 15s | Full resources by intent matrix |

### Early Termination Conditions

- Hard filter yields 0 candidates → Immediately output "not found, recommend self-build"
- Intent is only `assistant` → Don't trigger search
- High-match result found (score > 0.9) → Early termination

---

## Best Practices

1. **Extract specific keywords** before calling the script
2. **Classify complexity and intent accurately** - determines search strategy
3. **Check license compatibility** before final recommendation
4. **Provide context** when requirements are ambiguous
5. **Respect early termination** - L1 requirements should self-build if not found
6. **Always collect feedback** - ask users which package they chose and how satisfied they are
7. **Run --teach periodically** - especially after accumulating 5+ new feedback entries

---

## Why WheelSpotter Works

WheelSpotter isn't a "comprehensive search engine" — it's your **wheel-spotting scout**:

- **First determines if search is worthwhile** - Complexity grading
- **Then determines where to search most accurately** - Intent-driven platform selection
- **Gets decision evidence at lowest cost** - Budget control
- **Always provides next action** - Closed-loop delivery
- **Gets better over time** - Self-learning from feedback
- **Never stops exploring** - Anti-filter-bubble guarantees

---

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| 3.0.0 | 2026-04-30 | Self-learning feedback system: search recording, user feedback, learned platform weights, keyword expansion, diversity boost, 90-day decay, exploration floor; CLI: --learn/--teach/--stats/--forget/--no-memory |
| 2.0.0 | 2026-04-30 | Concurrent platform search (ThreadPoolExecutor); npm defensive parsing fix; GitHub noise filtering; `action` field (install commands) per result; description truncation; 15s timeout |
| 1.1.0 | 2026-04-30 | Zero external deps (stdlib only); fix URL encoding; fix PyPI keyword search; fix npm stars conflation; add downloads/popularity fields |
| 1.0.0 | 2026-04-28 | Initial release with triggers, error handling, standalone script, I/O spec |
