"""Configurations, verifier and scenarios.

Each configuration is BVI-R with at most ONE mechanism changed (except the three reference versions).
Every configuration sees identical calls and identical audio draws (common random numbers), so differences
come only from the mechanism that was changed.
"""
import os, random, time
from dataclasses import dataclass, field, replace
from .protocol import (Org, recipient_ephemeral, make_key_message, verify_key_message, make_stream,
                       verify_stream, H, canonical)
from .route_policy_audio import (Record, ORIGIN, RECIPIENT, positional_rule, linked_rule, threshold_for,
                                 chain_codec_key)

# ------------------------------------------------------------------ configurations
@dataclass(frozen=True)
class Config:
    name: str
    km: str            # v1: numbers not bound | v2: calling and called numbers bound
    route: str         # positional | linked | none
    stream: str        # v1 | v2 | v2_noterm
    codec: str         # carrier | chain | endpoint_strict | endpoint_lenient
    route_decides: bool = True
    note: str = ""

BVI_R = Config("BVI-R", "v2", "linked", "v2", "chain", True, "fully corrected reference")
CONFIGS = [
    Config("BVI-0", "v1", "positional", "v1", "carrier", True, "original implementation"),
    BVI_R,
    Config("BVI-B (strict)", "v2", "none", "v2", "endpoint_strict", False, "no carrier records; strict audio"),
    Config("BVI-B (lenient)", "v2", "none", "v2", "endpoint_lenient", False, "optional: lenient audio policy"),
    replace(BVI_R, name="R - number binding", km="v1", note="ablation 1: relay vulnerability"),
    replace(BVI_R, name="R - linked chain", route="positional", codec="carrier", note="ablation 2: original carrier-record rule"),
    replace(BVI_R, name="R - auth. termination", stream="v2_noterm", note="ablation 3: truncation / premature verification"),
    replace(BVI_R, name="R + endpoint strict", codec="endpoint_strict", note="ablation 4: security vs availability"),
]

# ------------------------------------------------------------------ numbers
ORG_A, ORG_A2 = "+61312345678", "+61312340000"      # organisation's two authorised numbers
VICTIM, MULE = "+61400000001", "+61400000999"       # recipient, attacker-controlled number
def national(n): return "0" + n[3:] if n.startswith("+61") else n

# ------------------------------------------------------------------ calls
@dataclass
class Call:
    scenario: str; honest: bool
    hops: list                      # [{"id", "beh", "codec"}]; beh: honest|silent|rewrite|collude|translate|codec_lie
    sender_codec: str = "g711u"
    offpath: list = field(default_factory=list)
    audio_kind: str = "honest"      # attack audio inside the evaluated part of the call
    strip: bool = False
    truncate_tail: int = 0
    bye_at: int = None
    late_attack: bool = False
    premature_at: int = None        # recipient asks for a verdict at this second
    relay: bool = False
    duration: int = 30

    def build(self):
        """Derive presented number, carrier records and the true media codec path."""
        cur_num, cur_codec, true_codecs = ORG_A, self.sender_codec, [self.sender_codec]
        recs, h = [], len(self.hops)
        for j, hop in enumerate(self.hops, start=1):
            prev = ORIGIN if j == 1 else self.hops[j - 2]["id"]
            nxt = RECIPIENT if j == h else self.hops[j]["id"]
            inn, beh = cur_num, hop["beh"]
            if beh in ("rewrite", "collude"):
                cur_num = ORG_A2
            elif beh == "translate":
                cur_num = national(cur_num)
            if hop.get("codec"):
                cur_codec = hop["codec"]; true_codecs.append(cur_codec)
            if beh in ("honest", "translate", "codec_lie"):
                recs.append(Record(hop["id"], j, inn, cur_num, "amr475" if beh == "codec_lie" else cur_codec,
                                   prev, nxt, translator=(beh == "translate")))
            elif beh == "collude":
                recs.append(Record(hop["id"], j, ORG_A2, ORG_A2, cur_codec, prev, nxt))
        self.presented, self.records = cur_num, recs + list(self.offpath)
        self.received_codec = cur_codec
        self.true_codec_key = chain_codec_key(true_codecs)
        self.terminating = self.hops[-1]["id"]
        return self

def _hops(h, beh="honest"):
    return [{"id": f"C{j}", "beh": beh, "codec": None} for j in range(1, h + 1)]

