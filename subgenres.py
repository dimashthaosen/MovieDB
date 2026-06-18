"""Curated "collections" — fine-grained sub-genres built on TMDb keywords.

Each collection maps a human label to a set of TMDb keyword names. A movie
belongs to the collection if it carries ANY of those keywords. This is what
lets us offer "Crime Noir" or "Anime" instead of just broad "Crime"/"Animation".

Keyword names are matched case-insensitively against the `keywords` table
populated by enrich_keywords.py. Collections with no movies in the current
database are hidden by the API, so this list can stay aspirational.
"""

COLLECTIONS = [
    {"slug": "crime-noir", "label": "Crime Noir", "emoji": "\U0001F575️",
     "keywords": ["film noir", "neo-noir", "noir", "hardboiled", "femme fatale", "private detective"]},
    {"slug": "anime", "label": "Anime", "emoji": "\U0001F338",
     "keywords": ["anime", "based on anime", "japanese animation", "based on manga"]},
    {"slug": "superhero", "label": "Superhero", "emoji": "\U0001F9B8",
     "keywords": ["superhero", "based on comic", "based on comic book", "marvel comic", "dc comics", "marvel cinematic universe"]},
    {"slug": "cyberpunk", "label": "Cyberpunk", "emoji": "\U0001F4BE",
     "keywords": ["cyberpunk", "virtual reality", "artificial intelligence", "dystopian future"]},
    {"slug": "heist", "label": "Heist", "emoji": "\U0001F4B0",
     "keywords": ["heist", "robbery", "bank robbery", "con artist"]},
    {"slug": "zombie", "label": "Zombie", "emoji": "\U0001F9DF",
     "keywords": ["zombie", "undead", "zombie apocalypse"]},
    {"slug": "time-travel", "label": "Time Travel", "emoji": "⏳",
     "keywords": ["time travel", "time loop", "time machine"]},
    {"slug": "slasher", "label": "Slasher", "emoji": "\U0001F52A",
     "keywords": ["slasher", "serial killer", "masked killer"]},
    {"slug": "space", "label": "Space", "emoji": "\U0001F680",
     "keywords": ["space", "outer space", "spacecraft", "astronaut", "space travel"]},
    {"slug": "martial-arts", "label": "Martial Arts", "emoji": "\U0001F94B",
     "keywords": ["martial arts", "kung fu", "samurai", "karate"]},
    {"slug": "coming-of-age", "label": "Coming of Age", "emoji": "\U0001F331",
     "keywords": ["coming of age"]},
    {"slug": "dystopian", "label": "Dystopian", "emoji": "\U0001F3DA️",
     "keywords": ["dystopia", "post-apocalyptic", "apocalypse", "post-apocalyptic future"]},
    {"slug": "biopic", "label": "Biopic", "emoji": "\U0001F3AD",
     "keywords": ["biography", "based on a true story", "based on true story"]},
    {"slug": "spy", "label": "Spy", "emoji": "\U0001F574️",
     "keywords": ["spy", "espionage", "secret agent"]},
    {"slug": "vampire", "label": "Vampire", "emoji": "\U0001F9DB",
     "keywords": ["vampire", "vampire hunter"]},
    {"slug": "monster", "label": "Monster", "emoji": "\U0001F432",
     "keywords": ["monster", "kaiju", "creature feature", "giant monster"]},
    {"slug": "holiday", "label": "Holiday", "emoji": "\U0001F384",
     "keywords": ["christmas", "holiday", "santa claus"]},
    {"slug": "sports", "label": "Sports", "emoji": "\U0001F3C6",
     "keywords": ["sport", "boxing", "football", "baseball", "basketball"]},
]

_BY_SLUG = {c["slug"]: c for c in COLLECTIONS}


def get(slug: str) -> dict | None:
    return _BY_SLUG.get(slug)
