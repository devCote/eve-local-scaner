import re


BAD_WORDS = {
    "local",
    "pilot",
    "channel",
    "member",
    "corp",
    "alliance",
    "system",
    "name",
    "return",
    "def",
    "class",
    "import",
    "from",
    "if",
    "else",
    "for",
    "while",
    "try",
    "except",
    "with",
    "as",
    "none",
    "true",
    "false",
}


BAD_PREFIXES = (
    "return ",
    "def ",
    "class ",
    "import ",
    "from ",
    "if ",
    "else",
    "for ",
    "while ",
    "try",
    "except",
    "with ",
    "print(",
    "self.",
    "layout.",
    "item.",
    "return",
)


def looks_like_code(line: str) -> bool:
    stripped = line.strip()
    lower = stripped.lower()

    if lower in BAD_WORDS:
        return True

    if lower.startswith(BAD_PREFIXES):
        return True

    code_symbols = ["=", "(", ")", "{", "}", "[", "]", ":", ";", '"', "'", ","]

    symbol_count = sum(1 for symbol in code_symbols if symbol in stripped)

    if symbol_count >= 2:
        return True

    if "->" in stripped:
        return True

    if stripped.startswith("#"):
        return True

    return False


def looks_like_pilot_name(name: str) -> bool:
    if len(name) < 3 or len(name) > 40:
        return False

    # EVE names usually contain letters, numbers, spaces, dots, apostrophes, hyphens
    if not re.fullmatch(r"[A-Za-z0-9 .'\-]+", name):
        return False

    # must contain at least one letter
    if not re.search(r"[A-Za-z]", name):
        return False

    return True


def parse_pilots(text: str) -> list[str]:
    lines = text.splitlines()
    pilots = []

    for line in lines:
        name = line.strip()

        if not name:
            continue

        if looks_like_code(name):
            continue

        if not looks_like_pilot_name(name):
            continue

        pilots.append(name)

    return sorted(set(pilots), key=str.lower)
