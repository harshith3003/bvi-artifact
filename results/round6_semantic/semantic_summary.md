# Item 1: semantic edits (held-out test speakers, 1% packet loss, pause rule on, per-codec threshold)

| Codec | Edit | Calls | Median length | Detected [95% CI] |
|---|---|---|---|---|
| g711u | neg_delete | 44 | 0.21 s | 13.6% [6.4-26.7] |
| g711u | neg_delete_mute | 44 | 0.20 s | 25.0% [14.6-39.4] |
| g711u | neg_insert | 60 | 0.20 s | 98.3% [91.1-99.7] |
| g711u | num_swap | 41 | 0.22 s | 9.8% [3.9-22.5] |
| g711u | word_swap | 60 | 0.33 s | 28.3% [18.5-40.8] |
| g711a | neg_delete | 44 | 0.21 s | 18.2% [9.5-32.0] |
| g711a | neg_delete_mute | 44 | 0.20 s | 25.0% [14.6-39.4] |
| g711a | neg_insert | 60 | 0.20 s | 96.7% [88.6-99.1] |
| g711a | num_swap | 41 | 0.22 s | 12.2% [5.3-25.5] |
| g711a | word_swap | 60 | 0.33 s | 23.3% [14.4-35.4] |
| opus16 | neg_delete | 44 | 0.21 s | 13.6% [6.4-26.7] |
| opus16 | neg_delete_mute | 44 | 0.20 s | 18.2% [9.5-32.0] |
| opus16 | neg_insert | 60 | 0.20 s | 91.7% [81.9-96.4] |
| opus16 | num_swap | 41 | 0.22 s | 22.0% [12.0-36.7] |
| opus16 | word_swap | 60 | 0.33 s | 18.3% [10.6-29.9] |
| amr122 | neg_delete | 44 | 0.21 s | 11.4% [5.0-24.0] |
| amr122 | neg_delete_mute | 44 | 0.20 s | 15.9% [7.9-29.4] |
| amr122 | neg_insert | 60 | 0.20 s | 90.0% [79.9-95.3] |
| amr122 | num_swap | 41 | 0.22 s | 17.1% [8.5-31.3] |
| amr122 | word_swap | 60 | 0.33 s | 11.7% [5.8-22.2] |
| amr475 | neg_delete | 44 | 0.21 s | 11.4% [5.0-24.0] |
| amr475 | neg_delete_mute | 44 | 0.20 s | 13.6% [6.4-26.7] |
| amr475 | neg_insert | 60 | 0.20 s | 71.7% [59.2-81.5] |
| amr475 | num_swap | 41 | 0.22 s | 9.8% [3.9-22.5] |
| amr475 | word_swap | 60 | 0.33 s | 8.3% [3.6-18.1] |
| amr122_g711u | neg_delete | 44 | 0.21 s | 13.6% [6.4-26.7] |
| amr122_g711u | neg_delete_mute | 44 | 0.20 s | 13.6% [6.4-26.7] |
| amr122_g711u | neg_insert | 60 | 0.20 s | 90.0% [79.9-95.3] |
| amr122_g711u | num_swap | 41 | 0.22 s | 17.1% [8.5-31.3] |
| amr122_g711u | word_swap | 60 | 0.33 s | 20.0% [11.8-31.8] |
