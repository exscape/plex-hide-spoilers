import sys
import datetime
import sqlite3
from urllib.request import pathname2url

class Database:
    def __init__(self, verbose = False, debug = False):
        self.verbose = verbose
        self.debug = debug
        if self.debug:
            self.verbose = True

        # Prevent multiple queries to add a single show
        self.added_shows = set()

        try:
            dbname = "summaries.sqlite3"
            dburi = 'file:{}?mode=rw'.format(pathname2url(dbname))
            self.con = sqlite3.connect(dburi, uri=True)
            if self.debug: print("Database loaded successfully")
        except sqlite3.OperationalError:
            if self.debug: print("Database not found, creating it")
            self.create_database()

            dburi = 'file:{}?mode=rw'.format(pathname2url(dbname))
            self.con = sqlite3.connect(dburi, uri=True)
            if self.debug: print("Database created successfully")

    def create_database(self):
        query_episodes = """
        CREATE TABLE episodes (
            id TEXT PRIMARY KEY,
            season INTEGER,
            episode INTEGER,
            title TEXT,
            summary TEXT,
            show TEXT,
            FOREIGN KEY (show) REFERENCES shows (id)
        );
        """
        query_shows = """
        CREATE TABLE shows (
            id TEXT PRIMARY KEY,
            title TEXT,
            ignore BOOLEAN
        );
        """
        try:
            con = sqlite3.connect("summaries.sqlite3")
            cur = con.cursor()
            cur.execute(query_episodes)
            cur.execute(query_shows)
            con.close()
        except Exception as e:
            print(f"Unable to create database file (summaries.sqlite3): {e}")
            sys.exit(32)

    def _add_show(self, id, title):
        """ Add a show, WITHOUT committing """
        data = ( {"id": id, "title": title} )
        cur = self.con.cursor()
        cur.execute("INSERT OR IGNORE INTO shows (id, title, ignore) VALUES (:id, :title, 0)", data)

    def add_episode(self, episode, season, show):
        """ Add an episode, WITHOUT committing """

        if not show.guid in self.added_shows:
            self._add_show(show.guid, show.title)
            self.added_shows.add(show.guid)

        data = ( {"id": episode.guid, "season": season.index, "episode": episode.index,
              "title": episode.title, "summary": episode.summary, "show": show.guid} )

        cur = self.con.cursor()
        cur.execute("INSERT OR IGNORE INTO episodes (id, season, episode, title, summary, show) VALUES (:id, :season, :episode, :title, :summary, :show)", data)
        if self.verbose and cur.rowcount > 0: print(f"Inserted {show.title} season {season.index} episode {episode.index}: {episode.title}")

        return cur.rowcount != 0

    def commit_changes(self):
        self.con.commit()

        if self.verbose:
            cur = self.con.cursor()
            cur.execute("SELECT COUNT(*) FROM shows")
            shows = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM episodes")
            episodes = cur.fetchone()[0]
            if self.debug: print(f"Database contains {episodes} episodes in {shows} shows")

    def summary_for_episode(self, episode_guid):
        cur = self.con.cursor()

        cur.execute("SELECT summary FROM episodes WHERE id = ?", (episode_guid,))
        if cur.rowcount == 0:
            raise KeyError(f"No summary in database for episode with GUID {episode_guid}")
        else:
            summary = cur.fetchone()[0]
            if len(summary) > 0:
                return summary
            else:
                raise KeyError(f"No summary in database for episode with GUID {episode_guid}")
