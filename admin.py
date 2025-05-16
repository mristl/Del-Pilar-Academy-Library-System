from django.contrib import admin, messages
from django.urls import path
from django.shortcuts import render, redirect
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.contrib.admin.views.decorators import staff_member_required
from .models import (Book, User, ComputerUsage, BorrowRecord, MARC_FIELD, 
                    BorrowRecordsBuffer, BorrowRecordsArchive, 
                    ComputerUsageBuffer, ComputerUsageArchive) 

# Custom action to set all selected books as borrowed
def mark_all_books_as_borrowed(modeladmin, request, queryset):
    updated_count = queryset.update(status='borrowed')
    modeladmin.message_user(request, f'{updated_count} books have been set to borrowed.')

mark_all_books_as_borrowed.short_description = _("Mark all selected books as borrowed")

# Custom action to set all selected books as available
def mark_all_books_as_available(modeladmin, request, queryset):
    updated_count = queryset.update(status='available')
    modeladmin.message_user(request, f'{updated_count} books have been set to available.')

mark_all_books_as_available.short_description = _("Mark all selected books as available")

def delete_all_unselected_books(modeladmin, request, queryset):
    selected_ids = queryset.values_list('accession_number',flat=True)
    deleted_count = Book.objects.exclude(accession_number__in=selected_ids).delete()
    modeladmin.message_user(request, f'{deleted_count} books have been deleted.')

delete_all_unselected_books.short_description = _("Deletes all books that aren't selected from the database")

def update_all_books(modeladmin, request, queryset):
    """Updates all book records using set_from_marc_field()"""
    
    updated_count = 0
    for book in queryset:
        book.set_from_marc_field()  # Call the update method
        book.save()  # Save the updated record
        updated_count += 1

    modeladmin.message_user(request, f"Updated {updated_count} book records successfully!")

class BookAdmin(admin.ModelAdmin):
    list_display = ('title', 'accession_number','marc_control_number', 'status','date_borrowed','collection_type')  # Display book details
    actions = [mark_all_books_as_borrowed, mark_all_books_as_available,delete_all_unselected_books,update_all_books]  # Add both actions
    list_filter = ('status',)  # Add filter by status
    search_fields = ('title', 'author', 'publisher', 'accession_number')  # Add search functionality

# Register the Book model with the custom admin class
admin.site.register(Book, BookAdmin)

class MARC_FIELDAdmin(admin.ModelAdmin):
    list_display = ('marc_001_control_number','marc_245_title_and_statement_of_responsibility','marc_100_main_entry_personal_name','marc_250_edition','marc_260_publication',)
    list_filter = ('marc_300_physical_description',)
    search_fields = ('marc_001_control_number', 'marc_245_title_and_statement_of_responsibility','marc_300_physical_description',)

# Register the MARC_FIELD model with custom admin class
admin.site.register(MARC_FIELD, MARC_FIELDAdmin)

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('id_number', 'name', 'user_type', 'section', 'school_email', 'is_flagged')  
    search_fields = ('id_number', 'name', 'school_email', 'section')  
    list_filter = ('user_type', 'section', 'is_flagged')  


class BorrowRecordAdmin(admin.ModelAdmin):
    list_display = (
        'borrow_record_number',  # Primary Key
        'book_accession_number',  # Accession Number of Book
        'user_id',  # User ID
        'borrow_date',  # When it was borrowed
        'expected_return_date',  # Due date
        'return_date',  # When it was returned
        'late_payment_fee_amount',  # Fine
        'near_overdue_date',  # Near overdue warning
        'borrow_status',  # Borrow Status (Borrowed/Returned)
    )
    list_filter = ('borrow_status',)  # Filter by status (Borrowed/Returned)
    search_fields = ('book_accession_number', 'user_id')  # Search by Book Accession or User ID
    
    actions = ['process_queue']

    def process_queue(self, request, queryset):
        """Admin action to manually process the queue"""
        try:
            process_borrow_records_queue()
            self.message_user(
                request, 
                "Queue processed successfully. Records moved: Current → Buffer → Archive",
                messages.SUCCESS
            )
        except Exception as e:
            self.message_user(
                request,
                f"Error processing queue: {str(e)}",
                messages.ERROR
            )
    
    process_queue.short_description = "Process queue (move records to buffer and archive)"


