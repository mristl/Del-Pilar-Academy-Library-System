import json
import random

# Template MARC Field
marc_field_template = {
    "model": "libapp.marc_field",
    "pk": None,
    "fields": {
        "marc_001_control_number": None,
        "marc_245_title_and_statement_of_responsibility": None,
        "marc_100_main_entry_personal_name": None,
        "marc_250_edition": "First edition.",
        "marc_260_publication": None,
        "marc_300_physical_description": "652 pages; 21 cm.",
        "marc_490_series_statement": None,
        "marc_501_note": None,
        "marc_024_standard_number": None,
        "marc_037_source_of_acquisition": None
    }
}

# Template Book
book_template = {
    "model": "libapp.book",
    "pk": None,
    "fields": {
        "accession_number": None,
        "marc_control_number": None,
        "author": None,
        "title": None,
        "publisher": None,
        "collection_type": "ficandscholastic",
        "room_use": False,
        "date_borrowed": None,
        "status": "available",
        "status_notes": None,
        "user": None,
        "due_date": None
    }
}

authors = ["J.K. Rowling", "Rick Riordan", "Veronica Roth", "Suzanne Collins", "Stephen King"]
titles = [
    "The Philosopher's Quest", "The Goblet's Secret", "The Lightning Rebellion", "The Fire Catcher",
    "The Maze of Shadows", "The Hunger Conflict", "The Stand Rewritten", "It Returns", "Castle High"
]
publishers = ["Scholastic Inc.", "Penguin Books", "HarperCollins", "Bloomsbury", "Random House"]

# Generate 50 unique MARC fields
marc_fields = []
for i in range(1, 51):
    title = random.choice(titles)
    author = random.choice(authors)
    publisher = random.choice(publishers)

    marc_fields.append({
        "model": "libapp.marc_field",
        "pk": i,
        "fields": {
            "marc_001_control_number": f"CTRL-{1000 + i}",
            "marc_245_title_and_statement_of_responsibility": f"{title} / {author}.",
            "marc_100_main_entry_personal_name": author,
            "marc_250_edition": "First edition.",
            "marc_260_publication": f"New York: {publisher}, 200{random.randint(0,9)}.",
            "marc_300_physical_description": "652 pages; 21 cm.",
            "marc_490_series_statement": f"Series {random.randint(1,10)}.",
            "marc_501_note": f"Book {i} in the generated series.",
            "marc_024_standard_number": None,
            "marc_037_source_of_acquisition": None
        }
    })

# Generate 100 books linked to the above MARC fields
books = []
for i in range(1, 101):
    marc_id = random.randint(1, 50)
    selected_marc = next(m for m in marc_fields if m["pk"] == marc_id)
    author = selected_marc["fields"]["marc_100_main_entry_personal_name"]
    title_full = selected_marc["fields"]["marc_245_title_and_statement_of_responsibility"]
    title = title_full.split(" / ")[0]
    publisher = selected_marc["fields"]["marc_260_publication"].split(": ")[1].split(",")[0]

    books.append({
        "model": "libapp.book",
        "pk": 700 + i,
        "fields": {
            "accession_number": f"FIC {i:06d}",
            "marc_control_number": marc_id,
            "author": author,
            "title": title,
            "publisher": publisher,
            "collection_type": "ficandscholastic",
            "room_use": False,
            "date_borrowed": None,
            "status": "available",
            "status_notes": None,
            "user": None,
            "due_date": None
        }
    })

# Combine into a single list
full_data = marc_fields + books
full_data_json = json.dumps(full_data, indent=2)

# Write the data to a JSON file
with open('marc_books_data.json', 'w') as json_file:
    json_file.write(full_data_json)

print("Data has been written to marc_books_data.json.")
