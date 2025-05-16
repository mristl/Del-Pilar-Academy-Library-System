from django.db import transaction, connection, models
from django.conf import settings
from .models import (BorrowRecord, BorrowRecordsBuffer, BorrowRecordsArchive, 
                    ComputerUsage, ComputerUsageBuffer, ComputerUsageArchive, User)
from django.utils import timezone


def has_unreturned_books():
    """
    Quick utility function to check if there are any unreturned books.
    Returns True if there are unreturned books, False otherwise.
    """
    return BorrowRecord.objects.filter(return_date__isnull=True).exists()

def move_records_to_buffer():
    """
    Move all records from BorrowRecord to BorrowRecordsBuffer.
    This converts user_id to section and book_accession_number to collection_type.
    """
    with transaction.atomic():
        # Get all borrow records
        borrow_records = BorrowRecord.objects.all()
        # Create buffer records from each borrow record
        for record in borrow_records:
            BorrowRecordsBuffer.create_from_borrow_record(record)
        # Return the count of records moved
        return borrow_records.count()

def move_buffer_to_archive():
    """
    Move all records from BorrowRecordsBuffer to BorrowRecordsArchive.
    """
    with transaction.atomic():
        # Get all buffer records
        buffer_records = BorrowRecordsBuffer.objects.all()
        # Create archive records from each buffer record
        for record in buffer_records:
            BorrowRecordsArchive.create_from_buffer_record(record)
        # Return the count of records moved
        return buffer_records.count()

def reset_borrowrecord_pk():
    """
    Reset the primary key sequence for BorrowRecord.
    Uses a database-agnostic approach that will work with most backends.
    """
    # Get the table name
    table_name = BorrowRecord._meta.db_table
    pk_field = BorrowRecord._meta.pk.name
    # Get database vendor name (postgresql, mysql, sqlite, etc.)
    db_vendor = connection.vendor
    with connection.cursor() as cursor:
        if db_vendor == 'sqlite':
            # SQLite approach
            cursor.execute(f"DELETE FROM sqlite_sequence WHERE name='{table_name}'")
        elif db_vendor == 'postgresql':
            # PostgreSQL approach
            sequence_name = f"{table_name}_{pk_field}_seq"
            cursor.execute(f"ALTER SEQUENCE {sequence_name} RESTART WITH 1")
        elif db_vendor == 'mysql':
            # MySQL approach
            cursor.execute(f"ALTER TABLE {table_name} AUTO_INCREMENT = 1")
        else:
            # For other databases, log a warning
            import logging
            logging.warning(f"PK sequence reset not implemented for {db_vendor}")

def reset_computer_usage_pk():
    """
    Reset the primary key sequence for ComputerUsage.
    Uses a database-agnostic approach that will work with most backends.
    """
    # Get the table name
    table_name = ComputerUsage._meta.db_table
    pk_field = 'counter'  # Use the counter field name directly
    # Get database vendor name (postgresql, mysql, sqlite, etc.)
    db_vendor = connection.vendor
    with connection.cursor() as cursor:
        if db_vendor == 'sqlite':
            # SQLite approach
            cursor.execute(f"DELETE FROM sqlite_sequence WHERE name='{table_name}'")
        elif db_vendor == 'postgresql':
            # PostgreSQL approach
            sequence_name = f"{table_name}_{pk_field}_seq"
            cursor.execute(f"ALTER SEQUENCE {sequence_name} RESTART WITH 1")
        elif db_vendor == 'mysql':
            # MySQL approach
            cursor.execute(f"ALTER TABLE {table_name} AUTO_INCREMENT = 1")
        else:
            # For other databases, log a warning
            import logging
            logging.warning(f"PK sequence reset not implemented for {db_vendor}")

def move_computer_usage_to_buffer(school_year=None):
    """
    Move all records from ComputerUsage to ComputerUsageBuffer.
    This converts user to section.
    
    Args:
        school_year: The school year to assign to buffer records (optional)
                   If not provided, will calculate based on current date
    """
    with transaction.atomic():
        # Determine school year if not provided
        if not school_year:
            today = timezone.now()
            if today.month >= 6:
                school_year = f"{today.year}-{today.year + 1}"
            else:
                school_year = f"{today.year - 1}-{today.year}"
        
        # Calculate previous school year
        try:
            current_start, current_end = school_year.split('-')
            previous_start = int(current_start) - 1
            previous_end = int(current_end) - 1
            previous_school_year = f"{previous_start}-{previous_end}"
        except (ValueError, AttributeError):
            previous_school_year = None
        
        # Get all computer usage records
        computer_records = ComputerUsage.objects.all()
        # Create buffer records from each computer usage record
        for record in computer_records:
            ComputerUsageBuffer.create_from_computer_usage(record, previous_school_year)
        # Return the count of records moved
        return computer_records.count()

