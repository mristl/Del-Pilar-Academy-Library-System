from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.utils.timezone import now
from datetime import timedelta, datetime
from .models import Book, User, MARC_FIELD, ComputerUsage, ComputerUsageBuffer, ComputerUsageArchive, BorrowRecord, BorrowRecordsArchive, BorrowRecordsBuffer
from django.contrib import messages
from django.http import JsonResponse
from django.core.paginator import Paginator
import datetime, os, tempfile, base64
from .generate_report import generate_pdf_report
from django.http import HttpResponse, FileResponse, JsonResponse
from django.contrib.auth.forms import UserCreationForm
from .forms import CreateUserForm, BookForm, MARCRecordForm
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.admin.views.decorators import staff_member_required
from typing import Protocol
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate, get_user_model
from django.contrib.auth.forms import SetPasswordForm
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache
from django.template.loader import render_to_string
from django.contrib.sites.shortcuts import get_current_site
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.core.mail import EmailMessage
from django.conf import settings
from collections import defaultdict
import base64, traceback
import re, csv, io
from django.db import IntegrityError
from django.views.decorators.csrf import csrf_exempt
from django.utils.safestring import mark_safe
from django.urls import reverse, NoReverseMatch # <--- ADD/MODIFY THIS LINE
from django.db.models import Max

from django.db import transaction



from .utils import reset_borrowrecord_pk, move_records_to_buffer, move_buffer_to_archive, reset_computer_usage_pk

from .utils import reset_borrowrecord_pk, move_records_to_buffer, move_buffer_to_archive

from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

from django.core.files.storage import default_storage


BACKUP_DIR = os.path.join(settings.BASE_DIR, 'backups')
DB_PATH = os.path.join(settings.BASE_DIR, 'db.sqlite3')


from .tokens import account_activation_token, password_reset_token
import base64

import os
from django.conf import settings
import shutil

from django.contrib.admin.views.decorators import staff_member_required

from django.urls import reverse_lazy
from django.shortcuts import render
from django.contrib.auth.views import PasswordResetConfirmView


COLLECTION_INFO = {
    'circulation': {'prefix': 'CIR', 'name': 'Circulation', 'room_use_only': False},
    'filipiniana': {'prefix': 'FIL', 'name': 'Filipiniana', 'room_use_only': False},
    'shsfilipiniana': {'prefix': 'SHS FIL', 'name': 'SHS Filipiniana', 'room_use_only': False},
    'shscirculation': {'prefix': 'SHS CIR', 'name': 'SHS Circulation', 'room_use_only': False},
    'ficandscholastic': {'prefix': 'FIC', 'name': 'Fiction and Scholastic', 'room_use_only': False},
    'reference': {'prefix': 'REF', 'name': 'Reference', 'room_use_only': True},
    'archives': {'prefix': 'ARC', 'name': 'Archives', 'room_use_only': True},
    'shsreference': {'prefix': 'SHS REF', 'name': 'SHS Reference', 'room_use_only': True},
    'periodicals': {'prefix': 'PER', 'name': 'Periodicals', 'room_use_only': True},
}

def get_next_accession_number(collection_type):
    info = COLLECTION_INFO.get(collection_type.lower())
    if not info:
        raise ValueError(f"No data found for collection type '{collection_type}'")

    prefix = info['prefix']
    prefix_with_space = f"{prefix} "

    latest_book = Book.objects.filter(accession_number__startswith=prefix_with_space).order_by('-accession_number').first()

    if latest_book:
        try:
            latest_number = int(latest_book.accession_number[len(prefix_with_space):])
        except (ValueError, IndexError):
            latest_number = 0
    else:
        latest_number = 0

    next_number = latest_number + 1
    return f"{prefix} {next_number:06}"
class CustomPasswordResetConfirmView(PasswordResetConfirmView):
    def dispatch(self, request, *args, **kwargs):
        self.validlink = False
        try:
            response = super().dispatch(request, *args, **kwargs)
            if not self.validlink:
                return render(request, 'libapp/password_reset_link_expired.html')
            return response
        except Exception:
            return render(request, 'libapp/password_reset_link_expired.html')

    def get_success_url(self):
        # Provide a fallback in case Django internally redirects on error
        return reverse_lazy('password_reset_done')  # or any valid view


def merge_sort(arr, key_func): #sorting criteria
    if len(arr) <= 1: #if list contains 1 or 0 elements
        return arr
    
    mid = len(arr) // 2 #array divided into 2, index
    left_half = merge_sort(arr[:mid], key_func) #create left half by slicing, then sorted until  divided into single-element arrays
    right_half = merge_sort(arr[mid:], key_func)

    return merge(left_half, right_half, key_func) #after both halves have been sorted, combine both halves

def merge(left, right, key_func):
    sorted_list = []
    
    while left and right: #loop until both halves are empty
        left_key = key_func(left[0]).lower() if isinstance(key_func(left[0]), str) else key_func(left[0])
        right_key = key_func(right[0]).lower() if isinstance(key_func(right[0]), str) else key_func(right[0])
        
        if left_key <= right_key: #if left key is less than or equal to right key
            sorted_list.append(left.pop(0)) #add left element to sorted list
        else:
            sorted_list.append(right.pop(0)) #add right element to sorted list
    
    sorted_list.extend(left) #add remaining elements to the end
    sorted_list.extend(right)
    
    return sorted_list

def binary_search(arr, key, key_attr): #partial implementation can be done by checking neighbors
    low, high = 0, len(arr) - 1
    while low <= high:
        mid = (low + high) // 2
        mid_key = getattr(arr[mid], key_attr).lower()  
        
        if mid_key == key.lower():
            return arr[mid]
        elif mid_key < key.lower():
            low = mid + 1
        else:
            high = mid - 1
    return None

# WEBSITE LOADING STARTS HERE

@never_cache
@login_required(login_url='login')
def home_page(request):
    return render(request, 'libapp/home_page.html')

# WEBSITE LOADING STARTS HERE

@never_cache
@login_required(login_url='login')
def borrow_book(request):
    all_users_qs = User.objects.all()
    # Fetch all books first, then filter for 'available' for the binary search list
    # but we also need to check the status of any book by accession number
    all_books_qs = Book.objects.all()

    # Create lists for sorting and binary search from querysets
    all_users_list = list(all_users_qs)
    all_books_list_for_status_check = list(all_books_qs) # For checking status of any book
    available_books_list_for_display = list(Book.objects.filter(status='available')) # For display and initial search

    # Sort the lists
    # Ensure key_func handles potential None or non-string attributes robustly
    all_users_list = merge_sort(all_users_list, key_func=lambda user: str(user.id_number) if user else "")
    available_books_list_for_display = merge_sort(available_books_list_for_display, key_func=lambda book: str(book.accession_number) if book else "")
    all_books_list_for_status_check = merge_sort(all_books_list_for_status_check, key_func=lambda book: str(book.accession_number) if book else "")


    paginator = Paginator(available_books_list_for_display, 10) # Paginate only available books
    page_number = request.GET.get('page')
    book_list_page_obj = paginator.get_page(page_number) # Renamed to avoid conflict

    if request.method == "POST":
        accession_number = request.POST.get('accession_number', '').strip()
        user_id = request.POST.get('user_id', '').strip()
        room_use_str = request.POST.get('room_use')

        if not accession_number or not user_id:
            messages.error(request, 'User ID and Accession Number are required.')
            return render(request, 'libapp/borrow_book.html', {'book_list': book_list_page_obj})


        try:
            user = binary_search(all_users_list, user_id, 'id_number')
            if user is None:
                messages.error(request, f'User ID "{user_id}" not found.')
                return render(request, 'libapp/borrow_book.html', {'book_list': book_list_page_obj})

            if user.is_flagged:
                messages.error(request, f'User {user.id_number} - {user.name} has been flagged and cannot borrow books.')
                return render(request, 'libapp/borrow_book.html', {'book_list': book_list_page_obj})
            
            # First, check if the book exists at all using the comprehensive list
            book_to_borrow = binary_search(all_books_list_for_status_check, accession_number, 'accession_number')

            if book_to_borrow is None:
                messages.error(request, f'Book with Accession No: "{accession_number}" does not exist in the library records.')
                return render(request, 'libapp/borrow_book.html', {'book_list': book_list_page_obj})

            # Now check its status specifically
            if book_to_borrow.status != 'available':
                if book_to_borrow.status == 'flagged':
                    messages.error(request, f"Book '{book_to_borrow.title}' (Accession No: {accession_number}) is currently flagged.\nREASON: {book_to_borrow.status_notes}).")
                    return render(request, 'libapp/borrow_book.html', {'book_list': book_list_page_obj})

                else:
                    messages.error(request, f"Book '{book_to_borrow.title}' (Accession No: {accession_number}) is currently not available (Status: {book_to_borrow.get_status_display()}).")
                    return render(request, 'libapp/borrow_book.html', {'book_list': book_list_page_obj})

            # If we reach here, book_to_borrow is the correct book object and it's available

            is_room_use = room_use_str == "True"

            if is_room_use:
                # For room use, we don't change book status to 'borrowed' persistently
                # We just record the usage.
                # book_to_borrow.date_borrowed = timezone.now() # Not strictly needed for Room Use if status isn't 'borrowed'
                # book_to_borrow.user = user # Not strictly needed for Room Use if status isn't 'borrowed'
                # No save on book_to_borrow for room use regarding persistent status change

                BorrowRecord.objects.create(
                    book_accession_number=book_to_borrow.accession_number,
                    user_id=user.id_number,
                    borrow_date=timezone.now(),
                    expected_return_date=timezone.now(), # For room use, expected and actual return is immediate
                    return_date=timezone.now(),
                    borrow_status="returned" # Mark as returned immediately for room use
                )
                messages.success(request, f"Successfully recorded: '{book_to_borrow.title}' for Room Use by {user.name}. (Accession No: {book_to_borrow.accession_number})")
                return redirect('view_books')

            # --- Home Use Logic ---
            borrowed_books_count = Book.objects.filter(status='borrowed', user=user, room_use=False).count()

            # Determine borrow limit based on user type
            if user.user_type == 'Student':
                borrow_limit = 1
            elif user.user_type == "Friends of the Library":
                borrow_limit = 2
            elif user.user_type == 'Staff':
                borrow_limit = 2
            else: # Default fallback
                borrow_limit = 1

            if borrowed_books_count >= borrow_limit:
                messages.error(request, f'Borrower {user.name} has exceeded their home-use borrow limit of {borrow_limit} book(s).')
                return render(request, 'libapp/borrow_book.html', {'book_list': book_list_page_obj})

            if book_to_borrow.collection_type in ["reference", "archives", "shsreference", "periodicals"] and not is_room_use:
                messages.error(request, f"Book '{book_to_borrow.title}' is for Room Use only and cannot be borrowed for home use.")
                return render(request, 'libapp/borrow_book.html', {'book_list': book_list_page_obj})
            
            # Final check of status, though already done, this is a safeguard
            if book_to_borrow.status == 'available':
                book_to_borrow.status = 'borrowed'
                book_to_borrow.user = user 
                book_to_borrow.date_borrowed = timezone.now() 
                book_to_borrow.room_use = False # Explicitly for home use

                expected_return_date_calculated = book_to_borrow.expected_return_date # Call property on the specific book

                if expected_return_date_calculated is None:
                    messages.error(request, "Critical Error: Could not determine the expected return date. Borrowing cancelled.")
                    # Revert status if calculation fails, though this indicates a deeper model logic issue
                    book_to_borrow.status = 'available'
                    book_to_borrow.user = None
                    book_to_borrow.date_borrowed = None
                    # book_to_borrow.save() # Save the revert if needed, or just don't proceed.
                    return render(request, 'libapp/borrow_book.html', {'book_list': book_list_page_obj})

                book_to_borrow.due_date = expected_return_date_calculated 
                book_to_borrow.save()

                new_borrow_record = BorrowRecord.objects.create(
                    book_accession_number=book_to_borrow.accession_number,
                    user_id=user.id_number,
                    borrow_date=book_to_borrow.date_borrowed, 
                    expected_return_date=expected_return_date_calculated,
                    borrow_status="borrowed"
                )

                try:
                    send_borrow_confirmation_email(request, new_borrow_record) # Assuming this function exists
                    messages.success(request, f"Successfully borrowed: '{book_to_borrow.title}' (Accession No: {book_to_borrow.accession_number}) by {user.name}. A confirmation email has been sent.")
                except Exception as email_exc:
                    print(f"Borrow successful for {book_to_borrow.accession_number}, but email sending failed: {email_exc}")
                    messages.warning(request, f"Successfully borrowed: '{book_to_borrow.title}' (Accession No: {book_to_borrow.accession_number}) by {user.name}. However, the confirmation email could not be sent.")
                
                return redirect('view_books')
            else:
                # This else should ideally not be reached if the first status check was done correctly
                messages.error(request, f"Book '{book_to_borrow.title}' is not available for borrowing (Current Status: {book_to_borrow.get_status_display()}). Please refresh the page.")
                return render(request, 'libapp/borrow_book.html', {'book_list': book_list_page_obj})

        except Exception as e:
            print(traceback.format_exc()) # For server-side debugging
            messages.error(request, f'An unexpected error occurred: {str(e)}')
            return render(request, 'libapp/borrow_book.html', {'book_list': book_list_page_obj})

    return render(request, 'libapp/borrow_book.html', {'book_list': book_list_page_obj})
