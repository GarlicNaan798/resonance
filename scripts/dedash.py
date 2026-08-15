"""
One-off: remove em dashes from the project without wrecking the prose.

A blind replace with a comma produces comma splices ("...local files, there is
no setting..."), and a blind replace with a full stop produces fragments
("...the winner. Or tells you..."). Neither is acceptable, so the substitution
looks at what FOLLOWS the dash:

  - a conjunction, preposition, participle or relative pronoun continues the
    same sentence            ->  comma
  - a determiner, pronoun or bare imperative starts a new one
                             ->  full stop, and the next letter is capitalised

En dashes are left alone. They are correct in "2013-15" and "60.8-62.8", and
replacing them would be a different, wrong change.

Not intended to be re-run; kept as the record of what was done.
"""

from __future__ import annotations

import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

EXTS = ("*.ts", "*.tsx", "*.js", "*.mjs", "*.py", "*.md", "*.css", "*.html")
SKIP = ("node_modules", ".next", ".git", "models", "data/raw", "data/interim")

# Continues the sentence: take a comma.
CONTINUE = {
    "and", "but", "or", "nor", "so", "yet", "because", "since", "although",
    "though", "while", "whereas", "which", "who", "whom", "whose", "that",
    "including", "excluding", "with", "without", "for", "from", "at", "in",
    "on", "to", "by", "as", "like", "than", "unless", "until", "if", "when",
    "where", "how", "why", "what", "not", "no", "never", "just", "only",
    "even", "also", "both", "either", "neither", "per", "via", "plus",
    "against", "toward", "towards", "about", "after", "before", "during",
    "despite", "beyond", "across", "between", "among", "under", "over",
    "better", "worse", "more", "less", "far", "well", "roughly", "about",
    "usually", "often", "always", "sometimes", "still", "then", "now",
}

# Starts a new sentence: take a full stop.
NEW_SENTENCE = {
    "the", "there", "this", "these", "those", "it", "we", "you", "they",
    "he", "she", "i", "a", "an", "nobody", "everyone", "everything",
    "anything", "nothing", "someone", "each", "one", "most", "every", "some",
    "many", "few", "all", "our", "your", "their", "its", "his", "her", "my",
    # bare imperatives that show up in this codebase's voice
    "pick", "run", "read", "use", "treat", "send", "keep", "stop", "start",
    "check", "verify", "report", "publish", "recruit", "add", "remove",
    "write", "do", "note", "see", "consider", "assume", "compare",
}


def replace(text: str) -> tuple[str, int]:
    count = 0

    def sub(m: re.Match) -> str:
        nonlocal count
        count += 1
        after = m.group("after")
        first = re.match(r"[A-Za-z']+", after)
        word = first.group(0).lower() if first else ""
        if word in NEW_SENTENCE:
            head = after[0].upper() + after[1:] if after[:1].isalpha() else after
            return ". " + head
        return ", " + after

    # Only horizontal whitespace around the dash. Allowing \s would let a
    # line-final dash swallow the newline and pull the next line up, silently
    # reflowing every wrapped comment in the file.
    text, n1 = re.subn(r"[ 	]*, [ 	]*(?P<after>\S+)", sub, text)

    # A dash left at end of line has nothing to inspect. A comma is safe there
    # because the sentence continues on the next line.
    text, n2 = re.subn(r"[ 	]*, [ 	]*$", ",", text, flags=re.M)

    # HTML entity form, used in the quiz markup.
    text, n3 = re.subn(r"\s*, \s*", ", ", text)

    return text, count + n2 + n3


def main() -> None:
    changed = total = 0
    for ext in EXTS:
        for path in glob.glob(os.path.join(ROOT, "**", ext), recursive=True):
            rel = os.path.relpath(path, ROOT).replace("\\", "/")
            if any(s in rel for s in SKIP):
                continue
            src = open(path, encoding="utf-8").read()
            if ", " not in src:
                continue
            new, n = replace(src)
            if new != src:
                open(path, "w", encoding="utf-8", newline="").write(new)
                changed += 1
                total += n
                print(f"{rel}: {n}")
    print(f"\n{total} em dashes removed across {changed} files")


if __name__ == "__main__":
    main()
