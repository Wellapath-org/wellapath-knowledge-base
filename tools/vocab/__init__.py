"""WellaPath Symptom Vocabulary 2.0 tooling (I2 / W2).

Standard library only — this repository has no dependency manifest and every
prior generator (`testing/build_case_bank.py`, `facilities/source/build_e5.py`)
is a plain `python3 script.py` with no third-party imports. That convention is
kept deliberately: the artifacts must be reproducible on any machine with a
stock Python 3.9+.
"""

__all__ = [
    "artifact_io",
    "normalize",
    "resolve",
    "schema_check",
]

VOCAB_TOOLING_VERSION = "1.0.0"
