import random
import math # For math.ceil
from django.core.management.base import BaseCommand
from django.db import IntegrityError, transaction
from faker import Faker
from libapp.models import Book, MARC_FIELD # Assuming libapp.models exists

fake = Faker()

class Command(BaseCommand):
    help = (
        'Populates the database with books for each collection type, '
        'aiming for a specified total number of book copies across all collections (approx. 4500 by default). '
        'Creates multiple copies per unique MARC record, using Dewey Decimal for MARC control numbers.'
    )

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
    DEFAULT_TARGET_TOTAL_BOOKS = 4500 # Desired approximate total books across all collections

    def add_arguments(self, parser):
        num_collections = len(self.COLLECTION_INFO)
        default_books_per_type = 500 # Fallback
        if num_collections > 0:
            default_books_per_type = self.DEFAULT_TARGET_TOTAL_BOOKS // num_collections
        else: # Should not happen with defined COLLECTION_INFO
            default_books_per_type = 0


        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing Book and MARC_FIELD records before populating.',
        )
        parser.add_argument(
            '--count',
            type=int,
            default=default_books_per_type,
            help=(
                f'Number of book COPIES to create per collection type. '
                f'Default is {default_books_per_type} (calculated to aim for '
                f'~{self.DEFAULT_TARGET_TOTAL_BOOKS} total books across {num_collections} collections). '
                f'Actual total will be (COUNT * NUM_COLLECTIONS).'
            )
        )
        parser.add_argument(
            '--copies',
            type=int,
            default=3,
            help='Number of book copies to create per unique MARC record (default: 3).',
        )

    def _generate_dewey_decimal(self):
        """Generates a pseudo Dewey Decimal number."""
        main_class = random.randint(0, 999)
        if random.random() < 0.7: # 70% chance of having at least one decimal part
            sub_division1 = random.randint(0, 999)
            # More refined subdivision generation
            if len(str(sub_division1)) == 1: # e.g. .1, .2
                 sub_division_str = f"{sub_division1}"
            elif len(str(sub_division1)) == 2: # e.g. .12, .03
                 sub_division_str = f"{sub_division1:02d}"
            else: # e.g. .123, .045, .006
                 sub_division_str = f"{sub_division1:03d}"

            if random.random() < 0.4 and len(sub_division_str) < 6: # 40% chance of a second part, limit length
                sub_division2 = random.randint(0, 99)
                return f"{main_class:03d}.{sub_division_str}{sub_division2:02d}"
            return f"{main_class:03d}.{sub_division_str}"
        return f"{main_class:03d}"

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.SUCCESS("Starting book population process..."))

        books_per_type_target = kwargs['count']
        copies_per_marc = kwargs['copies']
        num_collections = len(self.COLLECTION_INFO)
        grand_total_target = books_per_type_target * num_collections

        self.stdout.write(self.style.NOTICE(
            f"Configuration: {books_per_type_target} book copies per collection type, "
            f"{copies_per_marc} copies per unique title."
        ))
        self.stdout.write(self.style.NOTICE(
            f"This will aim for approximately {grand_total_target} total book copies across {num_collections} collections."
        ))


        if copies_per_marc < 1:
            self.stdout.write(self.style.ERROR("Number of copies per MARC record must be at least 1."))
            return
        
        if books_per_type_target < 0: # Can be 0 if user wants to only clear
            self.stdout.write(self.style.ERROR("Number of books per type cannot be negative."))
            return

        if kwargs['clear']:
            self.stdout.write(self.style.WARNING("Clearing existing Book and MARC_FIELD records..."))
            Book.objects.all().delete()
            MARC_FIELD.objects.all().delete()
            self.stdout.write(self.style.SUCCESS("Existing records cleared."))
        
        if books_per_type_target == 0:
            self.stdout.write(self.style.SUCCESS("Target books per type is 0. No new books will be created."))
            self.stdout.write(self.style.SUCCESS("Book population process finished."))
            return

        total_books_created_overall = 0
        total_marc_created_overall = 0

        for type_code, info in self.COLLECTION_INFO.items():
            prefix = info['prefix']
            type_name = info['name']
            is_room_use_only = info['room_use_only']

            self.stdout.write(self.style.HTTP_INFO(f"Populating books for collection type: {type_name} ({prefix})"))
            self.stdout.write(self.style.HTTP_INFO(f"  Targeting {books_per_type_target} book copies for this type."))

            books_created_for_this_type = 0
            marc_created_for_this_type = 0
            current_prefix_accession_sequence = 1
            
            last_book_for_prefix = Book.objects.filter(accession_number__startswith=f"{prefix} ").order_by('-accession_number').first()
            if last_book_for_prefix:
                try:
                    num_part_str = last_book_for_prefix.accession_number.split(' ')[-1]
                    if num_part_str.isdigit():
                         current_prefix_accession_sequence = int(num_part_str) + 1
                         self.stdout.write(self.style.NOTICE(f"  Resuming accession numbers for {prefix} from {current_prefix_accession_sequence}"))
                except (IndexError, ValueError, TypeError):
                    self.stdout.write(self.style.WARNING(f"  Could not parse last accession for {prefix}: {last_book_for_prefix.accession_number if last_book_for_prefix else 'N/A'}. Starting from 1."))
                    current_prefix_accession_sequence = 1

            num_unique_marc_records_needed = math.ceil(books_per_type_target / copies_per_marc)
            if books_per_type_target == 0: # if target is 0, no marc records needed
                num_unique_marc_records_needed = 0

            self.stdout.write(f"  Need to create {num_unique_marc_records_needed} unique MARC records for this type.")


            for marc_idx in range(num_unique_marc_records_needed):
                if books_created_for_this_type >= books_per_type_target:
                    break 

                marc_cn = None 
                acc_num = None
                marc_record = None

                try:
                    with transaction.atomic():
                        while True:
                            marc_cn = self._generate_dewey_decimal()
                            if not MARC_FIELD.objects.filter(marc_001_control_number=marc_cn).exists():
                                break
                        
                        marc_title = fake.catch_phrase() + " " + fake.word().capitalize() + " " + fake.word().capitalize()
                        marc_author = fake.name()
                        marc_publisher = fake.company()

                        marc_record = MARC_FIELD.objects.create(
                            marc_001_control_number=marc_cn,
                            marc_245_title_and_statement_of_responsibility=marc_title,
                            marc_100_main_entry_personal_name=marc_author,
                            marc_250_edition=random.choice(["1st ed.", "2nd ed.", "International ed.", "Collector's ed."]),
                            marc_260_publication=f"{marc_publisher}; {fake.city()}: {fake.year()}",
                            marc_300_physical_description=f"{random.randint(50, 700)} p. : ill. ({random.choice(['some col.', 'b&w'])}) ; {random.randint(15, 30)} cm.",
                            marc_490_series_statement=f"Studies in {fake.word().capitalize()}" if random.random() < 0.25 else None,
                            marc_501_note=f"Includes index." if random.random() < 0.4 else None,
                        )
                        marc_created_for_this_type += 1

                        for _ in range(copies_per_marc):
                            if books_created_for_this_type >= books_per_type_target:
                                break 

                            while True:
                                acc_num = f"{prefix} {current_prefix_accession_sequence:06d}"
                                if not Book.objects.filter(accession_number=acc_num).exists():
                                    break
                                current_prefix_accession_sequence += 1
                            
                            Book.objects.create(
                                accession_number=acc_num,
                                marc_control_number=marc_record,
                                author=marc_record.marc_100_main_entry_personal_name,
                                title=marc_record.marc_245_title_and_statement_of_responsibility,
                                publisher=marc_record.marc_260_publication,
                                collection_type=type_code,
                                room_use=is_room_use_only,
                                status='available',
                            )
                            books_created_for_this_type +=1
                            current_prefix_accession_sequence += 1

                except IntegrityError as e:
                    self.stdout.write(self.style.ERROR(f"IntegrityError for {type_name} (MARC: {marc_cn}, Accession: {acc_num}): {e}. Retrying next MARC record."))
                    current_prefix_accession_sequence += random.randint(1,3) 
                    continue 
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"An unexpected error occurred for {type_name} (MARC: {marc_cn or 'N/A'}, Acc: {acc_num or 'N/A'}): {e}. Skipping."))
                    continue

                if (marc_idx + 1) % (num_unique_marc_records_needed // 10 or 1) == 0 and num_unique_marc_records_needed > 0:
                    self.stdout.write(f"    Processed {marc_idx + 1} / {num_unique_marc_records_needed} unique titles. Books for type: {books_created_for_this_type}/{books_per_type_target}")
            
            total_books_created_overall += books_created_for_this_type
            total_marc_created_overall += marc_created_for_this_type
            self.stdout.write(self.style.SUCCESS(f"  Finished populating {type_name}: {books_created_for_this_type} book copies from {marc_created_for_this_type} unique MARC records."))

        self.stdout.write(self.style.SUCCESS(f"----------------------------------------------------"))
        self.stdout.write(self.style.SUCCESS(f"Total unique MARC records created overall: {total_marc_created_overall}"))
        self.stdout.write(self.style.SUCCESS(f"Total Book copies created overall: {total_books_created_overall} (Target was approx: {grand_total_target})"))
        self.stdout.write(self.style.SUCCESS("Book population process finished."))