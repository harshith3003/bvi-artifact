"""
Select spoofed utterances from ASVspoof 2019 LA as the main synthetic source,
balanced across attack systems (eval: A07-A19, 13 TTS / VC / hybrid systems).
Fixed seed, so the selection is reproducible; the list is written next to the copies.

Usage: python3 select_asvspoof_spoof.py LA_DIR OUT_DIR [N] [partition] [EXCLUDE_TSV]
  EXCLUDE_TSV  a previous selection.tsv; none of its utterances are selected again
  LA_DIR    the extracted 'LA' folder from LA.zip (https://datashare.ed.ac.uk/handle/10283/3336)
  partition eval (default) or dev
"""
import collections, os, random, shutil, sys

la, out = sys.argv[1], sys.argv[2]
n = int(sys.argv[3]) if len(sys.argv) > 3 else 390
part = sys.argv[4] if len(sys.argv) > 4 else "eval"
exclude = set()
if len(sys.argv) > 5:
    exclude = {l.split()[0] for l in open(sys.argv[5]) if l.strip()}
proto = os.path.join(la, "ASVspoof2019_LA_cm_protocols",
                     f"ASVspoof2019.LA.cm.{part}.{'trl' if part == 'eval' else 'trl'}.txt")
flac = os.path.join(la, f"ASVspoof2019_LA_{part}", "flac")
by_attack = collections.defaultdict(list)
for line in open(proto):
    f = line.split()
    if len(f) >= 5 and f[4] == "spoof" and f[1] not in exclude:
        by_attack[f[3]].append(f[1])
rng = random.Random(20260909)
per = max(1, n // len(by_attack))
chosen = []
for attack in sorted(by_attack):
    ids = sorted(by_attack[attack]); rng.shuffle(ids)
    chosen += [(attack, u) for u in ids[:per]]
os.makedirs(out, exist_ok=True)
with open(os.path.join(out, "selection.tsv"), "w") as fh:
    for attack, u in chosen:
        shutil.copy(os.path.join(flac, u + ".flac"), out)
        fh.write(f"{u}\t{attack}\n")
print(f"excluded {len(exclude)} previously used utterances")
print(f"copied {len(chosen)} spoofed utterances ({per} from each of {len(by_attack)} attack systems: "
      f"{', '.join(sorted(by_attack))}) to {out}")
