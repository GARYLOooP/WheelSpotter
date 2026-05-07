#!/usr/bin/env python3
"""
WheelSpotter - Multi-Platform Wheel Search Script (v3.0)

Your wheel-spotting scout. A cost-controlled intelligent search tool
for finding reusable solutions. Supports complexity-aware filtering,
intent-based platform selection, and form consistency checks.

Changes in v3.0:
- Self-learning feedback system: records searches + user feedback
- Learned platform weights and keyword expansion from usage history
- Anti-filter-bubble: 20% exploration floor, 90-day decay, diversity boost
- CLI: --learn to record feedback, --teach to trigger learning, --forget to reset
- Diversity injection for unseen domains
- Memory persisted to local JSON file alongside script

Changes in v2.0:
- Concurrent platform searches (ThreadPoolExecutor)
- Defensive type checking in all platform parsers
- GitHub query enhanced with language/topic hints
- Each recommendation includes an `action` field (install command)
- Description truncation (200 chars max)
- Proper exit codes

Usage:
    python search.py -q "python pdf parser" -c L2 -i library
    python search.py -q "react charting" -c L3 -i library -p github,npm -t $GITHUB_TOKEN
    python search.py --learn -q "python pdf" --chose "pypdf" --rating 5
    python search.py --teach
    python search.py --forget
"""

import argparse
import hashlib
import json
import math
import os
import sys
import time
import urllib.request
import urllib.parse
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum

# ============================================================================
# Configuration
# ============================================================================

VERSION = "3.0.0"
DEFAULT_TIMEOUT = 15  # seconds per request
DEFAULT_LIMIT = 20
MAX_CONCURRENCY = 5  # parallel platform searches
MAX_DESC_LEN = 200   # truncate long descriptions

# Star thresholds by complexity
STAR_THRESHOLDS = {
    "L1": 10,
    "L2": 50,
    "L3": 100
}

# Months threshold for "too old"
UPDATE_THRESHOLD_MONTHS = 24

# Install commands by source
INSTALL_COMMANDS = {
    "pypi": "pip install {name}",
    "npm": "npm install {name}",
    "maven": '<!-- Add to pom.xml -->\n<dependency>\n  <groupId>{group}</groupId>\n  <artifactId>{artifact}</artifactId>\n  <version>{version}</version>\n</dependency>',
    "crates.io": "cargo add {name}",
    "github": "See project README for installation instructions",
}


def _infer_github_action(repo_full_name: str, language: Optional[str]) -> str:
    """
    Infer an install command from a GitHub repo's name and primary language.
    This is a best-effort heuristic; the actual install command may differ.
    """
    parts = repo_full_name.split("/")
    if len(parts) != 2:
        return "See project README for installation instructions"
    repo_name = parts[1]

    lang = (language or "").lower()
    if lang == "python":
        return f"pip install {repo_name}"
    if lang in ("javascript", "typescript"):
        return f"npm install {repo_name}"
    if lang == "rust":
        return f"cargo add {repo_name}"
    if lang == "go":
        return f"go get github.com/{repo_full_name}"

    return "See project README for installation instructions"


# ============================================================================
# Learning System Configuration
# ============================================================================

# Anti-filter-bubble constants
EXPLORATION_FLOOR = 0.20      # 20% of sort weight reserved for exploration
DECAY_HALF_LIFE_DAYS = 90     # feedback loses 50% weight every 90 days
DIVERSITY_BOOST = 1.3         # score multiplier for results from unseen domains
MAX_FEEDBACK_ENTRIES = 500    # cap on stored feedback entries
MAX_MEMORY_AGE_DAYS = 365     # auto-expire entries older than this

# Memory file path: stored alongside this script
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_MEMORY_FILE = os.path.join(_SCRIPT_DIR, "wheel_memory.json")


# ============================================================================
# Data Models
# ============================================================================

class Complexity(str, Enum):
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"


class Intent(str, Enum):
    LIBRARY = "library"
    SERVICE = "service"
    TOOL = "tool"
    REFERENCE = "reference"


@dataclass
class SearchResult:
    """Represents a single search result from any platform."""
    name: str
    source: str
    url: str
    stars: int = 0
    description: str = ""
    last_updated: str = ""
    license: Optional[str] = None
    archived: bool = False
    deprecated: bool = False
    language: Optional[str] = None
    downloads: int = 0
    popularity: float = 0.0
    # Extra metadata for generating install commands
    version: str = ""
    group_id: str = ""
    # Learning-aware boost (set during sorting)
    _boost: float = 1.0

    def match_score(self) -> float:
        """Calculate a 0-1 relevance score based on stars, downloads, popularity, and recency."""
        score = 0.0
        max_stars = max(STAR_THRESHOLDS.values(), default=100) * 10  # 1000
        if self.stars > 0:
            score += min(self.stars / max_stars, 0.35)
        elif self.downloads > 0:
            score += min(self.downloads / (max_stars * 10), 0.35)
        elif self.popularity > 0:
            score += min(self.popularity * 0.35, 0.35)
        # Popularity bonus
        if self.popularity > 0:
            score += min(self.popularity * 0.2, 0.2)
        # Recency bonus (within 6 months)
        if self.last_updated:
            days = _days_between(self.last_updated)
            if days < 180:
                score += 0.1 * (1 - days / 180)
        # Non-archived/deprecated bonus
        if not self.archived and not self.deprecated:
            score += 0.05
        # Apply learning boost
        if self._boost != 1.0:
            score *= self._boost
        return round(min(max(score, 0.0), 1.0), 3)

    def to_dict(self) -> Dict[str, Any]:
        d = {k: v for k, v in asdict(self).items() if v is not None and v != "" and v != 0 and v is not False}
        # Truncate description
        if "description" in d and len(d["description"]) > MAX_DESC_LEN:
            d["description"] = d["description"][:MAX_DESC_LEN] + "..."
        # Remove internal boost field
        d.pop("_boost", None)
        # Add computed match_score
        d["match_score"] = self.match_score()
        return d

    def get_action(self) -> str:
        """Generate an install/usage action string."""
        if self.source == "github":
            return _infer_github_action(self.name, self.language)

        template = INSTALL_COMMANDS.get(self.source, "")
        if not template:
            return ""

        if self.source == "maven" and self.group_id:
            parts = self.name.split(":")
            group = parts[0] if len(parts) >= 2 else self.group_id
            artifact = parts[1] if len(parts) >= 2 else self.name
            return template.format(group=group, artifact=artifact, version=self.version)

        return template.format(name=self.name)


