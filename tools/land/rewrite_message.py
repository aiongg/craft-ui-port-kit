"""rewrite_message.py: apply a `git filter-repo` rules file to a commit message, leaving trailer lines alone.

Used by lib.sh `land_rewrite` as the body of `--message-callback`:
    import sys; sys.path.insert(0, DIR); import rewrite_message; return rewrite_message.apply(message, RULES_FILE)

Rules: `OLD==>NEW` (literal) or `regex:PATTERN==>NEW`, one per line; `#` lines are ignored. A trailer is a line of the
message's last paragraph, when every line of that paragraph reads `Key: value` (`Co-authored-by`, `Signed-off-by`):
trailers keep their text, because identities are reported by the scan, never rewritten.
"""
import re
import sys

TRAILER = re.compile(rb"^[A-Za-z][A-Za-z0-9-]*:\s")


def load(path):
    rules = []
    for line in open(path, "rb").read().splitlines():
        if not line.strip() or line.lstrip().startswith(b"#"):
            continue
        old, sep, new = line.partition(b"==>")
        if not sep:
            continue
        if old.startswith(b"regex:"):
            rules.append((re.compile(old[6:]), new))
        else:
            rules.append((re.compile(re.escape(old)), new.replace(b"\\", b"\\\\")))
    return rules


def apply(message, rules_path):
    rules = load(rules_path)
    lines = message.split(b"\n")
    body = lines[:]
    while body and not body[-1].strip():
        body.pop()
    start = len(body)
    while start > 0 and body[start - 1].strip():
        start -= 1
    last = body[start:]
    keep_from = len(lines) + 1
    # The first paragraph is the subject, never a trailer block.
    if start > 0 and last and all(TRAILER.match(x) for x in last):
        keep_from = start
    out = []
    for i, line in enumerate(lines):
        if i < keep_from:
            for rx, new in rules:
                line = rx.sub(new, line)
        out.append(line)
    return b"\n".join(out)


if __name__ == "__main__":
    sys.stdout.buffer.write(apply(sys.stdin.buffer.read(), sys.argv[1]))