# Define queue management functions directly in admin.py to avoid import issues
def process_borrow_records_queue():
    """Process the queue, moving records from current → buffer → archive → deletion"""
    # Step 1: Delete all records in Archive to make room for Buffer records
    BorrowRecordsArchive.objects.all().delete()
    
    # Step 2: Move all Buffer records to Archive
    buffer_records = BorrowRecordsBuffer.objects.all()
    for buffer_record in buffer_records:
        # Create archive record from buffer record
        BorrowRecordsArchive.create_from_buffer_record(buffer_record)
    
    # Clear the buffer after moving records to archive
    buffer_records.delete()
    
    # Step 3: Move all current BorrowRecord records to Buffer
    current_records = BorrowRecord.objects.all()
    for record in current_records:
        # Create buffer record from borrow record
        BorrowRecordsBuffer.create_from_borrow_record(record)


# Admin model classes
class BufferRecordAdmin(admin.ModelAdmin):
    list_display = ('borrow_record_number', 'section', 'collection_type',
                   'formatted_borrow_date', 'formatted_expected_return', 'formatted_return_date',
                   'borrow_status', 'near_overdue_date')
    list_filter = ('borrow_status', 'section', 'collection_type')  # Removed borrow_date from filters
    search_fields = ('section', 'collection_type')
    # Removed date_hierarchy to avoid timezone issues
    
    def formatted_borrow_date(self, obj):
        """Safely format the borrow date to avoid timezone issues"""
        try:
            if obj.borrow_date:
                return obj.borrow_date.strftime('%Y-%m-%d %H:%M')
            return '-'
        except (ValueError, AttributeError):
            return 'Invalid date'
    formatted_borrow_date.short_description = 'Borrow Date'
    
    def formatted_expected_return(self, obj):
        """Safely format the expected return date"""
        try:
            if obj.expected_return_date:
                return obj.expected_return_date.strftime('%Y-%m-%d %H:%M')
            return '-'
        except (ValueError, AttributeError):
            return 'Invalid date'
    formatted_expected_return.short_description = 'Expected Return'
    
    def formatted_return_date(self, obj):
        """Safely format the return date"""
        try:
            if obj.return_date:
                return obj.return_date.strftime('%Y-%m-%d %H:%M')
            return '-'
        except (ValueError, AttributeError):
            return 'Invalid date'
    formatted_return_date.short_description = 'Return Date'
    
    def get_queryset(self, request):
        """Override queryset to handle timezone issues"""
        qs = super().get_queryset(request)
        return qs


class ArchiveRecordAdmin(admin.ModelAdmin):
    list_display = ('borrow_record_number', 'section', 'collection_type',
                   'formatted_borrow_date', 'formatted_expected_return', 'formatted_return_date',
                   'borrow_status', 'near_overdue_date')
    list_filter = ('borrow_status', 'section', 'collection_type')  # Removed borrow_date from filters
    search_fields = ('section', 'collection_type')
    # Removed date_hierarchy to avoid timezone issues
    
    def formatted_borrow_date(self, obj):
        """Safely format the borrow date to avoid timezone issues"""
        try:
            if obj.borrow_date:
                return obj.borrow_date.strftime('%Y-%m-%d %H:%M')
            return '-'
        except (ValueError, AttributeError):
            return 'Invalid date'
    formatted_borrow_date.short_description = 'Borrow Date'
    
    def formatted_expected_return(self, obj):
        """Safely format the expected return date"""
        try:
            if obj.expected_return_date:
                return obj.expected_return_date.strftime('%Y-%m-%d %H:%M')
            return '-'
        except (ValueError, AttributeError):
            return 'Invalid date'
    formatted_expected_return.short_description = 'Expected Return'
    
    def formatted_return_date(self, obj):
        """Safely format the return date"""
        try:
            if obj.return_date:
                return obj.return_date.strftime('%Y-%m-%d %H:%M')
            return '-'
        except (ValueError, AttributeError):
            return 'Invalid date'
    formatted_return_date.short_description = 'Return Date'
    
    def get_queryset(self, request):
        """Override queryset to handle timezone issues"""
        qs = super().get_queryset(request)
        return qs


# Register models with admin
admin.site.register(BorrowRecordsBuffer, BufferRecordAdmin)
admin.site.register(BorrowRecordsArchive, ArchiveRecordAdmin)
admin.site.register(BorrowRecord, BorrowRecordAdmin)

# Updated admin classes for ComputerUsage models to fix timezone issues

