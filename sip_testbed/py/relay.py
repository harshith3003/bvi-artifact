"""
Carrier media relay (in the media path between caller and callee).
Control (harness only): UDP :40100 'SCEN <scenario> <substitute file or ->' before each call.
  honest / rewrite : forwards RTP and the digest stream unchanged
  substitute       : replaces every RTP payload with the substitute audio (ASVspoof spoof)
  splice3s         : replaces RTP payloads between 3 s and 6 s only
  strip            : forwards RTP, drops the key message and every digest block
The relay never holds k_c, so it cannot produce valid digest tags for altered audio.
"""
import audioop, os, select, socket, struct
import numpy as np
import channel

_C = os.environ.get("CALLEE_HOST", "callee")
CALLEE_RTP = (_C, int(os.environ.get("CALLEE_RTP_PORT", "40000")))
CALLEE_DIG = (_C, int(os.environ.get("CALLEE_DIG_PORT", "40002")))


def main():
    rtp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); rtp.bind(("0.0.0.0", 40000))
    dig = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); dig.bind(("0.0.0.0", 40002))
    ctl = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); ctl.bind(("0.0.0.0", 40100))
    out = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    scen, sub, first_seq = "honest", None, None
    print("[relay] ready", flush=True)
    while True:
        for s in select.select([rtp, dig, ctl], [], [])[0]:
            data, _ = s.recvfrom(65535)
            if s is ctl:
                parts = data.decode().split()
                scen, path, first_seq = parts[1], parts[2], None
                sub = None
                if path != "-":
                    x = channel.load_audio(path)
                    x = np.resize(x, 8000 * 60)                       # loop if shorter than the call
                    sub = audioop.lin2ulaw((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes(), 2)
                print(f"[relay] scenario {scen} {path}", flush=True)
            elif s is rtp:
                seq = struct.unpack("!H", data[2:4])[0]
                if first_seq is None:
                    first_seq = seq
                i = (seq - first_seq) & 0xFFFF
                t = i * 0.020
                if sub is not None and (scen == "substitute" or (scen == "splice3s" and 3.0 <= t < 6.0)):
                    data = data[:12] + sub[i * 160:(i + 1) * 160]
                out.sendto(data, CALLEE_RTP)
            elif s is dig:
                if scen != "strip":
                    out.sendto(data, CALLEE_DIG)


if __name__ == "__main__":
    main()
