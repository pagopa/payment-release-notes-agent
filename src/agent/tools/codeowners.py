"""CODEOWNERS parsing and per-file owner resolution.

Implements the common subset of GitHub's CODEOWNERS pattern syntax
(gitignore-style, without "**", which CODEOWNERS does not support):
- leading "/"   → pattern anchored to the repo root
- trailing "/"  → pattern matches a directory and everything under it
- no "/" at all → pattern matches a file/dir with that name at any depth
- "*"           → matches anything except "/"
- "?"           → matches a single character except "/"
"""

import re
from typing import List, Tuple

Rule = Tuple[re.Pattern, List[str]]


def parse(content: str) -> List[Rule]:
    """Parse CODEOWNERS text into an ordered list of (compiled_pattern, owners)."""
    rules: List[Rule] = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        pattern, owners = parts[0], parts[1:]
        if owners:
            rules.append((_pattern_to_regex(pattern), owners))
    return rules


def resolve_owners(rules: List[Rule], file_paths: List[str]) -> List[str]:
    """Resolve the owners covering *file_paths*.

    Per CODEOWNERS semantics, for each file the LAST matching rule in the
    file wins. Returns the deduplicated owners (first-seen order) across all
    given files.
    """
    owners_seen: List[str] = []
    for path in file_paths:
        matched: List[str] = []
        for regex, owners in rules:
            if regex.match(path):
                matched = owners
        for owner in matched:
            if owner not in owners_seen:
                owners_seen.append(owner)
    return owners_seen


def _pattern_to_regex(pattern: str) -> re.Pattern:
    anchored = pattern.startswith("/")
    pat = pattern.lstrip("/")
    is_dir_pattern = pat.endswith("/")
    pat = pat.rstrip("/")

    segments = pat.split("/")
    regex_segments = []
    for seg in segments:
        escaped = re.escape(seg).replace(r"\*", "[^/]*").replace(r"\?", "[^/]")
        regex_segments.append(escaped)
    body = "/".join(regex_segments)

    prefix = "^" if (anchored or "/" in pat) else r"^(?:.*/)?"
    suffix = r"(?:/.*)?$"
    return re.compile(prefix + body + suffix)
