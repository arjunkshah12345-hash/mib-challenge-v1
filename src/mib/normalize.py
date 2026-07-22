from __future__ import annotations

from datetime import date
from difflib import get_close_matches
import re


SPECIES_CODES = {
    "ALPHA_DRACONIAN",
    "ANDROMEDAN",
    "AQUARIAN_MANTIS",
    "ARCTURIAN",
    "CENTAURI_SYNTH",
    "JOVIAN_GASFORM",
    "KAIJU_MICRO",
    "LUNA_SECURID",
    "ORION_GRAYS",
    "SIRIUS_AVIAN",
    "TRIANGULAN",
    "VENUSIAN_MYCELIAL",
}
HOME_WORLDS = {
    "Barnard-c",
    "Eris Relay",
    "Europa Station",
    "Gliese-581g",
    "Kepler-186f",
    "Luyten-b",
    "Mars Dome-7",
    "Proxima-b",
    "Sirius Outpost",
    "Titan Freeport",
    "TRAPPIST-1e",
    "Wolf-1061c",
    "Zeta Reticuli",
}
VISA_CLASSES = {"XW-1", "XW-2", "DIP-1", "MED-3", "TRANSIT-7"}
PURPOSES = {
    "archive audit",
    "cultural exchange",
    "diplomatic",
    "field repair",
    "medical consult",
    "reactor maintenance",
    "research",
    "transit",
    "translation",
    "xenobotany",
}
RISK_FLAGS = {
    "active_warrant",
    "biohazard_red",
    "identity_conflict",
    "illegible_biometrics",
    "memory_tampering",
    "planetary_embargo",
    "rescinded_denial",
    "sponsor_mismatch",
}
FEE_VALUES = {"paid", "waived", "unpaid", "unknown"}
NAME_PREFIXES = (
    "Ari",
    "Ixo",
    "Lu",
    "Mira",
    "Nex",
    "Ori",
    "Qor",
    "Sol",
    "Tek",
    "Vee",
    "Xan",
    "Za",
)
NAME_SUFFIXES = (
    "dane",
    "ix",
    "kesh",
    "mora",
    "nax",
    "quell",
    "rix",
    "tari",
    "ul",
    "vara",
    "voss",
    "zarn",
)
NAME_TOKENS = {prefix + suffix for prefix in NAME_PREFIXES for suffix in NAME_SUFFIXES}
MISSING_MARKERS = {
    "",
    "blank",
    "cut out",
    "illegible",
    "lost",
    "obscured",
    "torn",
    "unreadable",
    "washed out",
    "whiteout",
}


def missing_marker(value: str) -> bool:
    stripped = value.strip()
    normalized = stripped.casefold().strip("[]")
    return (stripped.startswith("[") and stripped.endswith("]")) or normalized in MISSING_MARKERS


def closest(value: str, choices: set[str], cutoff: float = 0.78) -> str | None:
    by_folded = {choice.casefold(): choice for choice in choices}
    normalized = " ".join(value.strip().split()).casefold()
    if normalized in by_folded:
        return by_folded[normalized]
    matches = get_close_matches(normalized, by_folded, n=1, cutoff=cutoff)
    return by_folded[matches[0]] if matches else None


