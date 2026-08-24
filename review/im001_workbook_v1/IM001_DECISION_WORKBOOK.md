# IM-001 Product Decision Workbook

**Phase:** I2/W3 Step 10 · **Reviewer:** Ayodele John Oluwaseyi, Co-Founder & CEO, WellaPath · **Authority:** Product only

## Executive summary

**136 Product decisions are pending: 135 wording choices + 1 global option-ordering rule.** Nothing else. Every measured clinical-impact dimension is **zero** — option membership, labels, token mappings, reachable tokens, scoring reachability and red-flag reachability are all identical between the live behaviour and candidate 1.1 — so these are display-wording and display-order choices, reviewable by Product alone *while those dimensions stay zero*.

The 135 wording decisions collapse naturally into **20 question-slot batches**: each slot has exactly one candidate wording contested against several alternatives, so approving a batch approves one wording, once, for one question. Every one of the 135 remains individually listed and individually overridable below — grouping hides nothing. This workbook records **no verdicts**; all reviewer fields are blank.

| Progress | Count |
|---|---:|
| Reviewed | 0 |
| Pending | 136 |
| Deferred | 0 |

## Authorization boundaries

- **Product review only.** No clinical approval is granted, and none is required for the already-measured display-only differences.
- That classification is **conditional**: it holds only while all clinical-impact dimensions stay zero. Any future nonzero membership, token-mapping, scoring or red-flag difference **reopens Clinical review**.
- Approval here does **not** publish or activate candidate 1.1 and does **not** authorize Mobile implementation.
- **IM-003 and IM003-SB-001 are outside this review** — IM-003 remains disabled and the blocker remains open.
- **Mobile PR #76 remains unauthorized to merge.**

## How to record decisions

Use `im001_decision_template_v1.json` beside this file. Per item: `keep_candidate_wording`, `use_alternative_wording` (name it in the rationale), or `defer` — with rationale, name, title and date. A batch approval is shorthand for recording `keep_candidate_wording` on every listed member ID; the expansion is that explicit list. Any member can be overridden individually.

## Review priority by path volume

Batches ordered by how often their wording is seen on captured paths (attribution sums; a path can count under several decisions). **Volume is presentation frequency, not clinical importance.**

| # | Batch | Decisions | Path attributions |
|---:|---|---:|---:|
| 1 | `IM001-BATCH-DURATION-abdominal_cramps` | 15 | 240 |
| 2 | `IM001-BATCH-DURATION-body_pain` | 14 | 217 |
| 3 | `IM001-BATCH-DURATION-chills` | 13 | 195 |
| 4 | `IM001-BATCH-DURATION-cough` | 12 | 174 |
| 5 | `IM001-BATCH-DURATION-dark_urine` | 11 | 154 |
| 6 | `IM001-BATCH-DURATION-dizziness` | 10 | 135 |
| 7 | `IM001-BATCH-DURATION-fatigue` | 9 | 117 |
| 8 | `IM001-BATCH-SEVERITY-abdominal_cramps` | 5 | 105 |
| 9 | `IM001-BATCH-DURATION-fever` | 8 | 100 |
| 10 | `IM001-BATCH-DURATION-headache` | 7 | 84 |
| 11 | `IM001-BATCH-SEVERITY-body_pain` | 4 | 82 |
| 12 | `IM001-BATCH-DURATION-nausea` | 6 | 69 |
| 13 | `IM001-BATCH-SEVERITY-cough` | 3 | 60 |
| 14 | `IM001-BATCH-DURATION-pain` | 5 | 55 |
| 15 | `IM001-BATCH-DURATION-sweating` | 4 | 42 |
| 16 | `IM001-BATCH-SEVERITY-fast_breathing_child` | 2 | 39 |
| 17 | `IM001-BATCH-DURATION-swelling` | 3 | 30 |
| 18 | `IM001-BATCH-DURATION-vomiting` | 2 | 19 |
| 19 | `IM001-BATCH-SEVERITY-headache` | 1 | 19 |
| 20 | `IM001-BATCH-DURATION-watery_stool` | 1 | 9 |

