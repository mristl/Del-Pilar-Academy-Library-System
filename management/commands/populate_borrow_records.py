import random
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from django.db import transaction, IntegrityError
from libapp.models import Book, User, BorrowRecord # Import necessary models
from faker import Faker
import traceback

fake = Faker()

class Command(BaseCommand):
    help = ('Populates the database with historical (returned) borrow records. '
            'The --clear option will delete all existing borrow records AND reset associated books to "available".')

    def add_arguments(self, parser):
        parser.add_argument(
            '--count',
            type=int,
            default=1000,
            help='Number of historical borrow records to create (default: 1000).',
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help=('Clear ALL existing BorrowRecord entries before populating. '
                  'This will also find books linked to active (borrowed) records being deleted '
                  'and reset their status to "available", and clear their borrowing details.'),
        )

    def handle(self, *args, **kwargs):
        num_records_to_create = kwargs['count']
        clear_existing = kwargs['clear']

        self.stdout.write(self.style.SUCCESS(f"Starting population of {num_records_to_create} historical borrow records..."))

        if clear_existing:
            self.stdout.write(self.style.WARNING(
                "Clearing ALL existing BorrowRecord entries and resetting associated book statuses..."
            ))
            
            # Step 1: Find accession numbers of books that are in active borrow records
            active_borrow_records_book_accessions = BorrowRecord.objects.filter(
                borrow_status='borrowed',
                return_date__isnull=True
            ).values_list('book_accession_number', flat=True).distinct()

            # Step 2: Filter Book objects whose accession numbers are in this list
            # and whose status is currently 'borrowed' (as a safeguard)
            books_to_reset_qs = Book.objects.filter(
                accession_number__in=list(active_borrow_records_book_accessions),
                status='borrowed' # Ensure we only reset books that are actually marked as borrowed
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


            count_deleted, _ = BorrowRecord.objects.all().delete()
            self.stdout.write(self.style.SUCCESS(
                f"Successfully deleted {count_deleted} existing BorrowRecord entries."
            ))

        # --- Rest of the record population logic remains the same ---
        all_users = list(User.objects.all())
        all_books_for_history = list(Book.objects.all())

        if not all_users:
            self.stdout.write(self.style.ERROR("No users found. Cannot create borrow records."))
            return
        if not all_books_for_history:
            self.stdout.write(self.style.ERROR("No books found. Cannot create borrow records."))
            return

        created_count = 0

        for i in range(num_records_to_create):
            try:
                with transaction.atomic():
                    selected_user = random.choice(all_users)
                    selected_book_instance = random.choice(all_books_for_history)

                    days_ago_borrowed = random.randint(1, 365) 
                    borrow_date = timezone.now() - timedelta(days=days_ago_borrowed)
                    
                    if timezone.is_naive(borrow_date) and timezone.is_aware(timezone.now()):
                        borrow_date = timezone.make_aware(borrow_date, timezone.get_current_timezone())
                    
                    temp_borrow_limit = 5 
                    if selected_user:
                        if selected_user.user_type == "Staff":
                            temp_borrow_limit = 10
                        elif selected_user.user_type in ["Student", "Friends of the Library"]:
                            if selected_book_instance.collection_type in ["circulation", "filipiniana", "shsfilipiniana", "shscirculation"]:
                                temp_borrow_limit = 3
                            elif selected_book_instance.collection_type == "ficandscholastic":
                                temp_borrow_limit = 7
                    
                    expected_return_date = borrow_date
                    added_weekdays = 0
                    while added_weekdays < temp_borrow_limit:
                        expected_return_date += timedelta(days=1)
                        if expected_return_date.weekday() < 5: 
                            added_weekdays += 1
                    
                    if timezone.is_naive(expected_return_date) and timezone.is_aware(borrow_date):
                         expected_return_date = timezone.make_aware(expected_return_date, timezone.get_current_timezone())

                    borrow_status = 'returned'
                    
                    days_borrowed_for = random.randint(1, temp_borrow_limit + 15)
                    return_date = borrow_date + timedelta(days=days_borrowed_for)

                    if timezone.is_naive(return_date) and timezone.is_aware(borrow_date):
                         return_date = timezone.make_aware(return_date, timezone.get_current_timezone())

                    late_fee = 0
                    if return_date.date() > expected_return_date.date():
                        temp_check_date = expected_return_date.date()
                        overdue_weekdays = 0
                        while temp_check_date < return_date.date():
                            if temp_check_date.weekday() < 5:
                                overdue_weekdays +=1
                            temp_check_date += timedelta(days=1)
                        late_fee = overdue_weekdays * 5

                    BorrowRecord.objects.create(
                        user_id=selected_user.id_number,
                        book_accession_number=selected_book_instance.accession_number,
                        borrow_date=borrow_date,
                        expected_return_date=expected_return_date,
                        return_date=return_date,
                        borrow_status=borrow_status,
                        late_payment_fee_amount=late_fee
                    )
                    
                    created_count += 1

            except IntegrityError as e:
                self.stdout.write(self.style.ERROR(f"IntegrityError creating historical borrow record {i+1}: {e}. Skipping."))
                continue
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Unexpected error creating historical borrow record {i+1}: {e}"))
                traceback.print_exc()
                continue
            
            if (created_count) % (num_records_to_create // 20 or 1) == 0 and created_count > 0 :
                 self.stdout.write(f"  Progress: {created_count}/{num_records_to_create} records created...")

        self.stdout.write(self.style.SUCCESS(f"----------------------------------------------------"))
        self.stdout.write(self.style.SUCCESS(f"Total historical BorrowRecords created: {created_count}"))
        self.stdout.write(self.style.SUCCESS("Historical borrow record population process finished."))