def canonicalize(field: str, value: str | None) -> str | None:
    if value is None:
        return None
    # For risk_flags, bare "illegible"/"unreadable" are flag tokens, not missing markers.
    if field == "risk_flags":
        folded = value.strip().casefold().strip("[]")
        if folded in {"illegible", "unreadable", "garbled"}:
            return "illegible_biometrics"
    if missing_marker(value):
        return None
    cleaned = " ".join(value.strip().split())

    if field == "species_code":
        return closest(cleaned.replace(" ", "_"), SPECIES_CODES)
    if field == "home_world":
        return closest(cleaned, HOME_WORLDS, cutoff=0.7)
    if field == "visa_class":
        compact = re.sub(r"[^a-z0-9]+", "", cleaned.casefold())
        # Only accept clear TRANSIT-7 tokens (must include a 7), not bare "transit"
        # substrings that appear in OCR noise.
        if re.fullmatch(r"(?:transit|tran5it|trnsit|translt|transi[tl])7?", compact) and (
            "7" in compact or cleaned.strip().endswith("7")
        ):
            return "TRANSIT-7"
        if re.search(r"(?:transit|tran5it|trnsit)[\s\-]*7\b", cleaned, re.IGNORECASE):
            return "TRANSIT-7"
        return closest(cleaned.replace(" ", "-"), VISA_CLASSES, cutoff=0.7)
    if field == "declared_purpose":
        return closest(cleaned, PURPOSES)
    if field == "fee_status":
        folded = cleaned.casefold().strip(" \"'`”’")
        # Strobl-style OCR wreckage of "paid" (p/n/m + a/o + i/l/1 + d/c/l).
        key = re.sub(r"[^a-z0-9]", "", folded)
        if re.fullmatch(r"[pnm][ao][i1l][dcl]l?", key):
            return "paid"
        if re.fullmatch(r"w[ao][il1]v(?:ed|d)?", key) or key in {"waived", "waiver"}:
            return "waived"
        if re.fullmatch(r"unp[ao][i1l][dcl]", key) or key == "unpaid":
            return "unpaid"
        return closest(cleaned, FEE_VALUES, cutoff=0.72)
    if field == "sponsor_id":
        match = re.search(r"SPN[- ]?(\d{4})", cleaned, re.IGNORECASE)
        return f"SPN-{match.group(1)}" if match else None
    if field == "arrival_date":
        match = re.search(r"\d{4}-\d{2}-\d{2}", cleaned)
        if not match:
            return None
        try:
            parsed = date.fromisoformat(match.group())
            return parsed.isoformat() if parsed.year in {2025, 2026} else None
        except ValueError:
            return None
    if field == "risk_flags":
        if cleaned.casefold() in {"none", "clear", "no flags", "no flag"}:
            return "none"
        # OCR often splits or mangling flags ("troharard red" → biohazard_red).
        compacted = re.sub(r"[^a-z0-9]+", "", cleaned.casefold())
        parts = re.split(r"[|,]", cleaned.casefold())
        if " " in cleaned:
            parts.extend(cleaned.casefold().split())
            parts.append(cleaned.casefold().replace(" ", "_"))
        recognized: set[str] = set()
        for part in parts:
            token = part.strip().replace(" ", "_")
            if not token or token in {"none", "clear", "flags", "observed"}:
                continue
            hit = closest(token, RISK_FLAGS, cutoff=0.62)
            if hit is None:
                flat = re.sub(r"[^a-z0-9]+", "", token)
                for flag in RISK_FLAGS:
                    flag_flat = flag.replace("_", "")
                    if flat == flag_flat or (len(flat) >= 6 and (flat in flag_flat or flag_flat in flat)):
                        hit = flag
                        break
            if hit is None and (
                "hazard" in token
                or "bioh" in token
                or token.startswith("troh")
                or "hazard" in compacted
            ):
                hit = "biohazard_red"
            if hit is None and (
                "illeg" in token
                or "unread" in token
                or "garbled" in token
                or token in {"biometrics", "biometric"}
            ):
                # Bare "illegible" / "unreadable" on a flags line → illegible_biometrics.
                if "illeg" in token or "unread" in token or "garbled" in token:
                    hit = "illegible_biometrics"
            if hit is None and ("mismatch" in token or "sponsormis" in compacted):
                hit = "sponsor_mismatch"
            if hit is None and ("identity" in token or "idconflict" in compacted):
                hit = "identity_conflict"
            if hit is None and ("rescind" in token or "prior denial" in cleaned.casefold()):
                hit = "rescinded_denial"
            if hit is not None:
                recognized.add(hit)
        if not recognized and compacted:
            for flag in RISK_FLAGS:
                if flag.replace("_", "") in compacted:
                    recognized.add(flag)
        if not recognized and ("illegible" in cleaned.casefold() or "unreadable" in cleaned.casefold()):
            recognized.add("illegible_biometrics")
        return "|".join(sorted(recognized)) if recognized else None
    if field == "applicant_name":
        if not re.fullmatch(r"[A-Za-z]+(?:[ '-][A-Za-z]+)+", cleaned):
            return None
        tokens = re.findall(r"[A-Za-z]+", cleaned)
        corrected = [closest(token, NAME_TOKENS, cutoff=0.72) for token in tokens]
        return " ".join(corrected) if len(corrected) == 2 and all(corrected) else None
    if field == "case_id":
        return cleaned
    return cleaned
