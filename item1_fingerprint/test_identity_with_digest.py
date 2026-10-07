"""
Checks that fingerprint.py produces exactly the same bits as the original
experiments/digest/digest.py (default DigestParams), so both papers describe one digest.
Run from round4/item1_fingerprint inside the bvi project:  python3 test_identity_with_digest.py
"""
import os, sys
import numpy as np
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.environ.get("BVI_DIGEST_DIR", os.path.join(here, "..", "experiments", "digest")))
import digest
import fingerprint as fp

rng = np.random.default_rng(20260909)
for t in range(20):
    n = int(rng.integers(8000, 8000 * 30))
    x = rng.normal(0, 0.1, n) * (0.2 + np.abs(np.sin(np.linspace(0, rng.uniform(5, 60), n))))
    ref = digest.digest_bits(x, digest.DigestParams()).astype(bool)
    mine, _ = fp.analyse(x)
    assert np.array_equal(ref, mine[1:]), f"mismatch on signal {t}"
print(f"PASS: fingerprint.py == digest.py on 20 random signals; {digest.DigestParams().label()}")