@admin.register(ComputerUsage)
class ComputerUsageAdmin(admin.ModelAdmin):
    list_display = ('counter', 'user_id_display', 'user_name_display', 'formatted_date')
    list_filter = ('user__user_type',)  # Remove date from list_filter temporarily
    search_fields = ('user__id_number', 'user__name')
    # Remove date_hierarchy completely to avoid timezone issues
    actions = ['process_queue']
    
    def user_id_display(self, obj):
        return obj.user.id_number
    user_id_display.short_description = 'User ID'
    
    def user_name_display(self, obj):
        return obj.user.name
    user_name_display.short_description = 'User Name'
    
    def formatted_date(self, obj):
        """Safely format the date to avoid timezone issues"""
        try:
            if obj.date:
                return obj.date.strftime('%Y-%m-%d %H:%M')
            return '-'
        except (ValueError, AttributeError):
            return 'Invalid date'
    formatted_date.short_description = 'Date'
    
    def get_queryset(self, request):
        """Override queryset to handle timezone issues"""
        qs = super().get_queryset(request)
        # Use extra with CAST to handle problematic datetime values
        return qs
    
    def process_queue(self, request, queryset):
        """Admin action to manually process the computer usage queue"""
        try:
            process_computer_usage_queue()  # Call the global function
            self.message_user(
                request, 
                "Computer usage queue processed successfully. Records moved: Current → Buffer → Archive",
                messages.SUCCESS
            )
        except Exception as e:
            self.message_user(
                request,
                f"Error processing queue: {str(e)}",
                messages.ERROR
            )
    
    process_queue.short_description = "Process queue (move records to buffer and archive)"

@admin.register(ComputerUsageBuffer)
class ComputerUsageBufferAdmin(admin.ModelAdmin):
    list_display = ('counter', 'section', 'formatted_date', 'school_year')
    list_filter = ('section', 'school_year')  # Remove date from list_filter temporarily
    search_fields = ('section',)
    # Remove date_hierarchy completely to avoid timezone issues
    
    def formatted_date(self, obj):
        """Safely format the date to avoid timezone issues"""
        try:
            if obj.date:
                return obj.date.strftime('%Y-%m-%d %H:%M')
            return '-'
        except (ValueError, AttributeError):
            return 'Invalid date'
    formatted_date.short_description = 'Date'
    
    def get_queryset(self, request):
        """Override queryset to handle timezone issues"""
        qs = super().get_queryset(request)
        # Use extra with CAST to handle problematic datetime values
        return qs


@admin.register(ComputerUsageArchive)
class ComputerUsageArchiveAdmin(admin.ModelAdmin):
    list_display = ('counter', 'section', 'formatted_date', 'school_year')
    list_filter = ('section', 'school_year')  # Remove date from list_filter temporarily 
    search_fields = ('section',)
    # Remove date_hierarchy completely to avoid timezone issues
    
    def formatted_date(self, obj):
        """Safely format the date to avoid timezone issues"""
        try:
            if obj.date:
                return obj.date.strftime('%Y-%m-%d %H:%M')
            return '-'
        except (ValueError, AttributeError):
            return 'Invalid date'
    formatted_date.short_description = 'Date'
    
    def get_queryset(self, request):
        """Override queryset to handle timezone issues"""
        qs = super().get_queryset(request)
        # Use extra with CAST to handle problematic datetime values
        return qs
    
# Define queue management functions directly in admin.py to avoid import issues
def process_borrow_records_queue():
    """Process the queue, moving records from current → buffer → archive → deletion"""
    # Step 1: Delete all records in Archive to make room for Buffer records
    BorrowRecordsArchive.objects.all().delete()
    
    # Step 2: Move all Buffer records to Archive
    buffer_records = BorrowRecordsBuffer.objects.all()
    for buffer_record in buffer_records:
        # Create archive record from buffer record
        BorrowRecordsArchive.create_from_buffer_record(buffer_record)
    
    # Clear the buffer after moving records to archive
    buffer_records.delete()
    
    # Step 3: Move all current BorrowRecord records to Buffer
    current_records = BorrowRecord.objects.all()
    for record in current_records:
        # Create buffer record from borrow record
        BorrowRecordsBuffer.create_from_borrow_record(record)

# Process Computer Usage Queue Function - ADD HERE AS STANDALONE FUNCTION
def process_computer_usage_queue():
    """Process the queue, moving records from current → buffer → archive → deletion"""
    # Step 1: Delete all records in Archive to make room for Buffer records
    ComputerUsageArchive.objects.all().delete()
    
    # Step 2: Move all Buffer records to Archive
    buffer_records = ComputerUsageBuffer.objects.all()
    for buffer_record in buffer_records:
        # Create archive record from buffer record
        ComputerUsageArchive.create_from_buffer_record(buffer_record)
    
    # Clear the buffer after moving records to archive
    buffer_records.delete()
    
    # Step 3: Move all current ComputerUsage records to Buffer with current school year
    current_records = ComputerUsage.objects.all()
    
    # Determine current school year
    today = timezone.now()
    if today.month >= 6:
        current_school_year = f"{today.year}-{today.year + 1}"
    else:
        current_school_year = f"{today.year - 1}-{today.year}"
    
    for record in current_records:
        # Create buffer record from computer usage record
        ComputerUsageBuffer.create_from_computer_usage(record, current_school_year)