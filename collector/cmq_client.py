"""Thin client for the CMQ bottin internal API.

Endpoint: POST https://www.cmq.org/api/directory
Public, unauthenticated JSON API used by the CMQ member directory front-end.
Standard library only.
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request

API_URL = "https://www.cmq.org/api/directory"

# Identify the collector honestly (transparency / good faith): who we are, a page
# explaining the project, and a contact address so the CMQ can reach us rather
# than silently block us.
USER_AGENT = (
    "medecins-sanctionnes/1.0 "
    "(+https://medecinssanctionnes.ca/a-propos; contact@medecinssanctionnes.ca)"
)


class ApiError(Exception):
    """Transient/network/5xx error worth retrying."""


class RateLimited(ApiError):
    """Server signalled throttling (HTTP 429)."""


class PermanentError(Exception):
    """4xx (other than 429) — retrying will not help."""


def _post(payload: dict, timeout: float = 20.0):
    """POST a payload and return (status_code, parsed_json_or_None)."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        API_URL,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            body = resp.read()
            if status == 204 or not body:
                return status, None
            return status, json.loads(body.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise RateLimited(f"HTTP 429") from exc
        if 500 <= exc.code < 600:
            raise ApiError(f"HTTP {exc.code}") from exc
        raise PermanentError(f"HTTP {exc.code}") from exc
    except (urllib.error.URLError, socket.timeout, ConnectionError, TimeoutError) as exc:
        # Includes connection resets / aborts observed under sustained load.
        raise ApiError(f"NET {exc}") from exc


def _post_raw(payload: dict, timeout: float = 30.0) -> str:
    """POST and return the raw response body as text (for non-JSON endpoints)."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        API_URL,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def get_decision_document_b64(document_id: int, timeout: float = 30.0) -> str:
    """Return the base64-encoded PDF text for a disciplinary decision document."""
    return _post_raw(
        {
            "language": "fr",
            "method": "getDisciplinaryDecisionDocument",
            "documentId": document_id,
        },
        timeout=timeout,
    )


def get_specialties(language: str = "fr", timeout: float = 20.0) -> list:
    """Return the list of {specialtyId, specialtyName} for the given language."""
    raw = _post_raw({"method": "getSpecialties", "language": language}, timeout=timeout)
    return json.loads(raw)


# getNoticeListing "category" ids (the /fr/bottin/avis feeds, last ~3 months).
NOTICE_CATEGORIES = {
    1: "radiation",
    2: "limitation",
    3: "suspension",
    4: "new_members",
    5: "deceased",
    6: "revocation",
    7: "radiation_non_payment",  # administrative, not a disciplinary finding
}
# Disciplinary notice categories worth harvesting incrementally.
DISCIPLINARY_NOTICE_CATEGORIES = (1, 2, 3, 6)


def get_notice_listing(category: int, language: str = "fr", timeout: float = 20.0) -> list:
    """Recent public notices (~last 3 months) for a category.

    Each item: {noticeId, physicianId, formattedLabel, number, specialtyLabel,
    city, date}. Powers the incremental collector — a cheap "what's new" feed.
    """
    raw = _post_raw(
        {"method": "getNoticeListing", "language": language, "category": category},
        timeout=timeout)
    return json.loads(raw)


def get_physician_details(physician_id: int, timeout: float = 20.0):
    """Full record for one physician. Returns (status, body).

    status 200 -> body is the record dict.
    status 204 -> body is None (no physician at this id).

    Note: only reflects *currently active* sanctions; the narrative for a served
    temporary radiation/suspension drops off. Use disciplinary files for history.
    """
    return _post(
        {
            "language": "fr",
            "method": "getPhysicianDetails",
            "physicianId": physician_id,
        },
        timeout=timeout,
    )


def get_physician_history(physician_id: int, timeout: float = 20.0):
    """Membership + discipline-history summary. Returns (status, body).

    Body carries pastDecisionCount / currentDecisionCount, which flag whether a
    physician has any disciplinary decisions (even long-expired ones).
    """
    return _post(
        {
            "language": "fr",
            "method": "getPhysicianHistory",
            "physicianId": physician_id,
        },
        timeout=timeout,
    )


def search_disciplinary_files(
    number: str = "",
    lastname: str = "",
    firstname: str = "",
    file_number: str = "",
    language: str = "fr",
    timeout: float = 20.0,
):
    """Permanent disciplinary case history. Returns (status, list).

    Persists for decades. Each entry has items[] with decisions[], where each
    decision carries a date, precision, and links to the full published ruling
    (linkQuebec = SOQUIJ, linkCanada = CanLII, or a CMQ documentId).
    Requires at least one of number/lastname/firstname (empty -> 0 results).
    """
    return _post(
        {
            "language": language,
            "method": "searchDisciplinaryFiles",
            "number": number,
            "lastname": lastname,
            "firstname": firstname,
            "fileNumber": file_number,
        },
        timeout=timeout,
    )


def search_physicians(
    lastname: str = "",
    firstname: str = "",
    number: str = "",
    city: str = "",
    specialty_id: int = 0,
    unlisted: bool = False,
    language: str = "fr",
    timeout: float = 20.0,
):
    """Search the directory. Returns (status, list_of_summary_dicts)."""
    return _post(
        {
            "language": language,
            "method": "searchPhysicians",
            "number": number,
            "lastname": lastname,
            "firstname": firstname,
            "city": city,
            "specialtyId": specialty_id,
            "unlisted": unlisted,
        },
        timeout=timeout,
    )


# Sanction categories present in getPhysicianDetails. Each is {"items": [...], "count": N}.
SANCTION_FIELDS = (
    "strikingOffTheRoll",  # radiations
    "suspensions",
    "revocations",
    "restrictions",  # limitations
    "commitments",  # engagements
)


def sanction_counts(record: dict) -> dict:
    """Return {field: count} for the sanction categories with count > 0."""
    counts = {}
    for field in SANCTION_FIELDS:
        value = record.get(field)
        if isinstance(value, dict):
            n = value.get("count", 0) or 0
            if n > 0:
                counts[field] = n
    return counts


def is_sanctioned(record: dict) -> bool:
    return bool(sanction_counts(record))


def flatten_disciplinary_files(files: list) -> list:
    """Flatten searchDisciplinaryFiles output into a list of case dicts."""
    cases = []
    for entry in files or []:
        for item in entry.get("items", []) or []:
            cases.append(item)
    return cases


def decision_links(files: list) -> list:
    """Collect all external ruling links (SOQUIJ / CanLII) from disciplinary files."""
    links = []
    for case in flatten_disciplinary_files(files):
        for dec in case.get("decisions", []) or []:
            for key in ("linkQuebec", "linkCanada"):
                url = (dec.get(key) or "").strip()
                if url:
                    links.append({"case": case.get("number"), "date": dec.get("date"), "url": url})
    return links


def has_disciplinary_history(details: dict, history: dict, files: list) -> bool:
    """True if the physician has any current OR past disciplinary trace."""
    if details and is_sanctioned(details):
        return True
    if history:
        if (history.get("pastDecisionCount") or 0) > 0:
            return True
        if (history.get("currentDecisionCount") or 0) > 0:
            return True
    if flatten_disciplinary_files(files):
        return True
    return False
