# forms.py
from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
# --- Import Validation Helpers ---
from django.core.exceptions import ValidationError
from django.contrib.auth import password_validation
# --- End Import ---

class CreateUserForm(UserCreationForm):
    username = forms.CharField(
        required=True,
        help_text="Make a username",
        max_length= 255
    )

    email = forms.EmailField(
        required=True,
        help_text='Required. Please enter a valid email address.',
        max_length= 255
    )

    password1 = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput,
        max_length= 20,
        help_text=password_validation.password_validators_help_text_html(),
    )

    password2 = forms.CharField(
        label="Password confirmation",
        widget=forms.PasswordInput,
        strip=False,
        max_length= 20,
        help_text="Enter the same password for verification.",
    )

    class Meta(UserCreationForm.Meta):
        fields = UserCreationForm.Meta.fields + ('email',)

    def clean_email(self):
        """
        Validate that the email is unique within the auth.User table.
        """
        email = self.cleaned_data.get('email')
        if email and User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email address already exists.")
        return email

    # --- ADD THIS METHOD to validate password1 content ---
    def clean_password1(self):
        """
        Run Django's password validators against the first password field.
        """
        password = self.cleaned_data.get("password1")
        if password: # Only proceed if a password was entered
            try:
                # Get the user instance (might be None if creating)
                user = self.instance
                # Validate password using settings validators
                password_validation.validate_password(password, user)
            except ValidationError as error:
                # If validation fails, add the error(s) directly to password1
                self.add_error('password1', error)
        # Always return the password (or None) to allow further checks
        # like comparison in the parent form's clean() method.
        return password
    # --- END ADDED METHOD ---

# REMOVE your incorrect SetPasswordForm - use the standard one in the view

from django import forms
from .models import Book, MARC_FIELD

class MARCRecordForm(forms.ModelForm):
    class Meta:
        model = MARC_FIELD
        fields = [
            'marc_001_control_number',
            'marc_245_title_and_statement_of_responsibility',
            'marc_100_main_entry_personal_name',
            'marc_250_edition',
            'marc_260_publication',
            'marc_300_physical_description',
            'marc_490_series_statement',
            'marc_501_note',
            'marc_024_standard_number',
            'marc_037_source_of_acquisition',
        ]

    marc_001_control_number = forms.CharField(
        required=True,
        max_length=50
    )

    marc_245_title_and_statement_of_responsibility = forms.CharField(
        required=True,
        max_length=255
    )

    marc_100_main_entry_personal_name = forms.CharField(
        required=True,
        max_length=255
    )

class BookForm(forms.ModelForm):
    class Meta:
        model = Book
        fields = [
            'collection_type',
        ]

    def __init__(self, *args, **kwargs):
        super(BookForm, self).__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = True

