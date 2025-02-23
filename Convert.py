import xml.etree.ElementTree as ET
import re
import tkinter as tk
from tkinter import filedialog, simpledialog
import requests
import concurrent.futures
import time
from requests.exceptions import RequestException


# --- API Request Functions ---

# Function to get the user ID from MAL username
def get_user_id(username):
    search_url = f"https://api.jikan.moe/v4/users/{username}"
    try:
        response = requests.get(search_url)
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
        data = response.json()
        return str(data.get("data", {}).get("mal_id", "0"))
    except RequestException as e:
        print(f"Error getting user ID: {e}")
        return "0"  # Or handle the error in a more robust way (e.g., retry)
    except (ValueError, KeyError) as e:
        print(f"Error parsing user ID response: {e}")
        return "0"


# Function to search for manga ID on Jikan API
def get_manga_id_jikan(title, max_retries=3):
    for attempt in range(max_retries):
        try:
            search_url = "https://api.jikan.moe/v4/manga"
            response = requests.get(search_url, params={"q": title})
            response.raise_for_status()
            data = response.json()
            if "data" in data and len(data["data"]) > 0:
                manga_id = data["data"][0].get("mal_id", 0)
                print(f"Found Jikan MAL ID: {manga_id} for {title}")
                return manga_id
            else:
                print(f"Jikan: No results for '{title}'")
                return 0
        except RequestException as e:
            if isinstance(e, requests.exceptions.HTTPError) and e.response.status_code == 429:
                print(f"Jikan: Rate limit detected (attempt {attempt + 1}/{max_retries}). Waiting...")
                time.sleep(20)  # Wait for 20 seconds
            else:
                print(f"Jikan Request failed (attempt {attempt + 1}/{max_retries}): {e}")
                break  # Exit the retry loop for other errors
        except (ValueError, KeyError) as e:
            print(f"Jikan JSON error for '{title}' (attempt {attempt + 1}/{max_retries}): {e}")
            break
    return 0  # Return 0 if retries are exhausted


# New function to search for manga ID using AniList API as an alternative
def get_manga_id_anilist(title):
    # AniList GraphQL endpoint
    url = "https://graphql.anilist.co"

    # GraphQL query
    query = """
    query ($search: String) {
      Media(search: $search, type: MANGA) {
        idMal
      }
    }
    """
    variables = {
        "search": title
    }
    try:
        response = requests.post(url, json={"query": query, "variables": variables})
        response.raise_for_status()
        data = response.json()

        if data and data.get("data") and data["data"].get("Media"):
            anilist_data = data["data"]["Media"]
            mal_id = anilist_data.get("idMal")
            if mal_id:
                print(f"Found AniList MAL ID: {mal_id} for {title}")
                return mal_id
            else:
                print(f"AniList: No MAL ID found for '{title}'")
                return 0
        else:
            print(f"AniList: No results for '{title}'")
            return 0
    except RequestException as e:
        print(f"AniList Request failed for '{title}': {e}")
        return 0
    except (ValueError, KeyError, TypeError) as e:
        print(f"AniList JSON error for '{title}': {e}")
        return 0
    return 0


# Function to parse the manga list from a text file
def parse_manga_list(file_path):
    manga_list = []
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            for line in file:
                match = re.match(r'^(.*?) - Chapter (\d+)', line.strip())
                if match:
                    title, chapter = match.groups()
                    print(f"Parsed: {title} - Chapter {chapter}")
                    manga_list.append((title, int(chapter)))
    except FileNotFoundError:
        print(f"Error: File not found: {file_path}")
        return []
    except IOError as e:
        print(f"Error reading file: {e}")
        return []
    return manga_list


# Function to create the MAL XML
def create_mal_xml(manga_list, output_file, user_id, user_name):
    root = ET.Element("myanimelist")
    myinfo = ET.SubElement(root, "myinfo")
    ET.SubElement(myinfo, "user_id").text = user_id
    ET.SubElement(myinfo, "user_name").text = user_name
    ET.SubElement(myinfo, "user_export_type").text = "2"
    ET.SubElement(myinfo, "user_total_manga").text = str(len(manga_list))
    ET.SubElement(myinfo, "user_total_reading").text = "0"
    ET.SubElement(myinfo, "user_total_completed").text = "0"
    ET.SubElement(myinfo, "user_total_onhold").text = "0"
    ET.SubElement(myinfo, "user_total_dropped").text = "0"
    ET.SubElement(myinfo, "user_total_plantoread").text = "0"

    missing_titles = []
    batch_size = 15

    def process_batch(batch):
        with concurrent.futures.ThreadPoolExecutor(max_workers=batch_size) as executor:
            futures = {executor.submit(get_manga_id_jikan, title): (title, chapter) for title, chapter in batch}
            for future in concurrent.futures.as_completed(futures):
                title, chapter = futures[future]
                manga_id = future.result()

                if manga_id == 0:
                    manga_id = get_manga_id_anilist(title)  # Try AniList if Jikan fails
                if manga_id != 0:
                    manga_entry = ET.SubElement(root, "manga")
                    ET.SubElement(manga_entry, "manga_mangadb_id").text = str(manga_id)
                    ET.SubElement(manga_entry, "manga_title").text = f"<![CDATA[{title}]]>"
                    ET.SubElement(manga_entry, "manga_volumes").text = "0"
                    ET.SubElement(manga_entry, "manga_chapters").text = "0"
                    ET.SubElement(manga_entry, "my_id").text = "0"
                    ET.SubElement(manga_entry, "my_read_volumes").text = "0"
                    ET.SubElement(manga_entry, "my_read_chapters").text = str(chapter)
                    ET.SubElement(manga_entry, "my_start_date").text = "0000-00-00"
                    ET.SubElement(manga_entry, "my_finish_date").text = "0000-00-00"
                    ET.SubElement(manga_entry, "my_scanalation_group").text = "<![CDATA[]]>"
                else:
                    missing_titles.append((title, chapter))

    batches = [manga_list[i:i + batch_size] for i in range(0, len(manga_list), batch_size)]
    for batch in batches:
        process_batch(batch)

    # Write missing titles to a file
    if missing_titles:
        with open("failed_results.txt", "w", encoding="utf-8") as f:
            for title, chapter in missing_titles:
                f.write(f"{title} - Chapter {chapter}\n")
        print("Failed titles written to failed_results.txt")

    tree = ET.ElementTree(root)
    try:
        tree.write(output_file, encoding="utf-8", xml_declaration=True)
        print(f"XML written to {output_file}")
    except IOError as e:
        print(f"Error writing XML to file: {e}")


# Function to handle file selection
def on_drop_file():
    root = tk.Tk()
    root.withdraw()
    user_name = simpledialog.askstring("Input", "Enter your MyAnimeList Username:")
    if not user_name:
        print("Username not provided. Exiting.")
        return

    user_id = get_user_id(user_name)
    if user_id == "0":
        print("Could not retrieve user ID.  Check username or network connection.  Exiting.")
        return

    file_path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt")])
    if not file_path:
        print("No file selected. Exiting.")
        return

    print(f"File selected: {file_path}")
    output_file = "manga_list.xml"
    manga_list = parse_manga_list(file_path)
    if not manga_list:
        print("No manga entries found in the file. Exiting.")
        return
    create_mal_xml(manga_list, output_file, user_id, user_name)
    print(f"MAL XML creation process complete.")


# Main function
def main():
    on_drop_file()


if __name__ == "__main__":
    main()
