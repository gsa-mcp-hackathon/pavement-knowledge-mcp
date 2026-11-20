"""Compare report identifiers across catalog and index formatting."""
import re


def same_report(left: object, right: object) -> bool:
    def normalize(value: object) -> str:
        return re.sub(r"[-_\s]", "", str(value or "")).casefold()
    return bool(normalize(left)) and normalize(left) == normalize(right)