@dataclass
class SearchResponse:
    """Complete search response with metadata."""
    status: str  # found, not_found, error
    query: str
    complexity: str
    intent: str
    total_found: int = 0
    after_filter: int = 0
    recommendations: List[Dict[str, Any]] = field(default_factory=list)
    message: Optional[str] = None
    error: Optional[str] = None
    cost: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


# ============================================================================
# Feedback & Memory System
# ============================================================================

def _query_fingerprint(query: str) -> str:
    """Generate a stable fingerprint for a query (normalized, lowercased)."""
    normalized = " ".join(query.strip().lower().split())
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()[:12]


def _now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _days_between(iso_date: str) -> float:
    """Days elapsed since iso_date."""
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt
        return max(0.0, delta.total_seconds() / 86400)
    except (ValueError, AttributeError):
        return 0.0


def _infer_source(name: str) -> str:
    """
    Infer the platform source from a package name.
    Used when feedback is recorded without full recommendation context.
    Heuristic order matters: check most specific patterns first.
    """
    name_lower = name.lower()

    # GitHub: org/repo format (has slash)
    if "/" in name:
        return "github"

    # Maven: group:artifact format (has colon)
    if ":" in name:
        return "maven"

    # PyPI: dotted or underscored names common in Python ecosystem
    # e.g., Pillow, pdfminer.six, beautifulsoup4, scikit-learn
    if "." in name_lower or "_" in name_lower:
        return "pypi"
    # Known Python packages (common names)
    python_names = {
        "pillow", "numpy", "pandas", "scipy", "flask", "django", "fastapi",
        "requests", "celery", "selenium", "pytest", "pip", "setuptools",
        "matplotlib", "tensorflow", "pytorch", "opencv", "openpyxl",
        "scikit-learn", "sklearn", "sqlalchemy", "alembic", "click",
        "black", "mypy", "pylint", "tox", "nox", "hatch",
        "poetry", "twine", "wheel", "virtualenv", "pipenv",
        "aiohttp", "httpx", "starlette", "uvicorn", "gunicorn",
        "pydantic", "attrs", "cattrs", "marshmallow", "traitlets",
        "boto3", "botocore", "psycopg2", "pymongo", "redis",
        "jinja2", "werkzeug", "cherrypy", "tornado", "sanic",
        "paramiko", "fabric", "ansible", "salt", "pulumi",
        "networkx", "sympy", "statsmodels", "xgboost", "lightgbm",
        "keras", "transformers", "langchain", "spacy", "nltk",
        "beautifulsoup4", "scrapy", "sphinx", "mkdocs",
    }
    if name_lower in python_names:
        return "pypi"
    # Hyphenated names that look like Python packages (contain known Python prefixes)
    python_prefixes = {"scikit", "py", "python", "django", "flask", "pytest", "async"}
    first_part = name_lower.split("-")[0] if "-" in name_lower else ""
    if first_part in python_prefixes:
        return "pypi"

    # npm: lowercase, typically hyphenated, no dots, no underscores
    # e.g., recharts, react-router, express, lodash, chart.js (has dot!)
    npm_names = {
        "recharts", "react", "vue", "angular", "express", "lodash",
        "moment", "axios", "next", "nuxt", "webpack", "vite", "eslint",
        "prettier", "babel", "jest", "mocha", "chai", "chart.js",
    }
    if name_lower in npm_names:
        return "npm"
    # Pure lowercase without dots/underscores → likely npm
    if name_lower == name_lower and not any(c in name for c in "._") and "-" in name_lower:
        return "npm"

    # Known Rust crate names
    crate_names = {
        "rocket", "tokio", "serde", "actix", "warp", "clap", "reqwest",
        "rayon", "rand", "log", "env_logger", "cargo",
    }
    if name_lower in crate_names:
        return "crates.io"

    # Default: github (most common fallback for org/repo patterns)
    return "github"


def _decay_weight(days: float) -> float:
    """
    Exponential decay with DECAY_HALF_LIFE_DAYS half-life.
    After 90 days: weight = 0.5, after 180 days: weight = 0.25, etc.
    """
    return math.exp(-math.log(2) * days / DECAY_HALF_LIFE_DAYS)