## Batch index

### Duration wording — 15 batches, 120 decisions

| Batch | Slot | Candidate wording | Alternatives | Decisions |
|---|---|---|---:|---:|
| `IM001-BATCH-DURATION-abdominal_cramps` | `abdominal_cramps.duration` | How long have you had these abdominal cramps? | 15 | 15 |
| `IM001-BATCH-DURATION-body_pain` | `body_pain.duration` | How long have you had this body pain? | 14 | 14 |
| `IM001-BATCH-DURATION-chills` | `chills.duration` | How long have you had chills? | 13 | 13 |
| `IM001-BATCH-DURATION-cough` | `cough.duration` | How long have you had this cough? | 12 | 12 |
| `IM001-BATCH-DURATION-dark_urine` | `dark_urine.duration` | How long have you noticed dark urine? | 11 | 11 |
| `IM001-BATCH-DURATION-dizziness` | `dizziness.duration` | How long have you felt dizzy? | 10 | 10 |
| `IM001-BATCH-DURATION-fatigue` | `fatigue.duration` | How long have you felt this fatigue? | 9 | 9 |
| `IM001-BATCH-DURATION-fever` | `fever.duration` | How long have you had this fever? | 8 | 8 |
| `IM001-BATCH-DURATION-headache` | `headache.duration` | How long have you had this headache? | 7 | 7 |
| `IM001-BATCH-DURATION-nausea` | `nausea.duration` | How long have you had nausea? | 6 | 6 |
| `IM001-BATCH-DURATION-pain` | `pain.duration` | How long have you had this pain? | 5 | 5 |
| `IM001-BATCH-DURATION-sweating` | `sweating.duration` | How long have you had excessive sweating? | 4 | 4 |
| `IM001-BATCH-DURATION-swelling` | `swelling.duration` | How long have you had this swelling? | 3 | 3 |
| `IM001-BATCH-DURATION-vomiting` | `vomiting.duration` | How long have you been vomiting? | 2 | 2 |
| `IM001-BATCH-DURATION-watery_stool` | `watery_stool.duration` | How long have you had watery stool? | 1 | 1 |

### Severity wording — 5 batches, 15 decisions

| Batch | Slot | Candidate wording | Alternatives | Decisions |
|---|---|---|---:|---:|
| `IM001-BATCH-SEVERITY-abdominal_cramps` | `abdominal_cramps.severity` | How severe are your abdominal cramps? | 5 | 5 |
| `IM001-BATCH-SEVERITY-body_pain` | `body_pain.severity` | How severe is your body pain? | 4 | 4 |
| `IM001-BATCH-SEVERITY-cough` | `cough.severity` | How severe is your cough? | 3 | 3 |
| `IM001-BATCH-SEVERITY-fast_breathing_child` | `fast_breathing_child.severity` | How severe is the fast breathing? | 2 | 2 |
| `IM001-BATCH-SEVERITY-headache` | `headache.severity` | How severe is your headache? | 1 | 1 |

### Wording pattern families (index only — not an approval unit)

| Pattern | Decisions |
|---|---:|
| How long have you had this {symptom}? | 49 |
| How long have you had {symptom}? | 20 |
| How long have you had these {symptom}? | 15 |
| How long have you noticed {symptom}? | 11 |
| (irregular) How long have you felt dizzy? | 10 |
| How long have you felt this {symptom}? | 9 |
| How severe is your {symptom}? | 8 |
| How severe are your {symptom}? | 5 |
| How long have you had excessive {symptom}? | 4 |
| (irregular) How severe is the fast breathing? | 2 |
| How long have you been {symptom}? | 2 |

## Detailed decisions

Every one of the 135 wording decisions, grouped by batch. Status of all: **PENDING**. No duration or severity question has an option-order difference (all 903 measured order groups are additional-symptoms questions); option order is decided once, globally, in the next section.