def linear_search(books, query, key_func):
    matched_books = []

    for book in books:
        if query.lower() in key_func(book).lower():
            matched_books.append(book)

    return matched_books

from django.contrib import messages

@login_required(login_url='login')
def add_book(request):
    if request.method == 'POST':
        book_form = BookForm(request.POST)
        marc_form = MARCRecordForm(request.POST)

        if book_form.is_valid() and marc_form.is_valid():
            marc_record = marc_form.save()
            book = book_form.save(commit=False)

            # Generate accession number based on collection type
            collection_type = book.collection_type  # Assuming this field exists
            book.accession_number = get_next_accession_number(collection_type)

            book.marc_control_number = marc_record
            book.set_from_marc_field()
            book.save()
            
            messages.success(request, 'New book added successfully!')
            return redirect('add_books')
        else:
            # Collect specific error messages for each invalid field
            error_messages = []
            
            
            # If there are any error messages, display them
            if error_messages:
                messages.error(request, "Please correct the errors below: " + " ".join(error_messages))
    else:
        book_form = BookForm()
        marc_form = MARCRecordForm()

    return render(request, 'libapp/add_books.html', {
        'book_form': book_form,
        'marc_form': marc_form
    })


@never_cache
@login_required(login_url='login')
def view_books(request):
    borrowed_books = Book.objects.all()
    current_date = timezone.now().date()

    # Check if queryset is empty BEFORE any operations
    if not borrowed_books.exists():
        # Return early with empty list if no books
        return render(request, 'libapp/view_books.html', {
            'view_list': [],
            'current_date': current_date,
            'search_query': '',
            'sort_field': 'accession_number',
            'status_filters': [],
        })

    # Capture sorting criteria
    sort_field = request.GET.get('sort', 'accession_number')

    # Apply sorting based on selected field
    if sort_field == 'title':
        borrowed_books = merge_sort(borrowed_books, key_func=lambda book: book.title)
    elif sort_field == 'author':
        borrowed_books = merge_sort(borrowed_books, key_func=lambda book: book.author)
    elif sort_field == 'publisher':
        borrowed_books = merge_sort(borrowed_books, key_func=lambda book: book.publisher)
    elif sort_field == 'days_remaining':
        borrowed_books = merge_sort(borrowed_books, key_func=lambda book: book.days_remaining if book.days_remaining is not None else 9999
)
    elif sort_field == 'accession_number':
        borrowed_books = merge_sort(borrowed_books, key_func=lambda book: book.accession_number)

    # Apply search filtering (before pagination)
    search_query = request.GET.get('search', '')
    if search_query:
        borrowed_books = linear_search(
            borrowed_books,
            search_query,
            key_func=lambda book: f"{book.title} {book.accession_number} {book.user.name if book.user else ''}"
        )

    # Status filtering (before pagination)
    status_filters = []
    if request.GET.get('available'):
        status_filters.append('Available')
    if request.GET.get('overdue'):
        status_filters.append('Overdue')
    if request.GET.get('borrowed'):
        status_filters.append('Borrowed')
    if request.GET.get('flagged'):
        status_filters.append('Flagged')

    if status_filters:
        borrowed_books = [book for book in borrowed_books if book.status in status_filters]

    # Calculate return dates, expected return dates, and fines for overdue books
    overdue_books = []
    for book in borrowed_books:
        if book.days_remaining is not None and book.days_remaining < 0:  # Overdue
            book.status = 'overdue'
            fine = abs(book.days_remaining) * 5  # 5 pesos per day
            overdue_books.append({
                'accession_number': book.accession_number,
                'title': book.title,
                'fine': fine,
                'user': book.user.name if book.user else 'N/A'  # Handle missing users
            })

    # Pagination (AFTER filtering)
    paginator = Paginator(borrowed_books, len(borrowed_books))  # Show all on first page
    page_number = request.GET.get('page')
    paginated_books = paginator.get_page(page_number)


    return render(request, 'libapp/view_books.html', {
        'view_list': paginated_books,  # Pass paginated books to template
        'search_query': search_query,
        'sort_field': sort_field,
        'current_date': current_date,
        'status_filters': status_filters,  # Keep selected filters active
    })




@never_cache
@login_required(login_url='login')
def return_book(request):
    return_form_url_name = 'return_book'

    if request.method == "POST":
        accession_number = request.POST.get('accession_number', '').strip()
        if not accession_number:
             messages.error(request, "Please enter an Accession Number.")
             return redirect(return_form_url_name)

        try:
            try:
                book = Book.objects.get(accession_number__iexact=accession_number)
            except Book.DoesNotExist:
                messages.error(request, f"Book with Accession No: '{accession_number}' not found.")
                return redirect(return_form_url_name)

            if book.status == 'available':
                messages.error(request, f"The book '{book.title}' is already marked as available (not borrowed).")
                return redirect(return_form_url_name)

            borrow_record = BorrowRecord.objects.filter(
                book_accession_number=book.accession_number,
                user_id=book.user.id_number if book.user else None,
                return_date__isnull=True
            ).order_by('-borrow_date').first()

            if not borrow_record:
                borrow_record = BorrowRecord.objects.filter(
                   book_accession_number=book.accession_number,
                   return_date__isnull=True
                ).order_by('-borrow_date').first()

            if not borrow_record:
                messages.error(request, f"No active borrow record found for book '{book.title}'. Cannot process return.")
                return redirect(return_form_url_name)

            current_days_remaining = book.days_remaining
            is_overdue = current_days_remaining is not None and current_days_remaining < 0

            if book.status == 'overdue' or is_overdue:
                next_redirect_url = reverse(return_form_url_name)
                confirm_url = reverse('confirm_return', kwargs={'accession_number': accession_number})
                return redirect(f"{confirm_url}?next={next_redirect_url}")


            elif book.status == 'borrowed' and not is_overdue:
                late_fee = 0
                borrow_record.return_date = timezone.now()
                borrow_record.borrow_status = "returned"
                borrow_record.late_payment_fee_amount = late_fee
                borrow_record.save()
                book.status = 'available'
                book.date_borrowed = None
                book.user = None
                book.due_date = None
                book.save()
                messages.success(request, f"The book '{book.title}' has been successfully returned.")
                return redirect(return_form_url_name)
            else:
                messages.error(request, f"Unable to process return for book '{book.title}'. Current status is '{book.status}'.")
                return redirect(return_form_url_name)
        except Exception as e:
            messages.error(request, f"An unexpected error occurred. Please contact support.")
            print(traceback.format_exc())
            return redirect('view_books')
    return render(request, 'libapp/return_book.html')


@never_cache
@login_required(login_url='login')
def confirm_return(request, accession_number):
    book = get_object_or_404(Book, accession_number=accession_number)
    fine = 0
    current_days_remaining = book.days_remaining
    if current_days_remaining is not None and current_days_remaining < 0:
        fine = abs(current_days_remaining) * 5

    next_url = request.GET.get('next', reverse('view_books'))

    return render(request, 'libapp/confirm_return.html', {
        'book': book,
        'fine': fine,
        'next_url': next_url
    })


@never_cache
@login_required(login_url='login')
def process_return(request, accession_number):
    try:
        book = get_object_or_404(Book, accession_number=accession_number)
        borrow_record = BorrowRecord.objects.filter(
            book_accession_number=accession_number,
            user_id=book.user.id_number if book.user else None,
            return_date__isnull=True
        ).order_by('-borrow_date').first()

        if not borrow_record:
            borrow_record = BorrowRecord.objects.filter(
               book_accession_number=accession_number,
               return_date__isnull=True
            ).order_by('-borrow_date').first()

        if not borrow_record:
            messages.error(request, "No active borrow record found for this book.")
            return redirect(request.POST.get('next_url', reverse('view_books')))

        borrow_record.return_date = timezone.now()
        borrow_record.borrow_status = "returned"
        fine = 0
        current_days_remaining = book.days_remaining
        if current_days_remaining is not None and current_days_remaining < 0:
            fine = abs(current_days_remaining) * 5
        borrow_record.late_payment_fee_amount = fine
        borrow_record.save()

        if borrow_record.late_payment_fee_amount > 0:
            messages.success(request, f"Fine of ₱{borrow_record.late_payment_fee_amount:.2f} has been recorded. The book '{book.title}' has been successfully returned.")
        else:
            messages.success(request, f"The book '{book.title}' has been successfully returned without a fine.")

        book.status = 'available'
        book.date_borrowed = None
        book.user = None
        book.due_date = None
        book.save()

        final_redirect_url = request.POST.get('next_url', reverse('view_books'))
        try:
            resolved_url = reverse(final_redirect_url) if not final_redirect_url.startswith('/') else final_redirect_url
            return redirect(resolved_url)
        except NoReverseMatch:
             if final_redirect_url.startswith('/'): # Check if it's already a path
                 return redirect(final_redirect_url)
             messages.warning(request, f"Redirect failed: Could not resolve '{final_redirect_url}'. Defaulting.")
             return redirect(reverse('view_books'))

    except Book.DoesNotExist:
        messages.error(request, "The specified book does not exist.")
        return redirect(request.POST.get('next_url', reverse('view_books')))
    except Exception as e:
        messages.error(request, f"An unexpected error occurred: {e}")
        print(traceback.format_exc())
        return redirect(request.POST.get('next_url', reverse('view_books')))

def get_next_accession_ajax(request):
    collection_type = request.GET.get('collection_type', '').lower()

    if collection_type not in COLLECTION_MAP:
        return JsonResponse({'error': 'Invalid collection type'}, status=400)

    accession_number = get_next_accession_number(collection_type)
    return JsonResponse({'accession_number': accession_number})
