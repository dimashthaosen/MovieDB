"""Seed the database with a curated set of well-known movies.

This lets you explore the app immediately without a TMDb API key.
Run:  python seed_demo.py   (safe to re-run; it upserts)

Data (year / runtime / rating / language / genres) is hand-curated from
general knowledge. Posters are left empty — the UI renders a styled
gradient placeholder for those, and real TMDb posters will fill in if you
later run `python ingest.py`.
"""

from db import get_connection, init_db

# TMDb's canonical genre ids, so this demo data lines up with real ingests.
GENRES = {
    "Action": 28, "Adventure": 12, "Animation": 16, "Comedy": 35,
    "Crime": 80, "Documentary": 99, "Drama": 18, "Family": 10751,
    "Fantasy": 14, "History": 36, "Horror": 27, "Music": 10402,
    "Mystery": 9648, "Romance": 10749, "Science Fiction": 878,
    "TV Movie": 10770, "Thriller": 53, "War": 10752, "Western": 37,
}

# (title, year, rating, vote_count, runtime, language, [genres], overview)
MOVIES = [
    ("The Shawshank Redemption", 1994, 8.7, 26000, 142, "en",
     ["Drama", "Crime"],
     "Two imprisoned men bond over years, finding solace and redemption through acts of common decency."),
    ("The Godfather", 1972, 8.7, 19000, 175, "en",
     ["Drama", "Crime"],
     "The aging patriarch of a crime dynasty transfers control to his reluctant son."),
    ("The Dark Knight", 2008, 8.5, 31000, 152, "en",
     ["Action", "Crime", "Drama", "Thriller"],
     "Batman faces the Joker, a criminal mastermind bent on plunging Gotham into anarchy."),
    ("Pulp Fiction", 1994, 8.5, 27000, 154, "en",
     ["Thriller", "Crime"],
     "The lives of two hitmen, a boxer, and a gangster's wife intertwine in four tales of violence."),
    ("Forrest Gump", 1994, 8.5, 26000, 142, "en",
     ["Comedy", "Drama", "Romance"],
     "A slow-witted but kind-hearted man witnesses and influences decades of American history."),
    ("Inception", 2010, 8.4, 35000, 148, "en",
     ["Action", "Science Fiction", "Adventure"],
     "A thief who steals corporate secrets through dream-sharing is given the inverse task: planting an idea."),
    ("Fight Club", 1999, 8.4, 28000, 139, "en",
     ["Drama"],
     "An insomniac office worker and a soap salesman form an underground fight club that spirals out of control."),
    ("The Matrix", 1999, 8.2, 24000, 136, "en",
     ["Action", "Science Fiction"],
     "A hacker learns that reality is a simulation and joins a rebellion against its machine overlords."),
    ("Goodfellas", 1990, 8.5, 12000, 145, "en",
     ["Drama", "Crime"],
     "The rise and fall of a mob associate over three decades of life in the Mafia."),
    ("Interstellar", 2014, 8.4, 33000, 169, "en",
     ["Adventure", "Drama", "Science Fiction"],
     "Explorers travel through a wormhole in search of a new home for a dying humanity."),
    ("The Lord of the Rings: The Fellowship of the Ring", 2001, 8.4, 23000, 178, "en",
     ["Adventure", "Fantasy", "Action"],
     "A hobbit sets out to destroy a powerful ring and save Middle-earth from a dark lord."),
    ("The Lord of the Rings: The Return of the King", 2003, 8.5, 22000, 201, "en",
     ["Adventure", "Fantasy", "Action"],
     "The final confrontation against Sauron as Frodo nears the end of his quest to destroy the One Ring."),
    ("Parasite", 2019, 8.5, 17000, 133, "ko",
     ["Comedy", "Thriller", "Drama"],
     "A poor family schemes to become employed by a wealthy household, with dark consequences."),
    ("Spirited Away", 2001, 8.5, 15000, 125, "ja",
     ["Animation", "Family", "Fantasy"],
     "A young girl wanders into a spirit world and must work to free her parents and find her way home."),
    ("The Lion King", 1994, 8.3, 18000, 88, "en",
     ["Family", "Animation", "Drama"],
     "A young lion prince flees his kingdom after his father's death, only to learn to reclaim his throne."),
    ("Gladiator", 2000, 8.2, 18000, 155, "en",
     ["Action", "Drama", "Adventure"],
     "A betrayed Roman general rises through the gladiatorial arena to avenge his murdered family."),
    ("The Departed", 2006, 8.2, 14000, 151, "en",
     ["Drama", "Thriller", "Crime"],
     "An undercover cop and a mole in the police race to identify each other within the Boston mob."),
    ("Whiplash", 2014, 8.4, 15000, 107, "en",
     ["Drama", "Music"],
     "A young drummer enrolls at a cutthroat conservatory under a ruthless, abusive instructor."),
    ("The Prestige", 2006, 8.2, 16000, 130, "en",
     ["Drama", "Mystery", "Science Fiction", "Thriller"],
     "Two rival magicians engage in an escalating battle to create the ultimate illusion."),
    ("Saving Private Ryan", 1998, 8.2, 15000, 169, "en",
     ["Drama", "History", "War"],
     "A squad of soldiers ventures behind enemy lines to retrieve a paratrooper whose brothers have died."),
    ("Schindler's List", 1993, 8.6, 15000, 195, "en",
     ["Drama", "History", "War"],
     "A German industrialist saves the lives of more than a thousand Jewish refugees during the Holocaust."),
    ("The Green Mile", 1999, 8.5, 16000, 189, "en",
     ["Fantasy", "Drama", "Crime"],
     "Death row guards encounter a gentle giant with a mysterious gift of healing."),
    ("Se7en", 1995, 8.4, 20000, 127, "en",
     ["Crime", "Mystery", "Thriller"],
     "Two detectives hunt a serial killer who uses the seven deadly sins as his motifs."),
    ("Spider-Man: Into the Spider-Verse", 2018, 8.4, 14000, 117, "en",
     ["Action", "Adventure", "Animation", "Science Fiction"],
     "Teenager Miles Morales becomes Spider-Man and teams with spider-heroes from other dimensions."),
    ("Joker", 2019, 8.1, 24000, 122, "en",
     ["Crime", "Thriller", "Drama"],
     "A failed comedian descends into madness and becomes a symbol of chaos in Gotham City."),
    ("Avengers: Infinity War", 2018, 8.2, 28000, 149, "en",
     ["Adventure", "Action", "Science Fiction"],
     "The Avengers unite to stop Thanos from collecting the Infinity Stones and erasing half of life."),
    ("Coco", 2017, 8.2, 19000, 105, "en",
     ["Animation", "Family", "Music", "Adventure"],
     "A boy journeys to the Land of the Dead to unlock the truth behind his family's ban on music."),
    ("Your Name", 2016, 8.5, 11000, 106, "ja",
     ["Romance", "Animation", "Drama"],
     "Two teenagers who have never met find themselves mysteriously swapping bodies across time and space."),
    ("Django Unchained", 2012, 8.2, 25000, 165, "en",
     ["Drama", "Western"],
     "A freed slave teams with a bounty hunter to rescue his wife from a brutal plantation owner."),
    ("The Wolf of Wall Street", 2013, 8.0, 24000, 180, "en",
     ["Crime", "Drama", "Comedy"],
     "The rise and spectacular fall of a corrupt stockbroker fueled by greed and excess."),
    ("Mad Max: Fury Road", 2015, 7.6, 22000, 120, "en",
     ["Action", "Adventure", "Science Fiction"],
     "In a post-apocalyptic wasteland, a drifter and a rebel flee a tyrant across the desert."),
    ("Blade Runner 2049", 2017, 7.6, 14000, 164, "en",
     ["Science Fiction", "Drama"],
     "A young blade runner uncovers a secret that could plunge society into chaos and seeks a vanished man."),
    ("Dune", 2021, 7.8, 12000, 155, "en",
     ["Science Fiction", "Adventure"],
     "A noble heir becomes entangled in a deadly struggle for control of the galaxy's most valuable resource."),
    ("Oppenheimer", 2023, 8.1, 9000, 181, "en",
     ["Drama", "History"],
     "The story of J. Robert Oppenheimer and his role in developing the atomic bomb."),
    ("Everything Everywhere All at Once", 2022, 7.8, 8500, 139, "en",
     ["Action", "Adventure", "Science Fiction", "Comedy"],
     "An overwhelmed laundromat owner discovers she must connect with parallel-universe versions of herself."),
    ("Toy Story", 1995, 8.0, 17000, 81, "en",
     ["Animation", "Comedy", "Family"],
     "A cowboy doll is threatened when a new spaceman action figure becomes a boy's favorite toy."),
    ("Back to the Future", 1985, 8.3, 19000, 116, "en",
     ["Adventure", "Comedy", "Science Fiction", "Family"],
     "A teenager is accidentally sent thirty years into the past in a time-traveling DeLorean."),
    ("Alien", 1979, 8.2, 14000, 117, "en",
     ["Horror", "Science Fiction"],
     "The crew of a spaceship is hunted by a deadly extraterrestrial after investigating a distress signal."),
    ("The Silence of the Lambs", 1991, 8.3, 16000, 119, "en",
     ["Crime", "Drama", "Thriller", "Horror"],
     "A young FBI cadet seeks the help of an imprisoned cannibal to catch another serial killer."),
    ("Spider-Man: No Way Home", 2021, 8.0, 20000, 148, "en",
     ["Action", "Adventure", "Science Fiction"],
     "Peter Parker's identity is exposed, and his plea to undo it tears open the multiverse."),
]


