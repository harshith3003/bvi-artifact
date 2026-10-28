"""
semantic_edits.py: item 1, short meaning-changing edits (negations, numbers, words) through the SAME call
construction, codecs, packet loss and comparison as the round-5 held-out run.

Two steps:
  align  word timings for every test-speaker file used in a call (Whisper, run locally)
  run    build the edits, pass them through every codec at 1% loss, score with run_ber.compare

Calls are rebuilt with run_ber.build_calls itself (same seed, same random draws), while recording which file
and which pause landed where, so the calls are bit-identical to round 5 (checked against honest_raw.csv).
Only TEST speakers (not in manifest.json calibration_speakers) are edited.

Edits (all time-preserving, as a live in-path attacker must keep the call in sync; same-speaker audio):
  neg_delete   replace a negation word ("not", "never", "no", "...n't") with the call's own background noise
  neg_delete_mute  the naive variant: replace it with digital silence. Kept to show a side effect: the
               recipient's gate floor (running minimum over 2 s) drops, so later quiet speech is scored as
               pause violations and the call is flagged for a reason unrelated to the edit
  neg_insert   insert the speaker's own "not"/"never" at a word boundary and remove the same duration from the
               next pause, so later speech stays in place
  num_swap     replace a number word with a DIFFERENT number word from the same speaker, fitted to the original
               duration (trimmed or padded with background)
  word_swap    replace a content word (5+ letters) with a different content word of similar duration (+-25%) from
               the same speaker: the proxy for name and instruction substitutions
Usage:
  python3 semantic_edits.py align --natural DEV_CLEAN --manifest MANIFEST --out OUTDIR [--model base.en]
  python3 semantic_edits.py run   --natural DEV_CLEAN --manifest MANIFEST --thresholds THRESHOLDS --out OUTDIR
Outputs (OUTDIR): alignments.json, semantic_raw.csv (same columns as attack_raw.csv plus edit details),
                  semantic_summary.csv / .md (detection at the per-codec thresholds, Wilson 95% CI)
"""
import argparse, csv, json, math, os, re, sys, zlib
from multiprocessing import Pool
import numpy as np
import channel as ch
import fingerprint as fp
import run_ber as rb

SEED = rb.SEED

NEG = {"not", "never", "no", "nothing", "nobody", "none", "nor", "cannot", "neither"}
NUMW = set("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
           "seventeen eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety hundred thousand million "
           "first second third fourth fifth sixth seventh eighth ninth tenth half dozen".split())
STOP = set("about above after again against because before being below between could does doing during every "
           "further having herself himself itself myself other ought ourselves should their theirs themselves there "
           "these those through under until which while would yours yourself yourselves".split())
EDITS = ["neg_delete", "neg_delete_mute", "neg_insert", "num_swap", "word_swap"]
XF = int(0.01 * ch.FS)

def norm(w):
    return re.sub(r"[^a-z0-9']", "", w.lower())

def is_neg(w):
    return w in NEG or w.endswith("n't")

def is_num(w):
    return w in NUMW or w.isdigit()

# ── calls with provenance ───────────────────────────────────────────────────
def build_calls_tracked(natural):
    """Runs run_ber.build_calls unchanged (same rng draws) and records where every file and pause landed."""
    events, orig_load, orig_dither = [], ch.load_audio, rb.dither
    def load(path):
        u = orig_load(path); events.append(("file", path, len(u))); return u
    def dith(n, rng):
        events.append(("dither", None, n)); return orig_dither(n, rng)
    ch.load_audio, rb.dither = load, dith
    try:
        calls = rb.build_calls(natural, 60.0, 3, 0, np.random.default_rng(SEED))
    finally:
        ch.load_audio, rb.dither = orig_load, orig_dither
    need = int(60.0 * ch.FS); segs, cur, off, k = [], [], 0, 0
    for kind, path, n in events:
        if kind == "dither" and n == need:                      # end of a call: the final full-length dither
            segs.append(cur); cur, off = [], 0; k += 1; continue
        if kind == "file":
            cur.append((path, off, n))
        off += n
    assert len(segs) == len(calls), (len(segs), len(calls))
    for c, s in zip(calls, segs):
        c["files"] = s
    return calls

def test_calls(calls, manifest):
    calib = set(json.load(open(manifest))["calibration_speakers"])
    return [(i, c) for i, c in enumerate(calls) if c["speaker"] not in calib]

