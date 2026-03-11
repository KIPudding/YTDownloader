import json
import re
import subprocess
import sys
import threading
import yt_dlp

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from archive import DownloadArchive


BASE_DIR = Path(__file__).parent.resolve()
DATA_FILE = BASE_DIR / "app_data.json"
DB_FILE = BASE_DIR / "archive.db"


print_lock = threading.Lock()
update_lock = threading.Lock()

def thread_safe_print(msg) -> None:
    with print_lock:
        print(msg)


def sanitize_filename(name) -> str:
    name = re.sub(r"[^A-Za-z0-9 _-]", "", name)
    name = name.strip()
    name = name.replace(" ", "_")
    return name


def update_ytdlp() -> None:
    with update_lock:
        print("\n[System] Download error detected. Attempting to update yt-dlp...")
        try:
            # Runs the pip upgrade
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp", "--quiet"]
            )
            print("[System] yt-dlp update complete. Close and restart the program to apply changes.")
        except Exception as e:
            print(f"[Error] Failed to update yt-dlp: {e}")


def fetch_playlist_entries(url: str) -> list | None:
    ydl_opts = {
        'extract_flat': 'in_playlist', # Only get metadata, don't download
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info.get('entries', [])
    except Exception as e:
        print(f"[Error] Could not fetch playlist info: {e}")
        return None


def download_audio(youtube_url, download_folder, use_video_id, thumbnail, playlist_url=None, archive=None) -> None:
    # Create download directory
    download_path = Path(download_folder)
    try:
        download_path.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"[Error] Could not create directory: {e}")
        return

    # set filename format
    filename_tmpl = '%(title)s [%(id)s].%(ext)s' if use_video_id else '%(title)s.%(ext)s'
    out_tmpl = str(download_path / filename_tmpl)

    # configure yt-dlp options
    ydl_opts = {
        'format': 'bestaudio[ext=m4a]/best',
        'outtmpl': out_tmpl,
        'quiet': True,
        'verbose': False,
        'no_warnings': True,
        'no_progress': True,
        'ignoreerrors': True,
        'writethumbnail': thumbnail,
        'postprocessors': [{'key': 'FFmpegMetadata'}],
    }

    # add thumbnail if requested
    if thumbnail:
        ydl_opts['postprocessors'].append({'key': 'EmbedThumbnail'})

    # Check for local FFmpeg
    ffmpeg_dir = BASE_DIR / "FFmpeg" / "bin"
    ffmpeg_binary = ffmpeg_dir / "ffmpeg.exe"
    if ffmpeg_binary.exists():
        ydl_opts['ffmpeg_location'] = str(ffmpeg_dir)
    else:
        thread_safe_print("[Warning] Local FFmpeg binary not found. Relying on system PATH.")

    # run Download
    try:
        thread_safe_print(f"[Queueing] {youtube_url}")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Use extract_info with download=True to get metadata back for the DB
            info = ydl.extract_info(youtube_url, download=True)
            
            # Save to Database if part of a tracked playlist
            if archive and playlist_url:
                # Handle cases where URL might be a list (though usually it's single here)
                entries = info['entries'] if 'entries' in info else [info]
                
                for entry in entries:
                    vid = entry.get('id')
                    final_path = ydl.prepare_filename(entry)
                    archive.add(vid, playlist_url, final_path)

            thread_safe_print(f"[Finished] {youtube_url}")
    
    except Exception as e:
        if "returned non-zero exit status" in str(e):
             thread_safe_print(f"[Error] Download failed for {youtube_url}")
        else:
             thread_safe_print(f"[Error] Download failed. Triggering update")
             update_ytdlp()