### `IM001-BATCH-DURATION-abdominal_cramps`

**Slot** `abdominal_cramps.duration` · **Candidate wording:** How long have you had these abdominal cramps?

| Decision | Alternative wording | Paths | Example path |
|---|---|---:|---|
| `IM001-D001` | How long have you felt this weakness? | 23 | abdominal_cramps, bleeding, weakness |
| `IM001-D003` | How long have you had watery stool? | 22 | abdominal_cramps, bleeding, watery_stool |
| `IM001-D008` | How long have you been vomiting? | 21 | abdominal_cramps, bleeding, vomiting |
| `IM001-D014` | How long have you had this swelling? | 20 | abdominal_cramps, bleeding, swelling |
| `IM001-D022` | How long have you had excessive sweating? | 19 | abdominal_cramps, bleeding, sweating |
| `IM001-D033` | How long have you had this pain? | 18 | abdominal_cramps, bleeding, pain |
| `IM001-D040` | How long have you had nausea? | 17 | abdominal_cramps, bleeding, nausea |
| `IM001-D047` | How long have you had this headache? | 16 | abdominal_cramps, bleeding, headache |
| `IM001-D055` | How long have you had this fever? | 15 | abdominal_cramps, bleeding, fever |
| `IM001-D065` | How long have you felt this fatigue? | 14 | abdominal_cramps, bleeding, fatigue |
| `IM001-D075` | How long have you felt dizzy? | 13 | abdominal_cramps, bleeding, dizziness |
| `IM001-D087` | How long have you noticed dark urine? | 12 | abdominal_cramps, bleeding, dark_urine |
| `IM001-D099` | How long have you had this cough? | 11 | abdominal_cramps, bleeding, cough |
| `IM001-D113` | How long have you had chills? | 10 | abdominal_cramps, bleeding, chills |
| `IM001-D127` | How long have you had this body pain? | 9 | abdominal_cramps, bleeding, body_pain |

### `IM001-BATCH-SEVERITY-abdominal_cramps`

**Slot** `abdominal_cramps.severity` · **Candidate wording:** How severe are your abdominal cramps?

| Decision | Alternative wording | Paths | Example path |
|---|---|---:|---|
| `IM001-D002` | How severe is this pain? | 23 | abdominal_cramps, bleeding, pain |
| `IM001-D005` | How severe is your headache? | 22 | abdominal_cramps, bleeding, headache |
| `IM001-D010` | How severe is the fast breathing? | 21 | abdominal_cramps, bleeding, fast_breathing_child |
| `IM001-D017` | How severe is your cough? | 20 | abdominal_cramps, bleeding, cough |
| `IM001-D026` | How severe is your body pain? | 19 | abdominal_cramps, bleeding, body_pain |

### `IM001-BATCH-DURATION-body_pain`

**Slot** `body_pain.duration` · **Candidate wording:** How long have you had this body pain?

| Decision | Alternative wording | Paths | Example path |
|---|---|---:|---|
| `IM001-D004` | How long have you felt this weakness? | 22 | bleeding, body_pain, weakness |
| `IM001-D009` | How long have you had watery stool? | 21 | bleeding, body_pain, watery_stool |
| `IM001-D015` | How long have you been vomiting? | 20 | bleeding, body_pain, vomiting |
| `IM001-D023` | How long have you had this swelling? | 19 | bleeding, body_pain, swelling |
| `IM001-D034` | How long have you had excessive sweating? | 18 | bleeding, body_pain, sweating |
| `IM001-D041` | How long have you had this pain? | 17 | bleeding, body_pain, pain |
| `IM001-D048` | How long have you had nausea? | 16 | bleeding, body_pain, nausea |
| `IM001-D056` | How long have you had this headache? | 15 | bleeding, body_pain, headache |
| `IM001-D066` | How long have you had this fever? | 14 | bleeding, body_pain, fever |
| `IM001-D076` | How long have you felt this fatigue? | 13 | bleeding, body_pain, fatigue |
| `IM001-D088` | How long have you felt dizzy? | 12 | bleeding, body_pain, dizziness |
| `IM001-D100` | How long have you noticed dark urine? | 11 | bleeding, body_pain, dark_urine |
| `IM001-D114` | How long have you had this cough? | 10 | bleeding, body_pain, cough |
| `IM001-D128` | How long have you had chills? | 9 | bleeding, body_pain, chills |

