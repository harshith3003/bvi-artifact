# Round 6 performance (item 6)

Machine: macOS-26.6.2-arm64-arm-64bit, 10 cores; Python 3.12.10.

| Operation | median | p95 |
|---|---|---|
| Sender fingerprint, 60 s call | 12.539 ms | 13.391 ms |
| Recipient content check, 60 s call | 13.808 ms | 15.486 ms |
| Key message setup + open, v1 (BVI-0) | 0.620 ms | 0.630 ms |
| Key message setup + open, v2 (number binding) | 0.622 ms | 0.634 ms |
| Stream tagging, 60 s, v1 | 0.268 ms | 0.320 ms |
| Stream tagging, 60 s, v2 | 0.284 ms | 0.384 ms |
| Stream verification, 60 s, v1 | 0.274 ms | 0.300 ms |
| Stream verification, 60 s, v2 | 0.280 ms | 0.290 ms |

Recipient peak memory for a 60 s check: 20.1 MB.
Recipient cost per second of audio (content check + v2 stream): 0.23 ms (real-time factor 0.0002; about 4259 concurrent calls per core).
Stream bandwidth: v1 914 bit/s, v2 930 bit/s, plus a 16-byte termination once.
