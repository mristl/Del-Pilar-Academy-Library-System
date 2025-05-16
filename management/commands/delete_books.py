# In libapp/management/commands/clear_book_data.py (NEW FILE)
from django.core.management.base import BaseCommand
from django.db import transaction
from libapp.models import Book, MARC_FIELD # Import your models

class Command(BaseCommand):
    help = 'Deletes ALL Book and MARC_FIELD records from the database.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirm the deletion of all book and MARC data.',
        )

    def handle(self, *args, **kwargs):
        if not kwargs['confirm']:
            self.stdout.write(self.style.WARNING(
                "This command will delete ALL Book and MARC_FIELD records. "
                "This action is irreversible without a backup."
            ))
            self.stdout.write(self.style.WARNING("To proceed, run the command with the --confirm flag:"))
            self.stdout.write(self.style.NOTICE("  python manage.py clear_book_data --confirm"))
            return

        self.stdout.write(self.style.WARNING("Proceeding with deletion of ALL Book and MARC_FIELD records..."))
        
        try:
            with transaction.atomic():
                book_count = Book.objects.count()
                marc_count = MARC_FIELD.objects.count()

                Book.objects.all().delete()
                MARC_FIELD.objects.all().delete()

                self.stdout.write(self.style.SUCCESS(f"Successfully deleted {book_count} Book records."))
                self.stdout.write(self.style.SUCCESS(f"Successfully deleted {marc_count} MARC_FIELD records."))
                self.stdout.write(self.style.SUCCESS("All Book and MARC_FIELD data has been cleared."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"An error occurred during deletion: {e}"))