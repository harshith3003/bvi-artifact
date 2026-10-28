"""Route rules, codec-threshold policies and audio evidence.

ROUTE RULES
  positional (BVI-0): records from registered carriers are ordered by their DECLARED position and checked only
      for number transitions between consecutive records. Neighbour links are not checked, so an off-path
      registered carrier can insert a record at an unused position ("record laundering").
  linked (BVI-R): starting from the record of the recipient's own terminating carrier, walk backwards through
      records whose prev/next links are reciprocated and whose positions are contiguous. Only that linked chain
      is evidence. Records outside it are ignored, so unlinked or off-path records can neither launder a rewrite
      nor block an honest call. The chain is COMPLETE if it reaches the origin carrier (position 1, prev = ORIGIN).
  none (BVI-B): carrier records are not used in the decision.

CODEC POLICIES (threshold theta on the call's maximum window BER)
  carrier (BVI-0):        worst threshold over the sender's declared codec and every carrier-reported codec.
  chain (BVI-R):          worst threshold over the sender's codec and the codecs in a COMPLETE valid chain ending at
                          the recipient's carrier; otherwise the pooled threshold.
  endpoint_strict (B):    sender's signed codec and the recipient's own received codec. Equal -> that codec's
                          threshold. Different -> transcoding path unknown -> audio is "uncertain" (not verified).
  endpoint_lenient (B'):  as strict, but when the endpoints differ the pooled threshold is used.
"""
import csv, json, random
from dataclasses import dataclass

ORIGIN, RECIPIENT = "ORIGIN", "RECIPIENT"

@dataclass
class Record:
    writer: str; position: int; in_num: str; out_num: str; codec: str
    prev_id: str; next_id: str; translator: bool = False

def _translation_ok(r):
    return r.in_num == r.out_num or r.translator

def positional_rule(records, presented, path_len):
    """BVI-0. Returns (status, used_records). status: pass, bot (no evidence), fail."""
    if len(records) < 2:
        return ("bot", records)
    rs = sorted(records, key=lambda r: r.position)
    for r in rs:
        if not _translation_ok(r):
            return ("fail", rs)
    for a, b in zip(rs, rs[1:]):
        if a.position == b.position and (a.in_num != b.in_num or a.out_num != b.out_num):
            return ("fail", rs)
        if a.position != b.position and a.out_num != b.in_num:
            return ("fail", rs)
    last = rs[-1]
    if last.position == path_len and last.out_num != presented:
        return ("fail", rs)
    return ("pass", rs)

def linked_rule(records, terminating_id, presented, signed_calling):
    """BVI-R. Returns (status, admissible_records, complete).

    1. Two records are LINKED when each names the other as neighbour (a.next == b.writer, b.prev == a.writer)
       and their positions are consecutive. Maximal runs of linked records form segments.
    2. Admissible evidence: segments of two or more linked records, plus the record of the recipient's own
       terminating carrier (the recipient knows its carrier, so that record anchors the chain). A record no
       neighbour confirms (an isolated or off-path record) is ignored, so it can neither launder a rewrite
       nor block an honest call.
    3. Admissible segments must not overlap or claim a position that an admissible neighbour attributes to a
       different carrier; a conflict means someone lied about the route -> fail.
    4. Numbers are checked within segments and ACROSS GAPS between consecutive segments, so a rewrite
       straddled by linked evidence is still caught. Declared changes are allowed only for translators.
    5. COMPLETE = a single admissible segment from position 1 (prev = ORIGIN) to the terminating carrier; only
       then are carrier codec declarations used (see threshold_for)."""
    by = {}
    for r in records:
        by.setdefault(r.writer, r)
    rs = list(by.values())
    succ, pred = {}, {}
    for a in rs:
        b = by.get(a.next_id)
        if b is not None and b.prev_id == a.writer and b.position == a.position + 1:
            succ[a.writer], pred[b.writer] = b, a
    segs = []
    for r in rs:
        if r.writer in pred: continue
        seg, cur = [r], r
        while cur.writer in succ:
            cur = succ[cur.writer]; seg.append(cur)
        if len(seg) >= 2 or r.writer == terminating_id:
            segs.append(seg)
    if not segs:
        return ("bot", [], False)
    segs.sort(key=lambda s: s[0].position)
    adm = [r for s in segs for r in s]
    pos_writer = {}
    for r in adm:
        if r.position in pos_writer and pos_writer[r.position] != r.writer:
            return ("fail", adm, False)                      # two admissible records claim one position
        pos_writer[r.position] = r.writer
    for r in adm:                                            # neighbour claims must agree with admissible records
        for p, claim in ((r.position - 1, r.prev_id), (r.position + 1, r.next_id)):
            if p in pos_writer and claim not in (ORIGIN, RECIPIENT) and pos_writer[p] != claim:
                return ("fail", adm, False)
    for r in adm:
        if not _translation_ok(r):
            return ("fail", adm, False)
    for s in segs:
        for a, b in zip(s, s[1:]):
            if a.out_num != b.in_num:
                return ("fail", adm, False)
    for s1, s2 in zip(segs, segs[1:]):                       # across gaps
        if s1[-1].out_num != s2[0].in_num:
            return ("fail", adm, False)
    t = by.get(terminating_id)
    if t is not None and t in adm and t.out_num != presented:
        return ("fail", adm, False)
    complete = (len(segs) == 1 and segs[0][0].position == 1 and segs[0][0].prev_id == ORIGIN
                and segs[0][-1].writer == terminating_id)
    if signed_calling is not None and segs[0][0].position == 1 and segs[0][0].prev_id == ORIGIN \
            and segs[0][0].in_num != signed_calling:
        return ("fail", adm, complete)
    if len(adm) < 2:
        return ("bot", adm, complete)
    return ("pass", adm, complete)

