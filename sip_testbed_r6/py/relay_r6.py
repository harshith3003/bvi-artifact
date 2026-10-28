"""
Round-6 carrier media relay (RTP and the digest channel, between caller and callee). It never holds k_c.
Control (harness only, UDP :40100):  SCEN <scenario> <substitute file|-> <codec chain|-> <loss> <truncate_s|->
  codec chain   real transcoding of the media leg with FFmpeg (e.g. amr122 = G.711 -> AMR-NB 12.2 -> G.711): audio is
                processed in 1 s chunks, each with the preceding 200 ms as codec context, then re-encoded to G.711
  loss          drop this fraction of RTP packets (seeded per call); the callee repeats the previous packet
  truncate_s    stop forwarding RTP, fingerprint blocks and the termination from this time on
  substitute / splice3s   replace the whole call / seconds 3-6 with the substitute audio (ASVspoof)
  strip         drop the key messages, blocks and termination (RTP still forwarded)
"""
import audioop, os, random, select, socket, struct, time
import numpy as np
import channel
import wire

_C = os.environ.get("CALLEE_HOST", "callee")
CALLEE_RTP = (_C, int(os.environ.get("CALLEE_RTP_PORT", "40000")))
CALLEE_DIG = (_C, int(os.environ.get("CALLEE_DIG_PORT", "40002")))
CHUNK, CONTEXT = 50, int(0.2 * 8000)


def transcode_chunk(payloads, context, chain):
    """payloads: list of 160-byte mu-law payloads; context: preceding linear audio (float). Returns (payloads, context)."""
    x = np.frombuffer(audioop.ulaw2lin(b"".join(payloads), 2), np.int16).astype(np.float64) / 32768.0
    y = channel.codec(np.concatenate([context, x]), chain)[len(context):]
    pcm = (np.clip(y, -1, 1) * 32767).astype(np.int16).tobytes()
    out = [audioop.lin2ulaw(pcm[i * 320:(i + 1) * 320], 2) for i in range(len(payloads))]
    return out, x[-CONTEXT:]


def main():
    base = int(os.environ.get("RELAY_PORT_BASE", "40000"))
    rtp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); rtp.bind(("0.0.0.0", base))
    dig = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); dig.bind(("0.0.0.0", base + 2))
    ctl = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); ctl.bind(("0.0.0.0", base + 100))
    out = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    st = dict(scen="honest", sub=None, chain=None, loss=0.0, trunc=None, first=None, buf=[], ctx=np.zeros(0), last=0.0, rng=random.Random(0))
    print("[relay] ready", flush=True)

    def flush():
        if not st["buf"]:
            return
        hdrs = [p[:12] for p in st["buf"]]; pays = [p[12:] for p in st["buf"]]
        try:
            pays, st["ctx"] = transcode_chunk(pays, st["ctx"], st["chain"])
        except Exception as e:                                   # never silently skip transcoding
            print(f"[relay] TRANSCODING FAILED ({st['chain']}): {e}", flush=True); raise
        for h, p in zip(hdrs, pays):
            out.sendto(h + p, CALLEE_RTP)
        st["buf"] = []

    while True:
        ready = select.select([rtp, dig, ctl], [], [], 0.05)[0]
        if st["buf"] and time.time() - st["last"] > 0.3:            # end of a call: flush the partial chunk
            flush()
        for s in ready:
            data, _ = s.recvfrom(65535)
            if s is ctl:
                if st["buf"]: flush()
                p = data.decode().split()
                st.update(scen=p[1], chain=None if p[3] == "-" else p[3], loss=float(p[4]),
                          trunc=None if p[5] == "-" else float(p[5]), first=None, buf=[], ctx=np.zeros(0),
                          rng=random.Random(f"{p[1]}|{time.time_ns()}"), sub=None)
                if p[2] != "-":
                    x = np.resize(channel.load_audio(p[2]), 8000 * 60)
                    st["sub"] = audioop.lin2ulaw((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes(), 2)
                print(f"[relay] scenario {p[1]} chain={st['chain']} loss={st['loss']} truncate={st['trunc']}", flush=True)
            elif s is rtp:
                seq = struct.unpack("!H", data[2:4])[0]
                if st["first"] is None:
                    st["first"] = seq
                i = (seq - st["first"]) & 0xFFFF; t = i * 0.020; st["last"] = time.time()
                if st["trunc"] is not None and t >= st["trunc"]:
                    continue
                if st["sub"] is not None and (st["scen"] == "substitute" or (st["scen"] == "splice3s" and 3.0 <= t < 6.0)):
                    data = data[:12] + st["sub"][i * 160:(i + 1) * 160]
                if st["loss"] and st["rng"].random() < st["loss"]:
                    continue
                if st["chain"]:
                    st["buf"].append(data)
                    if len(st["buf"]) >= CHUNK:
                        flush()
                else:
                    out.sendto(data, CALLEE_RTP)
            elif s is dig:
                if st["scen"] == "strip":
                    continue
                if st["trunc"] is not None:
                    idx = wire.block_index(data)
                    if data[:1] == b"E" or (idx is not None and idx >= st["trunc"]):
                        continue
                out.sendto(data, CALLEE_DIG)


if __name__ == "__main__":
    main()
