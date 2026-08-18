"""IM-003 additive re-branching: the trigger graph, its closure, and its reach.

IM-003 would re-evaluate question eligibility after an answer, so a token
derived from an answer can make a further question eligible. It is NOT
implemented and nothing here implements it — this module builds the analysis
model used to decide whether it ever should be.

## The graph

A node is a token that is a key in ``kFollowupQuestionMap``. An edge ``a -> b``
exists when ``a``'s additional-symptoms question offers ``b`` as an option AND
``b`` is itself a map key, so answering "yes, I also have b" would make b's
questions eligible.

Those edges are exactly the 56 ``(source, option)`` pairs the candidate records.

## Why cycles do not mean non-termination

The graph is heavily cyclic — 30 two-cycles. Under ADDITIVE-only re-branching
the selected-token set is monotone non-decreasing and bounded above by the
finite token universe, so the iteration reaches a fixed point in at most
``|universe|`` steps regardless of cycles. That is proved by construction in
``closure()`` and measured in ``convergence_depth()``; it is not assumed.

Monotonicity is a property of ADDITIVE re-branching only. Removal or
invalidation re-branching is NOT monotone and is explicitly out of scope.

Standard library only. No network.
"""

import collections

#: The four re-branching modes. Only the first is analysed.
REBRANCH_MODES = {
    "additive_only": (
        "After an answer, newly satisfied triggers make further questions "
        "eligible. Nothing already eligible is withdrawn. The token set only "
        "grows, so the iteration is monotone."
    ),
    "removal_invalidation": (
        "A question that was eligible becomes ineligible and is withdrawn. NOT "
        "monotone, NOT analysed, NOT proposed."
    ),
    "answer_edit_driven": (
        "Changing an earlier answer re-derives state and may withdraw or add "
        "questions. Requires the editing model the MVP does not have. NOT "
        "analysed."
    ),
    "restoration_driven": (
        "Re-deriving a flow from persisted answers on resume. Requires the "
        "persistence model the MVP does not have. NOT analysed."
    ),
}


def build_trigger_graph(entries):
    """token -> tokens whose questions its additional-symptoms answers unlock.

    Only edges to tokens that are themselves map keys can unlock a question, so
    only those are edges. Options that are not map keys are recorded separately
    by :func:`option_tokens` because they still reach scoring.
    """
    graph = {}
    for token in sorted(entries):
        targets = set()
        for entry in entries[token]:
            if entry["type"] != "additionalSymptoms":
                continue
            for option in entry["options"]:
                if option in entries:
                    targets.add(option)
        graph[token] = targets
    return graph


def trigger_pairs(entries):
    """Every ``(source, option)`` pair where the option is itself a map key.

    This is the set the candidate reports as 56. Returned sorted so the count
    and the contents are both reproducible.
    """
    pairs = []
    for source in sorted(entries):
        for entry in entries[source]:
            if entry["type"] != "additionalSymptoms":
                continue
            for option in entry["options"]:
                if option in entries:
                    pairs.append((source, option))
    return sorted(pairs)


def option_tokens(entries, token):
    """Every token an additional-symptoms answer on ``token`` can contribute.

    Includes options that are NOT map keys: they unlock no question but they do
    reach scoring, which is the impact that matters clinically.
    """
    out = set()
    for entry in entries.get(token, ()):
        if entry["type"] == "additionalSymptoms":
            out.update(entry["options"])
    return out


def closure(graph, seeds):
    """Every node reachable from ``seeds``, and the step at which each appears.

    The proof of termination is the algorithm: ``seen`` only grows, every
    iteration adds at least one node or stops, and the node set is finite.
    """
    seen = set(seeds)
    depth = {s: 0 for s in seeds}
    frontier = set(seeds)
    step = 0
    while frontier:
        step += 1
        nxt = set()
        for token in frontier:
            for target in graph.get(token, ()):
                if target not in seen:
                    seen.add(target)
                    depth[target] = step
                    nxt.add(target)
        frontier = nxt
    return seen, depth


def convergence_depth(graph, seeds):
    """Steps needed to reach the fixed point from ``seeds``. Measured."""
    _seen, depth = closure(graph, seeds)
    return max(depth.values()) if depth else 0


def find_cycles(graph):
    """Two-cycles and self-loops, reported rather than assumed absent."""
    two = sorted(
        {
            tuple(sorted((a, b)))
            for a in graph
            for b in graph[a]
            if a in graph.get(b, ())
        }
    )
    loops = sorted(a for a in graph if a in graph[a])
    return {"two_cycles": two, "self_loops": loops}


