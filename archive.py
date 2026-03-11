import sqlite3
from pathlib import Path

class DownloadArchive:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS downloads (
                        video_id TEXT,
                        playlist_url TEXT,
                        file_path TEXT,
                        PRIMARY KEY (video_id, playlist_url)
                    )
                """)
                conn.commit()
                print("[System] Database initialized.")
        except sqlite3.Error as e:
            print(f"[Error] Database initialization failed: {e}")

    def add(self, video_id: str, playlist_url: str, file_path: str, conn: sqlite3.Connection = None) -> None:
        local_conn = None
        try:
            if conn is None:
                local_conn = self._connect()
                conn = local_conn

            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO downloads (video_id, playlist_url, file_path)
                VALUES (?, ?, ?)
            """, (video_id, playlist_url, str(file_path)))
            conn.commit()
        except sqlite3.Error as e:
            print(f"[Error] DB Write Failed: {e}")
        finally:
            if local_conn:
                local_conn.close()

    def remove(self, video_id: str, playlist_url: str, conn: sqlite3.Connection = None) -> None:
        local_conn = None
        try:
            if conn is None:
                local_conn = self._connect()
                conn = local_conn

            cursor = conn.cursor()
            cursor.execute("DELETE FROM downloads WHERE video_id = ? AND playlist_url = ?", (video_id, playlist_url))
            conn.commit()
        except sqlite3.Error as e:
            print(f"[Error] DB Delete Failed: {e}")
        finally:
            if local_conn:
                local_conn.close()

    def get_map(self, playlist_url: str, conn: sqlite3.Connection = None) -> dict:
        local_conn = None
        try:
            if conn is None:
                local_conn = self._connect()
                conn = local_conn

            cursor = conn.cursor()
            cursor.execute("SELECT video_id, file_path FROM downloads WHERE playlist_url = ?", (playlist_url,))
            return {row[0]: row[1] for row in cursor.fetchall()}
        except sqlite3.Error as e:
            print(f"[Error] DB Read Failed: {e}")
            return {}
        finally:
            if local_conn:
                local_conn.close()
