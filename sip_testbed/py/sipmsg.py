"""Minimal SIP over UDP: just enough for INVITE / 200 / ACK / BYE through Kamailio."""
import random
import re
import string


def rand(n=10):
    return "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(n))


class Msg:
    def __init__(self, first, headers, body=b""):
        self.first = first              # request line or status line
        self.headers = headers          # list of (name, value), order kept
        self.body = body

    def get(self, name, default=None):
        for k, v in self.headers:
            if k.lower() == name.lower():
                return v
        return default

    def get_all(self, name):
        out = []
        for k, v in self.headers:
            if k.lower() == name.lower():
                out += split_header_values(v)
        return out

    @property
    def is_request(self):
        return not self.first.startswith("SIP/2.0")

    @property
    def method(self):
        return self.first.split()[0] if self.is_request else None

    @property
    def status(self):
        return None if self.is_request else int(self.first.split()[1])

    @property
    def cseq_method(self):
        return self.get("CSeq", "").split()[-1]

    def encode(self):
        hs = [(k, v) for k, v in self.headers if k.lower() != "content-length"]
        hs.append(("Content-Length", str(len(self.body))))
        return (self.first + "\r\n" + "".join(f"{k}: {v}\r\n" for k, v in hs) + "\r\n").encode() + self.body


def split_header_values(v):
    """Split 'a, <b;x>, c' on commas outside <> (Via/Route/Record-Route may be combined)."""
    out, depth, cur = [], 0, ""
    for ch in v:
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur.strip()); cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def parse(data):
    head, _, body = data.partition(b"\r\n\r\n")
    lines = head.decode(errors="replace").split("\r\n")
    headers = []
    for ln in lines[1:]:
        if ":" in ln:
            k, v = ln.split(":", 1)
            headers.append((k.strip(), v.strip()))
    return Msg(lines[0], headers, body)


def uri_host_port(uri):
    """'<sip:172.18.0.4;lr>' or 'sip:callee@callee:5060' -> (host, port)."""
    m = re.search(r"sip:(?:[^@;>]+@)?([^:;>]+)(?::(\d+))?", uri)
    return m.group(1), int(m.group(2) or 5060)


def strip_brackets(uri):
    m = re.search(r"<([^>]+)>", uri)
    return m.group(1) if m else uri.split(";")[0].strip()


def user_of(uri):
    m = re.search(r"sip:([^@;>]+)@", uri)
    return m.group(1) if m else ""


def response(req, code, reason, extra=(), body=b"", to_tag=None):
    hs = [(k, v) for k, v in req.headers if k.lower() in ("via", "record-route", "from", "call-id", "cseq")]
    to = req.get("To")
    if to_tag and ";tag=" not in to:
        to += f";tag={to_tag}"
    hs.insert(0, ("To", to))
    hs += list(extra)
    return Msg(f"SIP/2.0 {code} {reason}", hs, body)
