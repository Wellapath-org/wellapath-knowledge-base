# Vocabulary Expansion Request Process

**Template:** `templates/vocabulary_expansion_request.template.json`
**Owner:** Product / Clinical propose · Knowledge Base / Data Engineering implement · Clinical approve

---

## 1. The rule

> Unapproved entries must not enter a release artifact.

W2 Step 1 deliberately ships **zero** aliases, body-area associations, complaint
groups and severity/duration descriptors. Not because the schema cannot hold
them, but because no approved catalogue for any of them exists in this
repository, and filling the fields with plausible guesses would put unreviewed
clinical content into a distributed artifact.

This process is how that content gets in legitimately.

---

## 2. Alias first, new token last

The cheapest proposal is an **alias**: a new way to find an existing token. It is
`search_only_metadata`, it cannot affect scoring, and it needs no rules or KB
change.

A **new token** is expensive. It is a `clinical_token_identity` change, it
escalates to `red_flag_affecting` or `scoring_rule_affecting` if any rule or KB
condition would reference it, it blocks publication pending clinical review, and
it needs regression cases. It is also useless on its own: a token that no KB
condition scores on and no rule references adds nothing but a picker entry — the
repository already has 55 such tokens (`reports/token_reference_graph_v1.json`).

Propose a new token only when the concept is genuinely clinically distinct from
every one of the existing 295.

---

## 3. Workflow

```
Product/Clinical            Data Engineering              Clinical
    |                              |                          |
    | 1. fill the template         |                          |
    |----------------------------->|                          |
    |                              | 2. feasibility read      |
    |                              |    - collision check     |
    |                              |    - classification      |
    |                              |    - regression scoping  |
    |<-----------------------------|                          |
    |                              |                          |
    | 3. revise if needed          |                          |
    |------------------------------------------------------->|
    |                              |     4. clinical review   |
    |                              |        reviewer + date   |
    |                              |        + evidence link   |
    |<-------------------------------------------------------|
    |                              |                          |
    |                              | 5. implement, validate,  |
    |                              |    classify, PR          |
    |                              |                          |
```

**Step 2 comes before step 4 on purpose.** A feasibility read is cheap; clinical
review time is not. Sending a proposal with an unnoticed collision or an alias
that normalization already handles wastes the scarcest resource in the loop.

---

## 4. Required fields

Full definitions live in the template. In summary, every entry requires:

| Field | Why it is required |
|---|---|
| `proposed_canonical_label` | Caregiver-facing plain English. The vocabulary carries no approved labels today. |
| `proposed_aliases` | The actual search phrases. |
| `intended_body_area` | Picker routing. Must be an existing `body_area_token`. |
| `severity_applicability` / `duration_applicability` | Which descriptors the token may be qualified by. Descriptive only — changes no weight or urgency. |
| `complaint_group` | Grouping for the picker. |
| `ambiguity_notes` | **The most important field.** What else could a user mean? |
| `source_provenance` | Where the wording came from. "Seemed sensible" is not provenance. |
| `clinical_reviewer` + `review_date` + `approval_evidence` | No approval without all three. A claim with no link is not an approval. |
| `affected_existing_tokens` | Blast radius. |
| `affected_questions_or_rules` | Any non-empty value escalates beyond search-only metadata. |
| `regression_cases_required` | Required for any blocking classification. |
| `expected_change_classification` | Forces the proposer to think about which gate applies. |

---

## 5. Checking a proposal before submitting

**Does normalization already handle it?** Spelling, case, punctuation and hyphen
variants need no alias at all:

```bash
python3 -c "import sys; sys.path.insert(0,'tools'); from vocab.normalize import normalize; print(normalize('Chest-Pain!'))"
# -> chest pain   (already resolves; no alias needed)
```

**Does it collide with an existing token?**

```bash
python3 -c "
import sys, json; sys.path.insert(0,'tools')
from vocab.resolve import build_index
idx = build_index(json.load(open('candidate/token_dictionary.ng.v2.0.json')))
r = idx.resolve('your proposed phrase')
print(r['status'], r['resolved_token_id'], [c['token_id'] for c in r['candidates']])
"
```

**What class will the change be?** After implementing, before opening the PR:

```bash
python3 tools/classify_vocabulary_diff.py
```

---

## 6. Identified candidate sources, not yet approved

These exist in or near the repository and are the obvious first inputs for a real
expansion batch. **None is approved for vocabulary use**, and W2 Step 1 imported
nothing from any of them.

| Source | State | What it could supply | Why not used yet |
|---|---|---|---|
| `mobile_handoff/red_flag_display_map.json` (PR #21, merged) | Merged in this repository | Caregiver display names and body areas for 12 global red-flag tokens | Approved as a **mobile display map**, not as vocabulary metadata. Promoting it needs a scope decision plus clinical sign-off on each label. |
| `mobile_handoff/picker_scoring_gap_tokens.json` (PR #24, merged) | Merged in this repository | Display names and body areas for 9 scoring-gap tokens; recommends `breathlessness` become an alias of `shortness_of_breath` | Same scope question. The alias recommendation is a `clinical_token_identity` change and explicitly needs clinical review. |
| `symptom_display_body_area_map.csv` / `.json` (PR #9) | **Open, unmerged** | Display name and body area for all 164 symptom tokens; flags 61 as ambiguous for lay users | Unmerged and unapproved. Importing from an open PR would put unreviewed content in a distributed artifact. |
| `source/WellaPath_E2.1_Token_Dictionary_v1.0.xlsx` | Committed source | The original token authoring sheet | Would need re-reading against the current 295-token set, and it predates the 1.1 corrections. |

**Recommended first batch:** promote `red_flag_display_map.json` labels and body
areas into `display.canonical_label` and `associations.body_areas` for those 12
tokens, with clinical sign-off on the labels. It is small, the content is already
merged and already reviewed once for a closely related purpose, and it directly
addresses a recorded beta gap.

---

## 7. What the data engineer does on receipt

1. Validate the request against the template — reject incomplete ones.
2. Run the collision and normalization checks above.
3. Confirm the proposed classification with `tools/classify_vocabulary_diff.py`.
4. Implement in the generator, never by hand-editing the artifact.
5. `python3 tools/run_w2_checks.py` — all 11 checks green.
6. Open a PR with the classification output and the approval evidence links in
   the description.
7. If the classification is a blocking class, the PR does not merge to a release
   branch until the named approval is recorded and linked.
