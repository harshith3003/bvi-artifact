"""
bvi_eval.py: the recipient's verdict under all eight configurations, computed from ONE received call.

The caller sends both key-message versions (v1: digest_auth, v2: digest_auth_v2 with bound numbers), every
fingerprint block with both tag versions, and the v2 termination record. Carriers write linked records
(attestLinked); BVI-0's positional rule ignores the links. So every configuration is judged on exactly the same
audio, packets and network events: a paired comparison.

Inputs come from the network (what arrived) and from the chain service (route status, thresholds). Nothing here
reads the scenario label.
"""
import hmac
import numpy as np
import digest_auth as da
import digest_auth_v2 as d2
import fingerprint as fp

CONFIGS = {
    "BVI-0":                 dict(km="v1", route="positional", stream="v1",        codec="carrier",          route_decides=True),
    "BVI-R":                 dict(km="v2", route="linked",     stream="v2",        codec="chain",            route_decides=True),
    "BVI-B (strict)":        dict(km="v2", route="none",       stream="v2",        codec="endpoint_strict",  route_decides=False),
    "BVI-B (lenient)":       dict(km="v2", route="none",       stream="v2",        codec="endpoint_lenient", route_decides=False),
    "R - number binding":    dict(km="v1", route="linked",     stream="v2",        codec="chain",            route_decides=True),
    "R - linked chain":      dict(km="v2", route="positional", stream="v2",        codec="carrier",          route_decides=True),
    "R - auth. termination": dict(km="v2", route="linked",     stream="v2_noterm", codec="chain",            route_decides=True),
    "R + endpoint strict":   dict(km="v2", route="linked",     stream="v2",        codec="endpoint_strict",  route_decides=True),
}
CODEC_NAME = {1: "g711u", 2: "g711a", 3: "opus16", 4: "amr122", 5: "amr475"}


def max_window_ber(s_bits, s_act, y, shifts=3):
    """Maximum 2 s window BER (pause rule on), best alignment within +-shifts frames (codec / relay delay)."""
    r_bits, r_strong = fp.receiver_view(y)
    best = None
    for sh in range(-shifts, shifts + 1):
        err, cnt, act = fp.frame_errors(s_bits, s_act, np.roll(r_bits, sh, axis=0), np.roll(r_strong, sh))
        tot = err.sum() / max(cnt.sum(), 1)
        if best is None or tot < best[0]:
            best = (tot, fp.window_bers(err, cnt, act))
    wb = best[1]; conc = wb[~np.isnan(wb)]
    return float(conc.max()) if conc.size else None


def open_keys(km1, km2, recipient1, recipient2, did, sid, org_pub, onchain, presented, own_number):
    """Returns dict with v1 / v2 key outcomes. km2 = (KeyMsg, signed_calling, signed_called) or None."""
    out = {"v1": {"ok": False, "k": None, "codec": None, "why": "no v1 key message"},
           "v2": {"ok": False, "k": None, "codec": None, "why": "no v2 key message", "binding_fail": False}}
    if km1 is not None:
        try:
            k, c = recipient1.open(km1, did, sid, org_pub, onchain); out["v1"] = {"ok": True, "k": k, "codec": c, "why": ""}
        except Exception as e:
            out["v1"]["why"] = f"v1 key message rejected: {e}"
    out["v2_nobind"] = {"ok": False, "k": None, "codec": None, "why": "no v2 key message"}
    if km2 is not None:
        msg, s_calling, s_called = km2
        try:
            k, c = recipient2.open_bound(msg, did, sid, org_pub, onchain, presented, own_number, s_calling, s_called)
            out["v2"] = {"ok": True, "k": k, "codec": c, "why": "", "binding_fail": False}
        except ValueError as e:
            out["v2"]["why"] = str(e)
            out["v2"]["binding_fail"] = "number mismatch" in str(e)
        try:   # ablation 1: same message, signature checked, the numbers NOT compared with the call
            k, c = recipient2.open_bound(msg, did, sid, org_pub, onchain, s_calling, s_called, s_calling, s_called)
            out["v2_nobind"] = {"ok": True, "k": k, "codec": c, "why": ""}
        except ValueError as e:
            out["v2_nobind"]["why"] = str(e)
    return out