# ------------------------------------------------------------------ thresholds
DEFAULT_THRESHOLDS = {   # held-out dev-clean, pause rule on (thesis Table 15); replaced by thresholds.json when given
    "g711u": 0.215, "g711a": 0.212, "opus16": 0.316, "amr122": 0.404, "amr122_g711u": 0.394, "amr475": 0.500,
    "pooled": 0.455}

def load_thresholds(path=None):
    th = dict(DEFAULT_THRESHOLDS)
    if path:
        js = json.load(open(path))
        flat = js.get("pause_on", js) if isinstance(js, dict) else {}
        for k, v in flat.items():
            if isinstance(v, (int, float)): th[k] = float(v)
    return th

def chain_codec_key(codecs):
    """Map a set of codecs seen on a path to the calibrated codec key with the worst (largest) threshold."""
    cs = set(codecs)
    if "amr475" in cs: return "amr475"
    if "amr122" in cs and ({"g711u", "g711a"} & cs): return "amr122_g711u"
    if "amr122" in cs: return "amr122"
    if "opus16" in cs: return "opus16"
    if "g711a" in cs: return "g711a"
    return "g711u"

def threshold_for(policy, th, sender_codec, reported_codecs, chain_codecs, chain_complete, received_codec):
    """Returns (theta or None, label). None means the policy refuses to verify the audio (uncertain)."""
    if policy == "carrier":
        k = chain_codec_key([sender_codec] + list(reported_codecs)); return th[k], k
    if policy == "chain":
        if chain_complete:
            k = chain_codec_key([sender_codec] + list(chain_codecs)); return th[k], k
        return th["pooled"], "pooled"
    if policy in ("endpoint_strict", "endpoint_lenient"):
        if sender_codec == received_codec:
            return th[sender_codec], sender_codec
        if policy == "endpoint_strict":
            return None, "uncertain"
        return th["pooled"], "pooled"
    raise ValueError(policy)

# ------------------------------------------------------------------ audio evidence
class EmpiricalOracle:
    """Draws per-call maximum window BER from REAL measured samples.
    CSV columns: codec, kind, max_ber  (kind: honest, splice_0.5, splice_1, splice_2, splice_3, splice_5,
    full_nat, full_asv, pause_3, and later semantic_* from item 1)."""
    label = "EMPIRICAL"
    def __init__(self, path, rng):
        self.rng, self.s = rng, {}
        for row in csv.DictReader(open(path)):
            if row.get("split", "test") != "test":
                continue                       # held-out evaluation: calibration speakers never drawn
            self.s.setdefault((row["codec"], row["kind"]), []).append(float(row["max_ber"]))
        if not self.s: raise SystemExit("no BER samples found in " + path)
    def sample(self, codec, kind):
        xs = self.s.get((codec, kind))
        if not xs: raise KeyError(f"no samples for codec={codec} kind={kind}")
        return self.rng.choice(xs)

class SelfTestOracle:
    """SYNTHETIC distributions, only to exercise the pipeline. Never report these numbers."""
    label = "SELFTEST (synthetic, not results)"
    MEAN = {"g711u": .06, "g711a": .06, "opus16": .17, "amr122": .26, "amr122_g711u": .25, "amr475": .35}
    def __init__(self, rng): self.rng = rng
    def sample(self, codec, kind):
        base = self.MEAN[codec]; r = self.rng
        if kind == "honest": return min(1, max(0, r.gauss(base + .07, .035)))
        sev = {"splice_0.5": .12, "splice_1": .2, "splice_2": .32, "splice_3": .38, "splice_5": .42,
               "full_nat": .5, "full_asv": .5, "pause_3": .6}.get(kind, .3)
        return min(1, max(0, r.gauss(max(base + .07, sev + base * .3), .05)))