@never_cache
@login_required(login_url='login')
def view_book_record(request,control_number):

    marc_record = get_object_or_404(MARC_FIELD, marc_001_control_number=control_number)

    related_books = list(Book.objects.filter(marc_control_number=marc_record))

    #to show all similar books
    paginator = Paginator(related_books,1)
    page_number = request.GET.get("page")
    related_books_page = paginator.get_page(page_number)

    if request.method == "POST":
        action = request.POST.get("action")
        page = request.POST.get("page")

        if action == "flag_book":
            book_id = request.POST.get("book_id")
            status_notes = request.POST.get("status_notes")
            try:
                book = get_object_or_404(Book,accession_number=book_id)
                
                if book.status == 'available':
                    book.status = "flagged"
                    book.status_notes = status_notes
                    book.save()
                    messages.success(request, f"Book '{book.accession_number}: {book.title}' has been flagged.")
                elif book.status == 'flagged':
                    book.status = "available"
                    book.status_notes = ""
                    book.save()
                    messages.success(request, f"Book '{book.accession_number}: {book.title}' has been made available.")
                elif book.status == 'borrowed':
                    messages.error(request,f"The book is currently borrowed.")

                return redirect(f'/view_book_record/{control_number}/?page={page}')
            except Exception as e:
                messages.error(request, f"An unexpected error has occured: {e}")
        elif action == "change_collection":
            try:
                book_id = request.POST.get("book_id")
                book = get_object_or_404(Book, accession_number = book_id)
                collection_type = request.POST.get("collection_type")

                if book.status == 'borrowed':
                    messages.error(request,f"The book is currently being borrowed. Return the book first.")
                else:
                    book.collection_type = collection_type  # Assuming this field exists
                    book.accession_number = get_next_accession_number(collection_type)

                    book.save()
                    messages.success(request, f"Book '{book.accession_number}: {book.title}' has been updated to '{book.collection_type}'.")
                return redirect(f'/view_book_record/{control_number}/?page={page}')
            except Exception as e:
                messages.error(request, f"An unexpected error has occured: {e}")
        elif action == "change_marc":
            title = request.POST.get('title_and_statement').strip()
            author = request.POST.get('main_entry_personal_name').strip()
            edition = request.POST.get("edition").strip()
            publication = request.POST.get("publication").strip()
            physical_description = request.POST.get("physical_description").strip()
            series = request.POST.get("series_statement").strip()
            note = request.POST.get("marc_note")

            try:
                marc_record.marc_245_title_and_statement_of_responsibility = title
                marc_record.marc_100_main_entry_personal_name = author
                marc_record.marc_250_edition = edition
                marc_record.marc_260_publication = publication
                marc_record.marc_300_physical_description = physical_description
                marc_record.marc_490_series_statement = series
                marc_record.marc_501_note = note

                marc_record.save()

                for book in related_books:
                    book.set_from_marc_field()
                    book.save()

                messages.success(request, f"Book under control number {marc_record.marc_001_control_number} has been successfully edited and saved.")
            except Exception as e:
                messages.error(request, f"An unexpected error has occured: {e}")

    return render(request, 'libapp/view_book_record.html', {'marc_record': marc_record,'related_books':related_books_page})

@never_cache
@login_required(login_url='login')
def computer_use(request):
    all_users = list(User.objects.all())
    
    if request.method == "POST":
        # Get the user ID and trim any whitespace
        user_id = request.POST.get("user_id", "").strip()
        
        if not user_id:
            messages.error(request, "Please enter a valid User ID.")
            return render(request, 'libapp/computer_use.html')
        
        # Search for user in database
        user = next((u for u in all_users if u.id_number == user_id), None)
        
        if user:
            # Determine the next counter value (1 to n)
            last_record = ComputerUsage.objects.order_by('-counter').first()
            next_counter = last_record.counter + 1 if last_record else 1
            
            # Create new record with correct counter
            record = ComputerUsage.objects.create(
                user=user, 
                date=now(), 
                counter=next_counter
            )
            
            messages.success(request, f"{user.id_number} - {user.name} has been registered.")
        else:
            messages.error(request, f"User ID '{user_id}' not found.")
    
    return render(request, 'libapp/computer_use.html')


@never_cache
@login_required(login_url='login')
def generate_report(request):
    if request.method == "POST":
        # Get selected school years
        selected_years = request.POST.getlist('school_years')
        report_type = request.POST.get('report_type')
        output_format = request.POST.get('format')
        csv_file = request.FILES.get('csv_file')
        
        if not csv_file:
            messages.error(request, "Please upload a CSV file.")
            return render(request, "libapp/reports.html")
        
        # Save the uploaded file temporarily
        temp_dir = tempfile.gettempdir()
        file_path = os.path.join(temp_dir, csv_file.name)
        with open(file_path, "wb+") as destination:
            for chunk in csv_file.chunks():
                destination.write(chunk)
        
        # Validate CSV file first
        from libapp.generate_report import process_attendance
        try:
            # This will raise ValueError with "INVALID_CSV_STRUCTURE" if validation fails
            process_attendance(file_path)
        except ValueError as e:
            if str(e) == "INVALID_CSV_STRUCTURE":
                messages.error(request, "Invalid CSV structure.")
                return render(request, "libapp/reports.html")
            else:
                messages.error(request, str(e))
                return render(request, "libapp/reports.html")
        
        # If we get here, CSV is valid, so generate report
        try:
            if output_format == 'pdf':
                # Generate PDF report
                output_path = os.path.join(temp_dir, f"library_report_{'-'.join(selected_years)}.pdf")
                
                # Call the appropriate function from generate_report.py
                from libapp.generate_report import integrate_with_pdf_report
                integrate_with_pdf_report(file_path, selected_years, report_type, output_path)
                
                # Store the report path and redirect
                request.session["report_path"] = output_path
                return redirect("view_report")
            else:
                # Generate CSV report
                if report_type == 'summary':
                    # Call the statistics report function
                    from libapp.generate_report import generate_statistics_report
                    return generate_statistics_report(request, selected_years)
                else:
                    # Call the detailed report function
                    from libapp.generate_report import generate_borrow_report
                    return generate_borrow_report(request, selected_years)
        except Exception as e:
            messages.error(request, f"An error occurred while generating the report: {str(e)}")
            return render(request, "libapp/reports.html")
            
    return render(request, "libapp/reports.html")

@never_cache
@login_required(login_url='login')
def view_report(request):
    pdf_path = request.session.get("report_path") # Get stored path from session
    if not pdf_path or not os.path.exists(pdf_path):
        messages.error(request, "No report found. Please generate one first.")
        return redirect("generate_report") # Redirect to generate page if missing
    with open(pdf_path, "rb") as pdf_file:
        encoded_pdf = base64.b64encode(pdf_file.read()).decode("utf-8") # Convert to base64
    return render(request, "libapp/view_report.html", {"pdf_base64": encoded_pdf})

@never_cache
@login_required(login_url='login')
def download_report(request):
    pdf_path = request.session.get("report_path") # Retrieve the stored path
    if not pdf_path or not os.path.exists(pdf_path):
        messages.error(request, "No report found. Please generate one first.")
        return redirect("generate_report")
    return FileResponse(open(pdf_path, "rb"), as_attachment=True, filename=os.path.basename(pdf_path))



@never_cache
@login_required(login_url='login')
def book_records(request):
    records = BorrowRecord.objects.all() # Get all borrow records

    # Manually fetch the related Book and User for each BorrowRecord
    for record in records:
        record.book = Book.objects.filter(accession_number=record.book_accession_number).first()
        record.user = User.objects.filter(id_number=record.user_id).first()

    return render(request, 'libapp/book_records.html', {'records': records})

def is_superuser_check(user):
    return user.is_superuser
@login_required(login_url='login') # Make sure user is logged in
@never_cache
def register(request):
    if request.method == 'POST':
        form = CreateUserForm(request.POST)
        username_from_post = request.POST.get('username')
        email_from_post = request.POST.get('email', '').lower()

        if form.is_valid():
            try:
                user = form.save(commit=False)
                user.is_active = False
                user.save()

                activateEmail(request, user, user.email)

                messages.success(
                    request,
                    f"The account for {user.username} has been created successfully. Please check registered email ({user.email}) to activate your account. If you cannot find the email, check your junk or spam folder as well."
                )
                return redirect('login')
            except IntegrityError:
                User = get_user_model()
                potentially_existing_user = User.objects.filter(username=username_from_post).first()
                if potentially_existing_user and \
                   not potentially_existing_user.is_active and \
                   potentially_existing_user.email.lower() == email_from_post:
                    messages.success(
                        request,
                        f"Hi {potentially_existing_user.username}, your account was created! Please check your email ({email_from_post}) to confirm and activate your account. If you cannot find the email, check your junk or spam folder as well."
                    )
                    return redirect('login')
                else:
                    messages.error(request, "Registration failed due to a database conflict. The username or email might already be in use by an active account.")
                    return render(request, 'libapp/register.html', {'form': CreateUserForm(request.POST)})
        else:
            User = get_user_model()
            user_by_username_from_post = User.objects.filter(username=username_from_post).first()

            username_exists_error_msg = "A user with that username already exists."
            email_exists_error_msg = "An account with this email address already exists."

            username_error_present = False
            if 'username' in form.errors:
                for error in form.errors['username']:
                    if username_exists_error_msg in str(error):
                        username_error_present = True
                        break
            
            email_error_present = False
            if 'email' in form.errors:
                for error in form.errors['email']:
                    if email_exists_error_msg in str(error):
                        email_error_present = True
                        break
            
            if username_error_present and \
               email_error_present and \
               user_by_username_from_post and \
               not user_by_username_from_post.is_active and \
               user_by_username_from_post.email.lower() == email_from_post:
                
                messages.success(
                    request,
                    f"The account for {user_by_username_from_post.username} has been created successfully. Please check registered email ({email_from_post}) to activate your account. If you cannot find the email, check your junk or spam folder as well."
                )
                return redirect('register')
            else:
                pass

    else:
        form = CreateUserForm()
    return render(request, 'libapp/register.html', {'form': form})

def reset_passwordPage(request):
    if request.user.is_authenticated:
        return redirect('home_page')
    else:
        if request.method == 'POST':
            username = request.POST.get('username')
            email = request.POST.get('email')

            User = get_user_model()
            try:
                user = User.objects.get(username=username, email=email)
                # Send Reset Password Email
                resetPasswordEmail(request, user, email)

                messages.success(
                    request,
                    f"An email has been sent to {email}. Please read the email to proceed with changing your password. If you cannot find the email, check your junk or spam folder."
                )

                return redirect('login')
            except User.DoesNotExist:
                messages.error(
                    request,
                    f"Username and Email does not match or does not exist. Try again."
                )
                return redirect('reset_password')
    
    return render(request, 'libapp/reset_password.html')


def confirm_email(request):
    return render(request, 'libapp/confirm_email.html')

def loginPage(request):
    if request.user.is_authenticated:
        return redirect('home_page')
    else:
        if request.method == 'POST':
            username = request.POST.get('username').strip()
            password = request.POST.get('password').strip()

            user = authenticate(request, username=username, password=password)

            if user is not None:
                if not user.is_active:
                    messages.error(request, "Your account is not activated. Please check your email.")
                    return redirect('login')
                login(request, user)
                return redirect('home_page')
            else:
                messages.info(request, 'Username or password is incorrect.')

        context = {}
        return render(request, 'libapp/login.html', context)

def activate(request, uidb64, token):
    User = get_user_model()
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and account_activation_token.check_token(user, token):
        user.is_active = True
        user.save()
        messages.success(request, f"Thank you for confirming. {user.username} can now login to this account.")
        return redirect('login')
    else:
        messages.error(request, "Activation link is invalid!")

    return redirect('home_page')

def reset_password_done(request, uidb64, token):
    User = get_user_model()

    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (User.DoesNotExist, ValueError, TypeError, OverflowError):
        user = None

    if user is not None and password_reset_token.check_token(user, token):
        if request.method == 'POST':
            form = SetPasswordForm(user, request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, "Your password has been reset successfully.")
                return redirect('login')
        else:
            form = SetPasswordForm(user)

        return render(request, 'libapp/confirm_reset_password.html', {'form': form})
    else:
        messages.error(request, "The reset link is invalid or has expired.")
        return redirect('password_reset')

def activateEmail(request, user, to_email):
    mail_subject = "DPA Library - Account Activation"
    message = render_to_string("libapp/template_activate_account.html", {
        'user': user.username,
        'domain': get_current_site(request).domain,
        'uid': urlsafe_base64_encode(force_bytes(user.pk)),
        'token': account_activation_token.make_token(user),
        'protocol': 'https' if request.is_secure() else 'http'
    })

    email = EmailMessage(
        subject=mail_subject,
        body=message,
        from_email='DPA Library <{0}>'.format(settings.EMAIL_HOST_USER),
        to=[to_email]
    )
    email.content_subtype = "html"  # Let Django know it's HTML.
    email.send()

def resetPasswordEmail(request,user,to_email):
    mail_subject = "DPA Library - Reset Password"
    message = render_to_string("libapp/template_reset_password.html", {
        'user': user.username,
        'domain': get_current_site(request).domain,
        'uid': urlsafe_base64_encode(force_bytes(user.pk)),
        'token': password_reset_token.make_token(user),
        'protocol': 'https' if request.is_secure() else 'http'
    })

    email = EmailMessage(
        subject = mail_subject,
        body = message,
        from_email = 'DPA Library <{0}>'.format(settings.EMAIL_HOST_USER),
        to=[to_email]
    )

    email.content_subtype = "html"
    email.send()

