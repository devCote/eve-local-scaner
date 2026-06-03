def parse_pilots(text: str) -> list[str]:
    lines = text.splitlines()
    pilots = []

    bad_words = {
        "local", "pilot", "channel", "member",
        "corp", "alliance", "system", "name"
    }

    for line in lines:
        name = line.strip()

        if not name:
            continue

        if len(name) < 3 or len(name) > 40:
            continue

        if name.lower() in bad_words:
            continue

        pilots.append(name)

    return sorted(set(pilots), key=str.lower)