### `IM001-BATCH-SEVERITY-body_pain`

**Slot** `body_pain.severity` · **Candidate wording:** How severe is your body pain?

| Decision | Alternative wording | Paths | Example path |
|---|---|---:|---|
| `IM001-D006` | How severe is this pain? | 22 | bleeding, body_pain, pain |
| `IM001-D011` | How severe is your headache? | 21 | bleeding, body_pain, headache |
| `IM001-D019` | How severe is the fast breathing? | 20 | bleeding, body_pain, fast_breathing_child |
| `IM001-D028` | How severe is your cough? | 19 | bleeding, body_pain, cough |

### `IM001-BATCH-DURATION-chills`

**Slot** `chills.duration` · **Candidate wording:** How long have you had chills?

| Decision | Alternative wording | Paths | Example path |
|---|---|---:|---|
| `IM001-D007` | How long have you felt this weakness? | 21 | bleeding, chills, weakness |
| `IM001-D013` | How long have you had watery stool? | 20 | bleeding, chills, watery_stool |
| `IM001-D021` | How long have you been vomiting? | 19 | bleeding, chills, vomiting |
| `IM001-D032` | How long have you had this swelling? | 18 | bleeding, chills, swelling |
| `IM001-D039` | How long have you had excessive sweating? | 17 | bleeding, chills, sweating |
| `IM001-D046` | How long have you had this pain? | 16 | bleeding, chills, pain |
| `IM001-D054` | How long have you had nausea? | 15 | bleeding, chills, nausea |
| `IM001-D063` | How long have you had this headache? | 14 | bleeding, chills, headache |
| `IM001-D073` | How long have you had this fever? | 13 | bleeding, chills, fever |
| `IM001-D084` | How long have you felt this fatigue? | 12 | bleeding, chills, fatigue |
| `IM001-D096` | How long have you felt dizzy? | 11 | bleeding, chills, dizziness |
| `IM001-D110` | How long have you noticed dark urine? | 10 | bleeding, chills, dark_urine |
| `IM001-D124` | How long have you had this cough? | 9 | bleeding, chills, cough |

### `IM001-BATCH-DURATION-cough`

**Slot** `cough.duration` · **Candidate wording:** How long have you had this cough?

| Decision | Alternative wording | Paths | Example path |
|---|---|---:|---|
| `IM001-D016` | How long have you felt this weakness? | 20 | bleeding, cough, weakness |
| `IM001-D024` | How long have you had watery stool? | 19 | bleeding, cough, watery_stool |
| `IM001-D035` | How long have you been vomiting? | 18 | bleeding, cough, vomiting |
| `IM001-D042` | How long have you had this swelling? | 17 | bleeding, cough, swelling |
| `IM001-D049` | How long have you had excessive sweating? | 16 | bleeding, cough, sweating |
| `IM001-D057` | How long have you had this pain? | 15 | bleeding, cough, pain |
| `IM001-D067` | How long have you had nausea? | 14 | bleeding, cough, nausea |
| `IM001-D077` | How long have you had this headache? | 13 | bleeding, cough, headache |
| `IM001-D089` | How long have you had this fever? | 12 | bleeding, cough, fever |
| `IM001-D101` | How long have you felt this fatigue? | 11 | bleeding, cough, fatigue |
| `IM001-D115` | How long have you felt dizzy? | 10 | bleeding, cough, dizziness |
| `IM001-D129` | How long have you noticed dark urine? | 9 | bleeding, cough, dark_urine |

### `IM001-BATCH-SEVERITY-cough`

**Slot** `cough.severity` · **Candidate wording:** How severe is your cough?