# ── step 1: alignment ───────────────────────────────────────────────────────
def cmd_align(a):
    import whisper
    calls = test_calls(build_calls_tracked(a.natural), a.manifest)
    files = sorted({p for _, c in calls for p, _, _ in c["files"]})
    spk_files = {}
    for _, c in calls:
        spk = c["speaker"]; d = os.path.join(a.natural, spk)
        spk_files.setdefault(spk, set()).update(rb.audio_files(d)[:60])      # word bank: first 60 files per speaker
    files = sorted(set(files) | {f for fs in spk_files.values() for f in fs})
    print(f"aligning {len(files)} files from {len(spk_files)} test speakers with whisper {a.model}", flush=True)
    model = whisper.load_model(a.model)
    out, done = {}, 0
    path_out = os.path.join(a.out, "alignments.json"); os.makedirs(a.out, exist_ok=True)
    if os.path.exists(path_out):
        out = json.load(open(path_out))
    for f in files:
        if f in out: continue
        r = model.transcribe(f, language="en", word_timestamps=True, fp16=False, condition_on_previous_text=False)
        out[f] = [{"w": norm(w["word"]), "s": float(w["start"]), "e": float(w["end"])}
                  for seg in r["segments"] for w in seg.get("words", []) if norm(w["word"])]
        done += 1
        if done % 25 == 0:
            json.dump(out, open(path_out, "w")); print(f"  {done}/{len(files)}", flush=True)
    json.dump(out, open(path_out, "w")); print("wrote", path_out)

# ── step 2: edits ───────────────────────────────────────────────────────────
def call_words(call, align):
    T = 60.0; ws = []
    for path, off, n in call["files"]:
        for w in align.get(path, []):
            s, e = off / ch.FS + w["s"], off / ch.FS + w["e"]
            if e - s >= 0.05 and e < T - 0.5 and s > 1.0:
                ws.append({"w": w["w"], "s": s, "e": e})
    return sorted(ws, key=lambda x: x["s"])