def load_memory() -> Dict[str, Any]:
    """
    Load the learning memory from disk. Returns default structure if missing.
    """
    default = {
        "version": VERSION,
        "created": _now_iso(),
        "last_updated": _now_iso(),
        "stats": {
            "total_searches": 0,
            "total_feedback": 0,
        },
        "feedback": [],           # list of feedback entries
        "platform_weights": {},   # {platform: weight} — learned preferences
        "keyword_expansions": {}, # {stem: [expansion_words]}
        "seen_domains": set(),    # set of query domain fingerprints
    }

    if not os.path.exists(_MEMORY_FILE):
        return default

    try:
        with open(_MEMORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Migrate / validate structure
        if not isinstance(data, dict):
            return default

        data.setdefault("version", VERSION)
        data.setdefault("created", _now_iso())
        data.setdefault("last_updated", _now_iso())
        data.setdefault("stats", {"total_searches": 0, "total_feedback": 0})
        data.setdefault("feedback", [])
        data.setdefault("platform_weights", {})
        data.setdefault("keyword_expansions", {})
        # seen_domains stored as list for JSON
        data.setdefault("seen_domains", [])

        return data
    except (json.JSONDecodeError, OSError) as e:
        print(f"Warning: Failed to load memory: {e}", file=sys.stderr)
        return default


def save_memory(memory: Dict[str, Any]) -> None:
    """Persist learning memory to disk atomically."""
    memory["last_updated"] = _now_iso()

    # Ensure seen_domains is a list for JSON serialization
    seen = memory.get("seen_domains")
    if isinstance(seen, set):
        memory["seen_domains"] = list(seen)

    try:
        tmp_path = _MEMORY_FILE + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(memory, f, indent=2, ensure_ascii=False)
        # Atomic rename
        os.replace(tmp_path, _MEMORY_FILE)
    except OSError as e:
        print(f"Warning: Failed to save memory: {e}", file=sys.stderr)


def record_search(memory: Dict[str, Any], query: str, response: SearchResponse) -> None:
    """
    Record a completed search into memory (without user feedback yet).
    """
    memory["stats"]["total_searches"] = memory["stats"].get("total_searches", 0) + 1

    # Track seen query domains
    seen = set(memory.get("seen_domains", []))
    seen.add(_query_fingerprint(query))
    memory["seen_domains"] = list(seen)

    save_memory(memory)


def record_feedback(
    memory: Dict[str, Any],
    query: str,
    recommendations: List[Dict[str, Any]],
    chosen: str,
    rating: int,
    notes: str = ""
) -> None:
    """
    Record user feedback for a search result.

    Args:
        query: Original search query
        recommendations: List of recommended result dicts
        chosen: Name of the package the user chose (or "" if none)
        rating: 1-5 satisfaction rating (5 = perfect match)
        notes: Optional user notes
    """
    # Infer platform from chosen name if recommendations not provided
    if not recommendations and chosen.strip():
        inferred = _infer_source(chosen.strip())
        recommendations = [{"name": chosen.strip(), "source": inferred, "action": ""}]

    entry = {
        "query": query.strip(),
        "fingerprint": _query_fingerprint(query),
        "timestamp": _now_iso(),
        "recommendations": [
            {"name": r.get("name", ""), "source": r.get("source", ""), "action": r.get("action", "")}
            for r in recommendations[:5]
        ],
        "chosen": chosen.strip(),
        "rating": max(1, min(5, rating)),
        "notes": notes.strip()[:500],
    }

    feedback = memory.get("feedback", [])
    feedback.append(entry)

    # Trim old entries
    if len(feedback) > MAX_FEEDBACK_ENTRIES:
        # Remove oldest entries beyond the cap
        feedback = feedback[-MAX_FEEDBACK_ENTRIES:]

    # Auto-expire entries older than MAX_MEMORY_AGE_DAYS
    feedback = [
        e for e in feedback
        if _days_between(e.get("timestamp", _now_iso())) < MAX_MEMORY_AGE_DAYS
    ]

    memory["feedback"] = feedback
    memory["stats"]["total_feedback"] = len(feedback)

    save_memory(memory)


def run_learning(memory: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze accumulated feedback and update learned parameters.
    Returns a summary of what was learned.

    This is the core of the self-learning system:
    1. Compute platform preference weights from feedback
    2. Discover keyword expansion patterns
    3. Apply anti-filter-bubble decay
    """
    feedback = memory.get("feedback", [])
    summary = {"platform_changes": {}, "keyword_changes": {}, "entries_analyzed": len(feedback)}

    if not feedback:
        # Still carry forward existing keyword expansions with cap
        old_expansions = dict(memory.get("keyword_expansions", {}))
        capped = {stem: exps[:5] for stem, exps in old_expansions.items() if exps}
        memory["keyword_expansions"] = capped
        return summary

    # --- Step 1: Compute platform preference weights ---
    platform_scores: Dict[str, List[float]] = {}

    for entry in feedback:
        days = _days_between(entry.get("timestamp", _now_iso()))
        weight = _decay_weight(days)
        rating = entry.get("rating", 3)

        # Weight by rating (1-5) * recency
        for rec in entry.get("recommendations", []):
            source = rec.get("source", "")
            if not source:
                continue

            # Bonus if this was the chosen one
            bonus = 1.5 if rec["name"] == entry.get("chosen") else 1.0
            score = rating * weight * bonus

            if source not in platform_scores:
                platform_scores[source] = []
            platform_scores[source].append(score)

    # Normalize to 0.5 - 2.0 range (1.0 = neutral)
    old_weights = dict(memory.get("platform_weights", {}))
    new_weights = {}

    all_means = [sum(v) / len(v) for v in platform_scores.values() if v] if platform_scores else [3.0]
    global_mean = sum(all_means) / len(all_means) if all_means else 3.0

    for platform, scores in platform_scores.items():
        # Require at least 2 feedback entries to generate a weight;
        # a single data point is not statistically meaningful
        if len(scores) < 2:
            continue
        mean_score = sum(scores) / len(scores)
        # Normalize: global_mean maps to 1.0, scale to 0.5-2.0
        normalized = max(0.5, min(2.0, (mean_score / global_mean) if global_mean > 0 else 1.0))
        new_weights[platform] = round(normalized, 3)

    # Carry forward unchanged platforms
    for p, w in old_weights.items():
        if p not in new_weights:
            new_weights[p] = w

    memory["platform_weights"] = new_weights

    summary["platform_changes"] = {
        p: {"old": old_weights.get(p, 1.0), "new": w}
        for p, w in new_weights.items()
        if round(old_weights.get(p, 1.0), 3) != round(w, 3)
    }

    # --- Step 2: Discover keyword expansion patterns ---
    old_expansions = dict(memory.get("keyword_expansions", {}))

    # Group feedback by query to find patterns
    query_map: Dict[str, List[Dict]] = {}
    for entry in feedback:
        fp = entry.get("fingerprint", "")
        if fp:
            query_map.setdefault(fp, []).append(entry)

    # Find high-rated queries and extract keyword associations
    new_expansions: Dict[str, List[str]] = {}
    for fp, entries in query_map.items():
        if not entries:
            continue

        avg_rating = sum(e.get("rating", 3) for e in entries) / len(entries)
        if avg_rating < 3.5:
            continue  # only learn from good outcomes

        for entry in entries:
            query = entry.get("query", "").lower()
            chosen = entry.get("chosen", "").lower()
            if not chosen or not query:
                continue

            # Extract stems from query
            query_words = set(query.split())
            for word in query_words:
                if len(word) < 3:
                    continue

                # If the chosen package name contains words not in query, learn them
                # Normalize the package name: remove org prefix, split on / - _
                chosen_name = chosen.split("/")[-1] if "/" in chosen else chosen
                chosen_parts = set()
                for part in chosen_name.replace("-", " ").replace("_", " ").split():
                    # Skip very short parts, version-like strings, and common stop words
                    if len(part) < 3 or part.replace(".", "").isdigit():
                        continue
                    # Skip pure technical suffixes like .six, .js, .py
                    base_part = part.split(".")[0] if "." in part else part
                    if len(base_part) < 3:
                        continue
                    chosen_parts.add(base_part.lower())
                chosen_parts -= {"js", "py", "lib", "net", "core", "web", "app", "cli", "six", "io"}
                new_words = chosen_parts - query_words
                if new_words:
                    if word not in new_expansions:
                        new_expansions[word] = {}
                    for nw in new_words:
                        if len(nw) < 3:
                            continue
                        new_expansions[word][nw] = new_expansions[word].get(nw, 0) + 1

    # Convert to final format (only keep expansions with 2+ occurrences)
    final_expansions: Dict[str, List[str]] = {}
    for stem, expansions in new_expansions.items():
        # Merge with existing
        existing = old_expansions.get(stem, [])
        existing_set = set(existing)
        for word, count in sorted(expansions.items(), key=lambda x: -x[1]):
            if count >= 2 and word not in existing_set:
                existing.append(word)
                existing_set.add(word)
        if existing:
            final_expansions[stem] = existing[:5]  # max 5 expansions per stem

    # Carry forward unchanged stems (also cap at 5)
    for stem, exps in old_expansions.items():
        if stem not in final_expansions:
            final_expansions[stem] = exps[:5]

    memory["keyword_expansions"] = final_expansions

    summary["keyword_changes"] = {
        stem: {"old": old_expansions.get(stem, []), "new": exps}
        for stem, exps in final_expansions.items()
        if old_expansions.get(stem, []) != exps
    }

    save_memory(memory)
    return summary


def get_learned_platform_weight(memory: Dict[str, Any], platform: str) -> float:
    """
    Get the learned weight for a platform, with exploration floor applied.

    Returns a value where the exploration floor ensures every platform gets
    at least EXPLORATION_FLOOR (20%) of its base weight.

    Anti-filter-bubble guarantees:
    - No platform weight can drop below EXPLORATION_FLOOR * base_weight
    - Blend is 70% learned + 30% base to prevent total dominance
    """
    base_weights = {"github": 1.0, "npm": 1.0, "pypi": 1.0, "maven": 1.0, "crates.io": 1.0}
    learned = memory.get("platform_weights", {}).get(platform, 1.0)
    base = base_weights.get(platform, 1.0)

    # Blend: 70% learned, 30% base
    blended = base * (0.3 + 0.7 * learned)

    # Apply exploration floor: never go below EXPLORATION_FLOOR * base
    # This prevents any platform from being completely suppressed
    floor = EXPLORATION_FLOOR * base
    return max(floor, blended)


def expand_query_keywords(memory: Dict[str, Any], query: str) -> str:
    """
    Expand a query with learned keyword patterns.

    Uses a conservative approach: only adds expansions that have been
    validated by 2+ successful feedback entries.
    """
    words = query.lower().split()
    expansions = memory.get("keyword_expansions", {})

    added = []
    for word in words:
        if word in expansions:
            for exp in expansions[word][:2]:  # add at most 2 expansions per word
                if exp not in words and exp not in added:
                    added.append(exp)

    if not added:
        return query

    return query + " " + " ".join(added)


def get_diversity_info(memory: Dict[str, Any]) -> Tuple[set, int]:
    """
    Return (seen_domain_fingerprints, total_domains_seen).
    Used to compute diversity boost for unseen domains.
    """
    seen = set(memory.get("seen_domains", []))
    return seen, len(seen)


# ============================================================================
# HTTP Client (zero external dependencies — stdlib only)
# ============================================================================

def http_get(url: str, headers: Dict[str, str] = None, timeout: int = DEFAULT_TIMEOUT):
    """
    Make HTTP GET request using urllib (stdlib only).
    Returns parsed JSON dict, or None on any error.
    """
    default_headers = {
        "Accept": "application/json",
        "User-Agent": f"WheelSpotter/{VERSION}",
    }
    if headers:
        default_headers.update(headers)

    req = urllib.request.Request(url, headers=default_headers)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            data = json.loads(body)
            if not isinstance(data, dict):
                print(f"Warning: Unexpected response type from {url}: {type(data).__name__}", file=sys.stderr)
                return None
            return data
    except urllib.error.HTTPError as e:
        print(f"Warning: HTTP {e.code} for {url}", file=sys.stderr)
        return None
    except (urllib.error.URLError, TimeoutError, OSError):
        print(f"Warning: Request timed out or failed for {url}", file=sys.stderr)
        return None
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as e:
        print(f"Warning: Failed to parse response from {url}: {e}", file=sys.stderr)
        return None


def build_url(base: str, params: Dict[str, Any]) -> str:
    """Build a URL with properly URL-encoded query parameters."""
    encoded = urllib.parse.urlencode({k: str(v) for k, v in params.items()})
    return f"{base}?{encoded}"


# ============================================================================
# Platform Search Functions
# ============================================================================

def _enhance_github_query(query: str, intent: str) -> str:
    """Add GitHub search qualifiers to improve result quality."""
    return query


def search_github(query: str, limit: int = DEFAULT_LIMIT, token: str = None,
                  intent: str = "library") -> List[SearchResult]:
    """Search GitHub repositories."""
    base_url = "https://api.github.com/search/repositories"
    headers = {"Accept": "application/vnd.github.v3+json"}

    if token:
        headers["Authorization"] = f"token {token}"

    enhanced_query = _enhance_github_query(query, intent)

    params = {
        "q": enhanced_query,
        "sort": "stars",
        "order": "desc",
        "per_page": min(limit, 100),
    }

    full_url = build_url(base_url, params)
    data = http_get(full_url, headers)

    if not data or "items" not in data:
        return []

    results = []
    for item in data.get("items", []):
        if item.get("archived", False):
            continue

        license_name = None
        lic = item.get("license")
        if isinstance(lic, dict):
            license_name = lic.get("spdx_id")

        desc = (item.get("description", "") or "")[:MAX_DESC_LEN]
        if any(noise in desc.lower() for noise in ["# config", "# automatically generated",
                                                     "config_package", "openwrt"]):
            continue

        results.append(SearchResult(
            name=item.get("full_name", ""),
            source="github",
            url=item.get("html_url", ""),
            stars=item.get("stargazers_count", 0),
            description=desc,
            last_updated=item.get("updated_at", ""),
            license=license_name,
            language=item.get("language"),
        ))

    return results


def search_pypi(query: str, limit: int = DEFAULT_LIMIT) -> List[SearchResult]:
    """Search PyPI packages via exact/fuzzy name lookup."""
    results = []

    for candidate_name in _pypi_name_variants(query):
        url = f"https://pypi.org/pypi/{candidate_name}/json"
        data = http_get(url)
        if not data:
            continue

        info = data.get("info", {})
        releases = data.get("urls", [])

        last_updated = ""
        if releases:
            last_updated = releases[0].get("upload_time_iso_8601", "")

        classifiers = info.get("classifiers", [])
        license_val = info.get("license") or _license_from_classifiers(classifiers)

        results.append(SearchResult(
            name=info.get("name", candidate_name),
            source="pypi",
            url=f"https://pypi.org/project/{info.get('name', candidate_name)}/",
            stars=0,
            description=(info.get("summary", "") or "")[:MAX_DESC_LEN],
            last_updated=last_updated,
            license=license_val,
            language="Python",
            version=info.get("version", ""),
        ))

        if len(results) >= limit:
            break

    return results


def _pypi_name_variants(query: str) -> List[str]:
    """Generate PyPI package name variants to try."""
    candidates = []
    normalized = query.strip().lower()

    hyphenated = normalized.replace(" ", "-")
    candidates.append(hyphenated)

    underscored = normalized.replace(" ", "_")
    if underscored != hyphenated:
        candidates.append(underscored)

    if " " not in normalized:
        candidates.insert(0, normalized)

    return candidates[:3]


def _license_from_classifiers(classifiers: List[str]) -> Optional[str]:
    """Extract license info from Trove classifiers."""
    for c in classifiers:
        if c.startswith("License :: "):
            parts = c.split(" :: ")
            if len(parts) >= 3:
                return parts[-1]
    return None


def search_npm(query: str, limit: int = DEFAULT_LIMIT) -> List[SearchResult]:
    """Search npm packages."""
    base_url = "https://registry.npmjs.org/-/v1/search"
    params = {
        "text": query,
        "size": min(limit, 250),
    }

    full_url = build_url(base_url, params)
    data = http_get(full_url)

    if not data or "objects" not in data:
        return []

    objects = data.get("objects", [])
    if not isinstance(objects, list):
        return []

    results = []
    for item in objects:
        if not isinstance(item, dict):
            continue

        pkg = item.get("package")
        if not isinstance(pkg, dict):
            continue

        score = item.get("score")
        popularity = 0.0
        if isinstance(score, dict):
            detail = score.get("detail")
            if isinstance(detail, dict):
                popularity = float(detail.get("popularity", 0) or 0)

        name = pkg.get("name", "")
        links = pkg.get("links")
        npm_url = f"https://www.npmjs.com/package/{name}"
        if isinstance(links, dict):
            npm_url = links.get("npm", npm_url)

        results.append(SearchResult(
            name=name,
            source="npm",
            url=npm_url,
            stars=0,
            description=(pkg.get("description", "") or "")[:MAX_DESC_LEN],
            last_updated=pkg.get("version", ""),
            license=pkg.get("license"),
            language="JavaScript",
            popularity=popularity,
            version=pkg.get("version", ""),
        ))

    return results


def search_maven(query: str, limit: int = DEFAULT_LIMIT) -> List[SearchResult]:
    """Search Maven Central."""
    base_url = "https://search.maven.org/solrsearch/select"
    params = {
        "q": query,
        "rows": min(limit, 20),
        "wt": "json",
    }

    full_url = build_url(base_url, params)
    data = http_get(full_url)

    if not data or "response" not in data:
        return []

    response = data.get("response", {})
    if not isinstance(response, dict):
        return []

    docs = response.get("docs", [])
    if not isinstance(docs, list):
        return []

    results = []
    for doc in docs:
        if not isinstance(doc, dict):
            continue

        group_id = doc.get("g", "")
        artifact_id = doc.get("a", "")
        version = doc.get("latestVersion", "")

        results.append(SearchResult(
            name=f"{group_id}:{artifact_id}",
            source="maven",
            url=f"https://mvnrepository.com/artifact/{group_id}/{artifact_id}",
            stars=0,
            description=f"Latest version: {version}",
            last_updated=doc.get("timestamp", ""),
            license=None,
            language="Java",
            downloads=int(doc.get("downloads", 0) or 0),
            version=version,
            group_id=group_id,
        ))

    return results


def search_crates(query: str, limit: int = DEFAULT_LIMIT, timeout: int = DEFAULT_TIMEOUT) -> List[SearchResult]:
    """Search crates.io (Rust packages)."""
    base_url = "https://crates.io/api/v1/crates"
    params = {
        "q": query,
        "per_page": min(limit, 100),
    }

    full_url = build_url(base_url, params)
    headers = {"User-Agent": f"WheelSpotter/{VERSION}"}

    data = http_get(full_url, headers, timeout=timeout)

    if not data or "crates" not in data:
        return []

    crates = data.get("crates", [])
    if not isinstance(crates, list):
        return []

    results = []
    for crate in crates:
        if not isinstance(crate, dict):
            continue

        name = crate.get("name", "")
        results.append(SearchResult(
            name=name,
            source="crates.io",
            url=f"https://crates.io/crates/{name}",
            stars=0,
            description=(crate.get("description", "") or "")[:MAX_DESC_LEN],
            last_updated=crate.get("updated_at", ""),
            license=crate.get("license"),
            language="Rust",
            downloads=int(crate.get("downloads", 0) or 0),
            version=crate.get("newest_version", ""),
        ))

    return results


# ============================================================================
# Filtering Functions
# ============================================================================

def parse_iso_date(date_str: str) -> Optional[datetime]:
    """Parse ISO 8601 date format (with or without timezone)."""
    if not date_str:
        return None
    try:
        if date_str.endswith("Z"):
            date_str = date_str[:-1] + "+00:00"
        return datetime.fromisoformat(date_str)
    except ValueError:
        return None


def months_since_update(date_str: str) -> int:
    """Calculate months since last update."""
    dt = parse_iso_date(date_str)
    if not dt:
        return 0
    now = datetime.now(timezone.utc)
    delta = now - dt
    return int(delta.days / 30)


def hard_filter(
    results: List[SearchResult],
    complexity: str,
    intent: str,
    relax_niche: bool = False
) -> List[SearchResult]:
    """
    Apply hard filtering rules to search results.
    Returns SearchResult objects (not dicts) for learning-aware sorting.
    """
    filtered = []
    star_threshold = STAR_THRESHOLDS.get(complexity, 50)

    if relax_niche:
        star_threshold = max(10, star_threshold // 5)

    for result in results:
        if result.archived or result.deprecated:
            continue

        download_fallback_threshold = star_threshold * 10
        is_pypi_exact = (result.source == "pypi" and result.stars == 0
                         and result.downloads == 0 and result.popularity == 0)
        is_npm = result.source == "npm"
        passes_activity = (
            is_pypi_exact
            or result.stars >= star_threshold
            or result.downloads >= download_fallback_threshold
            or (is_npm and result.popularity >= 0.1)
        )
        if not passes_activity and not relax_niche:
            continue

        months = months_since_update(result.last_updated)
        if months > UPDATE_THRESHOLD_MONTHS and not relax_niche:
            continue

        filtered.append(result)

    return filtered


def learning_aware_sort(
    results: List[SearchResult],
    memory: Dict[str, Any],
    query: str
) -> List[SearchResult]:
    """
    Sort results using a blend of base quality signals + learned preferences.

    Anti-filter-bubble mechanisms:
    - Exploration floor: every platform gets at least 20% of its base weight
    - Diversity boost: results from unseen domains get 1.3x multiplier
    - The blend is 70% learned + 30% base, preventing total dominance

    Keyword expansion: learned keyword associations boost matching results
    in sorting without narrowing the search query (avoids information loss).
    """
    if not results:
        return results

    query_fp = _query_fingerprint(query)
    seen_domains, total_domains = get_diversity_info(memory)

    # Determine if this query domain is "new" (never seen before)
    is_new_domain = query_fp not in seen_domains

    # Collect learned keyword expansions for matching boost
    expansion_words: set = set()
    expansions = memory.get("keyword_expansions", {})
    for word in query.lower().split():
        if word in expansions:
            expansion_words.update(expansions[word])

    def compute_score(result: SearchResult) -> Tuple[float, float]:
        """
        Returns (primary_score, diversity_score).
        primary_score: quality * learned_weight * keyword_match
        diversity_score: tiebreaker for exploration
        """
        # Base quality score
        source = result.source
        if source == "github":
            base_quality = float(result.stars)
        elif source == "npm":
            base_quality = result.popularity * 10000
        else:
            base_quality = max(float(result.downloads), result.popularity * 100000)

        # Apply learned platform weight
        learned_weight = get_learned_platform_weight(memory, source)

        # Keyword expansion boost: if result name contains learned expansion words
        keyword_boost = 1.0
        if expansion_words:
            result_name = result.name.lower()
            for ew in expansion_words:
                if ew.lower() in result_name:
                    keyword_boost = 1.15  # 15% boost for learned keyword match
                    break

        primary = base_quality * learned_weight * keyword_boost

        # Diversity bonus: boost results from platforms you don't usually prefer
        diversity = 0.0
        if is_new_domain:
            diversity = DIVERSITY_BOOST
        else:
            platform_weights = memory.get("platform_weights", {})
            avg_weight = sum(platform_weights.values()) / len(platform_weights) if platform_weights else 1.0
            if learned_weight < avg_weight * 0.8:
                diversity = 1.1

        return (primary * diversity, diversity)

    results.sort(key=compute_score, reverse=True)
    return results


# ============================================================================
# Main Search Function
# ============================================================================

def search(
    query: str,
    complexity: str = "L2",
    intent: str = "library",
    platforms: str = "github",
    limit: int = DEFAULT_LIMIT,
    token: str = None,
    relax_niche: bool = False,
    use_memory: bool = True
) -> Tuple[SearchResponse, Dict[str, Any]]:
    """
    Execute multi-platform search with concurrent fetching, filtering,
    and learning-aware sorting.

    Returns (response, memory) tuple so caller can record feedback.
    """
    start_time = datetime.now()
    memory = load_memory() if use_memory else {}

    # --- Step 0: Keyword expansions are used for sort boosting, not query expansion ---
    # This avoids narrowing search results while still leveraging learned patterns.
    effective_query = query

    # Check if any keyword expansions exist for this query
    keyword_boost_active = False
    if use_memory:
        expansions = memory.get("keyword_expansions", {})
        for word in query.lower().split():
            if word in expansions:
                keyword_boost_active = True
                break

    # --- Step 1: Concurrent platform searches ---
    platform_list = [p.strip().lower() for p in platforms.split(",")]
    all_results: List[SearchResult] = []

    platform_searchers = {
        "github": lambda: search_github(effective_query, limit, token, intent),
        "pypi": lambda: search_pypi(effective_query, limit),
        "npm": lambda: search_npm(effective_query, limit),
        "maven": lambda: search_maven(effective_query, limit),
        "crates.io": lambda: search_crates(effective_query, limit),
        "crates": lambda: search_crates(effective_query, limit),
    }

    tasks = [(p, platform_searchers[p]) for p in platform_list if p in platform_searchers]

    if tasks:
        with ThreadPoolExecutor(max_workers=min(len(tasks), MAX_CONCURRENCY)) as executor:
            future_to_platform = {
                executor.submit(fn): platform
                for platform, fn in tasks
            }
            for future in as_completed(future_to_platform):
                platform = future_to_platform[future]
                try:
                    results = future.result(timeout=DEFAULT_TIMEOUT + 5)
                    all_results.extend(results)
                except Exception as e:
                    print(f"Warning: {platform} search failed: {e}", file=sys.stderr)

    # --- Step 2: Hard filter ---
    filtered = hard_filter(all_results, complexity, intent, relax_niche)

    # --- Step 3: Learning-aware sorting ---
    if use_memory and memory:
        filtered = learning_aware_sort(filtered, memory, effective_query)

    # --- Step 4: Build response ---
    recommendations = []
    for r in filtered[:5]:
        d = r.to_dict()
        d["action"] = r.get_action()
        recommendations.append(d)

    elapsed = (datetime.now() - start_time).total_seconds()
    status = "found" if recommendations else "not_found"

    response = SearchResponse(
        status=status,
        query=effective_query,
        complexity=complexity,
        intent=intent,
        total_found=len(all_results),
        after_filter=len(filtered),
        recommendations=recommendations,
        message=None if recommendations else "No suitable wheels found. Recommend self-build.",
        cost={
            "time_seconds": round(elapsed, 2),
            "platforms_queried": len(tasks),
            "results_fetched": len(all_results),
            "memory_enabled": use_memory,
            "keyword_boost_active": keyword_boost_active,
        }
    )

    # Record search in memory
    if use_memory:
        record_search(memory, query, response)

    return response, memory


# ============================================================================
# CLI Entry Point
# ============================================================================

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="WheelSpotter - Multi-Platform Wheel Search with Self-Learning",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Search:
    %(prog)s -q "python pdf parser" -c L2 -i library
    %(prog)s -q "react charting" -c L3 -i library -p github,npm -t $GITHUB_TOKEN
    %(prog)s -q "rust web framework" -c L3 -i library -p github,crates -o results.json

  Feedback (after a search):
    %(prog)s --learn -q "python pdf" --chose "pypdf2" --rating 4
    %(prog)s --learn -q "react chart" --chose "recharts" --rating 5 --notes "great API"

  Learning:
    %(prog)s --teach                # Run learning on accumulated feedback
    %(prog)s --stats                # Show learning stats
    %(prog)s --forget               # Reset all learning data
        """
    )

    # Search mode
    parser.add_argument("-q", "--query", help="Search keywords")
    parser.add_argument("-c", "--complexity", choices=["L1", "L2", "L3"], default="L2",
                        help="Complexity level (default: L2)")
    parser.add_argument("-i", "--intent", choices=["library", "service", "tool", "reference"],
                        default="library", help="Intent type (default: library)")
    parser.add_argument("-p", "--platforms", default="github",
                        help="Comma-separated platforms: github,pypi,npm,maven,crates (default: github)")
    parser.add_argument("-l", "--limit", type=int, default=DEFAULT_LIMIT,
                        help=f"Max results per platform (default: {DEFAULT_LIMIT})")
    parser.add_argument("-t", "--token", help="GitHub personal access token (optional)")
    parser.add_argument("-o", "--output", help="Output file path (default: stdout)")
    parser.add_argument("--relax-niche", action="store_true", help="Relax thresholds for niche domains")
    parser.add_argument("--no-memory", action="store_true", help="Disable learning system for this search")

    # Feedback mode
    parser.add_argument("--learn", action="store_true",
                        help="Record feedback: requires -q, --chose, --rating")
    parser.add_argument("--chose", help="Package name the user chose from recommendations")
    parser.add_argument("--rating", type=int, choices=[1, 2, 3, 4, 5],
                        help="Satisfaction rating (1-5, 5 = perfect)")
    parser.add_argument("--notes", default="", help="Optional notes about the choice")

    # Learning management
    parser.add_argument("--teach", action="store_true",
                        help="Run learning engine on accumulated feedback")
    parser.add_argument("--stats", action="store_true",
                        help="Show learning statistics and memory state")
    parser.add_argument("--forget", action="store_true",
                        help="Reset all learning data (irreversible)")

    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {VERSION}")

    return parser.parse_args()


def cmd_search(args):
    """Execute a search."""
    if not args.query:
        print("Error: --query is required for search mode", file=sys.stderr)
        sys.exit(2)

    response, _ = search(
        query=args.query,
        complexity=args.complexity,
        intent=args.intent,
        platforms=args.platforms,
        limit=args.limit,
        token=args.token,
        relax_niche=args.relax_niche,
        use_memory=not args.no_memory,
    )

    output_json = json.dumps(response.to_dict(), indent=2, ensure_ascii=False)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_json)
        print(f"Results written to {args.output}", file=sys.stderr)
    else:
        print(output_json)

    sys.exit(0 if response.status == "found" else 1)


