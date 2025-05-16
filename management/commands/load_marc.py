import pandas as pd
from django.core.management.base import BaseCommand
from libapp.models import MARC_FIELD

class Command(BaseCommand):
    help = 'Load MARC Fields for books from CSV file into the database'

    def handle(self, *args, **kwargs):
        csv_file_path = 'finalproject/data/marc_dataset.csv'

        try:
            df = pd.read_csv(csv_file_path)
        except FileNotFoundError:
            print(f"File not found: {csv_file_path}")
            return
        except pd.errors.ParserError as e:
            print(f"Error parsing CSV file: {e}")
            return
        except ValueError as e:
            print(f"Error reading specified columns: {e}")
            return
        
        # Copying load_users.py here
        for index, row in df.iterrows():
            try:
                marc_field, created = MARC_FIELD.objects.update_or_create(
                    marc_001_control_number = row['control_number'],
                    defaults = {
                        'marc_245_title_and_statement_of_responsibility': row.get(),
                        'marc_100_main_entry_personal_name': row.get(),
                        'marc_250_edition': row.get(),
                        'marc_260_publication': row.get(),
                        'marc_300_physical_description': row.get(),
                        'marc_490_series_statement': row.get(),
                        'marc_501_note': row.get(),
                        'marc_024_standard_number': row.get(),
                        'marc_037_source_of_acquisition': row.get(),
                    }
                )

                if created:
                    print(f"Created new MARC FIELD with control number: {row['control_number']}")
                else:
                    print(f"Updated existing MARC FIELD with control number: {row['control_number']}")

            except Exception as e:
                print(f"Error processing row {index+1}:{e}")
                continue
        print("CSV data has been loaded into the Django database.")