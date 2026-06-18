"""Curated "collections" — fine-grained sub-genres built on TMDb keywords.

Each collection maps a human label to a set of TMDb keyword IDs. In live mode
these IDs are passed straight to TMDb's /discover/movie?with_keywords=... so a
movie belongs to the collection if it carries ANY of those keywords.

`keyword_ids` are pre-resolved from the keyword names (kept for readability)
so we never resolve keywords at request time.
"""

COLLECTIONS = [
    {"slug": "crime-noir", "label": "Crime Noir", "emoji": "\U0001F575️",
     "keywords": ["film noir", "neo-noir", "noir", "femme fatale"],
     "keyword_ids": [9807, 207268, 9016, 155790]},
    {"slug": "anime", "label": "Anime", "emoji": "\U0001F338",
     "keywords": ["anime", "based on anime", "japanese animation", "based on manga"],
     "keyword_ids": [210024, 222243, 339840, 13141]},
    {"slug": "superhero", "label": "Superhero", "emoji": "\U0001F9B8",
     "keywords": ["superhero", "based on comic"],
     "keyword_ids": [9715, 9717]},
    {"slug": "cyberpunk", "label": "Cyberpunk", "emoji": "\U0001F4BE",
     "keywords": ["cyberpunk", "virtual reality", "artificial intelligence"],
     "keyword_ids": [12190, 4563, 350338]},
    {"slug": "heist", "label": "Heist", "emoji": "\U0001F4B0",
     "keywords": ["heist", "robbery", "bank robbery", "con artist"],
     "keyword_ids": [10051, 642, 15363, 10453]},
    {"slug": "zombie", "label": "Zombie", "emoji": "\U0001F9DF",
     "keywords": ["zombie", "undead", "zombie apocalypse"],
     "keyword_ids": [12377, 10327, 186565]},
    {"slug": "time-travel", "label": "Time Travel", "emoji": "⏳",
     "keywords": ["time travel", "time loop", "time machine"],
     "keyword_ids": [4379, 10854, 5455]},
    {"slug": "slasher", "label": "Slasher", "emoji": "\U0001F52A",
     "keywords": ["slasher", "serial killer", "masked killer"],
     "keyword_ids": [12339, 10714, 305666]},
    {"slug": "space", "label": "Space", "emoji": "\U0001F680",
     "keywords": ["space", "outer space", "spacecraft", "astronaut", "space travel"],
     "keyword_ids": [9882, 252634, 1612, 14626, 3801]},
    {"slug": "martial-arts", "label": "Martial Arts", "emoji": "\U0001F94B",
     "keywords": ["martial arts", "kung fu", "samurai", "karate"],
     "keyword_ids": [779, 780, 1462, 3436]},
    {"slug": "coming-of-age", "label": "Coming of Age", "emoji": "\U0001F331",
     "keywords": ["coming of age"],
     "keyword_ids": [10683]},
    {"slug": "dystopian", "label": "Dystopian", "emoji": "\U0001F3DA️",
     "keywords": ["dystopia", "post-apocalyptic", "apocalypse", "dystopian future"],
     "keyword_ids": [4565, 359337, 12332, 4458]},
    {"slug": "biopic", "label": "Biopic", "emoji": "\U0001F3AD",
     "keywords": ["biography", "based on a true story"],
     "keyword_ids": [5565, 9672]},
    {"slug": "spy", "label": "Spy", "emoji": "\U0001F574️",
     "keywords": ["spy", "espionage", "secret agent"],
     "keyword_ids": [470, 5265, 4289]},
    {"slug": "vampire", "label": "Vampire", "emoji": "\U0001F9DB",
     "keywords": ["vampire", "vampire hunter"],
     "keyword_ids": [3133, 342966]},
    {"slug": "monster", "label": "Monster", "emoji": "\U0001F432",
     "keywords": ["monster", "kaiju", "creature feature", "giant monster"],
     "keyword_ids": [1299, 161791, 158126, 11100]},
    {"slug": "holiday", "label": "Holiday", "emoji": "\U0001F384",
     "keywords": ["christmas", "holiday", "santa claus"],
     "keyword_ids": [207317, 65, 1991]},
    {"slug": "sports", "label": "Sports", "emoji": "\U0001F3C6",
     "keywords": ["sport", "boxing", "american football", "baseball", "basketball"],
     "keyword_ids": [333328, 209476, 352822, 1480, 6496]},
]

_BY_SLUG = {c["slug"]: c for c in COLLECTIONS}


def get(slug: str) -> dict | None:
    return _BY_SLUG.get(slug)
