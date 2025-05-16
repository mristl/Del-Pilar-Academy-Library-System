from django.db import models
from django.utils.timezone import now
from django.utils import timezone
from datetime import datetime, timedelta
from django.utils.timezone import now


class Book(models.Model):
    ACCESSION_NUMBER_CHOICES = [
        ('borrowed', 'Borrowed'),
        ('available', 'Available'),
        ('overdue', 'Overdue'),
        ('flagged', 'Flagged'),
    ]

    #carried from book
    COLLECTION_TYPES = [
        ('circulation', 'Circulation'),
        ('filipiniana', 'Filipiniana'),
        ('shsfilipiniana', 'SHS Filipiniana'),
        ('shscirculation', 'SHS Circulation'),
        ('ficandscholastic', 'Fiction and Scholastic'),
        ('reference', 'Reference'),
        ('archives', 'Archives'),
        ('shsreference', 'SHS Reference'),
        ('periodicals', 'Periodicals'),
    ]
    accession_number = models.CharField(max_length=50, unique=True)

    marc_control_number = models.ForeignKey('MARC_FIELD',null=True, blank=True, on_delete=models.SET_NULL)
    # author, title, and publisher will all be carried over from the marc field.
    author = models.CharField(max_length=100)
    title = models.CharField(max_length=200)
    publisher = models.CharField(max_length=100)

    #CAN'T BE IN MARC FIELD. it will be based on accession number talaga so oh well!
    collection_type = models.CharField(choices=COLLECTION_TYPES,max_length=50,  null=True, blank=True)
    room_use = models.BooleanField(default=True)

    date_borrowed = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=ACCESSION_NUMBER_CHOICES, default='available')
    status_notes = models.CharField(max_length=255, null=True, blank=True)
    user = models.ForeignKey('User', null=True, blank=True, on_delete=models.SET_NULL)
    due_date = models.DateTimeField(null=True, blank=True)  # **NEW FIELD**

    @property
    def borrow_limit(self):
        """Determine borrow limit based on user type and book type."""
        if self.user:
            if self.user.user_type == "Staff":
                return 10  # Staff always get 10 days
            elif self.user.user_type in ["Student", "Friends of the Library"]:
                if self.collection_type in ["circulation", "filipiniana", "shsfilipiniana", "shscirculation"]:
                    return 3  # Student gets 3 days for these types
                elif self.collection_type == "ficandscholastic":
                    return 7  # Student gets 7 days for Fiction and Scholastic

        return 5  # Default case (fallback)

    @property
    def expected_return_date(self):
        """
        Calculates the due date based on borrow date and rules (weekdays).
        Used for initially setting the due_date field and for resetting simulation.
        THIS IS A CALCULATION, NOT THE STORED VALUE.
        """
        if self.date_borrowed:
            borrow_date = self.date_borrowed
            if timezone.is_naive(borrow_date): # Use timezone.is_naive
                 borrow_date = timezone.make_aware(borrow_date) # Use default timezone

            current_date = borrow_date
            added_days = 0
            days_limit = self.borrow_limit

            while added_days < days_limit:
                current_date += timedelta(days=1)
                if current_date.weekday() < 5: # Monday to Friday (0-4)
                    added_days += 1
            return current_date
        return None

    # *** THIS IS THE CORRECTED days_remaining PROPERTY using WEEKDAYS ***
    @property
    def days_remaining(self):
        """
        Calculates remaining days based on the STORED due_date field
        using **WEEKDAYS** difference. Determines overdue status.
        Returns None if due_date is not set.
        """
        if not self.due_date:
            return None # Cannot calculate if no due date is set

        # Ensure dates are timezone-aware for comparison, then get date part
        actual_due_dt = self.due_date
        if timezone.is_naive(actual_due_dt):
            actual_due_dt = timezone.make_aware(actual_due_dt)
        due_date_only = actual_due_dt.date()

        current_dt = timezone.now()
        if timezone.is_naive(current_dt):
            current_dt = timezone.make_aware(current_dt)
        today = current_dt.date()

        # Calculate WEEKDAYS remaining or overdue
        if today == due_date_only:
            return 0 # Due today
        elif today < due_date_only:
            # Due in the future: Count weekdays from tomorrow up to and including due date
            count = 0
            temp_date = today + timedelta(days=1)
            while temp_date <= due_date_only:
                if temp_date.weekday() < 5: # Monday to Friday
                    count += 1
                temp_date += timedelta(days=1)
            return count
        else: # Overdue (today > due_date_only)
            # Count weekdays from due_date up to (but not including) today
            count = 0
            temp_date = due_date_only
            while temp_date < today:
                if temp_date.weekday() < 5: # Monday to Friday
                    count += 1
                temp_date += timedelta(days=1)
            return -count # Return negative count

    def __str__(self):
        return self.title
    
    #to not screw over all the other programs -- i did not remove any existing book variables i just made it transfer from marc control number
    def set_from_marc_field(self):
        self.title = self.marc_control_number.marc_245_title_and_statement_of_responsibility
        self.author = self.marc_control_number.marc_100_main_entry_personal_name
        self.publisher = self.marc_control_number.marc_260_publication


