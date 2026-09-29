"""Reference resolver for the WellaPath symptom vocabulary (W2).

Implements the five-state match model documented in
`docs/VOCABULARY_AMBIGUITY_SPEC.md`. Mobile ships its own implementation; this
one is the contract it must match, and it is what the fixture expectations in
`testing/vocabulary/fixtures/search/` are generated against.

Non-negotiable safety properties (all covered by tests):

  * A query never resolves to a clinical token unless exactly one candidate
    survives. `AMBIGUOUS` carries candidates and a null `resolved_token_id`.
  * `scoring_eligible` is true only when `resolved_token_id` is non-null.
    An unresolved ambiguity can therefore never be scored.
  * Matching is whole-string equality on the normalized form. There is no
    substring, prefix, edit-distance or other fuzzy matching anywhere in this
    module, so "no fever" can never resolve to `fever`.
  * Candidate ordering is a fixed lexicographic sort. It deliberately encodes
    no clinical priority: ordering red flags first would be server-side
    clinical inference, which the architecture forbids.
"""

from .normalize import normalize, normalize_token_id

RESOLVER_VERSION = "1.0.0"

# Match statuses, in precedence order.
EXACT_CANONICAL = "exact_canonical"
EXACT_ALIAS = "exact_alias"
NORMALIZED = "normalized"
AMBIGUOUS = "ambiguous"
NO_MATCH = "no_match"

MATCH_STATUSES = (EXACT_CANONICAL, EXACT_ALIAS, NORMALIZED, AMBIGUOUS, NO_MATCH)

# Ordering rank for `matched_via`. A canonical form outranks an alias when both
# normalize to the same string — the canonical clinical name is the more
# conservative thing to show first. This is presentation order only; it never
# collapses an ambiguity.
_MATCHED_VIA_RANK = {"canonical_token_id": 0, "canonical_label": 1, "alias": 2}

# Category ordering is the plain lexicographic order of the legacy category key.
# It is NOT a clinical ranking. See the module docstring.
_CATEGORY_ORDER = (
    "body_area_tokens",
    "demographic_tokens",
    "duration_tokens",
    "red_flag_tokens",
    "severity_tokens",
    "symptom_tokens",
)


class VocabularyIndex(object):
    """Immutable lookup structure built from a vocabulary 2.0 artifact."""

    def __init__(self, artifact):
        self.artifact_version = artifact.get("_metadata", {}).get("version")
        self.schema_version = artifact.get("_metadata", {}).get("schema_version")

        self.entries = {}
        self._by_exact_token_id = {}
        self._by_exact_alias = {}
        self._by_normalized = {}

        for entry in artifact.get("tokens", []):
            token_id = entry["token_id"]
            self.entries[token_id] = entry
            self._by_exact_token_id[token_id] = token_id

            for alias in entry.get("search", {}).get("aliases", []):
                self._by_exact_alias.setdefault(alias, []).append(token_id)

            self._add_normalized(entry["search"]["normalized_form"], token_id, "canonical_token_id")
            label = entry.get("display", {}).get("canonical_label")
            if label:
                self._add_normalized(normalize(label), token_id, "canonical_label")
            for alias in entry.get("search", {}).get("aliases", []):
                self._add_normalized(normalize(alias), token_id, "alias")

        for key in self._by_exact_alias:
            self._by_exact_alias[key] = sorted(set(self._by_exact_alias[key]))
        for key in self._by_normalized:
            self._by_normalized[key] = self._sort_candidates(self._by_normalized[key])

    def _add_normalized(self, normalized_form, token_id, matched_via):
        bucket = self._by_normalized.setdefault(normalized_form, [])
        for existing in bucket:
            if existing["token_id"] == token_id:
                # Keep the strongest (lowest-rank) provenance for this token.
                if _MATCHED_VIA_RANK[matched_via] < _MATCHED_VIA_RANK[existing["matched_via"]]:
                    existing["matched_via"] = matched_via
                return
        bucket.append({"token_id": token_id, "matched_via": matched_via})

    def _sort_candidates(self, candidates):
        return sorted(
            candidates,
            key=lambda c: (
                _MATCHED_VIA_RANK[c["matched_via"]],
                _category_rank(self.entries[c["token_id"]]["category"]),
                c["token_id"],
            ),
        )

    def normalized_forms(self):
        """`{normalized_form: [token_id, ...]}` in resolver order.

        This is exactly what is emitted as `search_index.normalized_forms` in
        the artifact, so consumers can look up instead of re-deriving.
        """
        return {
            form: [c["token_id"] for c in candidates]
            for form, candidates in sorted(self._by_normalized.items())
        }

    def _candidate_view(self, token_id, matched_via):
        entry = self.entries[token_id]
        display = entry.get("display", {})
        return {
            "token_id": token_id,
            "category": entry["category"],
            "matched_via": matched_via,
            # `safe_display_label` is what a caller may put on screen for
            # disambiguation. When the label has not been clinically reviewed
            # the field is null and the caller must use its own approved
            # display map — it must never fall back to the raw token ID.
            "safe_display_label": display.get("canonical_label")
            if display.get("display_safe") is True
            else None,
            "display_safe": display.get("display_safe", False),
            "status": entry.get("clinical_identity", {}).get("status"),
            "replaced_by": entry.get("clinical_identity", {}).get("replaced_by"),
        }

    def resolve(self, query):
        """Resolve a raw user or consumer query to the match result contract."""
        if not isinstance(query, str):
            raise TypeError("resolve() expects str")

        normalized = normalize(query)
        base = {
            "query": query,
            "query_normalized": normalized,
            "resolver_version": RESOLVER_VERSION,
        }

        # 1. Exact canonical: byte equality against the stable token ID.
        if query in self._by_exact_token_id:
            return _result(base, EXACT_CANONICAL, [self._candidate_view(query, "canonical_token_id")])

        # 2. Exact alias: byte equality against an authored alias string.
        if query in self._by_exact_alias:
            token_ids = self._by_exact_alias[query]
            candidates = self._sort_candidates(
                [{"token_id": t, "matched_via": "alias"} for t in token_ids]
            )
            views = [self._candidate_view(c["token_id"], c["matched_via"]) for c in candidates]
            if len(views) == 1:
                return _result(base, EXACT_ALIAS, views)
            return _result(base, AMBIGUOUS, views)

        # 3. Normalized match against canonical forms, labels and aliases.
        if normalized in self._by_normalized:
            candidates = self._by_normalized[normalized]
            views = [self._candidate_view(c["token_id"], c["matched_via"]) for c in candidates]
            if len(views) == 1:
                return _result(base, NORMALIZED, views)
            return _result(base, AMBIGUOUS, views)

        # 4. Nothing matched.
        return _result(base, NO_MATCH, [])


def _category_rank(category):
    try:
        return _CATEGORY_ORDER.index(category)
    except ValueError:
        # Unknown categories sort last, then lexicographically, so a future
        # category addition cannot reorder existing results.
        return len(_CATEGORY_ORDER)


def _result(base, status, candidates):
    single = status in (EXACT_CANONICAL, EXACT_ALIAS, NORMALIZED) and len(candidates) == 1
    result = dict(base)
    result["status"] = status
    result["candidates"] = candidates
    result["resolved_token_id"] = candidates[0]["token_id"] if single else None
    # The engine may only score a token this flag marks. AMBIGUOUS and NO_MATCH
    # are never scoreable; disambiguation belongs to the approved question flow.
    result["scoring_eligible"] = single
    return result


def build_index(artifact):
    return VocabularyIndex(artifact)