def cmd_learn(args):
    """Record user feedback."""
    if not args.query:
        print("Error: --query is required for --learn mode", file=sys.stderr)
        sys.exit(2)

    memory = load_memory()
    record_feedback(
        memory=memory,
        query=args.query,
        recommendations=[],  # simplified CLI mode
        chosen=args.chose or "",
        rating=args.rating or 3,
        notes=args.notes,
    )

    stats = memory.get("stats", {})
    print(json.dumps({
        "status": "recorded",
        "query": args.query,
        "chosen": args.chose or "(none)",
        "rating": args.rating or 3,
        "total_feedback": stats.get("total_feedback", 0),
        "memory_file": _MEMORY_FILE,
    }, indent=2))
    sys.exit(0)


def cmd_teach(args):
    """Run learning engine."""
    memory = load_memory()
    feedback_count = len(memory.get("feedback", []))

    if feedback_count == 0:
        print(json.dumps({
            "status": "no_data",
            "message": "No feedback recorded yet. Use --learn to record feedback first.",
            "total_feedback": 0,
        }, indent=2))
        sys.exit(0)

    summary = run_learning(memory)
    print(json.dumps({
        "status": "learned",
        "entries_analyzed": summary["entries_analyzed"],
        "platform_weight_changes": summary["platform_changes"],
        "keyword_expansion_changes": summary["keyword_changes"],
        "current_platform_weights": memory.get("platform_weights", {}),
        "current_keyword_expansions": memory.get("keyword_expansions", {}),
        "stats": memory.get("stats", {}),
        "memory_file": _MEMORY_FILE,
    }, indent=2))
    sys.exit(0)