SEMANTIC = [("semantic_neg_delete", "X15 negation deleted (background fill)"),
            ("semantic_neg_insert", "X16 negation inserted"),
            ("semantic_num_swap", "X17 number swapped"),
            ("semantic_word_swap", "X18 word swapped (name / instruction proxy)")]

def scenarios(rng, semantic_kinds=()):
    """Returns {name: (honest, factory(rng) -> Call)}. Factories draw path details from rng.
    semantic_kinds: semantic-edit kinds present in the BER samples; each adds an attack scenario on a
    landline path, plus the same edit combined with an on-path codec lie (BVI-R's residual weakness)."""
    S = {}
    def add(name, honest, f): S[name] = (honest, f)

    def honest_full(r, codec="g711u"):
        return Call("", True, _hops(r.randint(4, 6)), sender_codec=codec)
    add("H1 honest, landline, all carriers attest", True, lambda r: honest_full(r))
    def partial(r):
        c = Call("", True, _hops(r.randint(4, 6)))
        for hp in c.hops: hp["beh"] = "honest" if r.random() < .5 else "silent"
        return c
    add("H2 honest, landline, half the carriers attest", True, partial)
    def mobile(r, silent_transcoder=False):
        c = Call("", True, _hops(r.randint(4, 6)), sender_codec="amr122")
        k = r.randint(2, len(c.hops) - 1); c.hops[k - 1]["codec"] = "g711u"
        if silent_transcoder: c.hops[k - 1]["beh"] = "silent"
        return c
    add("H3 honest, mobile to landline, transcoder attests", True, lambda r: mobile(r))
    add("H4 honest, mobile to landline, transcoder silent", True, lambda r: mobile(r, True))
    add("H5 honest, VoIP (Opus) end to end", True, lambda r: honest_full(r, "opus16"))
    def translation(r):
        c = honest_full(r); c.hops[r.randint(1, len(c.hops) - 2)]["beh"] = "translate"; return c
    add("H6 honest, declared number translation", True, translation)
    def hidden(r):
        c = honest_full(r); k = r.randint(2, len(c.hops) - 2)
        c.hops[k - 1].update(beh="silent", codec="amr122"); c.hops[k].update(beh="silent", codec="g711u"); return c
    add("H7 honest, hidden AMR leg between landline endpoints", True, hidden)
    def false_records(r):
        c = honest_full(r); j = r.randint(2, len(c.hops) - 1)
        c.offpath = [Record("OFF1", j, ORG_A, ORG_A2, "g711u", f"C{j-1}", f"C{j+1}")]   # contradicts the honest record
        return c
    add("H8 honest call, off-path carrier writes false records", True, false_records)

    def relay(r):
        c = honest_full(r); c.relay = True; return c
    add("X1 relay: session meant for another number", False, relay)
    def rewrite(r, sparse=False):
        c = honest_full(r); k = r.randint(2, len(c.hops) - 1); c.hops[k - 1]["beh"] = "rewrite"
        if sparse:
            for j, hp in enumerate(c.hops):
                if j != k - 1: hp["beh"] = "honest" if r.random() < .5 else "silent"
        return c
    add("X2 caller ID rewritten, neighbours attest", False, lambda r: rewrite(r))
    add("X3 caller ID rewritten, half the carriers attest", False, lambda r: rewrite(r, True))
    add("X4 full carrier collusion", False, lambda r: Call("", False, _hops(r.randint(4, 6), "collude")))
    def launder(r):
        c = honest_full(r); k = r.randint(2, len(c.hops) - 1); c.hops[k - 1]["beh"] = "rewrite"
        c.offpath = [Record("OFF1", k, ORG_A, ORG_A2, "g711u", f"C{k-1}", f"C{k+1}", translator=True)]
        return c
    add("X5 off-path record laundering", False, launder)
    def codec_off(r):
        c = honest_full(r); j = r.randint(1, len(c.hops))
        prev = ORIGIN if j == 1 else f"C{j-1}"; nxt = RECIPIENT if j == len(c.hops) else f"C{j+1}"
        c.offpath = [Record("OFF1", j, ORG_A, ORG_A, "amr475", prev, nxt)]
        c.audio_kind = "splice_1"; return c
    add("X6 codec manipulation by off-path record + 1 s splice", False, codec_off)
    def codec_on(r):
        c = honest_full(r); c.hops[r.randint(1, len(c.hops)) - 1]["beh"] = "codec_lie"; c.audio_kind = "splice_1"; return c
    add("X7 codec lie by on-path carrier + 1 s splice", False, codec_on)
    def trunc(r):
        c = honest_full(r); c.truncate_tail = 5; return c
    add("X8 tail truncation (last 5 s dropped)", False, trunc)
    def bye(r):
        c = honest_full(r); c.bye_at = r.randint(10, 25); return c
    add("X9 injected BYE cuts the call", False, bye)
    def premature(r):
        c = honest_full(r); c.premature_at = 10; c.late_attack = True; c.audio_kind = "splice_3"; return c
    add("X10 early verdict, then 3 s splice", False, premature)
    for kind, label in [("splice_3", "X11 3 s splice"), ("splice_1", "X12 1 s splice (short edit)"), ("full_asv", "X13 full voice substitution")]:
        add(label, False, (lambda kd: (lambda r: replace(honest_full(r), audio_kind=kd)))(kind))
    def strip(r):
        c = honest_full(r); c.strip = True; return c
    add("X14 key message and stream stripped", False, strip)
    for kind, label in SEMANTIC:
        if kind not in semantic_kinds: continue
        add(label, False, (lambda kd: (lambda r: replace(honest_full(r), audio_kind=kd)))(kind))
        def lie(r, kd=kind):
            c = honest_full(r); c.hops[r.randint(1, len(c.hops)) - 1]["beh"] = "codec_lie"; c.audio_kind = kd; return c
        add(label.split(" ", 1)[0] + "b " + label.split(" ", 1)[1] + " + on-path codec lie", False, lie)
    return S

