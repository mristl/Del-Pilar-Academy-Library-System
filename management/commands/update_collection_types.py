from django.core.management.base import BaseCommand
from libapp.models import Book

class Command(BaseCommand):
    help = "Updates book collection types based on accession numbers"

    def handle(self, *args, **kwargs):
        def book_type(new):
            newstring = new.accession_number.replace(" ", "").upper()
            letter_type = ""

            for c in newstring:
                if c.isdigit():
                    break
                letter_type += c

            mapping = {
                "FIC": "ficandscholastic",
                "SHSFIL": "shsfilipiniana",
                "SHSCIR": "shscirculation",
                "FIL": "filipiniana",
                "CIR": "circulation",
                "SHSREF": "shsreference",
                "REF": "reference",
                "PER": "periodicals",
                "ARC": "archives",
            }

            return mapping.get(letter_type, None)

        updated_count = 0
        for book in Book.objects.all():
            corrected_type = book_type(book)

            if corrected_type and book.collection_type != corrected_type:
                book.collection_type = corrected_type
                book.room_use = corrected_type in ["shsreference", "reference", "periodicals", "archives"]
                book.save()
                updated_count += 1
                self.stdout.write(f"Updated {book.accession_number}: {book.collection_type}")

        self.stdout.write(self.style.SUCCESS(f"Updated {updated_count} books!"))