class User(models.Model):
    USER_TYPE_CHOICES = [
        ('Student', 'Student'),
        ('Friends of the Library', 'Friends of the Library'),
        ('Staff', 'Staff'),
    ]

    id_number = models.CharField(max_length=20, unique=True)  # 6-digit unique ID
    name = models.CharField(max_length=100)
    user_type = models.CharField(max_length=30, choices=USER_TYPE_CHOICES)  # Either Student or Staff
    section = models.CharField(max_length=50, blank=True, null=True)  # Section (e.g., "7-Helium", "STEM 11-B")
    school_email = models.EmailField(unique=True)  # School-issued email (e.g., mia.thomas@student.delpa.edu)
    is_flagged = models.BooleanField(default=False)
    flag_reason = models.TextField(null=True, blank=True)
    flag_date = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.name} ({self.user_type}) - {self.section or ''}"


class ComputerUsage(models.Model):
    counter = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    date = models.DateTimeField(default=timezone.now)

    def save(self, *args, **kwargs):
        # Ensure date is timezone-aware
        if self.date and timezone.is_naive(self.date):
            self.date = timezone.make_aware(self.date)
            
        if not self.counter:
            last_record = ComputerUsage.objects.order_by('-counter').first()
            self.counter = last_record.counter + 1 if last_record else 1
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.counter}: {self.user.id_number} - {self.user.name} on {self.date}"

class ComputerUsageBuffer(models.Model):
    """
    First backup database in the queue system for computer usage.
    Records are moved here from ComputerUsage when a new school year begins.
    User is replaced with section.
    """
    counter = models.IntegerField(primary_key=True)
    section = models.CharField(max_length=50, null=True, blank=True)
    date = models.DateTimeField(default=timezone.now)
    school_year = models.CharField(max_length=9, null=True, blank=True)
    
    def save(self, *args, **kwargs):
        # Ensure date is timezone-aware
        if self.date and timezone.is_naive(self.date):
            self.date = timezone.make_aware(self.date)
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"Buffer Record {self.counter}: {self.section} on {self.date}"
    
    @classmethod
    def create_from_computer_usage(cls, computer_usage, school_year):
        """
        Create a buffer record from an original ComputerUsage instance.
        """
        try:
            # Get User section from the associated user
            section = computer_usage.user.section if computer_usage.user else "Unknown Section"
            
            # Ensure date is timezone-aware
            date = computer_usage.date
            if date and timezone.is_naive(date):
                date = timezone.make_aware(date)
            
            # Create buffer record with preserved primary key and transformed fields
            buffer_record = cls(
                counter=computer_usage.counter,
                section=section,
                date=date,
                school_year=school_year,
            )
            buffer_record.save()
            return buffer_record
        except Exception as e:
            print(f"Error in create_from_computer_usage: {str(e)}")
            raise

class ComputerUsageArchive(models.Model):
    """
    Oldest backup database in the queue system for computer usage.
    Records are moved here from ComputerUsageBuffer before being deleted.
    Contains section instead of user reference.
    """
    counter = models.IntegerField(primary_key=True)
    section = models.CharField(max_length=50, null=True, blank=True)
    date = models.DateTimeField(default=timezone.now)
    school_year = models.CharField(max_length=9, null=True, blank=True)
    
    def save(self, *args, **kwargs):
        # Ensure date is timezone-aware
        if self.date and timezone.is_naive(self.date):
            self.date = timezone.make_aware(self.date)
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"Archive Record {self.counter}: {self.section} on {self.date}"
    
    @classmethod
    def create_from_buffer_record(cls, buffer_record):
        """
        Create an archive record from a ComputerUsageBuffer instance.
        """
        try:
            # Ensure date is timezone-aware
            date = buffer_record.date
            if date and timezone.is_naive(date):
                date = timezone.make_aware(date)
                
            archive_record = cls(
                counter=buffer_record.counter,
                section=buffer_record.section,
                date=date,
                school_year=buffer_record.school_year,
            )
            archive_record.save()
            return archive_record
        except Exception as e:
            print(f"Error in create_from_buffer_record: {str(e)}")
            raise


