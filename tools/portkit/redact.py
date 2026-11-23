"""Redact personal data and secrets from a folder of logs in place, before it is sent anywhere.

    python3 redact.py DIR [--private FILE] [--word TEXT ...]

Every text file under DIR (binary files are left alone and listed), and every file and folder name, is rewritten with:
- the user's own identifiers: the home directory (to `~`), the login name, the host names and the git user name and
  email, each replaced wherever it appears, and any `--word` given;
- shapes that identify someone or something: email addresses (noreply ones stay), IPv4 addresses (loopback stays),
  home paths of other users, private host names;
- secrets: GitHub, Anthropic, OpenAI, AWS and Slack token shapes, bearer tokens and private key blocks;
- every line of the private patterns file (`land.private_patterns`, see scrub.py), each a regex.
Prints how many replacements each rule made and the binary files it could not check (screenshots, archives), which a
person has to look at. Matching cannot find everything: names of people, private projects or customer data written in
plain words still need a read-through.
"""
from __future__ import annotations

import argparse
import getpass
import os
import re
import socket
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from portkit import scrub  # noqa: E402

SECRETS = [
    ("github-token", r"\b(?:gh[pousr]|github_pat)_[A-Za-z0-9_]{20,}"),
    ("anthropic-key", r"\bsk-ant-[A-Za-z0-9_-]{20,}"),
    ("openai-key", r"\bsk-[A-Za-z0-9]{32,}"),
    ("aws-key", r"\bAKIA[0-9A-Z]{16}\b"),
    ("slack-token", r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    ("bearer", r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{16,}"),
    ("private-key", r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----"),
]
SHAPES = [
    ("email", r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "<email>", lambda s: "noreply" not in s.lower()),
    ("ipv4", r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "<ip>", lambda s: not s.startswith("127.")),
    ("home-path", r"/(?:home|Users)/[A-Za-z0-9._-]+", "/home/<user>", None),
    ("home-path", r"C:\\\\?Users\\\\?[A-Za-z0-9._-]+", r"C:\\Users\\<user>", None),
    ("private-host", r"\b[\w-]+\.(?:lan|local|internal|ts\.net)\b", "<host>", None),
]


def own_words(extra: list[str]) -> list[tuple[str, str, str]]:
    """(rule, text, replacement) for the user's own identifiers, longest first so a path wins over its parts."""
    out = [("home", os.path.expanduser("~"), "~")]
    for name in {getpass.getuser(), os.environ.get("USER", "")}:
        out.append(("login", name, "<user>"))
    for host in {socket.gethostname(), socket.gethostname().split(".")[0], socket.getfqdn()}:
        out.append(("host", host, "<host>"))
    for key, rep in (("user.name", "<name>"), ("user.email", "<email>")):
        try:
            v = subprocess.run(["git", "config", "--global", key], capture_output=True, text=True).stdout.strip()
        except OSError:
            v = ""
        out.append(("git-" + key.split(".")[1], v, rep))
    out += [("word", w, "<redacted>") for w in extra]
    # Two-letter logins or hosts like "pc" would hit ordinary words; keep only distinctive ones.
    return sorted({o for o in out if len(o[1]) >= 3}, key=lambda o: -len(o[1]))


def build(private: Path, extra: list[str]):
    rules = []
    for rule, text, rep in own_words(extra):
        rx = re.escape(text) if "/" in text else r"(?<![A-Za-z0-9])" + re.escape(text) + r"(?![A-Za-z0-9])"
        rules.append((rule, re.compile(rx, re.I), rep, None))
    rules += [(n, re.compile(rx, re.S), f"<{n}>", None) for n, rx in SECRETS]
    rules += [(n, re.compile(rx), rep, keep) for n, rx, rep, keep in SHAPES]
    if private.is_file():
        rules += [(p.name, p.rx, "<private>", None) for p in scrub.load_private(private)]
    return rules


def redact(text: str, rules, counts: Counter) -> str:
    for name, rx, rep, keep in rules:
        def sub(m, name=name, rep=rep, keep=keep):
            if keep is not None and not keep(m.group(0)):
                return m.group(0)
            counts[name] += 1
            return rep
        text = rx.sub(sub, text)
    return text


def rename_all(root: Path, rules, counts: Counter) -> None:
    """File and folder names too: Claude Code names a session folder after its directory with every character other
    than a letter or digit turned into '-', so the home path also appears in that form."""
    home_slug = re.sub(r"[^A-Za-z0-9]", "-", os.path.expanduser("~"))
    for f in sorted(root.rglob("*"), key=lambda p: -len(p.parts)):
        name = f.name.replace(home_slug, "-home")
        name = redact(name, rules, counts).replace("/", "-").replace("<", "").replace(">", "")
        if name != f.name:
            f.rename(f.with_name(name))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("dir")
    ap.add_argument("--private", help="private patterns file (default: land.private_patterns' default)")
    ap.add_argument("--word", action="append", default=[], help="another word to remove (repeatable)")
    a = ap.parse_args(argv)
    private = scrub.private_path(a.private)
    rules = build(private, a.word)
    counts, binary = Counter(), []
    for f in sorted(Path(a.dir).rglob("*")):
        if not f.is_file():
            continue
        data = f.read_bytes()
        if scrub.is_binary(data):
            binary.append(str(f.relative_to(a.dir)))
            continue
        text = data.decode("utf-8", errors="replace")
        new = redact(text, rules, counts)
        if new != text:
            f.write_text(new)
    rename_all(Path(a.dir), rules, counts)
    print("redacted: " + (", ".join(f"{k} {v}" for k, v in counts.most_common()) or "nothing matched"))
    if not private.is_file():
        print(f"note: no private patterns file at {private}; only the generic rules and your own identifiers ran")
    if binary:
        print(f"not checked (binary, {len(binary)}): " + ", ".join(binary[:20]) + (" ..." if len(binary) > 20 else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