def fade_in_place(y, a, seg):
    """Write seg into y at sample a with 10 ms cross-fades."""
    n = len(seg); seg = seg.copy(); r = np.linspace(0, 1, min(XF, n // 2) or 1)
    k = len(r)
    seg[:k] = seg[:k] * r + y[a:a + k] * (1 - r)
    seg[-k:] = seg[-k:] * (1 - r) + y[a + n - k:a + n] * r
    y[a:a + n] = seg

def background_pool(x, words):
    """Quiet inter-word segments of the call itself (natural room noise inside utterances), quietest first.
    Excludes the constructed dither gaps (below -60 dBFS), which are not natural background."""
    segs = []
    for w1, w2 in zip(words, words[1:]):
        a, b = int(w1["e"] * ch.FS) + XF, int(w2["s"] * ch.FS) - XF
        if b - a >= int(0.03 * ch.FS):
            seg = x[a:b]; lvl = 10 * np.log10(np.mean(seg ** 2) + 1e-12)
            if lvl > -60:
                segs.append((lvl, seg))
    segs.sort(key=lambda t: t[0])
    return [s for _, s in segs[:12]]

def background(pool, n, rng):
    """n samples of the call's own background noise (tiled quiet segments with cross-fades)."""
    if not pool:
        return rb.dither(n, rng)
    out = np.zeros(0)
    while len(out) < n:
        seg = pool[int(rng.integers(len(pool)))]
        if len(out) and len(seg) > 2 * XF:
            r = np.linspace(0, 1, XF); seg = seg.copy(); seg[:XF] = seg[:XF] * r + out[-XF:] * (1 - r); out = out[:-XF]
        out = np.concatenate([out, seg])
    return out[:n].copy()

def fit(seg, n, rng, pool):
    if len(seg) >= n:
        o = (len(seg) - n) // 2; return seg[o:o + n].copy()
    pad = n - len(seg); left = pad // 2
    return np.concatenate([background(pool, left, rng), seg, background(pool, pad - left, rng)])

def bank_audio(bank, cache, item):
    if item["path"] not in cache:
        cache[item["path"]] = ch.load_audio(item["path"])
    u = cache[item["path"]]
    return u[int(item["s"] * ch.FS):int(item["e"] * ch.FS)]

def make_edit(kind, x, words, bank, cache, rng, pool):
    """Returns (edited audio, info) or None if the call has no suitable word."""
    y = x.copy()
    if kind in ("neg_delete", "neg_delete_mute"):
        c = [w for w in words if is_neg(w["w"])]
        if not c: return None
        w = c[rng.integers(len(c))]; a, b = int(w["s"] * ch.FS), int(w["e"] * ch.FS)
        fill = rb.dither(b - a, rng) if kind == "neg_delete_mute" else background(pool, b - a, rng)
        fade_in_place(y, a, fill); return y, dict(start=w["s"], length=w["e"] - w["s"], frm=w["w"], to="")
    if kind == "neg_insert":
        src = [b for b in bank if b["w"] in ("not", "never")]
        if not src: return None
        ins = bank_audio(bank, cache, src[rng.integers(len(src))]); L = len(ins)
        bounds = [(w1["e"], w2["s"]) for w1, w2 in zip(words, words[1:]) if 0 <= w2["s"] - w1["e"] < 0.25]
        rng.shuffle(bounds)
        gaps = [(w1["e"], w2["s"]) for w1, w2 in zip(words, words[1:]) if w2["s"] - w1["e"] >= L / ch.FS + 0.05]
        for e1, s2 in bounds:
            p = int(((e1 + s2) / 2) * ch.FS)
            later = [g for g in gaps if g[0] * ch.FS > p + XF]
            if not later: continue
            q = int((later[0][0] + 0.02) * ch.FS)                # cut L samples from the start of the next pause
            y = np.concatenate([x[:p], ins, x[p:q], x[q + L:]])[:len(x)]
            fade_in_place(y, p, ins.copy())
            return y, dict(start=p / ch.FS, length=L / ch.FS, frm="", to="not/never", shifted_s=(q - p) / ch.FS)
        return None
    if kind in ("num_swap", "word_swap"):
        if kind == "num_swap":
            c = [w for w in words if is_num(w["w"])]
            cands_for = lambda w: [b for b in bank if is_num(b["w"]) and b["w"] != w["w"]]
        else:
            c = [w for w in words if len(w["w"]) >= 5 and w["w"].isalpha() and w["w"] not in STOP and not is_neg(w["w"])]
            def cands_for(w):
                d = w["e"] - w["s"]
                return [b for b in bank if len(b["w"]) >= 5 and b["w"].isalpha() and b["w"] not in STOP
                        and b["w"] != w["w"] and abs((b["e"] - b["s"]) - d) <= 0.25 * d]
        rng.shuffle(c)
        for w in c[:20]:
            cand = cands_for(w)
            if not cand: continue
            b = cand[rng.integers(len(cand))]; a, e = int(w["s"] * ch.FS), int(w["e"] * ch.FS)
            fade_in_place(y, a, fit(bank_audio(bank, cache, b), e - a, rng, pool))
            return y, dict(start=w["s"], length=w["e"] - w["s"], frm=w["w"], to=b["w"])
        return None
    raise ValueError(kind)

def semantic_task(args):
    i, call, words, bank, codecs = args
    rng = np.random.default_rng([SEED, 7, i])
    x = call["x"]; s_bits, s_act = fp.sender_fingerprint(x); cache, rows = {}, []
    pool = background_pool(x, words)
    for kind in EDITS:
        r = make_edit(kind, x, words, bank, cache, rng, pool)
        if r is None: continue
        y_edit, info = r
        f0 = int(info["start"] * 50); n = max(1, int(info["length"] * 50))
        overlap = float(s_act[f0:f0 + n].mean()) if f0 < len(s_act) else 0.0
        for cname in codecs:
            crng = np.random.default_rng([SEED, 8, i, zlib.crc32((kind + cname).encode())])
            y = ch.packet_loss(ch.codec(y_edit, cname), 0.01, crng)
            wb, wb_off, whole = rb.compare(s_bits, s_act, x, y)
            mx, nc = rb.summarise(wb); mx_off, nc_off = rb.summarise(wb_off)
            rows.append([call["speaker"], i, cname, f"semantic_{kind}", round(info["length"], 4), whole, mx, nc, overlap,
                         mx_off, nc_off, info.get("frm", ""), info.get("to", ""), round(info["start"], 3), round(info.get("shifted_s", 0.0), 3)])
    return rows

def wilson(k, n, z=1.96):
    if n == 0: return (float("nan"), float("nan"))
    p = k / n; d = 1 + z * z / n; c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))

