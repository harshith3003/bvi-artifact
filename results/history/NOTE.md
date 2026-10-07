# History: earlier fingerprint runs (not the results the paper reports)

- `item1_v1.1_test-clean/`: first full run (LibriSpeech test-clean). The pooled threshold came out at 0.70, above
  chance. The raw files showed that single-frame codec artefacts at word onsets and in near-silent pauses were being
  scored as pause violations.
- `item1_v1.2_test-clean/`: re-run after the fix (a violation now needs at least 100 ms of sustained speech, with
  +-40 ms of slack). That fix was diagnosed using all test-clean speakers, test speakers included, so these numbers
  are not a held-out result.

The results to quote are in `results/item1_devclean/`: spec v1.2 unchanged, run on LibriSpeech dev-clean speakers
and on ASVspoof utterances disjoint from these runs, neither of which played any part in the diagnosis.