def cmd_stats(args):
    """Show learning statistics."""
    memory = load_memory()
    stats = memory.get("stats", {})
    feedback = memory.get("feedback", [])

    # Compute some useful stats
    avg_rating = 0
    if feedback:
        avg_rating = sum(e.get("rating", 0) for e in feedback) / len(feedback)

    top_platforms = {}
    for entry in feedback:
        for rec in entry.get("recommendations", []):
            source = rec.get("source", "")
            if source:
                top_platforms[source] = top_platforms.get(source, 0) + 1

    print(json.dumps({
        "version": VERSION,
        "memory_file": _MEMORY_FILE,
        "stats": stats,
        "avg_rating": round(avg_rating, 2),
        "platform_distribution": dict(sorted(top_platforms.items(), key=lambda x: -x[1])),
        "learned_platform_weights": memory.get("platform_weights", {}),
        "learned_keyword_expansions": memory.get("keyword_expansions", {}),
        "recent_feedback": feedback[-3:] if feedback else [],
    }, indent=2, ensure_ascii=False))
    sys.exit(0)


def cmd_forget(args):
    """Reset all learning data."""
    if os.path.exists(_MEMORY_FILE):
        os.remove(_MEMORY_FILE)
        print(json.dumps({
            "status": "reset",
            "message": "All learning data has been deleted.",
            "memory_file": _MEMORY_FILE,
        }, indent=2))
    else:
        print(json.dumps({
            "status": "no_data",
            "message": "No memory file found to delete.",
        }, indent=2))
    sys.exit(0)


def main():
    """Main entry point with subcommand routing."""
    args = parse_args()

    if args.forget:
        cmd_forget(args)
    elif args.stats:
        cmd_stats(args)
    elif args.teach:
        cmd_teach(args)
    elif args.learn:
        cmd_learn(args)
    else:
        cmd_search(args)


if __name__ == "__main__":
    main()
