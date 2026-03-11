import json
import re
import subprocess
import sys
import threading
import yt_dlp

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path



BASE_DIR = Path(__file__).parent.resolve()
DATA_FILE = BASE_DIR / "app_data.json"


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


def download_audio(youtube_url, download_folder, use_video_id, thumbnail) -> None:
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
    if ffmpeg_dir.exists():
        ydl_opts['ffmpeg_location'] = str(ffmpeg_dir)
    else:
        thread_safe_print("[Warning] Local FFmpeg/bin folder not found. Relying on system PATH.")

    # run Download
    try:
        thread_safe_print(f"[Queueing] {youtube_url}")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            error_code = ydl.download([youtube_url])
            
            if error_code == 0:
                thread_safe_print(f"[Finished] {youtube_url}")
            else:
                # Force exception
                raise Exception("yt-dlp returned an error code.")
    
    except Exception as e:
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
            download_audio(user_input, settings['path'] / name, settings['id'], settings['thumb'])

        elif user_input.startswith(("http", "www", "youtu")):
            download_audio(user_input, settings['path'] / 'Download', settings['id'], settings['thumb'])

        elif cmd == "add to list" or cmd == "add_to_list" or cmd == "add":
            playlist_url = input("Playlist URL: ").strip()
            if playlist_url.startswith(("http", "www", "youtu")):
                if not any(item['url'] == playlist_url for item in stored_data['playlists']):
                    name = get_metadata(playlist_url)
                    name = sanitize_filename(name)
                    new_entry = {"url": playlist_url, "name": name, "path" : settings['path'] / name}
                    stored_data["playlists"].append(new_entry)
                    save_stored_data(stored_data)
                    print(f"[Info] Successfully saved: {name}")
                else:
                    print("[Info] Playlist already in stored list.")
            else:
                print("[Error] Not a valid URL.")

        elif cmd == "remove from list" or cmd == "remove_from_list" or cmd == "remove":
            playlist_name = input("Playlist URL or name to remove: ").strip()
            before_count = len(stored_data['playlists'])
            stored_data['playlists'] = [item for item in stored_data['playlists'] if item['url'] != playlist_name and item['name'] != playlist_name]
            after_count = len(stored_data['playlists'])
            if before_count != after_count:
                save_stored_data(stored_data)
                print("[Info] Playlist removed from list.")
            else:
                print("[Info] Playlist URL or name not found in list")

        elif cmd == "update":
            with ThreadPoolExecutor(max_workers = 3) as executor:
                # Todo
                break
            print("[Update] All updates finished.")
        
        else:
            print("[Error] Invalid command.")