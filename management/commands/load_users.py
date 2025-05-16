import pandas as pd
from django.core.management.base import BaseCommand
from libapp.models import User  

class Command(BaseCommand):
    help = 'Load users from a CSV file into the database'

    def handle(self, *args, **kwargs):
        csv_file_path = 'finalproject/data/user_dataset.csv'

        try:
            df = pd.read_csv(csv_file_path)
        except FileNotFoundError:
            print(f"File not found: {csv_file_path}")
            return

        # Iterate through the DataFrame and create or update User instances
        for index, row in df.iterrows():
            # Use update_or_create to either update the existing record or create a new one
            user, created = User.objects.update_or_create(
                id_number=row['ID Number'],  # Find or create based on ID Number
                defaults={
                    'name': row['Name'],
                    'user_type': row['User Type'],
                }
            )

            if created:
                print(f"Created new user with ID Number: {row['ID Number']}")
            else:
                print(f"Updated existing user with ID Number: {row['ID Number']}")

        print("CSV data has been loaded into the Django database.")