class BorrowRecord(models.Model):
    """
    Current borrow records database.
    Records user borrowing activities.
    """
    # Keep using AutoField for current records to auto-increment
    borrow_record_number = models.AutoField(primary_key=True)
    user_id = models.CharField(max_length=20)  # Links to User.id_number
    book_accession_number = models.CharField(max_length=50)  # Links to Book.accession_number
    borrow_date = models.DateTimeField(default=timezone.now)
    expected_return_date = models.DateTimeField(null=True, blank=True)
    return_date = models.DateTimeField(null=True, blank=True)
    late_payment_fee_amount = models.DecimalField(max_digits=6, decimal_places=2, default=0.00)
    borrow_status = models.CharField(
        max_length=10,
        choices=[('borrowed', 'Borrowed'), ('returned', 'Returned')],
        default='borrowed'
    )
    near_overdue_date = models.IntegerField(null=True, blank=True)
    overdue_notification_sent = models.BooleanField(default=False)
    
    def __str__(self):
        return f"Record {self.borrow_record_number}: {self.user_id} borrowed {self.book_accession_number}"
    
    def get_user(self):
        """Get the associated User instance."""
        from .models import User
        try:
            return User.objects.get(id_number=self.user_id)
        except User.DoesNotExist:
            return None
    
    def get_book(self):
        """Get the associated Book instance."""
        from .models import Book
        try:
            return Book.objects.get(accession_number=self.book_accession_number)
        except Book.DoesNotExist:
            return None

class BorrowRecordsBuffer(models.Model):
    """
    First backup database in the queue system.
    Records are moved here from BorrowRecord when new records are entered.
    User ID and book accession number are replaced with section and collection type.
    """
    # Use the same field name 'borrow_record_number' but don't make it auto-increment
    # This allows us to manually set the value when migrating records
    borrow_record_number = models.IntegerField(primary_key=True)
    section = models.CharField(max_length=50, null=True, blank=True)  # Derived from User.section
    collection_type = models.CharField(max_length=50, null=True, blank=True)  # Derived from Book.collection_type
    borrow_date = models.DateTimeField(default=timezone.now)
    expected_return_date = models.DateTimeField(null=True, blank=True)
    return_date = models.DateTimeField(null=True, blank=True)
    late_payment_fee_amount = models.DecimalField(max_digits=6, decimal_places=2, default=0.00)
    borrow_status = models.CharField(
        max_length=10,
        choices=[('borrowed', 'Borrowed'), ('returned', 'Returned')],
        default='borrowed'
    )
    near_overdue_date = models.IntegerField(null=True, blank=True)
    overdue_notification_sent = models.BooleanField(default=False)
    
    def __str__(self):
        return f"Buffer Record {self.borrow_record_number}: {self.section} borrowed {self.collection_type}"
    
    @classmethod
    def create_from_borrow_record(cls, borrow_record):
        """
        Create a buffer record from an original BorrowRecord instance.
        Converts user_id to section and book_accession_number to collection_type.
        Preserves the original primary key value.
        """
        # Get User section based on user_id
        user = borrow_record.get_user()
        section = user.section if user else "Unknown Section"
        
        # Get Book collection_type based on book_accession_number
        book = borrow_record.get_book()
        collection_type = book.collection_type if book else "Unknown Collection"
        
        # Create buffer record with preserved primary key and transformed fields
        buffer_record = cls(
            borrow_record_number=borrow_record.borrow_record_number,  # Preserve the original PK
            section=section,
            collection_type=collection_type,
            borrow_date=borrow_record.borrow_date,
            expected_return_date=borrow_record.expected_return_date,
            return_date=borrow_record.return_date,
            late_payment_fee_amount=borrow_record.late_payment_fee_amount,
            borrow_status=borrow_record.borrow_status,
            near_overdue_date=borrow_record.near_overdue_date,
            overdue_notification_sent=borrow_record.overdue_notification_sent,
        )
        buffer_record.save()
        return buffer_record
    