def send_borrow_confirmation_email(request, borrow_record_instance):
    user_instance = borrow_record_instance.get_user() # Uses your custom User model via BorrowRecord's method
    book_instance = borrow_record_instance.get_book()

    if not user_instance or not book_instance:
        print(f"Error: Could not find user or book for BorrowRecord ID {borrow_record_instance.pk}. Email not sent.")
        return

    mail_subject = "DPA Library - Book Borrowed Confirmation"
    message = render_to_string("libapp/template_book_borrowed.html", {
        'user_name': user_instance.name,
        'book_title': book_instance.title,
        'accession_number': book_instance.accession_number,
        'borrow_date': borrow_record_instance.borrow_date,
        'expected_return_date': borrow_record_instance.expected_return_date,
        'domain': get_current_site(request).domain,
        'protocol': 'https' if request.is_secure() else 'http'
    })

    email = EmailMessage(
        subject=mail_subject,
        body=message,
        from_email='DPA Library <{0}>'.format(settings.EMAIL_HOST_USER),
        to=[user_instance.school_email]
    )
    email.content_subtype = "html"
    try:
        email.send(fail_silently=False)
    except Exception as e:
        print(f"Error sending borrow confirmation email to {user_instance.school_email} for book {book_instance.accession_number}: {e}")

def logoutUser(request):
    logout(request)
    messages.success(request, "You have been logged out.")
    return redirect('login')

@never_cache
@login_required(login_url='login')


def all_library_users(request):
    users = User.objects.all()
    borrow_records = BorrowRecord.objects.filter(borrow_date__isnull=False, return_date__isnull=True)
    books = Book.objects.all()

    # Create dictionaries for fast lookup
    book_dict = {book.accession_number: book.title for book in books}
    user_data = defaultdict(lambda: {
        "user_id": "",
        "name": "",
        "user_type": "",
        "section": "",
        "school_email": "",
        "borrowed_books": [],
        "overdue_books": []
    })

    # Populate user base
    for user in users:
        user_data[user.id_number]["user_id"] = user.id_number
        user_data[user.id_number]["name"] = user.name
        user_data[user.id_number]["user_type"] = user.user_type
        user_data[user.id_number]["section"] = user.section or ""
        user_data[user.id_number]["school_email"] = user.school_email

    # Check borrow records for borrowed or overdue books
    for record in borrow_records:
        uid = record.user_id
        accession = record.book_accession_number
        title = book_dict.get(accession)

        if title:
            book_info = {
                "title": title,
                "accession_number": accession,
                "days_remaining": (record.expected_return_date.date() - now().date()).days if record.expected_return_date else 0
            }

            # Check if the book is overdue or borrowed
            if book_info["days_remaining"] >= 0:
                user_data[uid]["borrowed_books"].append(book_info)
            else:
                user_data[uid]["overdue_books"].append(book_info)

    # Convert to list for pagination
    users_with_books = list(user_data.values())

    return render(request, 'libapp/all_library_users.html', {
        'users_with_books': users_with_books,
        'total_users': len(users_with_books),
    })

@never_cache
@login_required(login_url='login')
def add_library_users(request):
    """
    Main view for adding library users with new school year functionality
    """
    # Check if there are unreturned books to show warning
    all_returned, unreturned_count = check_all_books_returned()
    
    context = {
        'has_unreturned_books': not all_returned,
        'unreturned_books_count': unreturned_count
    }
    
    # Display just the two buttons for admin options
    return render(request, 'libapp/add_library_users_new.html', context)


def check_all_books_returned():
    """
    Check if all books in BorrowRecord have been returned.
    Returns a tuple (bool, count) where:
    - First element is True if all books are returned, False otherwise
    - Second element is the count of unreturned books (0 if all returned)
    """
    # Find records with no return date (unreturned books)
    unreturned_books = BorrowRecord.objects.filter(return_date__isnull=True)
    
    if not unreturned_books.exists():
        return True, 0
    
    # Just return the count of unreturned books for template display
    return False, unreturned_books.count()


def get_unreturned_book_details():
    """
    Gets detailed information about unreturned books.
    Used when we need to show or process specific book information.
    """
    unreturned_books = BorrowRecord.objects.filter(return_date__isnull=True)
    
    if not unreturned_books.exists():
        return []
    
    # Prepare list of unreturned books with details for display
    unreturned_details = []
    for record in unreturned_books:
        user = record.get_user()
        book = record.get_book()
        
        user_name = user.name if user else "Unknown User"
        book_title = book.title if book else "Unknown Book"
        
        unreturned_details.append({
            "record_id": record.borrow_record_number,
            "book_title": book_title,
            "book_accession": record.book_accession_number,
            "borrower_name": user_name,
            "borrower_id": record.user_id,
            "borrow_date": record.borrow_date.strftime("%Y-%m-%d") if record.borrow_date else "Unknown"
        })
    
    return unreturned_details


def new_school_year(request):
    """
    Handle the New School Year process.
    Now also includes computer record archiving.
    """
    if request.method == 'POST':
        # Check if all books are returned before proceeding
        all_returned, unreturned_count = check_all_books_returned()
        
        if not all_returned:
            # Don't allow the process to continue if books are still out
            error_msg = f"Cannot start a new school year. There are {unreturned_count} unreturned books in the system. All books must be returned first."
            messages.error(request, error_msg)
            return redirect('add_library_users')
            
        # User confirmed the action, process the database migration
        if 'confirm_new_year' in request.POST:
            try:
                # Execute the database migration
                migration_stats = execute_new_school_year()
                
                # Create a success message with details
                success_msg = "New school year process completed successfully:<br>"
                # Include existing migration stats messages...
                
                # Add the computer records message
                if 'computer_records_archived' in migration_stats:
                    success_msg += f"• {migration_stats['computer_records_archived']} computer use records archived<br>"
                
                messages.success(request, mark_safe(success_msg))
                
                # Redirect to the CSV upload page
                return redirect('upload_users_csv')
                
            except Exception as e:
                messages.error(request, f"An error occurred during the new school year process: {str(e)}")
                return redirect('add_library_users')
        
        # User clicked cancel
        return redirect('add_library_users')
    
    # GET request - show confirmation page
    all_returned, unreturned_count = check_all_books_returned()
    
    # Get computer usage stats for confirmation page
    computer_usage_count = ComputerUsage.objects.count()
    
    # Pass variables to template for conditional rendering
    context = {
        'all_books_returned': all_returned,
        'unreturned_books_count': unreturned_count,
        'computer_usage_count': computer_usage_count
    }
    
    return render(request, 'libapp/new_school_year_confirm.html', context)


def upload_users_csv(request):
    """
    Page for uploading CSV files after selecting "New School Year"
    """
    if request.method == 'POST':
        # Handle the "Finish Uploading Files" button
        if 'finish_upload' in request.POST:
            messages.success(request, "CSV upload session completed.")
            return redirect('add_library_users')
        
        # Handle CSV file upload
        elif 'csv_file' in request.FILES:
            return handle_csv_upload(request)
    
    # Display the CSV upload page
    return render(request, 'libapp/upload_users_csv.html')



def manual_add_user(request):
    """
    Page for manually adding a new user
    """
    if request.method == 'POST':
        # Use the existing handler for manual user addition
        return handle_manual_add(request)
    
    # Display the manual add user form
    return render(request, 'libapp/manual_add_user.html')


def handle_manual_add(request):
    id_number = request.POST.get('lrn', '').strip()
    user_type = request.POST.get('group', '').strip()

    # Only Students and Friends of the Library can have a 12-digit ID number
    if user_type not in ["Student", "Friends of the Library"] and len(id_number) == 12:
        messages.error(request, "Only Students and Friends of the Library can have a 12-digit ID number.")
        return redirect('manual_add_user')

    # Continue with the rest of your existing validations for ID number length...
    if user_type in ["Student", "Friends of the Library"]:
        if not re.fullmatch(r'\d{12}', id_number):
            messages.error(request, "ID Number must be a 12-digit number for Students and Friends of the Library.")
            return redirect('manual_add_user')
    else:
        if not re.fullmatch(r'\d{1,11}|\d{13,20}', id_number):
            messages.error(request, "ID Number must be 1–11 or 13–20 digits for this user type.")
            return redirect('manual_add_user')

    name = request.POST.get('name', '').strip()
    # Name format validation
    name_pattern = r"^[A-ZÑÜÀ-ÿ'\-\. ]+,\s[A-Z][a-zA-ZÀ-ÿ'\-\. ]+(?:\s(Jr\.|Sr\.|II|III|IV))?$"
    if not re.match(name_pattern, name):
        messages.error(request, 'Name format is invalid. Use: "LASTNAME, First M."')
        return redirect('manual_add_user')

    section = request.POST.get('section', '').strip() if request.POST.get('section') else ''
    school_email = request.POST.get('email', '').strip().lower()

    confirm_update = request.POST.get('confirm_update', 'no')

    # Validation: Required fields
    if not all([id_number, name, user_type, school_email]) or (user_type != "Staff" and not section):
        messages.error(request, "Please fill out all required fields.")
        return redirect('manual_add_user')

    # Disallow section if user is staff
    if user_type == "Staff" and section:
        messages.error(request, "Staff members should not be assigned to a section.")
        return redirect('manual_add_user')

    # Email validation
    if not school_email.endswith('@student.delpa.edu') or ' ' in school_email:
        messages.error(request, "Invalid email format (must end in @student.delpa.edu).")
        return redirect('manual_add_user')

    # Section format validation (only if not Staff)
    if user_type != "Staff" and section:
        # Reject if starts with 11 or 12 and uses a dash format (e.g. 11-STEM A)
        if re.match(r"^(11|12)-", section):
            messages.error(request, 'Wrong Section Format. Follow this format: "STEM 11-A" if user is a Senior High student.')
            return redirect('manual_add_user')

        junior_high_pattern = r"^(7|8|9|10)-[A-Za-z0-9]+$"
        senior_high_pattern = r"^(STEM|ABM|HUMSS|GAS) (11|12)-[A-Za-z0-9]+$"

        if not re.match(junior_high_pattern, section) and not re.match(senior_high_pattern, section):
            messages.error(request, 'Invalid Section Format.')
            return redirect('manual_add_user')

    # Format normalization
    id_number = id_number.strip()
    section = '-'.join(part.strip() for part in section.split('-')) if section else None

    try:
        existing_user = User.objects.get(id_number=id_number)

        if confirm_update != 'yes':
            # Prepare confirmation
            request.session['pending_user'] = {
                'id_number': id_number,
                'name': name,
                'user_type': user_type,
                'section': section,
                'school_email': school_email
            }
            return render(request, 'libapp/manual_add_user.html', {
                'show_update_prompt': True,
                'pending_user': request.session['pending_user']
            })

        # Overwrite the existing user
        existing_user.name = name
        existing_user.user_type = user_type
        existing_user.section = section
        existing_user.school_email = school_email
        existing_user.save()

        BorrowRecord.objects.filter(user_id=id_number).update(user_id=id_number)

        messages.success(request, f"User with ID {id_number} has been updated successfully.")
        request.session.pop('pending_user', None)

    except User.DoesNotExist:
        try:
            User.objects.create(
                id_number=id_number,
                name=name,
                user_type=user_type,
                section=section,
                school_email=school_email,
            )
            messages.success(request, f"User {name} has been added successfully.")
        except IntegrityError:
            messages.error(request, "A user with this school email already exists.")
            return redirect('manual_add_user')

    return redirect('add_library_users')  # Return to main page with buttons

def normalize_name(raw_name):
    raw_name = raw_name.strip()
    if ',' in raw_name:
        # Already in "LASTNAME, First M." format — just title case last name
        last, first = raw_name.split(',', 1)
        last = last.strip().upper()
        first = first.strip()
        return f"{last}, {first}"
    else:
        # Format like "Jose P. Rizal" → convert to "RIZAL, Jose P."
        parts = raw_name.split()
        if len(parts) >= 2:
            last = parts[-1].upper()
            first_middle = ' '.join(parts[:-1])
            return f"{last}, {first_middle}"
        return raw_name  # fallback

