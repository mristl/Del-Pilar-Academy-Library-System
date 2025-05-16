import pandas as pd
from django.core.management.base import BaseCommand
from libapp.models import Book

class Command(BaseCommand):
    help = 'Load books from a CSV file into the database'

    def handle(self, *args, **kwargs):
        csv_file_path = 'finalproject/data/book_dataset.csv'  # Change to your actual file path

        try:
            # Read the CSV file, only selecting the necessary columns
            df = pd.read_csv(csv_file_path, usecols=['Accession Number', 'Author', 'Title', 'Publisher'], encoding='latin1')
            print(f"Loaded CSV file with {len(df)} rows.")
        except FileNotFoundError:
            print(f"File not found: {csv_file_path}")
            return
        except pd.errors.ParserError as e:
            print(f"Error parsing CSV file: {e}")
            return
        except ValueError as e:
            print(f"Error reading specified columns: {e}")
            return

        # Iterate through the DataFrame and create or update Book instances
        for index, row in df.iterrows():
            try:
                # Use update_or_create to either update the existing record or create a new one
                book, created = Book.objects.update_or_create(
                    accession_number=row['Accession Number'],  # Find or create based on Accession Number
                    defaults={
                        'author': row.get('Author', ''),  # Use an empty string if the author is missing
                        'title': row.get('Title', ''),    # Use an empty string if the title is missing
                        'publisher': row.get('Publisher', ''),  # Use an empty string if the publisher is missing
                    }
                )

                if created:
                    print(f"Created new book with Accession Number: {row['Accession Number']}")
                else:
                    print(f"Updated existing book with Accession Number: {row['Accession Number']}")

            except Exception as e:
                print(f"Error processing row {index + 1}: {e}")
                continue  # Continue processing other rows even if one fails

        print("CSV data has been loaded into the Django database.")
