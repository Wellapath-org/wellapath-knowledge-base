"""Adaptive Question Engine 2.0 tooling (I2 / W3 Step 1).

Standard library only, matching every other generator in this repository.

The current question flow is **not** a versioned artifact. It is Dart source in
the mobile repository. This package reads vendored copies of that source
(`baseline/questions_v1/*.vendored.dart`), extracts the question definitions
deterministically, and projects them into a candidate artifact — without
changing a single question, answer meaning or token effect.
"""

__all__ = ["dartparse", "conditions", "graph"]

QFLOW_TOOLING_VERSION = "1.0.0"

# Mobile develop commit the vendored sources were taken from.
MOBILE_SOURCE_COMMIT = "a269168e2ed9b3b1c0453797dce5c9f303366854"
MOBILE_SOURCE_REPO = "Wellapath-org/wellapath-mobile"