def normalize_section(raw_section):
    if raw_section is None:
        return ''
    return re.sub(r'\s*-\s*', '-', raw_section.strip())

def normalize_email(raw_email):
    email = raw_email.strip().lower()
    return email if email.endswith('@student.delpa.edu') else None


def handle_csv_upload(request):
    if request.method == "POST":
        if request.FILES.get("csv_file"):
            file = request.FILES["csv_file"]
            if not file.name.endswith('.csv'):
                messages.error(request, "Please upload a valid .csv file.")
                return redirect("upload_users_csv")  # Changed redirect
            try:
                data = file.read().decode("utf-8")
                
                # Check for empty file
                if not data.strip():
                    messages.error(request, "The uploaded CSV file is empty.")
                    return redirect("upload_users_csv")  # Changed redirect
                
                csv_data = list(csv.reader(io.StringIO(data)))
                
                # Check if file has any rows at all
                if len(csv_data) == 0:
                    messages.error(request, "CSV structure is invalid: The file is empty.")
                    return redirect("upload_users_csv")  # Changed redirect
                
                # Check for required headers
                required_headers = ["ID Number", "Name", "Description", "Group", "Email"]
                headers = [h.strip() for h in csv_data[0]]
                
                # Validate headers
                if len(headers) != len(required_headers):
                    messages.error(request, f"CSV structure is invalid: Expected 5 columns but found {len(headers)}.")
                    return redirect("upload_users_csv")  # Changed redirect
                
                # Check if all required headers are present
                for i, required_header in enumerate(required_headers):
                    if headers[i].lower() != required_header.lower():
                        messages.error(request, f"CSV structure is invalid: Expected '{required_header}' but found '{headers[i]}'.")
                        return redirect("upload_users_csv")  # Changed redirect
                
                # Check if there's data after headers
                if len(csv_data) == 1:
                    messages.error(request, "CSV structure is invalid: File contains only headers with no data.")
                    return redirect("upload_users_csv")  # Changed redirect
                
                # Skip header
                csv_data = csv_data[1:]
                
                users_created = 0
                users_updated = 0
                updated_users_info = []

                for index, row in enumerate(csv_data, start=2):
                    if len(row) != 5:
                        messages.error(request, f"Row {index}: Invalid format. Ensure 5 columns.")
                        return redirect("upload_users_csv")  # Changed redirect

                    id_number = row[0].strip()
                    user_type = row[3].strip()

                    # Validate ID number and enforce group (user_type) rules
                    id_length = len(id_number)

                    # Ensure ID number is all digits
                    if not id_number.isdigit():
                        messages.error(request, f"Row {index}: ID Number must be numeric.")
                        return redirect("upload_users_csv")  # Changed redirect

                    if id_length == 12:
                        if user_type not in ["Student", "Friends of the Library"]:
                            messages.error(request, f"Row {index}: 12-digit ID Numbers must belong to group 'Student' or 'Friends of the Library'.")
                            return redirect("upload_users_csv")  # Changed redirect
                    elif 1 <= id_length <= 11 or 13 <= id_length <= 20:
                        if user_type != "Staff":
                            messages.error(request, f"Row {index}: ID Numbers with {id_length} digits must belong to group 'Staff'.")
                            return redirect("upload_users_csv")  # Changed redirect
                    else:
                        messages.error(request, f"Row {index}: ID Number length of {id_length} digits is not allowed.")
                        return redirect("upload_users_csv")  # Changed redirect

                    name = row[1].strip()
                    name_pattern = r"^[A-ZÑÜÀ-ÿ'\-\. ]+,\s[A-Z][a-zA-ZÀ-ÿ'\-\. ]+(?:\s(Jr\.|Sr\.|II|III|IV))?$"
                    if not re.match(name_pattern, name, re.UNICODE):
                        messages.error(request, f"Row {index}: Name format is invalid. Use: 'LASTNAME, First M.'")
                        return redirect("upload_users_csv")  # Changed redirect

                    normalized_name = normalize_name(name)
                    section = normalize_section(row[2])
                    email = normalize_email(row[4])

                    if not (id_number and normalized_name and user_type and email):
                        messages.error(request, f"Row {index}: Missing/invalid required fields.")
                        return redirect("upload_users_csv")  # Changed redirect

                    if user_type not in ["Student", "Friends of the Library", "Staff"]:
                        messages.error(request, f"Row {index}: Invalid group type '{user_type}'.")
                        return redirect("upload_users_csv")  # Changed redirect

                    if user_type != "Staff" and not section:
                        messages.error(request, f"Row {index}: Section is required for group '{user_type}'.")
                        return redirect("upload_users_csv")  # Changed redirect

                    if user_type == "Staff":
                        section = ''

                    existing_user_by_id = User.objects.filter(id_number=id_number).first()
                    existing_user_by_email = User.objects.filter(school_email=email).exclude(id_number=id_number).first()

                    if existing_user_by_email:
                        messages.error(request, f"Row {index}: Email '{email}' is already used by another user.")
                        return redirect("upload_users_csv")  # Changed redirect

                    if existing_user_by_id:
                        old_name = existing_user_by_id.name
                        existing_user_by_id.name = normalized_name
                        existing_user_by_id.user_type = user_type
                        existing_user_by_id.section = section
                        existing_user_by_id.school_email = email
                        existing_user_by_id.save()
                        users_updated += 1
                        if old_name != normalized_name:
                            updated_users_info.append(f"{id_number} - from {old_name} to {normalized_name}")
                        else:
                            updated_users_info.append(f"{id_number} - {normalized_name}")
                    else:
                        User.objects.create(
                            id_number=id_number,
                            name=normalized_name,
                            user_type=user_type,
                            section=section,
                            school_email=email
                        )
                        users_created += 1

                success_msg = f"CSV processed successfully. Created {users_created} new user(s)."
                if users_updated > 0:
                    success_msg += f"<br>Updated {users_updated} existing user(s):"
                    success_msg += "<br>• " + "<br>• ".join(updated_users_info)
                messages.success(request, mark_safe(success_msg))
                return redirect("upload_users_csv")  # Changed redirect

            except Exception as e:
                messages.error(request, f"An error occurred during upload: {str(e)}")
                return redirect("upload_users_csv")  # Changed redirect

    return redirect("upload_users_csv")  # Changed redirect


def update_user(request):
    if request.method == "POST":
        user_id = request.POST.get('id_number')
        user = get_object_or_404(User, id_number=user_id)
        name = request.POST.get('name', '').strip()
        email = request.POST.get('school_email', '').strip()
        user_type = request.POST.get('user_type')
        section = request.POST.get('section', '').strip()
        flag_status = request.POST.get('flag_status')  # Parameter for flag toggle
        flag_reason = request.POST.get('flag_reason', '').strip()  # New field for flag reason
        
        # Add this debugging print
        print(f"Received flag_status: {flag_status}")
        print(f"Received flag_reason: {flag_reason}")
        print(f"User {user.id_number} flagged status before: {user.is_flagged}")

        # --- Validate Name Format ---
        name_pattern = r"^[A-ZÑÜÀ-ÿ'\-\. ]+,\s[A-Z][a-zA-ZÀ-ÿ'\-\. ]+(?:\s(Jr\.|Sr\.|II|III|IV))?$"
        if not re.match(name_pattern, name):
            return JsonResponse({'status': 'invalid', 'field': 'name'}, status=400)
        
        # --- Validate Email Format ---
        email = email.lower()
        if not email.endswith('@student.delpa.edu') or ' ' in email:
            return JsonResponse({'status': 'invalid', 'field': 'school_email'}, status=400)
        
        # --- Section validation (only for non-Staff) ---
        if user_type != "Staff":
            # JHS: Grades 7-10 — Format: 7-Helium
            match_jhs = re.match(r'^(7|8|9|10)-([A-Za-z]+)$', section)
            if match_jhs:
                grade, sec = match_jhs.groups()
                section = f"{grade}-{sec.strip().title()}"
            else:
                # SHS: Format: STEM 11-A
                match_shs = re.match(r'^([A-Z]{2,}) (11|12)-([A-Z])$', section)
                if match_shs:
                    track, level, letter = match_shs.groups()
                    section = f"{track.upper()} {level}-{letter.upper()}"
                else:
                    return JsonResponse({'status': 'invalid', 'field': 'section'}, status=400)
        else:
            section = None
        
        # --- Handle flag status change if requested ---
        flag_change_attempted = False
        flag_change_result = None
        
        if flag_status is not None:
            requested_flag_state = flag_status.lower() == 'true'
            current_flag_state = user.is_flagged
            
            # Only process if there's an actual change in flag status
            if requested_flag_state != current_flag_state:
                flag_change_attempted = True
                
                # If trying to flag the user, check for required reason and borrowed/overdue books
                if requested_flag_state and not current_flag_state:
                    # Validate that a reason is provided when flagging
                    if not flag_reason:
                        return JsonResponse({
                            'status': 'invalid', 
                            'field': 'flag_reason',
                            'message': 'A reason is required when flagging a user.'
                        }, status=400)
                    
                    # Check if user has any borrowed or overdue books
                    has_borrowed_books = Book.objects.filter(user=user, status='borrowed').exists()
                    has_overdue_books = Book.objects.filter(user=user, status='overdue').exists()
                    
                    # If there are borrowed or overdue books, don't allow flagging
                    if has_borrowed_books or has_overdue_books:
                        borrowed_books = list(Book.objects.filter(user=user, status='borrowed'))
                        overdue_books = list(Book.objects.filter(user=user, status='overdue'))
                        
                        all_books = borrowed_books + overdue_books
                        books_info = [f"{book.title} (Accession No: {book.accession_number}){' - OVERDUE' if book.status == 'overdue' else ''}" 
                                     for book in all_books]
                        
                        flag_change_result = {
                            'status': 'cannot_flag',
                            'message': 'This user has borrowed or overdue books and cannot be flagged.',
                            'books': books_info,
                            'has_overdue': has_overdue_books,
                            'overdue_count': len(overdue_books),
                            'regular_count': len(borrowed_books)
                        }
                    else:
                        # No borrowed/overdue books, can flag
                        user.is_flagged = requested_flag_state
                        user.flag_reason = flag_reason  # Save the flag reason
                        user.flag_date = timezone.now()  # Optional: record when the user was flagged
                        
                        flag_change_result = {
                            'status': 'flag_success',
                            'message': 'User has been flagged successfully.',
                            'flagged': user.is_flagged,
                            'reason': flag_reason
                        }
                else:
                    # Unflagging (always allowed)
                    user.is_flagged = requested_flag_state
                    # Clear flag reason and date when unflagging
                    user.flag_reason = None
                    user.flag_date = None
                    
                    flag_change_result = {
                        'status': 'flag_success',
                        'message': 'User has been unflagged successfully.',
                        'flagged': user.is_flagged
                    }
        
        # Save all changes
        user.name = name
        user.school_email = email
        user.user_type = user_type
        user.section = section
        user.save()

        # Add this debugging print
        print(f"User {user.id_number} flagged status after: {user.is_flagged}")
        if user.is_flagged:
            print(f"Flag reason: {user.flag_reason}")
        
        # Prepare response
        response_data = {'status': 'success'}
        if flag_change_attempted:
            response_data['flag_result'] = flag_change_result
        
        return JsonResponse(response_data)
    return JsonResponse({'status': 'invalid'}, status=400)