# ------------------------------------------------------------------ verifier
def verify(cfg, call, org, oracle, th, rng):
    """Returns a dict with identity, route, audio and final outcomes plus overhead."""
    sk_R, epk_R = recipient_ephemeral()
    sid = H(os.urandom(16), canonical(call.presented))
    signed_called = MULE if call.relay else VICTIM
    km = st = None
    if not call.strip:
        km, k_c = make_key_message(org, sid, epk_R, call.sender_codec, ORG_A, signed_called, cfg.km)
        st = make_stream(k_c, sid, call.duration, cfg.stream)
        if call.truncate_tail:
            st.blocks = st.blocks[:-call.truncate_tail]; st.term = None
        if call.bye_at:
            st.blocks = st.blocks[:call.bye_at]; st.term = None

    t0 = time.perf_counter()
    # ---- identity: credential (assumed valid) plus number binding carried by the key message
    km_status, k_r = verify_key_message(km, org.pk_hash, sid, epk_R, sk_R, call.presented, VICTIM)
    identity = "fail" if km_status in ("calling_mismatch", "called_mismatch") else "pass"
    # ---- route
    if cfg.route == "positional":
        route, used = positional_rule(call.records, call.presented, len(call.hops))
        reported = [r.codec for r in call.records]; chain_codecs, complete = [], False
    elif cfg.route == "linked":
        route, chain, complete = linked_rule(call.records, call.terminating, call.presented,
                                             canonical(ORG_A) if cfg.km == "v2" else None)
        reported, chain_codecs = [], [r.codec for r in chain]
    else:
        route, reported, chain_codecs, complete = "unused", [], [], False
    # ---- audio
    theta, th_label, ber = None, "", None
    if km_status != "ok":
        audio = "unverifiable"
    else:
        premature = cfg.stream == "v1" and call.premature_at is not None
        s_status, n_eval = verify_stream(k_r, sid, st, cfg.stream, verdict_at=call.premature_at if premature else None)
        if s_status != "ok":
            audio = "unverifiable"
        else:
            policy = cfg.codec
            theta, th_label = threshold_for(policy, th, call.sender_codec, reported, chain_codecs, complete, call.received_codec)
            if theta is None:
                audio = "uncertain"
            else:
                kind = call.audio_kind
                if call.late_attack and premature:
                    kind = "honest"                  # the verdict was taken before the attack happened
                ber = oracle.sample(call.true_codec_key, kind)
                audio = "fail" if ber > theta else "pass"
    ms = (time.perf_counter() - t0) * 1000
    # ---- final verdict
    if identity == "fail" or (cfg.route_decides and route == "fail") or audio == "fail":
        final = "fail"
    elif audio in ("unverifiable", "uncertain"):
        final = "not verified"
    else:
        final = "verified"
    reads = 2 + (len(call.records) if cfg.route != "none" else 0)
    nbytes = (km.size() if km else 0) + (st.overhead_bytes() if st else 0)
    return dict(identity=identity, route=route, audio=audio, final=final, theta=theta, theta_src=th_label,
                ber=ber, verify_ms=ms, bytes=nbytes, reads=reads, writes=len([r for r in call.records]))