| Decision | Alternative wording | Paths | Example path |
|---|---|---:|---|
| `IM001-D012` | How severe is this pain? | 21 | bleeding, cough, pain |
| `IM001-D020` | How severe is your headache? | 20 | bleeding, cough, headache |
| `IM001-D029` | How severe is the fast breathing? | 19 | bleeding, cough, fast_breathing_child |

### `IM001-BATCH-DURATION-dark_urine`

**Slot** `dark_urine.duration` · **Candidate wording:** How long have you noticed dark urine?

| Decision | Alternative wording | Paths | Example path |
|---|---|---:|---|
| `IM001-D025` | How long have you felt this weakness? | 19 | bleeding, dark_urine, weakness |
| `IM001-D036` | How long have you had watery stool? | 18 | bleeding, dark_urine, watery_stool |
| `IM001-D043` | How long have you been vomiting? | 17 | bleeding, dark_urine, vomiting |
| `IM001-D051` | How long have you had this swelling? | 16 | bleeding, dark_urine, swelling |
| `IM001-D060` | How long have you had excessive sweating? | 15 | bleeding, dark_urine, sweating |
| `IM001-D070` | How long have you had this pain? | 14 | bleeding, dark_urine, pain |
| `IM001-D081` | How long have you had nausea? | 13 | bleeding, dark_urine, nausea |
| `IM001-D093` | How long have you had this headache? | 12 | bleeding, dark_urine, headache |
| `IM001-D106` | How long have you had this fever? | 11 | bleeding, dark_urine, fever |
| `IM001-D120` | How long have you felt this fatigue? | 10 | bleeding, dark_urine, fatigue |
| `IM001-D135` | How long have you felt dizzy? | 9 | bleeding, dark_urine, dizziness |

### `IM001-BATCH-DURATION-dizziness`

**Slot** `dizziness.duration` · **Candidate wording:** How long have you felt dizzy?

| Decision | Alternative wording | Paths | Example path |
|---|---|---:|---|
| `IM001-D031` | How long have you felt this weakness? | 18 | bleeding, dizziness, weakness |
| `IM001-D037` | How long have you had watery stool? | 17 | bleeding, dizziness, watery_stool |
| `IM001-D044` | How long have you been vomiting? | 16 | bleeding, dizziness, vomiting |
| `IM001-D052` | How long have you had this swelling? | 15 | bleeding, dizziness, swelling |
| `IM001-D061` | How long have you had excessive sweating? | 14 | bleeding, dizziness, sweating |
| `IM001-D071` | How long have you had this pain? | 13 | bleeding, dizziness, pain |
| `IM001-D082` | How long have you had nausea? | 12 | bleeding, dizziness, nausea |
| `IM001-D094` | How long have you had this headache? | 11 | bleeding, dizziness, headache |
| `IM001-D108` | How long have you had this fever? | 10 | bleeding, dizziness, fever |
| `IM001-D122` | How long have you felt this fatigue? | 9 | bleeding, dizziness, fatigue |

### `IM001-BATCH-SEVERITY-fast_breathing_child`

**Slot** `fast_breathing_child.severity` · **Candidate wording:** How severe is the fast breathing?

| Decision | Alternative wording | Paths | Example path |
|---|---|---:|---|
| `IM001-D018` | How severe is this pain? | 20 | bleeding, fast_breathing_child, pain |
| `IM001-D027` | How severe is your headache? | 19 | bleeding, fast_breathing_child, headache |

### `IM001-BATCH-DURATION-fatigue`

**Slot** `fatigue.duration` · **Candidate wording:** How long have you felt this fatigue?