def is_monotone(graph):
    """Additive re-branching never removes a node from the reachable set.

    Verified structurally: adding a seed can only add reachable nodes, never
    take one away. Checked over every pair of seeds rather than asserted.
    """
    violations = []
    nodes = sorted(graph)
    for a in nodes:
        reach_a, _ = closure(graph, {a})
        for b in nodes:
            reach_both, _ = closure(graph, {a, b})
            if not reach_a.issubset(reach_both):
                violations.append((a, b))
    return not violations, violations


#: Roles a newly eligible question can carry, and whether the role's own answer
#: tokens carry clinical weight. Populated by measurement, never by assumption.
ROLE_KINDS = ("severity", "duration", "additionalSymptoms")


def newly_eligible(entries, token):
    """Questions that become eligible when ``token`` enters the state."""
    return [
        {"role": e["type"], "question_text": e["question_text"],
         "option_count": len(e["options"])}
        for e in entries.get(token, ())
    ]


class ClinicalIndex:
    """Where a token appears in the frozen clinical artifacts.

    Duplicates no clinical rule. It reports references so an IM-003 effect can
    be traced to the conditions and rules it could touch, and makes no
    judgement about urgency or triage.
    """

    def __init__(self, kb, rules, clarifiers):
        self.scoring = collections.defaultdict(list)
        self.weights = {}
        self.condition_red_flags = collections.defaultdict(list)
        self.demographic_conditions = collections.defaultdict(list)
        self.global_rules = collections.defaultdict(list)
        self.clarifier_triggers = {}
        self.clarifier_red_flag_tokens = set()

        for condition in kb["conditions"]:
            cid = condition["condition_id"]
            has_demographic = bool(condition.get("demographic_modifiers"))
            for symptom in condition.get("symptoms", []):
                token = symptom["token"]
                weight = int(symptom.get("weight", 0))
                self.scoring[token].append({"condition_id": cid, "weight": weight})
                self.weights[token] = max(self.weights.get(token, 0), weight)
                if has_demographic:
                    self.demographic_conditions[token].append(cid)
            for flag in condition.get("red_flags", []):
                self.condition_red_flags[flag].append(cid)

        for rule in rules["rules"]:
            self.global_rules[rule["token"]].append(rule["rule_id"])

        for clarifier in clarifiers:
            self.clarifier_red_flag_tokens.add(clarifier["red_flag_token"])
            for trigger in clarifier["trigger_tokens"]:
                self.clarifier_triggers.setdefault(trigger, []).append(
                    clarifier["red_flag_token"]
                )

        self.condition_count = len(kb["conditions"])
        self.rule_count = len(rules["rules"])

    def references(self, token):
        return {
            "token": token,
            "scoring_conditions": sorted(
                r["condition_id"] for r in self.scoring.get(token, ())
            ),
            "scoring_condition_count": len(self.scoring.get(token, ())),
            "max_scoring_weight": self.weights.get(token, 0),
            "weight_by_condition": {
                r["condition_id"]: r["weight"] for r in self.scoring.get(token, ())
            },
            "global_red_flag_rules": sorted(self.global_rules.get(token, ())),
            "condition_specific_red_flags": sorted(
                self.condition_red_flags.get(token, ())
            ),
            "raises_clarifiers": sorted(self.clarifier_triggers.get(token, ())),
            "is_a_clarifier_red_flag_token": token in self.clarifier_red_flag_tokens,
            "demographic_modifier_conditions": sorted(
                set(self.demographic_conditions.get(token, ()))
            ),
        }

    def affects_scoring(self, token):
        return bool(self.scoring.get(token))

    def affects_red_flags(self, token):
        """ANY red-flag pathway, not just clarifier-trigger membership.

        Clarifier-trigger membership alone is the weaker test the earlier
        IM-003 note relied on. A token can be a danger sign through a global
        rule or a condition's own red_flags list without ever being a clarifier
        trigger, so all four pathways are checked.
        """
        return bool(
            self.global_rules.get(token)
            or self.condition_red_flags.get(token)
            or self.clarifier_triggers.get(token)
            or token in self.clarifier_red_flag_tokens
        )

    def red_flag_pathways(self, token):
        """Which red-flag pathways a token touches. Empty means none of them."""
        pathways = []
        if self.global_rules.get(token):
            pathways.append("global_rule")
        if self.condition_red_flags.get(token):
            pathways.append("condition_specific_red_flag")
        if self.clarifier_triggers.get(token):
            pathways.append("raises_clarifier")
        if token in self.clarifier_red_flag_tokens:
            pathways.append("is_clarifier_red_flag_token")
        return pathways


def classify_effect(index, token):
    """The impact class of a token entering state. Most severe wins."""
    if index.affects_red_flags(token):
        return "red_flag_affecting_reachability"
    if index.affects_scoring(token):
        return "scoring_affecting_reachability"
    return "no_current_scoring_or_red_flag_reference"