def cmd_run(a):
    align = json.load(open(os.path.join(a.out, "alignments.json")))
    calls = build_calls_tracked(a.natural)
    if a.check_honest:
        ref = {}
        for r in csv.DictReader(open(a.check_honest)):
            if r["codec"] == "g711u" and r["noise"] == "clean" and float(r["loss"]) == 0.0:
                ref[int(r["call"])] = float(r["max_window_ber"])
        i0 = sorted(ref)[0]; c0 = calls[i0]; s_bits, s_act = fp.sender_fingerprint(c0["x"])
        mx, _ = rb.summarise(rb.compare(s_bits, s_act, c0["x"], ch.codec(c0["x"], "g711u"))[0])
        print(f"bit-identical check: call {i0} g711u clean max BER {mx:.6f} vs round-5 {ref[i0]:.6f}", flush=True)
        assert abs(mx - ref[i0]) < 1e-9, "rebuilt calls differ from round 5"
    tc = test_calls(calls, a.manifest)
    banks = {}
    for path, ws in align.items():
        spk = os.path.relpath(path, a.natural).split(os.sep)[0]
        banks.setdefault(spk, []).extend({"w": w["w"], "s": w["s"], "e": w["e"], "path": path} for w in ws if w["e"] - w["s"] >= 0.08)
    avail = [c for c, ok in ch.available_codecs().items() if ok]
    codecs = [c for c in (a.codecs.split(",") if a.codecs else avail) if c in avail]
    print(f"{len(tc)} test calls; codecs {codecs}", flush=True)
    tasks = [(i, c, call_words(c, align), banks.get(c["speaker"], []), codecs) for i, c in tc]
    with Pool(a.jobs) as pool:
        rows = [r for rs in pool.map(semantic_task, tasks) for r in rs]
    hdr = ["speaker", "call", "codec", "attack", "length_s", "whole_call_ber", "max_window_ber", "conclusive_windows",
           "share_over_sender_speech", "max_window_ber_nopause", "conclusive_windows_nopause", "word_from", "word_to",
           "edit_start_s", "shifted_s"]
    rb.write_csv(os.path.join(a.out, "semantic_raw.csv"), hdr, rows)
    th = json.load(open(a.thresholds))
    S = [["codec", "edit", "calls", "median_length_s", "detected", "rate", "ci95_lo", "ci95_hi"]]
    L = ["# Item 1: semantic edits (held-out test speakers, 1% packet loss, pause rule on, per-codec threshold)", "",
         "| Codec | Edit | Calls | Median length | Detected [95% CI] |", "|---|---|---|---|---|"]
    for cname in codecs:
        for kind in EDITS:
            sel = [r for r in rows if r[2] == cname and r[3] == f"semantic_{kind}"]
            if not sel: continue
            det = sum(1 for r in sel if not np.isnan(r[6]) and r[6] > th[cname]); lo, hi = wilson(det, len(sel))
            med = float(np.median([r[4] for r in sel]))
            S.append([cname, kind, len(sel), round(med, 3), det, round(det / len(sel), 4), round(lo, 4), round(hi, 4)])
            L.append(f"| {cname} | {kind} | {len(sel)} | {med:.2f} s | {100*det/len(sel):.1f}% [{100*lo:.1f}-{100*hi:.1f}] |")
    rb.write_csv(os.path.join(a.out, "semantic_summary.csv"), S[0], S[1:])
    open(os.path.join(a.out, "semantic_summary.md"), "w").write("\n".join(L) + "\n"); print("\n".join(L))

def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("align", "run"):
        p = sub.add_parser(name)
        p.add_argument("--natural", required=True); p.add_argument("--manifest", required=True); p.add_argument("--out", required=True)
        if name == "align":
            p.add_argument("--model", default="base.en")
        else:
            p.add_argument("--thresholds", required=True); p.add_argument("--codecs", default="")
            p.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
            p.add_argument("--check-honest", default="", help="round-5 honest_raw.csv: verify the rebuilt calls are identical")
    a = ap.parse_args()
    cmd_align(a) if a.cmd == "align" else cmd_run(a)

if __name__ == "__main__":
    main()