| Decision | Alternative wording | Paths | Example path |
|---|---|---:|---|
| `IM001-D038` | How long have you felt this weakness? | 17 | bleeding, fatigue, weakness |
| `IM001-D045` | How long have you had watery stool? | 16 | bleeding, fatigue, watery_stool |
| `IM001-D053` | How long have you been vomiting? | 15 | bleeding, fatigue, vomiting |
| `IM001-D062` | How long have you had this swelling? | 14 | bleeding, fatigue, swelling |
| `IM001-D072` | How long have you had excessive sweating? | 13 | bleeding, fatigue, sweating |
| `IM001-D083` | How long have you had this pain? | 12 | bleeding, fatigue, pain |
| `IM001-D095` | How long have you had nausea? | 11 | bleeding, fatigue, nausea |
| `IM001-D109` | How long have you had this headache? | 10 | bleeding, fatigue, headache |
| `IM001-D123` | How long have you had this fever? | 9 | bleeding, fatigue, fever |

### `IM001-BATCH-DURATION-fever`

**Slot** `fever.duration` · **Candidate wording:** How long have you had this fever?

| Decision | Alternative wording | Paths | Example path |
|---|---|---:|---|
| `IM001-D050` | How long have you felt this weakness? | 16 | bleeding, fever, weakness |
| `IM001-D058` | How long have you had watery stool? | 15 | bleeding, fever, watery_stool |
| `IM001-D068` | How long have you been vomiting? | 14 | bleeding, fever, vomiting |
| `IM001-D078` | How long have you had this swelling? | 13 | bleeding, fever, swelling |
| `IM001-D090` | How long have you had excessive sweating? | 12 | bleeding, fever, sweating |
| `IM001-D102` | How long have you had this pain? | 11 | bleeding, fever, pain |
| `IM001-D116` | How long have you had nausea? | 10 | bleeding, fever, nausea |
| `IM001-D130` | How long have you had this headache? | 9 | bleeding, fever, headache |

### `IM001-BATCH-DURATION-headache`

**Slot** `headache.duration` · **Candidate wording:** How long have you had this headache?

| Decision | Alternative wording | Paths | Example path |
|---|---|---:|---|
| `IM001-D059` | How long have you felt this weakness? | 15 | bleeding, headache, weakness |
| `IM001-D069` | How long have you had watery stool? | 14 | bleeding, headache, watery_stool |
| `IM001-D079` | How long have you been vomiting? | 13 | bleeding, headache, vomiting |
| `IM001-D091` | How long have you had this swelling? | 12 | bleeding, headache, swelling |
| `IM001-D103` | How long have you had excessive sweating? | 11 | bleeding, headache, sweating |
| `IM001-D117` | How long have you had this pain? | 10 | bleeding, headache, pain |
| `IM001-D131` | How long have you had nausea? | 9 | bleeding, headache, nausea |

### `IM001-BATCH-SEVERITY-headache`

**Slot** `headache.severity` · **Candidate wording:** How severe is your headache?

| Decision | Alternative wording | Paths | Example path |
|---|---|---:|---|
| `IM001-D030` | How severe is this pain? | 19 | bleeding, headache, pain |

### `IM001-BATCH-DURATION-nausea`

**Slot** `nausea.duration` · **Candidate wording:** How long have you had nausea?

| Decision | Alternative wording | Paths | Example path |
|---|---|---:|---|
| `IM001-D064` | How long have you felt this weakness? | 14 | bleeding, nausea, weakness |
| `IM001-D074` | How long have you had watery stool? | 13 | bleeding, nausea, watery_stool |
| `IM001-D086` | How long have you been vomiting? | 12 | bleeding, nausea, vomiting |
| `IM001-D098` | How long have you had this swelling? | 11 | bleeding, nausea, swelling |
| `IM001-D112` | How long have you had excessive sweating? | 10 | bleeding, nausea, sweating |
| `IM001-D126` | How long have you had this pain? | 9 | bleeding, nausea, pain |

### `IM001-BATCH-DURATION-pain`

**Slot** `pain.duration` · **Candidate wording:** How long have you had this pain?