def move_computer_buffer_to_archive():
    """
    Move all records from ComputerUsageBuffer to ComputerUsageArchive.
    """
    with transaction.atomic():
        # Get all buffer records
        buffer_records = ComputerUsageBuffer.objects.all()
        # Create archive records from each buffer record
        for record in buffer_records:
            ComputerUsageArchive.create_from_buffer_record(record)
        # Return the count of records moved
        return buffer_records.count()

def archive_computer_usage_records(school_year=None):
    """
    Archive computer usage records as part of the new school year process.
    1. Delete existing ComputerUsageArchive records
    2. Move ComputerUsageBuffer records to ComputerUsageArchive
    3. Move ComputerUsage records to ComputerUsageBuffer
    4. Clear ComputerUsage records
    
    Args:
        school_year: The current school year (optional)
                   If not provided, will calculate based on current date
    
    Returns the number of records processed.
    """
    try:
        # Determine school year if not provided
        if not school_year:
            today = timezone.now()
            if today.month >= 6:
                school_year = f"{today.year}-{today.year + 1}"
            else:
                school_year = f"{today.year - 1}-{today.year}"
        
        # Log the process steps for debugging
        print(f"Starting computer usage archiving for school year {school_year}")
        
        # Step 1: Delete all archive records
        archive_deleted = ComputerUsageArchive.objects.count()
        print(f"Deleting {archive_deleted} archive records")
        ComputerUsageArchive.objects.all().delete()
        
        # Step 2: Move buffer records to archive
        buffer_records = ComputerUsageBuffer.objects.all()
        buffer_moved = buffer_records.count()
        print(f"Moving {buffer_moved} buffer records to archive")
        
        for record in buffer_records:
            try:
                ComputerUsageArchive.create_from_buffer_record(record)
            except Exception as e:
                print(f"Error moving buffer record {record.counter}: {str(e)}")
        
        # Step 3: Clear the buffer
        print("Clearing buffer records")
        ComputerUsageBuffer.objects.all().delete()
        
        # Step 4: Calculate previous school year
        try:
            current_start, current_end = school_year.split('-')
            previous_start = int(current_start) - 1
            previous_end = int(current_end) - 1
            previous_school_year = f"{previous_start}-{previous_end}"
        except (ValueError, AttributeError):
            previous_school_year = None
        
        print(f"Using previous school year: {previous_school_year}")
        
        # Step 5: Move current computer usage records to buffer
        computer_usage_records = ComputerUsage.objects.all()
        usage_moved = computer_usage_records.count()
        print(f"Moving {usage_moved} current records to buffer")
        
        for record in computer_usage_records:
            try:
                ComputerUsageBuffer.create_from_computer_usage(record, previous_school_year)
            except Exception as e:
                print(f"Error moving current record {record.counter}: {str(e)}")
        
        # Step 6: Clear the ComputerUsage table
        print("Clearing current records")
        ComputerUsage.objects.all().delete()
        
        print("Computer usage archiving completed successfully")
        return archive_deleted + buffer_moved + usage_moved
        
    except Exception as e:
        print(f"Error in archive_computer_usage_records: {str(e)}")
        # Re-raise the exception to trigger transaction rollback in the outer transaction
        raise

def get_current_school_year():
    """
    Determine the current school year based on today's date.
    School year is defined as running from June to May
    (e.g., June 2024 - May 2025 is "2024-2025")
    """
    today = timezone.now()
    year = today.year
    month = today.month
    
    # If date is from January to May, it's part of the previous year's school year
    if 1 <= month <= 5:
        return f"{year-1}-{year}"
    # If date is from June to December, it's the start of a new school year
    else:
        return f"{year}-{year+1}"
    
def get_db_school_years():
    """
    Returns a dictionary mapping each database to its school year
    - ComputerUsage = current school year
    - ComputerUsageBuffer = previous school year
    - ComputerUsageArchive = two years ago
    """
    current_year = get_current_school_year()
    
    # Extract the first year from the current school year
    start_year = int(current_year.split('-')[0])
    
    return {
        'current': current_year,  # e.g., "2024-2025"
        'buffer': f"{start_year-1}-{start_year}",  # e.g., "2023-2024"
        'archive': f"{start_year-2}-{start_year-1}"  # e.g., "2022-2023"
    }