def seed() -> None:
    init_db()
    conn = get_connection()
    with conn:
        # Genres
        conn.executemany(
            "INSERT INTO genres (id, name) VALUES (?, ?) "
            "ON CONFLICT(id) DO UPDATE SET name = excluded.name",
            [(gid, name) for name, gid in GENRES.items()],
        )

        for movie_id, m in enumerate(MOVIES, start=1):
            title, year, rating, votes, runtime, lang, genres, overview = m
            popularity = round(rating * votes / 1000, 1)
            conn.execute(
                """
                INSERT INTO movies
                    (id, title, release_year, rating, vote_count, runtime,
                     original_language, overview, poster_url, popularity)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title, release_year=excluded.release_year,
                    rating=excluded.rating, vote_count=excluded.vote_count,
                    runtime=excluded.runtime,
                    original_language=excluded.original_language,
                    overview=excluded.overview, popularity=excluded.popularity
                """,
                (movie_id, title, year, rating, votes, runtime, lang, overview, popularity),
            )
            conn.execute("DELETE FROM movie_genres WHERE movie_id = ?", (movie_id,))
            conn.executemany(
                "INSERT OR IGNORE INTO movie_genres (movie_id, genre_id) VALUES (?, ?)",
                [(movie_id, GENRES[g]) for g in genres],
            )

    conn.close()
    print(f"Seeded {len(MOVIES)} movies and {len(GENRES)} genres into the database.")


if __name__ == "__main__":
    seed()
