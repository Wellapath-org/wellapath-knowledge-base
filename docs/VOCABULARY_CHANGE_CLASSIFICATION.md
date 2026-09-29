# Vocabulary Change Classification

**Status:** contract for `token_dictionary` schema 2.0
**Implementation:** `tools/classify_vocabulary_diff.py`
**Reports:** `reports/baseline_diff_v1.json`, `reports/migration_report_v1.json`

Every difference between two vocabulary artifacts is assigned exactly one class.
The class decides who has to approve it before it can be published.

---

## 1. The classes

| Class | What it covers | Blocks publication | Required approval |
|---|---|---|---|
| `search_only_metadata` | Aliases, normalized forms, the search index, association metadata (body areas, complaint groups, severity/duration descriptors), new top-level keys | No | Data engineering merge |
| `display_only_metadata` | Canonical labels, `display_safe`, `label_review_status`, locale, body-area and complaint-group display text | No | Product review |
| `clinical_token_identity` | A token ID added, removed, recategorized, repointed, reordered, or its `scoring_eligible` changed | **Yes** | Clinical review + engineering lead |
| `red_flag_affecting` | Any change touching a token that a rules rule or a kb `red_flags` list depends on | **Yes** | Clinical review + engineering lead |
| `scoring_rule_affecting` | Any change touching a token carrying a kb symptom weight | **Yes** | Clinical review + engineering lead |
| `question_flow_affecting` | Any change to the set of tokens an assessment may submit | **Yes** | Clinical review + product review |
| `deprecation_removal` | A token deprecated or removed | **Yes** | Clinical review + engineering lead |

The blocking classes are not advisory. `publication_eligible` is `false` whenever
any is present, and `tools/run_w2_checks.py` asserts it in CI.

---

## 2. Escalation

A token-identity change **inherits the strongest clinical role the affected
token plays**. Adding a token that a rules rule references is not merely
`clinical_token_identity`; it is also `red_flag_affecting`. Roles are read from
the frozen consumers (`kb.ng.v2.4.json`, `rules.ng.v2.2.json`) at classification
time, so the escalation reflects what the artifacts actually do, not what a
reviewer remembers.

The reference graph records the role of every token up front:

- 50 tokens are `red_flag_affecting`
- 163 tokens are `scoring_affecting`
- 55 tokens have no kb or rules consumer at all

See `reports/token_reference_graph_v1.json`.

---

## 3. Why search metadata is not clinically inert by assumption

It is inert **by construction**, and the construction is checked:

1. Aliases have no entry of their own — no `token_id`, no `scoring_eligible`
   flag. There is no data path from an alias to a score.
2. `search.search_only` is a schema constant (`const: true`). Changing it
   requires a schema bump.
3. `resolved_token_id` is null unless exactly one candidate survives, and
   `scoring_eligible` is true only when `resolved_token_id` is non-null.
4. Association metadata (body areas, complaint groups, severity and duration
   descriptors) is documented as filter/routing data and is read by no rule.

**The default rule:** metadata added under schema 2.0 is search, input or display
metadata. It must not affect scoring, red-flag evaluation, urgency or condition
ranking unless a later clinically reviewed, versioned **rules** release
explicitly consumes it — which would itself be a rules schema change, reviewed on
its own terms.

---

## 4. The W2 Step 1 result

```
classifications: search_only_metadata
blocking:        none
classification gate passed: True
MAY PUBLISH:     False

token counts: {"old": 295, "new": 295, "added": 0, "removed": 0, "unchanged": 295}
```

The only finding is "new top-level keys added", classified `search_only_metadata`
because schema 1.0 consumers never read them.

### A clean classification is not an approval

`publication_eligible: true` answers exactly one question: *does this diff
contain a change requiring clinical review?* It is necessary for publication and
nowhere near sufficient. `reports/baseline_diff_v1.json` therefore carries a
separate `publication_decision` block, and its `may_publish` is **`false`**:

| Gate | State |
|---|---|
| Classification gate | ✅ passed |
| Clinical review of schema 2.0 | ❌ not performed |
| Engineering-lead approval | ❌ not recorded |
| 239-case Top-50 regression against kb 2.4 | ❌ not re-run |
| `release_status` | `candidate_unapproved` |
| Uploaded to R2 | ❌ no |
| Live manifest changed | ❌ no |

---

## 5. Using it

```bash
# classify the candidate against the frozen baseline
python3 tools/classify_vocabulary_diff.py

# classify any two artifacts
python3 tools/classify_vocabulary_diff.py old.json new.json

# regenerate the committed reports
python3 tools/classify_vocabulary_diff.py --write
```

Run this on **every** vocabulary change before opening a PR, and paste the output
into the PR description. A PR whose diff carries a blocking class must not be
merged to a release branch until the named approval is recorded and linked.