def stream_v1_status(k, sid, blocks1, n_blocks_from_audio):
    """BVI-0: expects as many blocks as the received audio covers (no authenticated end)."""
    if k is None:
        return "unverifiable", None, None
    ok, bits, act = [], [], []
    for i in range(n_blocks_from_audio):
        b = blocks1.get(i)
        if b is None:
            ok.append(False); continue
        b_bits, b_act, tag = b
        ok.append(hmac.compare_digest(da.block_tag(k, sid, i, b_bits, b_act), tag)); bits.append(b_bits); act.append(b_act)
    st = da.stream_status(True, ok, n_blocks_from_audio)
    if st != "ok" or not bits:
        return "unverifiable", None, None
    return "ok", np.concatenate(bits), np.concatenate(act)


def stream_v2_status(k, sid, blocks2, term, require_termination):
    """v2: blocks in index order with their frame counts; positions are authenticated; termination optional."""
    if k is None or not blocks2:
        return "unverifiable", None, None
    idx = sorted(blocks2)
    if idx != list(range(len(idx))):
        return "unverifiable", None, None                    # a block is missing in the middle
    bits = np.concatenate([blocks2[i][0] for i in idx]); act = np.concatenate([blocks2[i][1] for i in idx])
    tags = [(len(blocks2[i][0]), blocks2[i][2]) for i in idx]
    st, why = d2.verify_stream_v2(k, sid, bits, act, tags, term, require_termination=require_termination)
    return (st, bits, act) if st == "ok" else ("unverifiable", None, None)


def theta_for(cfg, chain, thresholds, origin_codec, received_codec):
    if cfg["codec"] == "carrier":
        return chain["carrier_theta"]
    if cfg["codec"] == "chain":
        return chain["chain_theta"]
    a, b = CODEC_NAME.get(origin_codec), CODEC_NAME.get(received_codec)
    if a and a == b:
        return thresholds[a]
    return None if cfg["codec"] == "endpoint_strict" else thresholds["pooled"]


def evaluate(call, chain, thresholds, received_codec=1):
    """call: dict with keys l1, keys (from open_keys), sid, blocks1, blocks2, term, y (received audio).
    chain: dict with route_positional, route_linked, carrier_theta, chain_theta (from the chain service).
    Returns {config: {outcome, identity, route, content, theta, max_ber}}."""
    n_audio_blocks = len(call["y"]) // (160 * 50)
    s1 = stream_v1_status(call["keys"]["v1"]["k"], call["sid"], call["blocks1"], n_audio_blocks)
    k2 = call["keys"]["v2"]["k"] or call["keys"]["v2_nobind"]["k"]       # same k_c; nobind opens when binding fails
    s2 = stream_v2_status(k2, call["sid"], call["blocks2"], call["term"], True)
    s2n = stream_v2_status(k2, call["sid"], call["blocks2"], call["term"], False)
    ber_cache = {}
    def ber(bits, act, tag):
        if tag not in ber_cache:
            ber_cache[tag] = max_window_ber(bits, act, call["y"]) if bits is not None else None
        return ber_cache[tag]
    out = {}
    for name, cfg in CONFIGS.items():
        # which key material this configuration uses: v1 stream -> v1 key; v2 stream with unbound numbers -> v2 key
        # opened without the number checks (ablation 1); otherwise the bound v2 key
        kname = "v1" if cfg["stream"] == "v1" else ("v2_nobind" if cfg["km"] == "v1" else "v2")
        key = call["keys"][kname]
        identity = "pass" if call["l1"] == "pass" and not (cfg["km"] == "v2" and key.get("binding_fail")) else "fail"
        linked = chain["route_linked"] if cfg["km"] == "v2" else chain.get("route_linked_unbound", chain["route_linked"])
        route = {"positional": chain["route_positional"], "linked": linked, "none": "unused"}[cfg["route"]]
        st, bits, act = {"v1": s1, "v2": s2, "v2_noterm": s2n}[cfg["stream"]]
        theta, mb = None, None
        if not key["ok"] or st != "ok":
            content = "unverifiable"
        else:
            theta = theta_for(cfg, chain, thresholds, key["codec"], received_codec)
            mb = ber(bits, act, cfg["stream"])
            if theta is None:
                content = "uncertain"
            elif mb is None:
                content = "unknown"
            else:
                content = "fail" if mb > theta else "pass"
        if identity == "fail" or (cfg["route_decides"] and route == "fail") or content == "fail":
            outcome = "fail"
        elif content in ("unverifiable", "uncertain"):
            outcome = "not verified"
        else:
            outcome = "verified"
        out[name] = dict(outcome=outcome, identity=identity, route=route, content=content, theta=theta,
                         max_ber=None if mb is None else round(mb, 4))
    return out
