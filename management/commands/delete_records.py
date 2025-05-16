from django.core.management.base import BaseCommand
from django.db import transaction
from libapp.models import Book, BorrowRecord # Import your models
import traceback

class Command(BaseCommand):
    help = ('Deletes ALL BorrowRecord entries and resets the status of any associated '
            'books (that were actively borrowed) to "available".')

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirm the deletion of all borrow history and resetting of book statuses.',
        )

    def handle(self, *args, **kwargs):
        if not kwargs['confirm']:
            self.stdout.write(self.style.WARNING(
                "This command will delete ALL BorrowRecord entries and reset associated Book statuses. "
                "This action is irreversible without a backup."
            ))
            self.stdout.write(self.style.WARNING("To proceed, run the command with the --confirm flag:"))
            self.stdout.write(self.style.NOTICE("  python manage.py delete_records --confirm"))
            return

        self.stdout.write(self.style.WARNING(
            "Proceeding with deletion of ALL BorrowRecord entries and resetting associated Book statuses..."
        ))
        
        try:
            with transaction.atomic():
                # Step 1: Identify books that are currently 'borrowed' according to active records
                active_borrow_records_book_accessions = BorrowRecord.objects.filter(
                    borrow_status='borrowed',
                    return_date__isnull=True
                ).values_list('book_accession_number', flat=True).distinct()

                books_to_reset_qs = Book.objects.filter(
                    accession_number__in=list(active_borrow_records_book_accessions),
                    status__in=['borrowed', 'overdue'] # Consider books marked as borrowed or overdue
                )

                books_reset_count = 0
                if books_to_reset_qs.exists():
                    self.stdout.write(self.style.NOTICE(
                        f"Found {books_to_reset_qs.count()} Book object(s) linked to active borrow records to reset."
                    ))
                    for book_to_reset in books_to_reset_qs:
                        book_to_reset.status = 'available'
                        book_to_reset.user = None
                        book_to_reset.date_borrowed = None
                        book_to_reset.due_date = None
                        book_to_reset.save(update_fields=['status', 'user', 'date_borrowed', 'due_date'])
                        books_reset_count += 1
                
                if books_reset_count > 0:
                    self.stdout.write(self.style.SUCCESS(
                        f"Reset {books_reset_count} Book object(s) to 'available' status."
                    ))
                else:
                    self.stdout.write(self.style.NOTICE(
                        "No books needed status reset (or no active borrow records found)."
                    ))

                # Step 2: Delete all BorrowRecord entries
                borrow_record_count = BorrowRecord.objects.count()
                BorrowRecord.objects.all().delete()

                self.stdout.write(self.style.SUCCESS(f"Successfully deleted {borrow_record_count} BorrowRecord entries."))
                self.stdout.write(self.style.SUCCESS("All BorrowRecord data has been cleared and associated books reset."))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"An error occurred during the clearing process: {e}"))
            traceback.print_exc()