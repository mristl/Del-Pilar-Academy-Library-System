# finalproject-finalver/libapp/management/commands/send_overdue_notifications.py

import logging
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.template.loader import render_to_string
from django.core.mail import EmailMessage
from django.conf import settings
from datetime import datetime, time # Import time for datetime.combine

# Import your specific models
from libapp.models import BorrowRecord, Book, User # Adjust import path if needed

# Configure logging
logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Checks for overdue books based on BorrowRecord and sends email notifications if not already sent.'

    def handle(self, *args, **options):
        now_dt = timezone.now() # Get current timezone-aware datetime

        # --- Calculate the start of today (midnight) in the current timezone ---
        # This is the reference point for "before today"
        current_date_for_comparison = now_dt.date() # Get just the date part for logging
        
        # Create a datetime object for midnight at the beginning of the current day
        # This handles both naive and aware settings for timezone.now()
        if timezone.is_naive(now_dt):
            # If Django's now() is naive, make it aware then set to midnight
            aware_now_dt = timezone.make_aware(now_dt, timezone.get_current_timezone())
            start_of_today_dt = aware_now_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            # If Django's now() is already aware, just set to midnight
            start_of_today_dt = now_dt.replace(hour=0, minute=0, second=0, microsecond=0)


        self.stdout.write(f"[{now_dt}] Starting check for overdue books...")
        self.stdout.write(f"Current date for logging comparison: {current_date_for_comparison}")
        self.stdout.write(f"Querying records with expected_return_date < {start_of_today_dt} (start of today)")


        # --- For detailed debugging (optional, can be commented out after testing) ---
        all_potentially_relevant_records = BorrowRecord.objects.filter(
            borrow_status='borrowed',
            overdue_notification_sent=False,
            expected_return_date__isnull=False
        )
        self.stdout.write(f"Found {all_potentially_relevant_records.count()} records with status 'borrowed', notification_sent=False, and an expected_return_date (before date filter).")
        for br_test in all_potentially_relevant_records:
            is_past_due_for_debug = False
            expected_return_datetime_for_debug = None
            if br_test.expected_return_date:
                expected_return_datetime_for_debug = br_test.expected_return_date
                # Ensure it's aware for comparison
                if timezone.is_naive(expected_return_datetime_for_debug):
                    expected_return_datetime_for_debug = timezone.make_aware(expected_return_datetime_for_debug, timezone.get_current_timezone())
                is_past_due_for_debug = expected_return_datetime_for_debug < start_of_today_dt

            self.stdout.write(
                f"  Inspecting Record ID {br_test.borrow_record_number}: "
                f"Expected Return: {br_test.expected_return_date}, "
                f"Book: {br_test.book_accession_number}, User: {br_test.user_id}"
            )
            self.stdout.write(f"    Is ERD ({expected_return_datetime_for_debug}) < start_of_today ({start_of_today_dt})? : {is_past_due_for_debug}")
        # --- End detailed debugging ---


        # --- MODIFIED QUERY ---
        overdue_records = BorrowRecord.objects.filter(
            borrow_status='borrowed',
            expected_return_date__isnull=False,
            expected_return_date__lt=start_of_today_dt, # Compare DateTimeField with a DateTime object
            overdue_notification_sent=False
        )
        # --- END MODIFIED QUERY ---

        if not overdue_records.exists():
            self.stdout.write("No new overdue books found requiring notification (after final filter).")
            return

        self.stdout.write(f"Found {overdue_records.count()} overdue record(s) needing notification.")
        sent_count = 0
        failed_count = 0

        for record in overdue_records:
            user = record.get_user()
            book = record.get_book()

            if not user or not user.school_email:
                logger.warning(f"Skipping record ID {record.borrow_record_number}: User {record.user_id} not found or has no school email.")
                failed_count += 1
                continue

            if not book:
                logger.warning(f"Skipping record ID {record.borrow_record_number}: Book {record.book_accession_number} not found.")
                failed_count += 1
                continue

            try:
                mail_subject = f"DPA Library - Overdue Book: {book.title}"
                message = render_to_string("libapp/overdue_notification_email.html", {
                    'user_name': user.name,
                    'book_title': book.title,
                    'accession_number': book.accession_number,
                    'due_date': record.expected_return_date, # This is the date it was due
                })

                email = EmailMessage(
                    subject=mail_subject,
                    body=message,
                    from_email=f'DPA Library <{settings.EMAIL_HOST_USER}>',
                    to=[user.school_email]
                )
                email.content_subtype = "html"
                email.send(fail_silently=False)

                record.overdue_notification_sent = True
                record.save(update_fields=['overdue_notification_sent'])
                sent_count += 1
                self.stdout.write(self.style.SUCCESS(f"Successfully sent overdue notification for Record ID {record.borrow_record_number} to {user.school_email}"))

            except Exception as e:
                failed_count += 1
                logger.error(f"Failed to send overdue notification for Record ID {record.borrow_record_number} to {user.school_email}: {e}")
                self.stdout.write(self.style.ERROR(f"Failed to send notification for Record ID {record.borrow_record_number}: {e}"))

        self.stdout.write(f"[{timezone.now()}] Overdue check finished. Sent: {sent_count}, Failed/Skipped: {failed_count}")