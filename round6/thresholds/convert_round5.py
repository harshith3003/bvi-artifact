"""Convert the round-5 held-out results into ber_samples.csv for the ablation harness and robustness analysis.

Reads <results>/honest_raw.csv, attack_raw.csv and manifest.json (calibration speakers). Writes one row per
call-condition (honest) or attack instance:
  codec, kind, max_ber (pause rule on), max_ber_nopause, call_id, speaker, condition, split (cal | test)
Kinds: honest; splice_<L> (natural), splice_syn_<L> (ASVspoof), full_nat, full_asv, pause_3, pause_3_syn.
Semantic edits (item 1): if <results dir>/../round6_semantic/semantic_raw.csv exists, its rows are added with
kinds semantic_neg_delete, semantic_neg_delete_mute, semantic_neg_insert, semantic_num_swap, semantic_word_swap.
Usage: python convert_round5.py <round5 results dir> [out.csv]
"""
import csv, json, os, sys

KIND = {"full_natural": "full_nat", "full_synthetic": "full_asv",
        "pause_inject_natural": "pause_3", "pause_inject_synthetic": "pause_3_syn"}

def main():
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "bvi", "round5", "results", "item1_devclean")
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "ber_samples.csv")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    calib = set(json.load(open(os.path.join(src, "manifest.json")))["calibration_speakers"])
    n = {"honest": 0, "attack": 0}
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["codec", "kind", "max_ber", "max_ber_nopause", "call_id", "speaker", "condition", "split"])
        for r in csv.DictReader(open(os.path.join(src, "honest_raw.csv"))):
            w.writerow([r["codec"], "honest", r["max_window_ber"], r["max_window_ber_nopause"], r["call"], r["speaker"],
                        f"{r['noise']}_loss{float(r['loss']):g}", "cal" if r["speaker"] in calib else "test"]); n["honest"] += 1
        for r in csv.DictReader(open(os.path.join(src, "attack_raw.csv"))):
            a = r["attack"]
            if a.startswith("splice_"):
                L = f"{float(r['length_s']):g}"
                kind = f"splice_{L}" if a == "splice_natural" else f"splice_syn_{L}"
            else:
                kind = KIND[a]
            w.writerow([r["codec"], kind, r["max_window_ber"], r["max_window_ber_nopause"], r["call"], r["speaker"],
                        "clean_loss0.01", "cal" if r["speaker"] in calib else "test"]); n["attack"] += 1
        sem = os.path.join(src, "..", "round6_semantic", "semantic_raw.csv"); n["semantic"] = 0
        if os.path.exists(sem):
            for r in csv.DictReader(open(sem)):
                w.writerow([r["codec"], r["attack"], r["max_window_ber"], r["max_window_ber_nopause"], r["call"], r["speaker"],
                            "clean_loss0.01", "cal" if r["speaker"] in calib else "test"]); n["semantic"] += 1
    print(f"wrote {out}: {n['honest']} honest call-conditions, {n['attack']} attack instances, "
          f"{n['semantic']} semantic edits, {len(calib)} calibration speakers")

if __name__ == "__main__":
    main()
