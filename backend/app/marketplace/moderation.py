"""Prohibited-item keyword check on listing text (requirements §5). A match blocks the listing outright;
anything the list misses is caught by user reports and moderators. Extend the list as reports come in."""

import re

from app.errors import AppError

# Whole-word, case-insensitive. Includes common Tok Pisin / PNG terms. Avoid bare words with innocent uses
# ("gun" in "glue gun", "weed" in "weed killer"); prefer specific terms.
PROHIBITED_TERMS = (
    # weapons
    "firearm",
    "firearms",
    "rifle",
    "pistol",
    "shotgun",
    "homemade gun",
    "home made gun",
    "ammo",
    "ammunition",
    "bullets",
    "shotgun shells",
    "explosive",
    "explosives",
    "dynamite",
    "detonator",
    "grenade",
    # drugs
    "marijuana",
    "cannabis",
    "spak brus",
    "cocaine",
    "heroin",
    "methamphetamine",
    "meth",
    # alcohol / tobacco / betel nut (banned in v1)
    "beer",
    "whisky",
    "whiskey",
    "vodka",
    "rum",
    "alcohol",
    "home brew",
    "homebrew",
    "cigarettes",
    "cigarette",
    "vape",
    "buai",
    "betel nut",
    "daka",
    # wildlife (protected species)
    "bird of paradise",
    "birds of paradise",
    "cassowary",
    "tree kangaroo",
    "turtle shell",
    "dugong",
    # documents, SIMs, fakes
    "passport",
    "nid card",
    "birth certificate",
    "sim card",
    "sim cards",
    "counterfeit",
    "fake money",
    # adult
    "porn",
    "escort",
    # money products
    "crypto",
    "bitcoin",
    "loan shark",
    "money doubling",
)

_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(t) for t in sorted(PROHIBITED_TERMS, key=len, reverse=True)) + r")\b", re.IGNORECASE
)


def find_prohibited(*texts: str) -> str | None:
    for text in texts:
        match = _PATTERN.search(text or "")
        if match:
            return match.group(1).lower()
    return None


def check_listing_text(title: str, description: str) -> None:
    term = find_prohibited(title, description)
    if term:
        raise AppError(
            f'Listings cannot include "{term}". McXus does not allow weapons, drugs, alcohol, tobacco, betel nut, '
            "protected wildlife, documents or adult content. If this is a mistake, change the wording.",
            code="prohibited_content",
        )