class BorrowRecordsBuffer(models.Model):
    """
    First backup database in the queue system.
    Records are moved here from BorrowRecord when new records are entered.
    User ID and book accession number are replaced with section and collection type.
    """
    # Use the same field name 'borrow_record_number' but don't make it auto-increment
    # This allows us to manually set the value when migrating records
    borrow_record_number = models.IntegerField(primary_key=True)
    section = models.CharField(max_length=50, null=True, blank=True)  # Derived from User.section
    collection_type = models.CharField(max_length=50, null=True, blank=True)  # Derived from Book.collection_type
    borrow_date = models.DateTimeField(default=timezone.now)
    expected_return_date = models.DateTimeField(null=True, blank=True)
    return_date = models.DateTimeField(null=True, blank=True)
    late_payment_fee_amount = models.DecimalField(max_digits=6, decimal_places=2, default=0.00)
    borrow_status = models.CharField(
        max_length=10,
        choices=[('borrowed', 'Borrowed'), ('returned', 'Returned')],
        default='borrowed'
    )
    near_overdue_date = models.IntegerField(null=True, blank=True)
    overdue_notification_sent = models.BooleanField(default=False)
    
    def __str__(self):
        return f"Buffer Record {self.borrow_record_number}: {self.section} borrowed {self.collection_type}"
    
    @classmethod
    def create_from_borrow_record(cls, borrow_record):
        """
        Create a buffer record from an original BorrowRecord instance.
        Converts user_id to section and book_accession_number to collection_type.
        Preserves the original primary key value.
        """
        # Get User section based on user_id
        user = borrow_record.get_user()
        section = user.section if user else "Unknown Section"
        
        # Get Book collection_type based on book_accession_number
        book = borrow_record.get_book()
        collection_type = book.collection_type if book else "Unknown Collection"
        
        # Create buffer record with preserved primary key and transformed fields
        buffer_record = cls(
            borrow_record_number=borrow_record.borrow_record_number,  # Preserve the original PK
            section=section,
            collection_type=collection_type,
            borrow_date=borrow_record.borrow_date,
            expected_return_date=borrow_record.expected_return_date,
            return_date=borrow_record.return_date,
            late_payment_fee_amount=borrow_record.late_payment_fee_amount,
            borrow_status=borrow_record.borrow_status,
            near_overdue_date=borrow_record.near_overdue_date,
            overdue_notification_sent=borrow_record.overdue_notification_sent,
        )
        buffer_record.save()
        return buffer_record

class BorrowRecordsArchive(models.Model):
    """
    Oldest backup database in the queue system.
    Records are moved here from BorrowRecordsBuffer before being deleted.
    User ID and book accession number are replaced with section and collection type.
    """
    # Use IntegerField instead of AutoField to allow manually setting the PK
    borrow_record_number = models.IntegerField(primary_key=True)
    section = models.CharField(max_length=50, null=True, blank=True)
    collection_type = models.CharField(max_length=50, null=True, blank=True)
    borrow_date = models.DateTimeField(default=timezone.now)
    expected_return_date = models.DateTimeField(null=True, blank=True)
    return_date = models.DateTimeField(null=True, blank=True)
    late_payment_fee_amount = models.DecimalField(max_digits=6, decimal_places=2, default=0.00)
    borrow_status = models.CharField(
        max_length=10,
        choices=[('borrowed', 'Borrowed'), ('returned', 'Returned')],
        default='borrowed'
    )
    near_overdue_date = models.IntegerField(null=True, blank=True)
    overdue_notification_sent = models.BooleanField(default=False)

    def __str__(self):
        return f"Archive Record {self.borrow_record_number}: {self.section} borrowed {self.collection_type}"
    
    @classmethod
    def create_from_buffer_record(cls, buffer_record):
        """
        Create an archive record from a BorrowRecordsBuffer instance.
        Preserves the original primary key.
        """
        archive_record = cls(
            borrow_record_number=buffer_record.borrow_record_number,  # Preserve the PK
            section=buffer_record.section,
            collection_type=buffer_record.collection_type,
            borrow_date=buffer_record.borrow_date,
            expected_return_date=buffer_record.expected_return_date,
            return_date=buffer_record.return_date,
            late_payment_fee_amount=buffer_record.late_payment_fee_amount,
            borrow_status=buffer_record.borrow_status,
            near_overdue_date=buffer_record.near_overdue_date,
            overdue_notification_sent=buffer_record.overdue_notification_sent
        )
        archive_record.save()
        return archive_record


class LibraryReport(models.Model):
    uploaded_at = models.DateTimeField(auto_now_add=True)
    start_date = models.DateField()
    end_date = models.DateField()
    csv_file = models.FileField(upload_to='reports/csv/')
    pdf_report = models.FileField(upload_to='reports/pdf/', null=True, blank=True)

    def __str__(self):
        return f"Report from {self.start_date} to {self.end_date} - {self.uploaded_at}"


class MARC_FIELD(models.Model):
    marc_001_control_number = models.CharField(max_length=50, unique=True)
    marc_245_title_and_statement_of_responsibility = models.CharField(max_length=255)
    marc_100_main_entry_personal_name = models.CharField(max_length=255)
    marc_250_edition = models.CharField(max_length=255)
    marc_260_publication = models.CharField(max_length=255)

    marc_300_physical_description = models.CharField(max_length = 255, null=True, blank=True)
    marc_490_series_statement = models.CharField(max_length = 255, null=True, blank=True)
    marc_501_note = models.CharField(max_length=255, null=True, blank=True)
    marc_024_standard_number = models.CharField(max_length=255, null=True, blank=True)
    marc_037_source_of_acquisition = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return f"{self.marc_001_control_number} - {self.marc_245_title_and_statement_of_responsibility}"