| Decision | Alternative wording | Paths | Example path |
|---|---|---:|---|
| `IM001-D080` | How long have you felt this weakness? | 13 | bleeding, pain, weakness |
| `IM001-D092` | How long have you had watery stool? | 12 | bleeding, pain, watery_stool |
| `IM001-D104` | How long have you been vomiting? | 11 | bleeding, pain, vomiting |
| `IM001-D118` | How long have you had this swelling? | 10 | bleeding, pain, swelling |
| `IM001-D132` | How long have you had excessive sweating? | 9 | bleeding, pain, sweating |

### `IM001-BATCH-DURATION-sweating`

**Slot** `sweating.duration` · **Candidate wording:** How long have you had excessive sweating?

| Decision | Alternative wording | Paths | Example path |
|---|---|---:|---|
| `IM001-D085` | How long have you felt this weakness? | 12 | bleeding, sweating, weakness |
| `IM001-D097` | How long have you had watery stool? | 11 | bleeding, sweating, watery_stool |
| `IM001-D111` | How long have you been vomiting? | 10 | bleeding, sweating, vomiting |
| `IM001-D125` | How long have you had this swelling? | 9 | bleeding, sweating, swelling |

### `IM001-BATCH-DURATION-swelling`

**Slot** `swelling.duration` · **Candidate wording:** How long have you had this swelling?

| Decision | Alternative wording | Paths | Example path |
|---|---|---:|---|
| `IM001-D105` | How long have you felt this weakness? | 11 | bleeding, swelling, weakness |
| `IM001-D119` | How long have you had watery stool? | 10 | bleeding, swelling, watery_stool |
| `IM001-D133` | How long have you been vomiting? | 9 | bleeding, swelling, vomiting |

### `IM001-BATCH-DURATION-vomiting`

**Slot** `vomiting.duration` · **Candidate wording:** How long have you been vomiting?

| Decision | Alternative wording | Paths | Example path |
|---|---|---:|---|
| `IM001-D107` | How long have you felt this weakness? | 10 | bleeding, vomiting, weakness |
| `IM001-D121` | How long have you had watery stool? | 9 | bleeding, vomiting, watery_stool |

### `IM001-BATCH-DURATION-watery_stool`

**Slot** `watery_stool.duration` · **Candidate wording:** How long have you had watery stool?

| Decision | Alternative wording | Paths | Example path |
|---|---|---:|---|
| `IM001-D134` | How long have you felt this weakness? | 9 | bleeding, watery_stool, weakness |

## The global ordering decision — `IM001-ORD-GLOBAL-001`

**In plain terms:** Today, the order of answer options in the grouped additional-symptoms question can depend on the order the user tapped their symptoms. The same symptoms tapped in a different order can show the same options in a different sequence. Candidate 1.1 always shows those options in one declared, deterministic order.

What is unchanged either way:

- option membership (which options appear): unchanged
- option labels: unchanged
- option-to-token mappings: unchanged
- reachable scoring tokens: unchanged
- reachable red-flag tokens: unchanged

**This decision affects display order only** — 903 option groups on 1872 captured paths. Approving the ordering rule does not approve any of the 135 wording choices and does not activate or publish candidate 1.1.

Choose exactly one (none is pre-selected):

- **ORD-A** — Approve candidate 1.1 deterministic option ordering.
- **ORD-B** — Retain current selection-order-dependent option ordering.
- **ORD-C** — Request a different deterministic ordering rule.

Status: **PENDING**.

## Evidence bindings

| Artifact | SHA256 |
|---|---|
| `reports/im001_product_review_v1_1.json` | `4788fee0b6bcf764c22add101d9e4ea806c70a4119c73e6b16b2ebdd2d4324c2` |
| `reports/im001_option_order_decision_v1.json` | `6adbfcc4e2a6983b4a07ff6e04298444061c9343e8da9a86b433b6e6f505f1b1` |
| `reports/im001_option_order_evidence_v1.json` | `fd4391a21c5db85c4881c2b5d238f968def58b999d6caa28580d28830e181939` |

The workbook is regenerated deterministically from these artifacts by `tools/build_im001_workbook.py`; drift fails `--check` and validation.

