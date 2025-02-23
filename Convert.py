import xml.etree.ElementTree as ET
import re
import tkinter as tk
from tkinter import filedialog, simpledialog
import requests
import threading
import concurrent.futures

# Function to get the user ID from MAL username
def get_user_id(username):
    search_url = f"https://api.jikan.moe/v4/users/{username}"
    response = requests.get(search_url)
    if response.status_code == 200:
        data = response.json()
        return str(data.get("data", {}).get("mal_id", "0"))
    return "0"

# Function to search for manga ID on Jikan API
def get_manga_id(title):
    search_url = "https://api.jikan.moe/v4/manga"
    response = requests.get(search_url, params={"q": title})
    print(f"Searching for: {title}")  # Debug print
    if response.status_code == 200:
        data = response.json()
        if "data" in data and len(data["data"]) > 0:
            manga_id = data["data"][0].get("mal_id", 0)
            print(f"Found MAL ID: {manga_id} for {title}")  # Debug print
            return manga_id
    print(f"No MAL ID found for {title}")  # Debug print
    return 0

# Function to check alternative APIs for missing manga
def get_manga_id_from_other_sources(title):
    alternative_sources = [
        f"https://kitsu.io/api/edge/manga?filter[text]={title}"
    ]
    
    for url in alternative_sources:
        response = requests.get(url)
        print(f"Checking: {url}")  # Debug print
        if response.status_code == 200:
            data = response.json()
            if "data" in data and len(data["data"]) > 0:
                alt_id = data["data"][0].get("id", 0)
                print(f"Found Alternative ID: {alt_id} for {title} from {url}")  # Debug print
                return alt_id
    print(f"No alternative ID found for {title}")  # Debug print
    return 0

# Function to parse the manga list from a text file
def parse_manga_list(file_path):
    manga_list = []
    with open(file_path, 'r', encoding='utf-8') as file:
        for line in file:
            match = re.match(r'^(.*?) - Chapter (\d+)', line.strip())
            if match:
                title, chapter = match.groups()
                print(f"Parsed: {title} - Chapter {chapter}")  # Debug print
                manga_list.append((title, int(chapter)))
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

    # Updated batch size to 15
    batch_size = 15

    # Function to fetch manga IDs in batches
    def process_batch(batch):
        batch_results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=batch_size) as executor:
            futures = {executor.submit(get_manga_id, title): (title, chapter) for title, chapter in batch}
            for future in concurrent.futures.as_completed(futures):
                title, chapter = futures[future]
                manga_id = future.result()
                if manga_id == 0:
                    missing_titles.append((title, chapter))  # Store titles not found
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

        return batch_results

    # Split manga list into batches and process
    batches = [manga_list[i:i + batch_size] for i in range(0, len(manga_list), batch_size)]
    for batch in batches:
        process_batch(batch)

    # Search for missing titles in alternative sources
    if missing_titles:
        print("Searching alternative sources for missing titles...")
        for title, chapter in missing_titles:
            alt_id = get_manga_id_from_other_sources(title)
            if alt_id != 0:
                manga_entry = ET.SubElement(root, "manga")
                ET.SubElement(manga_entry, "manga_mangadb_id").text = str(alt_id)
                ET.SubElement(manga_entry, "manga_title").text = f"<![CDATA[{title}]]>"
                ET.SubElement(manga_entry, "manga_volumes").text = "0"
                ET.SubElement(manga_entry, "manga_chapters").text = "0"
                ET.SubElement(manga_entry, "my_id").text = "0"
                ET.SubElement(manga_entry, "my_read_volumes").text = "0"
                ET.SubElement(manga_entry, "my_read_chapters").text = str(chapter)
                ET.SubElement(manga_entry, "update_on_import").text = "1"

    tree = ET.ElementTree(root)
    tree.write(output_file, encoding="utf-8", xml_declaration=True)
    print(f"XML written to {output_file}")  # Debug print

# Function to handle file selection
def on_drop_file():
    root = tk.Tk()
    root.withdraw()
    user_name = simpledialog.askstring("Input", "Enter your MyAnimeList Username:")
    user_id = get_user_id(user_name)
    file_path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt")])
    if file_path and user_name and user_id:
        print(f"File selected: {file_path}")  # Debug print
        output_file = "manga_list.xml"
        manga_list = parse_manga_list(file_path)
        create_mal_xml(manga_list, output_file, user_id, user_name)
        print(f"MAL XML created: {output_file}")

# Main function
def main():
    on_drop_file()

if __name__ == "__main__":
    main()