def get_metadata(url) -> str | None:
    ydl_opts = {
        'extract_flat': True,
        'quiet': True,
        'no_warnings': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info.get('title', 'Unknown Title')
    except Exception as e:
        print(f"[Error] Could not fetch name: {e}")
        return None



def load_stored_data() -> dict:
    if not DATA_FILE.exists():
        return {"playlists": []}

    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

        for item in data.get("playlists", []):
            if "path" in item:
                item["path"] = Path(item["path"])

        return data

    except:
        return {"playlists": []}


def save_stored_data(data) -> None:
    serializable = {"playlists": []}

    for item in data["playlists"]:
        serializable["playlists"].append({
            "url": item["url"],
            "name": item["name"],
            "path": str(item["path"])
        })

    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(serializable, f, indent=4)




if __name__ == "__main__":
    # Initialize SQLite Database
    archive = DownloadArchive(DB_FILE)

    # Settings
    stored_data = load_stored_data()

    settings = {
        'path': BASE_DIR,
        'id': False,
        'thumb': False
    }

    print(f"Save Directory: {settings['path']}")
    print("Type 'help' for a list of commands.")

    while True:
        user_input = input("Enter URL or command: ").strip()
        if not user_input: continue
        cmd = user_input.lower()
        
        if cmd == "stop" or cmd == "exit": break

        elif cmd == "help":
            print(
                "stop:\t\t\tClose the program\n"
                "add id:\t\t\tToggle appending video ID to filename\n"
                "set directory:\t\tChange download folder\n"
                "thumbnail\t\tToggle adding thumbnail to file\n"
                "reset:\t\t\tReset to default settings\n"
                
                "add to list:\t\tAdd playlist to stored list\n"
                "remove from list:\tRemove playlist from stored list\n"
                "update\t\t\tUpdate stored playlists\n"
            )
        
        elif cmd == "add id":
            settings['id'] = not settings['id']
            id_state = "ON" if settings['id'] else "OFF"
            print(f"[Settings] Append Video ID is now: {id_state}")
        
        elif cmd == "thumbnail":
            settings['thumb'] = not settings['thumb']
            thumbnail_state = "ON" if settings['thumb'] else "OFF"
            print(f"[Settings] Add thumbnail is now: {thumbnail_state}")
        
        elif cmd == "set directory":
            p = Path(input("Path: ").strip(' "'))
            if p.is_dir(): 
                settings['path'] = p
                print(f"[Settings] Directory set to: {p}")
            else:
                print("[Error] Invalid directory path.")
        
        elif cmd == "reset":
            settings['path'] = BASE_DIR / 'Download'
            settings['id'] = False
            settings['thumb'] = False
            print("[Settings] Reset to defaults.")
        
        elif user_input.startswith(("http", "www", "youtu")) and user_input.__contains__("playlist?list"):
            name = get_metadata(user_input)
            name = sanitize_filename(name)
            download_audio(user_input, settings['path'] / 'Download' / name, settings['id'], settings['thumb'])

        elif user_input.startswith(("http", "www", "youtu")):
            download_audio(user_input, settings['path'] / 'Download' / 'loose_songs', settings['id'], settings['thumb'])

        elif cmd == "add to list" or cmd == "add_to_list" or cmd == "add":
            playlist_url = input("Playlist URL: ").strip()
            if playlist_url.startswith(("http", "www", "youtu")):
                if not any(item['url'] == playlist_url for item in stored_data['playlists']):
                    name = get_metadata(playlist_url)
                    name = sanitize_filename(name)
                    new_entry = {"url": playlist_url, "name": name, "path" : settings['path'] / 'Download' / name}
                    stored_data["playlists"].append(new_entry)
                    save_stored_data(stored_data)
                    print(f"[Info] Successfully saved: {name}")
                else:
                    print("[Info] Playlist already in stored list.")
            else:
                print("[Error] Not a valid URL.")

        elif cmd == "remove from list" or cmd == "remove_from_list" or cmd == "remove":
            playlist_name = input("Playlist URL or name to remove or type 'list' to get a list of saved playlists: ").strip()
            if playlist_name == "list":
                print("Saved Playlists:")
                for idx, item in enumerate(stored_data['playlists'], start=1):
                    print(f"{idx}. {item['name']}")
                playlist_name = input("Playlist name or number to remove ").strip()
                if playlist_name.isdigit():
                    playlist_name = stored_data['playlists'][int(playlist_name) - 1]['name']
            before_count = len(stored_data['playlists'])
            stored_data['playlists'] = [item for item in stored_data['playlists'] if item['url'] != playlist_name and item['name'] != playlist_name]
            after_count = len(stored_data['playlists'])
            if before_count != after_count:
                save_stored_data(stored_data)
                print("[Info] Playlist removed from list.")
            else:
                print("[Info] Playlist URL or name not found in list")

        elif cmd == "update":
            download_tasks = []
            print("[Update] Syncing playlists...")
            
            # Identify Deletions and New Downloads
            for item in stored_data['playlists']:
                url = item['url']
                path = item['path']
                
                # Get Live IDs from YouTube
                live_entries = fetch_playlist_entries(url)
                if live_entries is None: continue
                live_ids = {entry['id'] for entry in live_entries if entry.get('id')}

                # Get Local IDs from DB
                local_map = archive.get_map(url)
                local_ids = set(local_map.keys())

                # Calculate Diff
                to_delete = local_ids - live_ids
                to_download = live_ids - local_ids

                # Process Deletions Immediately
                for vid in to_delete:
                    file_path = local_map[vid]
                    try:
                        p = Path(file_path)
                        if p.exists():
                            p.unlink() # Delete actual file
                        archive.remove(vid, url) # Update DB
                        print(f"[Deleted] {vid} from {item['name']}")
                    except Exception as e:
                        print(f"[Error] Deleting {vid}: {e}")

                # Queue Downloads
                for vid in to_download:
                    video_url = f"https://www.youtube.com/watch?v={vid}"
                    download_tasks.append((video_url, path, settings['id'], settings['thumb'], url))

            if download_tasks:
                print(f"[Update] Starting {len(download_tasks)} new downloads")
                with ThreadPoolExecutor(max_workers = 3) as executor:
                    for task in download_tasks:
                        executor.submit(download_audio, *task, archive=archive)
            else:
                print("[Update] No new videos found.")
                
            print("[Update] All updates finished.")
        
        else:
            print("[Error] Invalid command.")