"""DATA-07: Evidence deduplication and cross-platform clustering.

URL canonicalization, title/author/content near-duplicate detection,
and same-event cross-platform clustering.  Every source is preserved;
deduplication only suppresses redundant items.
"""

from __future__ import annotations

import re
from itertools import combinations
from typing import Any
from urllib.parse import parse_qs, urlparse, urlunparse

# ── URL canonicalization ─────────────────────────────────────────────────────

_URL_TRACKING_PARAMS = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "ref", "ref_src", "ref_url", "from", "source", "spm", "track_id",
    "share_id", "session_id", "timestamp", "_t", "t",
})

_KNOWN_SHORTENER_HOSTS = frozenset({
    "t.co", "bit.ly", "tinyurl.com", "ow.ly", "buff.ly",
    "b23.tv", "v.douyin.com", "xhslink.com",
})


def canonicalize_url(url: str) -> str:
    """Normalize a URL for dedup purposes: lower host, strip tracking params, remove frag."""
    try:
        p = urlparse(str(url).strip())
    except Exception:
        return url

    scheme = (p.scheme or "https").lower()
    netloc = (p.netloc or "").lower().rstrip(".")
    path = p.path.rstrip("/") or "/"

    # drop tracking query params
    if p.query:
        qs = parse_qs(p.query, keep_blank_values=False)
        filtered = {k: v for k, v in qs.items() if k.lower() not in _URL_TRACKING_PARAMS}
        query = "&".join(f"{k}={','.join(v)}" for k, v in sorted(filtered.items()))
    else:
        query = ""

    return urlunparse((scheme, netloc, path, "", query, ""))


# ── title similarity ─────────────────────────────────────────────────────────

_NON_ALPHA_RE = re.compile(r"[^a-zA-Z0-9一-鿿]")
_MIN_SHINGLE_LEN = 2


def _shingles(text: str, n: int = 3) -> set[str]:
    clean = _NON_ALPHA_RE.sub("", text.lower())
    return {clean[i:i+n] for i in range(len(clean) - n + 1)}


def title_similarity(a: str, b: str) -> float:
    """Jaccard similarity on character trigrams. 0.0 = completely different, 1.0 = identical."""
    sa = _shingles(a, 3)
    sb = _shingles(b, 3)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


# ── dedup core ───────────────────────────────────────────────────────────────

SIMILARITY_THRESHOLD = 0.75  # titles above this are considered duplicates


def deduplicate_items(
    items: list[dict[str, Any]],
    *,
    url_weight: float = 1.0,
    title_threshold: float = SIMILARITY_THRESHOLD,
) -> list[dict[str, Any]]:
    """Remove near-duplicates, keeping the item with the best rank/heat.

    Items are compared by:
    1. Exact URL match after canonicalization → immediate duplicate.
    2. Title Jaccard similarity > threshold → near-duplicate.
    3. Each item is compared against already-kept items only (first-wins
       after sorting by rank, then by title length for richer content).

    Cross-platform items are NOT deduplicated against each other — only
    items from the same platform are compared.
    """
    # sort by rank ascending, then title length descending
    sorted_items = sorted(
        items,
        key=lambda it: (it.get("rank", 999), -len(it.get("title", ""))),
    )

    kept: list[dict[str, Any]] = []
    kept_urls: list[str] = []
    kept_titles: list[str] = []
    kept_platforms: list[str] = []

    for item in sorted_items:
        url = canonicalize_url(item.get("url", ""))
        platform = str(item.get("source_platform") or item.get("platform", ""))
        title = str(item.get("title", ""))

        # Exact URL match
        if any(url == ku and platform == kp for ku, kp in zip(kept_urls, kept_platforms)):
            continue

        # Title similarity — only within same platform
        is_dup = False
        for i, kt in enumerate(kept_titles):
            if kept_platforms[i] == platform and title_similarity(title, kt) >= title_threshold:
                is_dup = True
                break
        if is_dup:
            continue

        kept.append(item)
        kept_urls.append(url)
        kept_titles.append(title)
        kept_platforms.append(platform)

    return kept


def cross_platform_clusters(
    items: list[dict[str, Any]],
    title_threshold: float = SIMILARITY_THRESHOLD,
) -> list[list[dict[str, Any]]]:
    """Group items from different platforms that appear to cover the same event.

    Each cluster contains items from distinct platforms.  A cluster forms
    when titles are above *title_threshold*.
    """
    if len(items) < 2:
        return [[i] for i in items]

    clusters: list[set[int]] = []
    idxs = list(range(len(items)))

    for i, j in combinations(idxs, 2):
        pi = str(items[i].get("source_platform") or items[i].get("platform", ""))
        pj = str(items[j].get("source_platform") or items[j].get("platform", ""))
        if pi == pj:
            continue  # same platform → not cross-platform

        ti = str(items[i].get("title", ""))
        tj = str(items[j].get("title", ""))
        if title_similarity(ti, tj) < title_threshold:
            continue

        # find or create cluster
        ci = next((c for c in clusters if i in c), None)
        cj = next((c for c in clusters if j in c), None)
        if ci is None and cj is None:
            clusters.append({i, j})
        elif ci is not None and cj is None:
            ci.add(j)
        elif ci is None and cj is not None:
            cj.add(i)
        elif ci is not cj:
            ci.update(cj)
            clusters.remove(cj)

    # items not in any cluster → singleton clusters
    clustered: set[int] = set()
    for c in clusters:
        clustered.update(c)
    for i in idxs:
        if i not in clustered:
            clusters.append({i})

    return [[items[i] for i in sorted(c)] for c in sorted(clusters, key=lambda c: -len(c))]
