# Changelog

All notable changes to WheelSpotter will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [3.0.0] - 2026-04-30

### Added
- **Self-Learning Feedback System**
  - --learn mode: Record user feedback (chosen package + rating 1-5)
  - --teach command: Run learning engine to update platform weights and keyword expansions
  - --forget command: Reset learning data
  - --stats command: Display learning statistics
  - Memory persisted to scripts/wheel_memory.json

- **Anti-Filter-Bubble Mechanisms**
  - 20% exploration floor: No platform weight drops below 20% of base
  - 90-day decay: Old feedback loses influence over time
  - 1.3x diversity boost for unseen query domains
  - 70/30 blending: Learned preferences never fully dominate

- **Enhanced Search Results**
  - match_score field: 0-1 score indicating result quality (based on stars/threshold)
  - action field: Ready-to-use install command (pip install, npm install, etc.)
  - Description truncation: 200 chars max for cleaner output

- **Improved Platform Detection**
  - _infer_source(): Better package-to-platform inference
  - Added 50+ Python package names to recognition list
  - Packages with - in name prioritized as Python packages

### Fixed
- **BUG-06**: SearchResult.to_dict() now outputs match_score field
- **BUG-10**: _infer_source() correctly identifies Python packages like scikit-learn, pytorch, tensorflow
- **Carry-forward bug**: Keyword expansions correctly capped at 5 per stem, even when feedback is empty
- **API consistency**: search_crates() now accepts timeout parameter like other platform search functions
- **Platform weights**: Single feedback entry no longer causes division-by-zero or unexpected weight changes

### Changed
- Base weights normalized to 1.0 for all platforms (was 0.8 for some)
- Exploration floor formula corrected to ensure minimum 20% exploration
- keyword_expansions now filters common stopwords to avoid noise

### Documentation
- SKILL.md converted to full English
- README.md created with Quick Start, CLI reference, and learning system docs
- Added GITHUB_TOKEN setup instructions (required for 5000 req/hour vs 60 req/hour)

---

## [2.0.0] - 2026-04-15

### Added
- **Concurrent Platform Searches**
  - ThreadPoolExecutor for parallel API calls
  - Configurable concurrency limit (MAX_FEEDBACK_ENTRIES=500)

- **Defensive Type Checking**
  - All platform parsers handle malformed API responses gracefully
  - Safe extraction of stars, description, license, etc.

- **GitHub Query Enhancement**
  - Language hints from intent (language:python, etc.)
  - Topic-based search refinement

- **CLI Improvements**
  - --output flag for JSON file export
  - --no-memory flag to disable learning temporarily
  - Proper exit codes (0=found, 1=error, 2=no results)

### Fixed
- npm search API handling (was returning empty results)
- GitHub noise filtering (archived/deprecated repos deprioritized)

---

## [1.1.0] - 2026-04-01

### Added
- Zero external dependencies (stdlib only)
- PyPI search via official JSON API
- npm search via registry API

### Fixed
- PyPI package metadata extraction
- npm version parsing edge cases

---

## [1.0.0] - 2026-03-15

### Added
- Initial release
- GitHub repository search
- Basic CLI with query, complexity, intent parameters
- JSON output format

---

## Version History Summary

| Version | Date | Key Feature |
|---------|------|-------------|
| 3.0.0 | 2026-04-30 | Self-learning feedback system |
| 2.0.0 | 2026-04-15 | Concurrent searches, type safety |
| 1.1.0 | 2026-04-01 | Zero deps, PyPI/npm support |
| 1.0.0 | 2026-03-15 | Initial release |