@csrf_exempt
def check_borrowed_books(request, id_number):
    """
    Check if a user has borrowed or overdue books without attempting to flag them.
    This endpoint is used before showing the flag confirmation dialog.
    """
    if request.method == "GET":
        try:
            user = User.objects.get(id_number=id_number)
            
            # If user is already flagged, they can be unflagged
            if user.is_flagged:
                return JsonResponse({
                    'status': 'success',
                    'can_toggle': True,
                    'current_state': 'flagged',
                    'message': 'User can be unflagged'
                })
            
            # Check if user has any borrowed or overdue books
            borrowed_books = Book.objects.filter(user=user, status='borrowed')
            overdue_books = Book.objects.filter(user=user, status='overdue')
            
            has_any_books = borrowed_books.exists() or overdue_books.exists()
            
            if has_any_books:
                # Process books with different statuses
                borrowed_list = [f"{book.title} (Accession No: {book.accession_number})" for book in borrowed_books]
                overdue_list = [f"{book.title} (Accession No: {book.accession_number}) - OVERDUE" for book in overdue_books]
                
                all_books = overdue_list + borrowed_list
                
                return JsonResponse({
                    'status': 'success',
                    'can_toggle': False,
                    'current_state': 'unflagged',
                    'has_borrowed_books': True,
                    'books': all_books,
                    'has_overdue': overdue_books.exists(),
                    'overdue_count': overdue_books.count(),
                    'regular_count': borrowed_books.count(),
                    'message': 'User cannot be flagged because they have borrowed or overdue books'
                })
            else:
                return JsonResponse({
                    'status': 'success',
                    'can_toggle': True,
                    'current_state': 'unflagged',
                    'has_borrowed_books': False,
                    'has_overdue': False,
                    'message': 'User can be flagged'
                })
                
        except User.DoesNotExist:
            return JsonResponse({
                'status': 'error', 
                'message': 'User not found'
            }, status=404)
    
    return JsonResponse({
        'status': 'error', 
        'message': 'Invalid request method'
    }, status=400)


def get_user_flag_status(request, id_number):
    """
    Get the current flag status for a user.
    This endpoint is used to ensure the flag button has the correct label.
    """
    if request.method == "GET":
        try:
            user = User.objects.get(id_number=id_number)
            return JsonResponse({
                'status': 'success',
                'is_flagged': user.is_flagged
            })
        except User.DoesNotExist:
            return JsonResponse({
                'status': 'error', 
                'message': 'User not found'
            }, status=404)
    
    return JsonResponse({
        'status': 'error', 
        'message': 'Invalid request method'
    }, status=400)


# This can be kept for backward compatibility or removed if no longer needed
@csrf_exempt
def flag_user(request, id_number):
    """
    Legacy endpoint for directly flagging/unflagging a user.
    Consider deprecating in favor of the integrated update_user approach.
    """
    if request.method == "POST":
        try:
            user = User.objects.get(id_number=id_number)
            
            # If we're unflagging, just do it without checks
            if user.is_flagged:
                user.is_flagged = False
                user.save()
                return JsonResponse({
                    'status': 'success', 
                    'flagged': user.is_flagged
                })
            
            # Check if user has any borrowed or overdue books
            has_borrowed_books = Book.objects.filter(user=user, status='borrowed').exists()
            has_overdue_books = Book.objects.filter(user=user, status='overdue').exists()
            
            # If there are borrowed or overdue books, don't allow flagging
            if has_borrowed_books or has_overdue_books:
                borrowed_books = list(Book.objects.filter(user=user, status='borrowed'))
                overdue_books = list(Book.objects.filter(user=user, status='overdue'))
                
                all_books = borrowed_books + overdue_books
                books_info = [f"{book.title} (Accession No: {book.accession_number}){' - OVERDUE' if book.status == 'overdue' else ''}" 
                             for book in all_books]
                
                return JsonResponse({
                    'status': 'cannot_flag',
                    'message': 'This user has borrowed or overdue books and cannot be flagged.',
                    'books': books_info,
                    'has_overdue': has_overdue_books,
                    'overdue_count': len(overdue_books),
                    'regular_count': len(borrowed_books)
                })
                
            # If we get here, no borrowed or overdue books, so we can flag the user
            user.is_flagged = True
            user.save()
            
            return JsonResponse({
                'status': 'success', 
                'flagged': user.is_flagged
            })
            
        except User.DoesNotExist:
            return JsonResponse({
                'status': 'error', 
                'message': 'User not found'
            }, status=404)
    
    return JsonResponse({
        'status': 'error', 
        'message': 'Invalid request method'
    }, status=400)


def get_user_details(request, user_id):
    """Get complete user details including flag reason for the modal"""
    if not request.user.is_authenticated:
        return JsonResponse({'status': 'error', 'message': 'Authentication required'}, status=401)
        
    try:
        user = User.objects.get(id_number=user_id)
        user_data = {
            'id_number': user.id_number,
            'name': user.name,
            'school_email': user.school_email,
            'user_type': user.user_type,
            'section': user.section,
            'is_flagged': user.is_flagged,
            'flag_reason': user.flag_reason,
            'flag_date': user.flag_date.isoformat() if user.flag_date else None
        }
        return JsonResponse({'status': 'success', 'user': user_data})
    except User.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'User not found'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    
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
    


def execute_new_school_year():
    """
    Implement the FIFO queue system for the start of a new school year:
    1. Move archive records to oblivion (delete them)
    2. Move buffer records to archive
    3. Move borrow records to buffer
    4. Archive computer usage records
    5. Clear the User database
    6. Reset the primary key sequence for BorrowRecord
    """
    from django.db import transaction
    from django.utils import timezone
    
    # Determine current school year
    today = timezone.now()
    if today.month >= 6:
        school_year = f"{today.year}-{today.year + 1}"
    else:
        school_year = f"{today.year - 1}-{today.year}"
    
    with transaction.atomic():
        # Step 1: Delete all archive records - these are the oldest and will be removed
        archive_deleted = BorrowRecordsArchive.objects.count()
        BorrowRecordsArchive.objects.all().delete()
        
        # Step 2: Move buffer records to archive, preserving their primary keys
        buffer_records = BorrowRecordsBuffer.objects.all()
        buffer_moved = buffer_records.count()
        for record in buffer_records:
            BorrowRecordsArchive.create_from_buffer_record(record)
        
        # Step 3: Clear the buffer after moving records to archive
        BorrowRecordsBuffer.objects.all().delete()
        
        # Step 4: Move current borrow records to buffer, preserving their primary keys
        borrow_records = BorrowRecord.objects.all()
        borrow_moved = borrow_records.count()
        for record in borrow_records:
            BorrowRecordsBuffer.create_from_borrow_record(record)
        
        # Step 5: Clear all borrow records (they've been moved to buffer)
        BorrowRecord.objects.all().delete()
        
        # Step 6: Reset the primary key sequence for BorrowRecord to start from 1
        # This ensures new records after school year change start with ID 1
        reset_borrowrecord_pk()
        
        # Step 7: Archive computer usage records
        computer_records_archived = archive_computer_usage_records(school_year)
        
        # Step 8: Delete all users
        user_count = User.objects.count()
        User.objects.all().delete()
        
        # Remove reference to PastComputerRecords as we're replacing it with the new system
        # old_records_deleted = PastComputerRecords.cleanup_old_records(retention_years=3)
        
        return {
            'archive_deleted': archive_deleted,
            'buffer_moved': buffer_moved,
            'borrow_moved': borrow_moved,
            'computer_records_archived': computer_records_archived,
            # 'old_computer_records_deleted': old_records_deleted,
            'users_deleted': user_count
        }  

import subprocess
import os
import datetime
import shutil
import logging # For Celery task

from django.conf import settings
from django.shortcuts import render, redirect
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from celery import shared_task # Assuming your Celery task is also in this file

logger = logging.getLogger(__name__)

# --- Global Settings for Backup/Restore ---
# Define DB_SETTINGS from Django settings
DB_SETTINGS = {
    'NAME': settings.DATABASES['default']['NAME'],
    'USER': settings.DATABASES['default']['USER'],
    'PASSWORD': settings.DATABASES['default']['PASSWORD'],
    'HOST': settings.DATABASES['default'].get('HOST'), # Use .get() for safety
    'PORT': settings.DATABASES['default'].get('PORT'), # Use .get() for safety
    'SOCKET': settings.DATABASES['default'].get('OPTIONS', {}).get('unix_socket') # Get socket if defined
}

# Explicit path to the Oracle mysqldump and mysql clients
ORACLE_MYSQLDUMP_PATH = '/opt/homebrew/opt/mysql-client/bin/mysqldump'
ORACLE_MYSQL_CLIENT_PATH = '/opt/homebrew/opt/mysql-client/bin/mysql'

