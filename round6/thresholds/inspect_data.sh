#!/usr/bin/env bash
# Prints the layout of the round-5 held-out results so a converter to ber_samples.csv can be written.
D="${1:-$HOME/Desktop/bvi/round5/results/item1_devclean}"
echo "== files in $D"; ls -la "$D"
for f in "$D"/*.csv "$D"/*.json "$D"/*.jsonl; do
  [ -f "$f" ] || continue
  echo; echo "== $(basename "$f") ($(wc -l < "$f") lines)"; head -c 1500 "$f" | head -6
done
echo; echo "== python files that write these results"
grep -l -E "to_csv|DictWriter|json.dump" "$HOME/Desktop/bvi/round5/item1_fingerprint/"*.py 2>/dev/null