# --- Backup Function ---
def create_mysql_backup(manual=False):
    """
    Create a MySQL database backup using the Oracle mysqldump client.
    """
    if not DB_SETTINGS['NAME']:
        logger.error("Database backup error: Database name is empty in settings.")
        print("Error: Database name is empty")
        return None

    if not os.path.exists(ORACLE_MYSQLDUMP_PATH):
        logger.error(f"Database backup error: mysqldump executable not found at {ORACLE_MYSQLDUMP_PATH}")
        print(f"CRITICAL ERROR: Specified 'mysqldump' executable not found at {ORACLE_MYSQLDUMP_PATH}.")
        return None

    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    prefix = "[MANUAL]" if manual else "[AUTO]"
    backup_filename = f"{prefix}_{timestamp}.sql.gz"

    if not hasattr(settings, 'BACKUP_DIR'):
        logger.error("Database backup error: BACKUP_DIR not defined in Django settings.")
        print("Error: settings.BACKUP_DIR is not defined!")
        return None
    backup_path = os.path.join(settings.BACKUP_DIR, backup_filename)

    try:
        os.makedirs(settings.BACKUP_DIR, exist_ok=True)
    except OSError as e:
        logger.error(f"Database backup error: Could not create backup directory {settings.BACKUP_DIR}: {e}")
        print(f"Error: Could not create backup directory {settings.BACKUP_DIR}: {e}")
        return None

    mysqldump_cmd = [ORACLE_MYSQLDUMP_PATH]

    if DB_SETTINGS["USER"]:
        mysqldump_cmd.append(f'--user={DB_SETTINGS["USER"]}')
    if DB_SETTINGS["PASSWORD"]:
        mysqldump_cmd.append(f'--password={DB_SETTINGS["PASSWORD"]}')

    # Connection: Prefer TCP/IP (Host/Port) then Socket
    if DB_SETTINGS["HOST"] and DB_SETTINGS["HOST"].lower() != 'localhost' and DB_SETTINGS["HOST"] != '':
        mysqldump_cmd.append(f'--host={DB_SETTINGS["HOST"]}')
        if DB_SETTINGS["PORT"]:
            mysqldump_cmd.append(f'--port={DB_SETTINGS["PORT"]}')
    elif DB_SETTINGS["SOCKET"]:
        mysqldump_cmd.append(f'--socket={DB_SETTINGS["SOCKET"]}')
    elif DB_SETTINGS["HOST"] and (DB_SETTINGS["HOST"].lower() == 'localhost' or DB_SETTINGS["HOST"] == ''): # Default to localhost TCP/IP if socket not specified
        mysqldump_cmd.append(f'--host=127.0.0.1') # Be explicit with 127.0.0.1 for TCP/IP
        if DB_SETTINGS["PORT"]:
            mysqldump_cmd.append(f'--port={DB_SETTINGS["PORT"]}')
    else:
        # If no host or socket, client might default to localhost socket, which might be wrong one.
        # Forcing TCP to 127.0.0.1 if nothing else is specified.
        logger.warning("Backup: No explicit host or socket, defaulting mysqldump to --host=127.0.0.1")
        mysqldump_cmd.append(f'--host=127.0.0.1')
        if DB_SETTINGS["PORT"]:
            mysqldump_cmd.append(f'--port={DB_SETTINGS["PORT"]}')


    mysqldump_cmd.append('--ssl-mode=DISABLED') # For XAMPP MariaDB server

    mysqldump_cmd.extend([
        '--single-transaction',
        '--skip-routines',
        '--skip-triggers',
        '--skip-events',
        # '--skip-column-statistics', # Oracle client might not recognize this specific flag name
        '--no-tablespaces',       # Good practice for general compatibility
        '--add-drop-table',
        # '--add-drop-database', # Be careful with this if dumping specific tables vs whole DB
        '--comments',
    ])
    mysqldump_cmd.append(DB_SETTINGS["NAME"])

    logger.info(f"Attempting MySQL backup with command: {' '.join(arg for arg in mysqldump_cmd if not arg.startswith('--password='))}") # Log command without password
    print(f"DEBUG: Full mysqldump command (password omitted for security): {' '.join(arg for arg in mysqldump_cmd if not arg.startswith('--password='))}")


    temp_backup_path = backup_path + '.temp'
    try:
        with open(temp_backup_path, 'wb') as f_out:
            mysqldump_process = subprocess.Popen(
                mysqldump_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            gzip_executable = shutil.which('gzip')
            if not gzip_executable:
                logger.error("gzip executable not found in PATH.")
                print("CRITICAL ERROR: gzip not found in PATH!")
                if mysqldump_process.stdout: mysqldump_process.stdout.close()
                mysqldump_process.kill()
                mysqldump_process.wait()
                return None

            gzip_process = subprocess.Popen(
                [gzip_executable],
                stdin=mysqldump_process.stdout,
                stdout=f_out,
                stderr=subprocess.PIPE
            )
            if mysqldump_process.stdout: # Allow mysqldump to receive SIGPIPE if gzip exits early
                 mysqldump_process.stdout.close()

            # Important: Read stderr from mysqldump before waiting on gzip, or use communicate carefully
            mysqldump_stderr_bytes = mysqldump_process.stderr.read()
            gzip_stdout_bytes, gzip_stderr_bytes = gzip_process.communicate() # Wait for gzip to finish
            mysqldump_process.wait() # Ensure mysqldump has finished

            mysqldump_stderr = mysqldump_stderr_bytes.decode('utf-8', errors='replace').strip()
            gzip_stderr = gzip_stderr_bytes.decode('utf-8', errors='replace').strip()

            if mysqldump_process.returncode != 0:
                logger.error(f"mysqldump failed (code {mysqldump_process.returncode}): {mysqldump_stderr}")
                print(f"mysqldump error (return code {mysqldump_process.returncode}): {mysqldump_stderr}")
                if "Column count of mysql.proc is wrong" in mysqldump_stderr or \
                   "event scheduler is disabled" in mysqldump_stderr:
                    logger.warning("Ignoring known MariaDB compatibility warning during mysqldump.")
                    print("Note: Ignoring MariaDB version compatibility warning")
                else:
                    if os.path.exists(temp_backup_path): os.remove(temp_backup_path)
                    return None

            if gzip_process.returncode != 0:
                logger.error(f"gzip failed (code {gzip_process.returncode}): {gzip_stderr}")
                print(f"gzip error (return code {gzip_process.returncode}): {gzip_stderr}")
                if os.path.exists(temp_backup_path): os.remove(temp_backup_path)
                return None

        os.rename(temp_backup_path, backup_path)
        logger.info(f"MySQL backup successfully created: {backup_path}")
        print(f"MySQL backup created: {backup_path}")
        return backup_path

    except FileNotFoundError as e: # Should be caught by initial checks, but as a fallback
        logger.error(f"Error during backup process (FileNotFound): {e}")
        print(f"Error: Command not found during backup process - {e}.")
        if os.path.exists(temp_backup_path): os.remove(temp_backup_path)
        return None
    except Exception as e:
        logger.exception(f"An unexpected error occurred during MySQL backup: {e}")
        print(f"Error creating MySQL backup: {str(e)}")
        if os.path.exists(temp_backup_path): os.remove(temp_backup_path)
        return None

# --- Restore Function ---
def restore_mysql_backup(backup_path_to_load):
    """
    Restore MySQL database from a backup file using the Oracle mysql client.
    """
    if not os.path.exists(backup_path_to_load):
        logger.error(f"Restore error: Backup file not found: {backup_path_to_load}")
        print(f"Backup file not found: {backup_path_to_load}")
        return False

    if not os.path.exists(ORACLE_MYSQL_CLIENT_PATH):
        logger.error(f"Restore error: mysql client executable not found at {ORACLE_MYSQL_CLIENT_PATH}")
        print(f"CRITICAL ERROR: Specified 'mysql' client executable not found at {ORACLE_MYSQL_CLIENT_PATH}.")
        return False

    mysql_cmd = [ORACLE_MYSQL_CLIENT_PATH]
    mysql_cmd.append(f'--user={DB_SETTINGS["USER"]}')
    if DB_SETTINGS["PASSWORD"]:
        mysql_cmd.append(f'--password={DB_SETTINGS["PASSWORD"]}')

    # Connection: Prefer TCP/IP (Host/Port) then Socket
    if DB_SETTINGS["HOST"] and DB_SETTINGS["HOST"].lower() != 'localhost' and DB_SETTINGS["HOST"] != '':
        mysql_cmd.append(f'--host={DB_SETTINGS["HOST"]}')
        if DB_SETTINGS["PORT"]:
            mysql_cmd.append(f'--port={DB_SETTINGS["PORT"]}')
    elif DB_SETTINGS["SOCKET"]:
        mysql_cmd.append(f'--socket={DB_SETTINGS["SOCKET"]}')
    elif DB_SETTINGS["HOST"] and (DB_SETTINGS["HOST"].lower() == 'localhost' or DB_SETTINGS["HOST"] == ''):
        mysql_cmd.append(f'--host=127.0.0.1')
        if DB_SETTINGS["PORT"]:
            mysql_cmd.append(f'--port={DB_SETTINGS["PORT"]}')
    else:
        logger.warning("Restore: No explicit host or socket, defaulting mysql client to --host=127.0.0.1")
        mysql_cmd.append(f'--host=127.0.0.1')
        if DB_SETTINGS["PORT"]:
            mysql_cmd.append(f'--port={DB_SETTINGS["PORT"]}')


    mysql_cmd.append('--ssl-mode=DISABLED') # For XAMPP MariaDB server
    mysql_cmd.append(DB_SETTINGS["NAME"]) # Database name

    logger.info(f"Attempting MySQL restore from {backup_path_to_load} with command (password omitted)")
    print(f"DEBUG: Full mysql restore command (password omitted for security): {' '.join(arg for arg in mysql_cmd if not arg.startswith('--password='))}")


    is_gzipped = backup_path_to_load.endswith('.gz')
    restore_process = None
    source_process = None # For gunzip

    try:
        if is_gzipped:
            gunzip_executable = shutil.which('gunzip')
            if not gunzip_executable:
                logger.error("gunzip executable not found in PATH for restore.")
                print("CRITICAL ERROR: gunzip not found in PATH for restore!")
                return False

            source_process = subprocess.Popen(
                [gunzip_executable, '--stdout', backup_path_to_load],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            restore_process = subprocess.Popen(
                mysql_cmd,
                stdin=source_process.stdout,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            if source_process.stdout: # Allow gunzip to receive SIGPIPE if mysql exits early
                source_process.stdout.close()
        else:
            with open(backup_path_to_load, 'rb') as f_in:
                restore_process = subprocess.Popen(
                    mysql_cmd,
                    stdin=f_in,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )

        # Wait for restore process and capture output
        mysql_stdout_bytes, mysql_stderr_bytes = restore_process.communicate()
        mysql_stderr = mysql_stderr_bytes.decode('utf-8', errors='replace').strip()

        if source_process: # If gunzip was used, wait for it and check its errors
            source_process.wait()
            gunzip_stderr_bytes = source_process.stderr.read()
            gunzip_stderr = gunzip_stderr_bytes.decode('utf-8', errors='replace').strip()
            if source_process.returncode != 0:
                logger.error(f"gunzip failed during restore (code {source_process.returncode}): {gunzip_stderr}")
                print(f"gunzip error during restore (code {source_process.returncode}): {gunzip_stderr}")
                return False

        if restore_process.returncode != 0:
            logger.error(f"mysql client failed during restore (code {restore_process.returncode}): {mysql_stderr}")
            print(f"mysql error during restore (code {restore_process.returncode}): {mysql_stderr}")
            return False

        logger.info(f"MySQL database successfully restored from {backup_path_to_load}")
        print(f"MySQL database restored from {backup_path_to_load}")
        return True

    except FileNotFoundError as e:
        logger.error(f"Error during restore process (FileNotFound): {e}")
        print(f"Error: Command not found during restore process - {e}.")
        return False
    except Exception as e:
        logger.exception(f"An unexpected error occurred during MySQL restore: {e}")
        print(f"Error restoring MySQL backup: {str(e)}")
        return False

# --- Django View ---
@staff_member_required
def backup_view(request):
    """
    View for manual backup creation and restoration of MySQL database.
    """
    if not hasattr(settings, 'BACKUP_DIR'):
        messages.error(request, "BACKUP_DIR not defined in Django settings.")
        logger.error("Backup view: BACKUP_DIR not defined in Django settings.")
        return render(request, 'libapp/backup.html', {'backups': []})

    try:
        os.makedirs(settings.BACKUP_DIR, exist_ok=True)
        backup_files_list = os.listdir(settings.BACKUP_DIR)
    except FileNotFoundError:
        backup_files_list = []
        messages.warning(request, f"Backup directory {settings.BACKUP_DIR} not found. Will attempt to create.")
        logger.warning(f"Backup directory {settings.BACKUP_DIR} not found.")
    except OSError as e:
        backup_files_list = []
        messages.error(request, f"Error accessing backup directory {settings.BACKUP_DIR}: {e}")
        logger.error(f"Error accessing backup directory {settings.BACKUP_DIR}: {e}")


    backups = []
    for f_name in sorted(backup_files_list, reverse=True):
        if f_name.endswith(('.sql', '.sql.gz')): # Check for tuple of endings
            try:
                # Improved timestamp parsing
                name_part = f_name.replace('.sql.gz', '').replace('.sql', '')
                if name_part.startswith('[MANUAL]_'):
                    timestamp_str = name_part.split('[MANUAL]_', 1)[1]
                elif name_part.startswith('[AUTO]_'):
                    timestamp_str = name_part.split('[AUTO]_', 1)[1]
                else:
                    timestamp_str = name_part # Assuming filename is just timestamp

                dt = datetime.datetime.strptime(timestamp_str, '%Y%m%d_%H%M%S')
                display_name = dt.strftime('%B %d, %Y at %H:%M:%S')

                if f_name.startswith('[MANUAL]'):
                    display_name = "Manual: " + display_name
                elif f_name.startswith('[AUTO]'):
                    display_name = "Automatic: " + display_name
            except ValueError:
                display_name = f_name # Fallback if parsing fails
            backups.append({'filename': f_name, 'display_name': display_name})

    if request.method == "POST":
        action = request.POST.get('action')

        if action == "create_backup":
            try:
                backup_file_path = create_mysql_backup(manual=True)
                if backup_file_path:
                    messages.success(request, f"Backup created: {os.path.basename(backup_file_path)}")
                else:
                    messages.error(request, "Failed to create backup. Check server logs for details.")
            except Exception as e:
                logger.exception("Error during manual backup creation from view.")
                messages.error(request, f"Error during backup: {str(e)}")
            return redirect('backup') # Assumes URL name 'backup'

        elif action == "load_backup":
            filename_to_load = request.POST.get('filename')
            if not filename_to_load:
                messages.error(request, "No backup file selected.")
                return redirect('backup')

            full_backup_path = os.path.join(settings.BACKUP_DIR, filename_to_load)

            if not os.path.exists(full_backup_path):
                messages.error(request, f'Backup file not found: {filename_to_load}')
                return redirect('backup')

            try:
                success = restore_mysql_backup(full_backup_path)
                if success:
                    messages.success(request, f'Successfully restored database from {filename_to_load}.')
                else:
                    messages.error(request, 'Failed to restore database. Check server logs for details.')
            except Exception as e:
                logger.exception("Error during database restore from view.")
                messages.error(request, f'Failed to restore: {str(e)}')
            return redirect('backup')

    return render(request, 'libapp/backup.html', {'backups': backups})

# --- Celery Task for Scheduled Backups ---
def cleanup_old_backups(months_to_keep=6):
    """
    Remove backups older than the specified number of months.
    """
    if not hasattr(settings, 'BACKUP_DIR') or not os.path.isdir(settings.BACKUP_DIR):
        logger.error("Cleanup: BACKUP_DIR not defined or not a directory.")
        return

    logger.info(f"Starting cleanup of old backups. Keeping last {months_to_keep} months.")
    try:
        cutoff_date = datetime.datetime.now() - datetime.timedelta(days=30 * months_to_keep)
        for f_name in os.listdir(settings.BACKUP_DIR):
            if f_name.endswith(('.sql', '.sql.gz')):
                try:
                    name_part = f_name.replace('.sql.gz', '').replace('.sql', '')
                    if name_part.startswith('[MANUAL]_'):
                        timestamp_str = name_part.split('[MANUAL]_', 1)[1]
                    elif name_part.startswith('[AUTO]_'):
                        timestamp_str = name_part.split('[AUTO]_', 1)[1]
                    else:
                        # Skip files not matching the expected auto/manual prefix and timestamp format
                        # or handle them if you have other naming conventions.
                        # For now, we assume only prefixed files have parseable timestamps.
                        continue

                    file_date = datetime.datetime.strptime(timestamp_str, '%Y%m%d_%H%M%S')
                    if file_date < cutoff_date:
                        file_to_remove_path = os.path.join(settings.BACKUP_DIR, f_name)
                        os.remove(file_to_remove_path)
                        logger.info(f"Removed old backup: {f_name}")
                        print(f"Removed old backup: {f_name}")
                except ValueError:
                    logger.warning(f"Could not parse date from filename {f_name} during cleanup. Skipping.")
                except Exception as e:
                    logger.exception(f"Error processing file {f_name} during cleanup: {e}")
    except Exception as e:
        logger.exception(f"Error during old backups cleanup process: {e}")

@shared_task(name="scheduled_backup_task") # Explicit name for Celery task
def scheduled_backup_task():
    """
    Celery task to create automatic database backups and cleanup old ones.
    """
    logger.info(f"Starting scheduled automatic backup at {datetime.datetime.now()}")
    try:
        backup_file_path = create_mysql_backup(manual=False)
        if backup_file_path:
            logger.info(f"Scheduled automatic backup created: {backup_file_path}")
            # Cleanup old backups (e.g., keeping last 6 months)
            cleanup_old_backups(months_to_keep=6)
            return True
        else:
            logger.error("Scheduled automatic backup failed to create a file.")
            return False
    except Exception as e:
        logger.exception(f"Unhandled error in scheduled_backup_task: {e}")
        return False

@staff_member_required
def overdue_simulation_tool(request):
    # Fetch books eligible for simulation (borrowed or already marked overdue)
    # Using select_related improves efficiency by fetching related user in one query
    simulatable_books = Book.objects.filter(status__in=['borrowed', 'overdue']).select_related('user')

    if request.method == 'POST':
        book_accession = request.POST.get('book_accession_number')
        action = request.POST.get('action') # 'set_overdue_days' or 'reset_due_date'

        # --- Input Validation ---
        if not book_accession:
             messages.error(request, "No book selected.")
             return redirect('overdue_simulation_tool')
        if not action:
             messages.error(request, "No action specified.")
             return redirect('overdue_simulation_tool')
        # --- End Validation ---

        try:
            book = get_object_or_404(Book, accession_number=book_accession)

            # --- Find Active Borrow Record ---
            # Look for the record corresponding to the current borrowing session
            borrow_record = BorrowRecord.objects.filter(
                book_accession_number=book.accession_number,
                user_id=book.user.id_number if book.user else None, # Match user if book has one
                return_date__isnull=True # Ensure it hasn't been returned
            ).order_by('-borrow_date').first() # Get the latest active one

            if not borrow_record:
                 # Attempt fallback if status is borrowed/overdue but no specific record found (less ideal)
                 borrow_record = BorrowRecord.objects.filter(
                    book_accession_number=book.accession_number,
                    return_date__isnull=True
                 ).order_by('-borrow_date').first()

            if not borrow_record:
                 messages.error(request, f"Could not find an active borrow record for book '{book.title}' (Accession: {book.accession_number}). Cannot simulate.")
                 return redirect('overdue_simulation_tool')
            # --- End Find Record ---


            # --- Action Logic ---
            if action == 'set_overdue_days':
                days_overdue_str = request.POST.get('days_overdue', '1')
                try:
                    # Renamed for clarity: this is the number of weekdays we want to be overdue by
                    weekdays_to_simulate = int(days_overdue_str)
                    if weekdays_to_simulate <= 0:
                        raise ValueError("Days must be positive")
                except (ValueError, TypeError):
                    messages.error(request, "Please enter a valid positive number for 'Days Overdue'.")
                    return redirect('overdue_simulation_tool')

                # *** CALCULATE DATE N WEEKDAYS AGO ***
                target_due_date = timezone.now() # Start from today
                weekdays_subtracted = 0
                # Loop backwards until we've subtracted the desired number of weekdays
                while weekdays_subtracted < weekdays_to_simulate:
                    target_due_date -= datetime.timedelta(days=1)
                    # Only count it if the day we moved *to* was a weekday
                    if target_due_date.weekday() < 5: # Monday to Friday (0-4)
                        weekdays_subtracted += 1
                # target_due_date now holds the date N weekdays ago

                # Timezone consistency check
                if timezone.is_aware(timezone.now()) and timezone.is_naive(target_due_date):
                     target_due_date = timezone.make_aware(target_due_date)
                elif timezone.is_naive(timezone.now()) and timezone.is_aware(target_due_date):
                     target_due_date = timezone.make_naive(target_due_date)

                # Update models - Set both Book.due_date and the record's expected_return_date
                book.due_date = target_due_date
                borrow_record.expected_return_date = target_due_date # Keep synchronized
                book.save(update_fields=['due_date'])
                borrow_record.save(update_fields=['expected_return_date'])

                messages.success(request, f"Book '{book.title}' due date forced to {weekdays_to_simulate} weekday(s) ago ({target_due_date.strftime('%Y-%m-%d %H:%M')}).")

            elif action == 'reset_due_date':
                # Reset logic correctly uses the weekday-based calculation property
                correct_due_date = book.expected_return_date # Uses the @property calculation

                if correct_due_date:
                    book.due_date = correct_due_date
                    borrow_record.expected_return_date = correct_due_date # Keep synchronized

                    book.save(update_fields=['due_date'])
                    borrow_record.save(update_fields=['expected_return_date'])
                    messages.success(request, f"Book '{book.title}' (Accession: {book.accession_number}) due date reset to its calculated date: {correct_due_date.strftime('%Y-%m-%d %H:%M')}.")
                else:
                    # Handle case where calculation fails (e.g., no borrow date)
                    messages.warning(request, f"Could not automatically recalculate the due date for '{book.title}'. Original borrow date might be missing.")

            else:
                 messages.warning(request, "Invalid action specified.")

        # --- Exception Handling ---
        except Book.DoesNotExist:
             messages.error(request, f"Book with Accession No: {book_accession} not found.")
        # Removed redundant DoesNotExist check for BorrowRecord as it's handled above
        except Exception as e:
            messages.error(request, f"An error occurred during simulation: {e}")
            print(f"Error during simulation tool action: {e}")
            print(traceback.format_exc()) # Log full traceback for debugging
        # --- End Exception Handling ---

        return redirect('overdue_simulation_tool')

    # --- Render GET request ---
    context = {
        'borrowed_books': simulatable_books
    }
    return render(request, 'libapp/overdue_simulation_tool.html', context)
    simulatable_books = Book.objects.filter(status__in=['borrowed', 'overdue']).select_related('user')

    if request.method == 'POST':
        book_accession = request.POST.get('book_accession_number')
        action = request.POST.get('action') # 'set_overdue_days' or 'reset_due_date'

        if not book_accession:
             messages.error(request, "No book selected.")
             return redirect('overdue_simulation_tool')
        if not action:
             messages.error(request, "No action specified.")
             return redirect('overdue_simulation_tool')

        try:
            book = get_object_or_404(Book, accession_number=book_accession)

            borrow_record = BorrowRecord.objects.filter(
                book_accession_number=book.accession_number,
                borrow_status='borrowed',
                return_date__isnull=True
            ).order_by('-borrow_date').first()

            if not borrow_record:
                 if book.status == 'overdue' and book.user:
                     borrow_record = BorrowRecord.objects.filter(
                         book_accession_number=book.accession_number,
                         user_id=book.user.id_number,
                         return_date__isnull=True
                     ).order_by('-borrow_date').first()

            if not borrow_record:
                 messages.error(request, f"Could not find an active borrow record for book '{book.title}' (Accession: {book.accession_number}). Cannot simulate.")
                 return redirect('overdue_simulation_tool')

            # --- Action Logic ---
            if action == 'set_overdue_days':
                days_overdue_str = request.POST.get('days_overdue', '1') # Default to 1 if not provided
                try:
                    days_overdue = int(days_overdue_str)
                    if days_overdue <= 0:
                        raise ValueError("Days must be positive")
                except (ValueError, TypeError):
                    messages.error(request, "Please enter a valid positive number for 'Days Overdue'.")
                    return redirect('overdue_simulation_tool')

                # Calculate the target past due date
                target_due_date = timezone.now() - datetime.timedelta(days=days_overdue)

                # Ensure timezone consistency
                if timezone.is_aware(timezone.now()) and not timezone.is_aware(target_due_date):
                     target_due_date = timezone.make_aware(target_due_date, timezone.get_current_timezone())
                elif not timezone.is_aware(timezone.now()) and timezone.is_aware(target_due_date):
                     target_due_date = timezone.make_naive(target_due_date, timezone.get_current_timezone())

                # Update both models
                book.due_date = target_due_date
                borrow_record.expected_return_date = target_due_date

                book.save(update_fields=['due_date'])
                borrow_record.save(update_fields=['expected_return_date'])

                messages.success(request, f"Book '{book.title}' (Accession: {book.accession_number}) due date forced to {days_overdue} day(s) ago ({target_due_date.strftime('%Y-%m-%d %H:%M')}). It should now appear as overdue.")

            elif action == 'reset_due_date':
                correct_due_date = book.expected_return_date # Use the property based on original borrow date

                if correct_due_date:
                    book.due_date = correct_due_date
                    borrow_record.expected_return_date = correct_due_date

                    book.save(update_fields=['due_date'])
                    borrow_record.save(update_fields=['expected_return_date'])
                    messages.success(request, f"Book '{book.title}' (Accession: {book.accession_number}) due date reset to its calculated date: {correct_due_date.strftime('%Y-%m-%d %H:%M')}.")
                else:
                    messages.warning(request, f"Could not automatically recalculate the due date for '{book.title}'. The original borrow date might be missing or invalid.")

            else:
                 messages.warning(request, "Invalid action specified.")


        except Book.DoesNotExist:
             messages.error(request, f"Book with Accession No: {book_accession} not found.")
        except BorrowRecord.DoesNotExist:
             messages.error(request, f"Could not find an active borrow record for book '{book.title}' (Accession: {book.accession_number}).")
        except Exception as e:
            messages.error(request, f"An error occurred during simulation: {e}")
            print(f"Error during simulation tool action: {e}")
            print(traceback.format_exc())

        return redirect('overdue_simulation_tool')

    context = {
        'borrowed_books': simulatable_books
    }
    return render(request, 'libapp/overdue_simulation_tool.html', context)

@never_cache
@login_required(login_url='login')
def circulation(request):
    # Get all books (or filter as needed)
    books = Book.objects.all()
    current_date = timezone.now().date()

    # Check if queryset is empty BEFORE pagination
    if not books.exists():
        # Return early with empty list if no books
        return render(request, 'libapp/circulation.html', {
            'view_list': [],
            'current_date': current_date,
        })
    
    # Apply any filters here if needed
    # ...
    
    # Only attempt pagination if we have books
    paginator = Paginator(books, 10)  # Show 10 books per page
    page_number = request.GET.get('page')
    
    try:
        paginated_books = paginator.page(page_number)
    except PageNotAnInteger:
        # If page is not an integer, deliver first page
        paginated_books = paginator.page(1)
    except EmptyPage:
        # If page is out of range, deliver last page
        paginated_books = paginator.page(paginator.num_pages)

    return render(request, 'libapp/circulation.html', {
        'view_list': paginated_books,
        'current_date': current_date,
    })