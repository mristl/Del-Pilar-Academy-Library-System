from django.core.management.base import BaseCommand
from django.db.models import Count
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Image, Paragraph, Spacer, Frame, PageTemplate
from libapp.models import (BorrowRecord, BorrowRecordsBuffer, BorrowRecordsArchive, User, Book, ComputerUsage, ComputerUsageBuffer, ComputerUsageArchive)
import csv
import os
import re
import datetime
from django.conf import settings
from num2words import num2words
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib.colors import blue, red, green, orange, purple, pink, cyan
from reportlab.graphics.charts.legends import Legend
import math
from django.utils import timezone
from django.http import HttpResponse

def generate_pdf_report(csv_file_path, start_date, end_date, output_path, selected_years=None):
    try:
        attendance_counts = process_attendance(csv_file_path)
        borrow_counts = process_borrow_records(start_date, end_date, selected_years)
        computer_usage_counts = process_computer_usage(start_date, end_date, selected_years)

        data = compute_totals(attendance_counts, borrow_counts, computer_usage_counts)
        generate_pdf(output_path, data, start_date, end_date, selected_years)
    except ValueError as e:
        # Re-raise the error to be handled by the calling function
        raise

def compute_years_covered(start_date, end_date):
    start_year = int(start_date[:4])
    end_year = int(end_date[:4])
    years_covered = end_year - start_year + 1
    return num2words(years_covered).capitalize()  # Convert number to words

def get_current_school_year():
    today = datetime.datetime.today()
    year = today.year
    month = today.month
    if month >= 8:  # August to December (start of school year)
        return f"S.Y. {year}-{year + 1}"
    else:  # January to July (second term of school year)
        return f"S.Y. {year - 1}-{year}"

def process_attendance(csv_file):
    counts = initialize_counts()
    
    # Check if file is empty
    if os.path.getsize(csv_file) == 0:
        raise ValueError("INVALID_CSV_STRUCTURE")
    
    required_headers = ["Name", "ID Number", "Description", "Group", "Date"]
    
    try:
        with open(csv_file, "r", encoding="utf-8") as file:
            # Read the first line to check headers
            reader = csv.DictReader(file)
            
            # Check if all required headers exist
            if not reader.fieldnames:
                raise ValueError("INVALID_CSV_STRUCTURE")
                
            for header in required_headers:
                if header not in reader.fieldnames:
                    raise ValueError("INVALID_CSV_STRUCTURE")
            
            # Process data rows
            row_count = 0
            valid_row_count = 0
            
            for row in reader:
                row_count += 1
                
                # Check if all required fields have values
                all_required_fields_present = True
                for header in required_headers:
                    if not row.get(header):
                        all_required_fields_present = False
                        break
                
                if all_required_fields_present:
                    valid_row_count += 1
                    group = row["Group"]
                    section = row["Description"]
                    grade_level = extract_grade_level(section, group)
                    counts[grade_level]["Readers Admitted"] += 1
            
            # If no rows or no valid rows found
            if row_count == 0 or valid_row_count == 0:
                raise ValueError("INVALID_CSV_STRUCTURE")
                
    except (csv.Error, UnicodeDecodeError):
        # Handle CSV parsing errors
        raise ValueError("INVALID_CSV_STRUCTURE")
            
    return counts

def process_borrow_records(start_date, end_date, selected_years=None):
    """
    Process borrow records based on selected school years.
    
    Args:
        start_date, end_date: Overall date range (used for current records)
        selected_years: List of selected year keys ('current', 'buffer', 'archive')
        
    Returns:
        Dictionary with counts of library resources and periodical usage by grade level
    """
    counts = initialize_counts()
    
    # Define periodical collection types (case-insensitive)
    periodical_types = ["periodicals", "archives", "newspapers", "magazines"]
    
    # Get school years mapping
    school_years = get_db_school_years()
    
    # Determine which databases to query based on selected years
    if not selected_years:
        selected_years = ['current', 'buffer', 'archive']
    
    # Process current borrow records (BorrowRecord)
    if 'current' in selected_years:
        current_year_str = school_years.get('current')
        print(f"Processing current borrow records for {current_year_str}")
        
        # Convert ISO format strings to datetime objects without using fromisoformat
        try:
            # Parse strings in ISO format YYYY-MM-DD using strptime instead
            from datetime import datetime
            start_dt = datetime.strptime(start_date.split('T')[0], '%Y-%m-%d')
            end_dt = datetime.strptime(end_date.split('T')[0], '%Y-%m-%d')
            
            # Make timezone-aware
            from django.utils import timezone
            if timezone.is_naive(start_dt):
                start_dt = timezone.make_aware(start_dt)
            if timezone.is_naive(end_dt):
                end_dt = timezone.make_aware(end_dt)
            
            for record in BorrowRecord.objects.filter(borrow_date__range=[start_dt, end_dt]):
                user = User.objects.filter(id_number=record.user_id).first()
                if user:
                    grade_level = extract_grade_level(user.section, user.user_type)
                    book = Book.objects.filter(accession_number=record.book_accession_number).first()
                    if book:
                        if book.collection_type and book.collection_type.lower() in periodical_types:
                            counts[grade_level]["Periodical Usage"] += 1
                        else:
                            counts[grade_level]["Library Resources"] += 1
        except Exception as e:
            print(f"Error processing current records: {str(e)}")
            # Fallback to using all records if date parsing fails
            for record in BorrowRecord.objects.all():
                user = User.objects.filter(id_number=record.user_id).first()
                if user:
                    grade_level = extract_grade_level(user.section, user.user_type)
                    book = Book.objects.filter(accession_number=record.book_accession_number).first()
                    if book:
                        if book.collection_type and book.collection_type.lower() in periodical_types:
                            counts[grade_level]["Periodical Usage"] += 1
                        else:
                            counts[grade_level]["Library Resources"] += 1
    
    # Process buffer borrow records
    if 'buffer' in selected_years:
        buffer_year_str = school_years.get('buffer')
        print(f"Processing buffer borrow records for {buffer_year_str}")
        
        # For buffer records, we'll get all records
        buffer_records = BorrowRecordsBuffer.objects.all()
        print(f"Found {buffer_records.count()} buffer borrow records")
        
        for record in buffer_records:
            section = record.section or ""
            # Look for digits in section to determine if it's a student section
            is_student = bool(re.search(r"\d+", section))
            grade_level = extract_grade_level(section, 'Student' if is_student else 'Staff')
            
            if record.collection_type and record.collection_type.lower() in periodical_types:
                counts[grade_level]["Periodical Usage"] += 1
            else:
                counts[grade_level]["Library Resources"] += 1
    
    # Process archive borrow records - apply the same fix
    if 'archive' in selected_years:
        archive_year_str = school_years.get('archive')
        print(f"Processing archive borrow records for {archive_year_str}")
        
        # For archive records, we'll get all records
        archive_records = BorrowRecordsArchive.objects.all()
        print(f"Found {archive_records.count()} archive borrow records")
        
        for record in archive_records:
            section = record.section or ""
            # Look for digits in section to determine if it's a student section
            is_student = bool(re.search(r"\d+", section))
            grade_level = extract_grade_level(section, 'Student' if is_student else 'Staff')
            
            if record.collection_type and record.collection_type.lower() in periodical_types:
                counts[grade_level]["Periodical Usage"] += 1
            else:
                counts[grade_level]["Library Resources"] += 1
    
    return counts

def process_computer_usage(start_date, end_date, selected_years=None):
    """
    Process computer usage records based on selected school years.
    Uses direct school year matching for buffer and archive records.
    
    Args:
        start_date, end_date: Used only for current records if needed
        selected_years: List of selected year keys ('current', 'buffer', 'archive')
        
    Returns:
        Dictionary with counts of internet usage by grade level
    """
    counts = initialize_counts()
    
    # Get school years mapping
    school_years = get_db_school_years()
    
    # Determine which databases to query based on selected years
    if not selected_years:
        selected_years = ['current', 'buffer', 'archive']
    
    # Process current computer usage (ComputerUsage) - uses date range
    if 'current' in selected_years:
        # For current records, we'll still use date range as they don't have school_year field
        current_year_str = school_years.get('current')
        print(f"Processing current records for {current_year_str}")
        
        # Convert ISO format strings to datetime objects without using fromisoformat
        try:
            # Parse strings in ISO format YYYY-MM-DD using strptime instead
            from datetime import datetime
            start_dt = datetime.strptime(start_date.split('T')[0], '%Y-%m-%d')
            end_dt = datetime.strptime(end_date.split('T')[0], '%Y-%m-%d')
            
            # Make timezone-aware
            from django.utils import timezone
            if timezone.is_naive(start_dt):
                start_dt = timezone.make_aware(start_dt)
            if timezone.is_naive(end_dt):
                end_dt = timezone.make_aware(end_dt)
            
            for record in ComputerUsage.objects.filter(date__range=[start_dt, end_dt]):
                user = record.user
                if user:
                    grade_level = extract_grade_level(user.section, user.user_type)
                    counts[grade_level]["Internet Usage"] += 1
        except Exception as e:
            print(f"Error processing current records: {str(e)}")
            # Fallback to using all records if date parsing fails
            for record in ComputerUsage.objects.all():
                user = record.user
                if user:
                    grade_level = extract_grade_level(user.section, user.user_type)
                    counts[grade_level]["Internet Usage"] += 1
    
    # Process buffer records - use all records regardless of date
    if 'buffer' in selected_years:
        buffer_year_str = school_years.get('buffer')
        print(f"Processing buffer records for {buffer_year_str}")
        
        # Use all buffer records
        buffer_records = ComputerUsageBuffer.objects.all()
        print(f"Total buffer records: {buffer_records.count()}")
        
        for record in buffer_records:
            section = record.section or ""
            is_student = bool(re.search(r"(\d+)", section))
            user_type = 'Student' if is_student else 'Staff'
            
            grade_level = extract_grade_level(section, user_type)
            counts[grade_level]["Internet Usage"] += 1
    
    # Process archive records - use all records regardless of date
    if 'archive' in selected_years:
        archive_year_str = school_years.get('archive')
        print(f"Processing archive records for {archive_year_str}")
        
        # Get all archive records
        archive_records = ComputerUsageArchive.objects.all()
        print(f"Total archive records: {archive_records.count()}")
        
        for record in archive_records:
            section = record.section or ""
            is_student = bool(re.search(r"(\d+)", section))
            user_type = 'Student' if is_student else 'Staff'
            
            grade_level = extract_grade_level(section, user_type)
            counts[grade_level]["Internet Usage"] += 1
    
    return counts

def extract_grade_level(section, user_type):
    section = section.strip() if section else ""
    if user_type == "Staff":
        return "Faculty/Staff"
    match = re.search(r"(\d+)", section)
    return f"Grade {match.group(1)}" if match else "Faculty/Staff"

def initialize_counts():
    return {level: {"Readers Admitted": 0, "Library Resources": 0, "Internet Usage": 0, "Periodical Usage": 0} 
            for level in ["Grade 7", "Grade 8", "Grade 9", "Grade 10", "Grade 11", "Grade 12", "Faculty/Staff"]}

def compute_totals(attendance, borrow, computer):
    final_counts = initialize_counts()
    for level in final_counts.keys():
        final_counts[level]["Readers Admitted"] = attendance[level]["Readers Admitted"]
        final_counts[level]["Library Resources"] = borrow[level]["Library Resources"]
        final_counts[level]["Internet Usage"] = computer[level]["Internet Usage"]
        final_counts[level]["Periodical Usage"] = borrow[level]["Periodical Usage"]
        final_counts[level]["Total"] = sum(final_counts[level].values())

    final_counts["TOTAL"] = {key: sum(final_counts[grade][key] for grade in final_counts if grade != "TOTAL") 
                             for key in ["Readers Admitted", "Library Resources", "Internet Usage", "Periodical Usage"]}
    final_counts["TOTAL"]["Total"] = sum(final_counts["TOTAL"].values())
    return final_counts


def generate_pie_chart(data_dict, title, width=200, height=200):
    """Creates a pie chart with a title and a full legend (includes percentages)."""
    drawing = Drawing(width, height)

    # Add Title
    title_text = String(width / 2, height - 10, title, fontName="Helvetica-Bold", fontSize=10, fillColor=colors.black)
    title_text.textAnchor = "middle"  # Center the title
    drawing.add(title_text)

    pie = Pie()
    pie.x = 30
    pie.y = 30  # Adjusted to make space for title
    pie.width = width - 60
    pie.height = height - 60
    pie.data = list(data_dict.values())

    colors_list = [colors.blue, colors.red, colors.green, colors.orange, colors.purple, colors.pink, colors.cyan]
    for i, color in enumerate(colors_list[:len(pie.data)]):
        pie.slices[i].fillColor = color

    drawing.add(pie)

    total = sum(data_dict.values())

    # Legend (Includes ALL Percentages)
    legend_labels = [(colors_list[i], f"{key} ({round(value / total * 100, 1)}%)") for i, (key, value) in enumerate(data_dict.items())]

    legend = Legend()
    legend.x = width / 2 - 5  # Centered below the chart
    legend.y = 10  # Move below
    legend.dx = 8
    legend.dy = 8
    legend.fontName = "Helvetica"
    legend.fontSize = 7
    legend.boxAnchor = "n"
    legend.columnMaximum = len(data_dict)
    legend.deltax = 0
    legend.deltay = 5
    legend.colorNamePairs = legend_labels  # Always include all labels

    drawing.add(legend)

    return drawing


def generate_pdf(output_path, data, start_date, end_date, selected_years=None):
    PAGE_WIDTH, PAGE_HEIGHT = A4
    MARGIN = inch  # 1-inch margin on all sides
    TABLE_WIDTH = PAGE_WIDTH - 2 * MARGIN

    # Logo path
    logo_path = os.path.join(settings.BASE_DIR, "libapp/static/images/DELPA.png")

    # Initialize document with margins
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=0.5 * inch,  # Set top margin to 0.5 inches
        bottomMargin=0.5 * inch
    )
    
    styles = getSampleStyleSheet()

    # Custom styles
    header_style = ParagraphStyle("HeaderStyle", parent=styles["Normal"], alignment=1, fontSize=11, leading=13, textColor=colors.white)
    title_style = ParagraphStyle("TitleStyle", parent=styles["Title"], fontSize=11, leading=13, alignment=1)
    normal_style = ParagraphStyle("NormalStyle", parent=styles["Normal"], fontSize=11, leading=13, alignment=1)

    elements = []

    # Add Logo
    if os.path.exists(logo_path):
        logo = Image(logo_path, width=50, height=50)
        logo.hAlign = "CENTER"
        elements.append(logo)

    # Title & Address (with less space between them)
    elements.append(Paragraph(
        "<b>DEL PILAR ACADEMY LIBRARY</b><br/>City of Imus, Cavite", 
        title_style
    ))
    elements.append(Spacer(1, 20))  # Increased space below

    # Get the appropriate title text and school year range
    if selected_years:
        title_text = get_report_title_text(selected_years)
        school_year_range = get_school_year_range(selected_years)
    else:
        # Fallback to the old method if no selected_years provided (backward compatibility)
        years_covered = compute_years_covered(start_date, end_date).upper()
        title_text = f"FOR THE LAST {years_covered} YEARS"
        school_year_range = get_current_school_year()

    elements.append(Paragraph(
        f"<b>SUMMARY UTILIZATION REPORT OF LIBRARY SERVICES PER GRADE LEVEL<br/>"
        f"{title_text}<br/>"
        f"S.Y. {school_year_range}</b>", 
        title_style
    ))
    elements.append(Spacer(1, 10))

    # Table Headers
    headers = [
        Paragraph("<b>GRADE LEVEL</b>", header_style),
        Paragraph("<b>READERS<br/>ADMITTED</b>", header_style),
        Paragraph("<b>LIBRARY<br/>RESOURCES</b>", header_style),
        Paragraph("<b>INTERNET<br/>USAGE</b>", header_style),
        Paragraph("<b>PERIODICAL<br/>USAGE</b>", header_style),
        Paragraph("<b>TOTAL</b>", header_style),  # TOTAL column header remains dark blue
    ]

    # Insert Data with Empty Rows
    table_data = [headers]
    grade_levels = list(data.keys())

    for i, level in enumerate(grade_levels):
        table_data.append([level] + list(map(str, data[level].values())))

        # Add empty row for clear separation
        if level in ["Grade 12", "Faculty/Staff"]:
            table_data.append([""] * len(headers))  # Empty row

    # Column Widths
    col_widths = [1.4 * inch, 1.3 * inch, 1.5 * inch, 1.2 * inch, 1.5 * inch, 1.1 * inch]
    if sum(col_widths) > TABLE_WIDTH:
        scale_factor = TABLE_WIDTH / sum(col_widths)
        col_widths = [w * scale_factor for w in col_widths]

    # Create Table
    table = Table(table_data, colWidths=col_widths)

    # Table Styling
    style_commands = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.darkblue),  # Header row (dark blue)
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),  # White text for headers
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (1, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]

    # Grey Background for TOTAL Row
    total_index = len(table_data) - 1
    style_commands.append(("BACKGROUND", (0, total_index), (-1, total_index), colors.lightgrey))  # TOTAL row

    # TOTAL Column Background (Except Header)
    style_commands.append(("BACKGROUND", (-1, 1), (-1, total_index - 1), colors.lightgrey))  # TOTAL column (except header)

    table.setStyle(TableStyle(style_commands))

    elements.append(table)
    
    # Pie Charts Data
    total_data = {
        "Readers Admitted": data["TOTAL"]["Readers Admitted"],
        "Library Resources": data["TOTAL"]["Library Resources"],
        "Internet Usage": data["TOTAL"]["Internet Usage"],
        "Periodical Usage": data["TOTAL"]["Periodical Usage"],
    }

    level_data = {key: data[key]["Total"] for key in data.keys() if key != "TOTAL"}

    # Generate Pie Charts with Titles - use school_year_range for titles
    elements.append(Spacer(1, 10))
    pie_chart_1 = generate_pie_chart(total_data, f"Library Services S.Y. {school_year_range}")
    pie_chart_2 = generate_pie_chart(level_data, f"Library Services S.Y. {school_year_range} by Level")

    # Insert Pie Charts Side-by-Side
    elements.append(Spacer(1, 20))
    pie_chart_table = Table([[pie_chart_1, pie_chart_2]], colWidths=[3 * inch, 3 * inch])
    elements.append(pie_chart_table)
    elements.append(Spacer(1, 70))  # Less space before description

    # Overall Description of Pie Charts
    chart_description = Paragraph(
        "The pie charts above show library service usage over the selected period. The first chart displays usage by service type, while the second breaks it down by grade level and faculty. These charts offer insights into service access and user engagement.",
        normal_style
    )
    elements.append(chart_description)
    elements.append(Spacer(1, 0))  # Space before next section

    # Build PDF
    doc.build(elements)

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
    - BorrowRecords = current school year
    - BorrowRecordsBuffer = previous school year
    - BorrowRecordsArchive = two years ago
    """
    current_year = get_current_school_year()
    
    # Extract the first year from the current school year
    start_year = int(current_year.split('-')[0])
    
    return {
        'current': current_year,  # e.g., "2024-2025"
        'buffer': f"{start_year-1}-{start_year}",  # e.g., "2023-2024"
        'archive': f"{start_year-2}-{start_year-1}"  # e.g., "2022-2023"
    }

def generate_borrow_report(request, selected_years=None):
    """
    Generate a comprehensive report from all borrow records databases
    """
    # Determine school years for each database
    school_years = get_db_school_years()
    
    # If specific years are selected, only include those
    years_to_process = {}
    if selected_years:
        for year_key in selected_years:
            if year_key in school_years:
                years_to_process[year_key] = school_years[year_key]
    else:
        years_to_process = school_years
    
    all_records = []
    
    # Process selected databases
    if 'current' in selected_years:
        current_year_str = school_years.get('current')
        print(f"Processing current borrow records for report: {current_year_str}")
        current_records = process_current_records(
            BorrowRecord.objects.all(), 
            current_year_str
        )
        all_records.extend(current_records)
    
    if 'buffer' in selected_years:
        buffer_year_str = school_years.get('buffer')
        print(f"Processing buffer borrow records for report: {buffer_year_str}")
        # Use all buffer records
        buffer_records = process_buffer_records(
            BorrowRecordsBuffer.objects.all(),
            buffer_year_str
        )
        all_records.extend(buffer_records)
    
    if 'archive' in selected_years:
        archive_year_str = school_years.get('archive')
        print(f"Processing archive borrow records for report: {archive_year_str}")
        # Use all archive records
        archive_records = process_archive_records(
            BorrowRecordsArchive.objects.all(),
            archive_year_str
        )
        all_records.extend(archive_records)
    
    # Generate CSV response
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="library_borrow_report.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        'Record Number', 'School Year', 'Section', 'Collection Type', 
        'Borrow Date', 'Return Date', 'Status', 'Late Fee'
    ])
    
    for record in all_records:
        writer.writerow([
            record['record_number'],
            record['school_year'],
            record['section'],
            record['collection_type'],
            record['borrow_date'],
            record['return_date'],
            record['status'],
            record['late_fee']
        ])
    
    return response

def process_current_records(records, school_year):
    """
    Process current BorrowRecords by looking up section and collection_type
    """
    processed_records = []
    
    for record in records:
        # Look up section from User using get_user() helper method
        user = record.get_user()
        section = user.section if user else "Unknown"
        
        # Look up collection_type from Book using get_book() helper method
        book = record.get_book()
        collection_type = book.collection_type if book else "Unknown"
        
        processed_records.append({
            'record_number': record.borrow_record_number,
            'school_year': school_year,
            'section': section,
            'collection_type': collection_type,
            'borrow_date': record.borrow_date,
            'return_date': record.return_date,
            'status': record.borrow_status,
            'late_fee': record.late_payment_fee_amount
        })
    
    return processed_records

def process_buffer_records(records, school_year):
    """
    Process BorrowRecordsBuffer with direct section and collection_type fields
    """
    processed_records = []
    
    for record in records:
        # Use direct section and collection_type fields
        processed_records.append({
            'record_number': record.borrow_record_number,
            'school_year': school_year,
            'section': record.section,
            'collection_type': record.collection_type,
            'borrow_date': record.borrow_date,
            'return_date': record.return_date,
            'status': record.borrow_status,
            'late_fee': record.late_payment_fee_amount
        })
    
    return processed_records

def process_archive_records(records, school_year):
    """
    Process BorrowRecordsArchive with direct section and collection_type fields
    """
    processed_records = []
    
    for record in records:
        # Use direct section and collection_type fields
        processed_records.append({
            'record_number': record.borrow_record_number,
            'school_year': school_year,
            'section': record.section,
            'collection_type': record.collection_type,
            'borrow_date': record.borrow_date,
            'return_date': record.return_date,
            'status': record.borrow_status,
            'late_fee': record.late_payment_fee_amount
        })
    
    return processed_records

def generate_statistics_report(request, selected_years=None):
    """
    Generate statistics broken down by school year, section, and collection type
    """
    # Determine school years for each database
    school_years = get_db_school_years()
    
    # If specific years are selected, only include those
    years_to_process = {}
    if selected_years:
        for year_key in selected_years:
            if year_key in school_years:
                years_to_process[year_key] = school_years[year_key]
    else:
        years_to_process = school_years
    
    all_records = []
    
    # Process selected databases
    if 'current' in years_to_process:
        current_records = process_current_records(
            BorrowRecord.objects.all(), 
            years_to_process['current']
        )
        all_records.extend(current_records)
    
    if 'buffer' in years_to_process:
        buffer_records = process_buffer_records(
            BorrowRecordsBuffer.objects.all(),
            years_to_process['buffer']
        )
        all_records.extend(buffer_records)
    
    if 'archive' in years_to_process:
        archive_records = process_archive_records(
            BorrowRecordsArchive.objects.all(),
            years_to_process['archive']
        )
        all_records.extend(archive_records)
    
    # Generate CSV response with statistics
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="library_statistics_report.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        'School Year', 'Section', 'Collection Type', 
        'Total Borrows', 'Total Returns', 'Average Late Fee'
    ])
    
    # Group records by school year, section, and collection type
    stats = {}
    for record in all_records:
        year = record['school_year']
        section = record['section'] or "Unknown"
        collection = record['collection_type'] or "Unknown"
        
        # Create dictionary keys if they don't exist
        if year not in stats:
            stats[year] = {}
        if section not in stats[year]:
            stats[year][section] = {}
        if collection not in stats[year][section]:
            stats[year][section][collection] = {
                'borrows': 0,
                'returns': 0,
                'late_fees': []
            }
        
        # Add record to stats
        stats[year][section][collection]['borrows'] += 1
        if record['status'] == 'returned':
            stats[year][section][collection]['returns'] += 1
            if float(record['late_fee']) > 0:
                stats[year][section][collection]['late_fees'].append(float(record['late_fee']))
    
    # Write statistics to CSV
    for year in stats:
        for section in stats[year]:
            for collection in stats[year][section]:
                total_borrows = stats[year][section][collection]['borrows']
                total_returns = stats[year][section][collection]['returns']
                
                # Calculate average late fee
                late_fees = stats[year][section][collection]['late_fees']
                avg_late_fee = sum(late_fees) / len(late_fees) if late_fees else 0
                
                writer.writerow([
                    year,
                    section,
                    collection,
                    total_borrows,
                    total_returns,
                    f"{avg_late_fee:.2f}"
                ])
    
    return response

def generate_computer_usage_report(request, selected_years=None):
    """
    Generate a comprehensive report from all computer usage records
    including ComputerUsage, ComputerUsageBuffer, and ComputerUsageArchive
    """
    # Determine school years for each database
    school_years = get_db_school_years()
    
    # If specific years are selected, only include those
    years_to_process = {}
    if selected_years:
        for year_key in selected_years:
            if year_key in school_years:
                years_to_process[year_key] = school_years[year_key]
    else:
        years_to_process = school_years
    
    all_records = []
    
    # Process current computer usage records
    if 'current' in selected_years:
        current_year_str = school_years.get('current')
        print(f"Processing current computer records for report: {current_year_str}")
        current_records = process_current_computer_records(
            ComputerUsage.objects.all(), 
            current_year_str
        )
        all_records.extend(current_records)
    
    # Process buffer computer records
    if 'buffer' in selected_years:
        buffer_year_str = school_years.get('buffer')
        print(f"Processing buffer computer records for report: {buffer_year_str}")
        # Use all buffer records
        buffer_records = process_buffer_computer_records(
            ComputerUsageBuffer.objects.all(),
            buffer_year_str
        )
        all_records.extend(buffer_records)
    
    # Process archive computer records
    if 'archive' in selected_years:
        archive_year_str = school_years.get('archive')
        print(f"Processing archive computer records for report: {archive_year_str}")
        # Get all archive records
        archive_records = ComputerUsageArchive.objects.all()
        print(f"Found {archive_records.count()} archive records")
        
        # DEBUGGING: Print the school year values in the database
        school_years_in_db = set(archive_records.values_list('school_year', flat=True))
        print(f"School years in archive database: {school_years_in_db}")
        
        processed_archive_records = process_archive_computer_records(
            archive_records,
            archive_year_str
        )
        all_records.extend(processed_archive_records)
    
    # Generate CSV response
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="computer_usage_report.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        'Record Number', 'School Year', 'Section', 'Date',
        'Grade Level'
    ])
    
    for record in all_records:
        writer.writerow([
            record['record_number'],
            record['school_year'],
            record['section'],
            record['date'],
            record['grade_level']
        ])
    
    return response

def process_current_computer_records(records, school_year):
    """
    Process current ComputerUsage records by looking up user details
    """
    processed_records = []
    
    for record in records:
        user = record.user
        section = user.section if user else "Unknown"
        grade_level = extract_grade_level(section, user.user_type if user else "Unknown")
        
        processed_records.append({
            'record_number': record.counter,
            'school_year': school_year,
            'section': section,
            'date': record.date,
            'grade_level': grade_level
        })
    
    return processed_records

def process_buffer_computer_records(records, school_year):
    """
    Process ComputerUsageBuffer records which already have section field
    """
    processed_records = []
    
    for record in records:
        section = record.section or "Unknown"
        # Determine grade level based on section
        is_student = bool(re.search(r"(\d+)", section))
        user_type = 'Student' if is_student else 'Staff'
        grade_level = extract_grade_level(section, user_type)
        
        processed_records.append({
            'record_number': record.counter,
            'school_year': record.school_year or school_year,
            'section': section,
            'date': record.date,
            'grade_level': grade_level
        })
    
    return processed_records

def process_archive_computer_records(records, school_year):
    """
    Process ComputerUsageArchive records which already have section field
    """
    processed_records = []
    
    for record in records:
        section = record.section or "Unknown"
        # Determine grade level based on section
        is_student = bool(re.search(r"(\d+)", section))
        user_type = 'Student' if is_student else 'Staff'
        grade_level = extract_grade_level(section, user_type)
        
        processed_records.append({
            'record_number': record.counter,
            'school_year': record.school_year or school_year,
            'section': section,
            'date': record.date,
            'grade_level': grade_level
        })
    
    return processed_records

def integrate_with_pdf_report(attendance_path, selected_years, report_type, output_path):
    """
    Integrate the new database structure with your existing PDF report generator
    """
    # Get data from selected databases
    school_years = get_db_school_years()
    
    # If specific years are selected, only include those
    years_to_process = {}
    if selected_years:
        for year_key in selected_years:
            if year_key in school_years:
                years_to_process[year_key] = school_years[year_key]
    else:
        years_to_process = school_years
    
    # Calculate date ranges based on selected school years
    date_ranges = {}
    for year_key, year_value in years_to_process.items():
        start_year = int(year_value.split('-')[0])
        end_year = int(year_value.split('-')[1])
        date_ranges[year_key] = {
            'start': f"{start_year}-06-01",
            'end': f"{end_year}-05-31"
        }
    
    # Calculate overall date range for the report
    start_date = min([date_ranges[key]['start'] for key in date_ranges]) if date_ranges else None
    end_date = max([date_ranges[key]['end'] for key in date_ranges]) if date_ranges else None
    
    # Now call the existing report generator with the combined data and selected years
    generate_pdf_report(attendance_path, start_date, end_date, output_path, selected_years)


def generate_all_reports(request, output_dir, selected_years=None, attendance_path=None):
    """
    Generate all report types:
    1. PDF utilization report
    2. Borrow records CSV
    3. Statistics CSV
    4. Computer usage CSV
    
    This function acts as a central point for generating all reports.
    """
    # Ensure output directory exists
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # Generate PDF utilization report
    if attendance_path and os.path.exists(attendance_path):
        pdf_output_path = os.path.join(output_dir, "library_utilization_report.pdf")
        integrate_with_pdf_report(attendance_path, selected_years, "pdf", pdf_output_path)
    
    # Generate borrow records CSV
    borrow_csv = generate_borrow_report(request, selected_years)
    with open(os.path.join(output_dir, "library_borrow_report.csv"), 'wb') as f:
        f.write(borrow_csv.content)
    
    # Generate statistics CSV
    stats_csv = generate_statistics_report(request, selected_years)
    with open(os.path.join(output_dir, "library_statistics_report.csv"), 'wb') as f:
        f.write(stats_csv.content)
    
    # Generate computer usage CSV
    computer_csv = generate_computer_usage_report(request, selected_years)
    with open(os.path.join(output_dir, "computer_usage_report.csv"), 'wb') as f:
        f.write(computer_csv.content)
    
    return {
        'pdf_path': os.path.join(output_dir, "library_utilization_report.pdf") if attendance_path else None,
        'borrow_csv': os.path.join(output_dir, "library_borrow_report.csv"),
        'stats_csv': os.path.join(output_dir, "library_statistics_report.csv"),
        'computer_csv': os.path.join(output_dir, "computer_usage_report.csv")
    }

def get_report_title_text(selected_years):
    """
    Generate an appropriate title based on which school years were selected.
    
    Args:
        selected_years: A list of selected year keys ('current', 'buffer', 'archive')
        
    Returns:
        A string with the appropriate time period text for the title
    """
    # Sort the selected years to ensure consistent ordering
    selected_years = sorted(selected_years)
    
    if selected_years == ['current']:
        return "FOR THIS YEAR"
    elif selected_years == ['buffer']:
        return "LAST YEAR"
    elif selected_years == ['archive']:
        return "TWO YEARS AGO"
    elif selected_years == ['buffer', 'current']:
        return "FOR THE LAST TWO YEARS"
    elif selected_years == ['archive', 'buffer', 'current']:
        return "FOR THE LAST THREE YEARS"
    elif selected_years == ['archive', 'buffer']:
        return "FOR THE LAST TWO YEARS (EXCLUDING CURRENT YEAR)"
    elif selected_years == ['archive', 'current']:
        return "FOR THIS YEAR AND TWO YEARS AGO"
    else:
        # Fallback for any other combination
        return f"FOR THE SELECTED PERIOD"
    
def get_school_year_range(selected_years):
    """
    Generate the appropriate school year range based on which school years were selected.
    
    Args:
        selected_years: A list of selected year keys ('current', 'buffer', 'archive')
        
    Returns:
        A string with the appropriate school year range (e.g., "2023-2025")
    """
    # Get the school years dict
    school_years = get_db_school_years()
    
    # If no years selected, return current school year
    if not selected_years or not any(year in school_years for year in selected_years):
        return get_current_school_year()
        
    # Get all selected years that exist in school_years
    valid_selected_years = [school_years[year] for year in selected_years if year in school_years]
    
    if not valid_selected_years:
        return get_current_school_year()
        
    # Parse the years to find the earliest start and latest end
    earliest_start = None
    latest_end = None
    
    for year_range in valid_selected_years:
        start_year, end_year = year_range.split('-')
        start_year = int(start_year)
        end_year = int(end_year)
        
        if earliest_start is None or start_year < earliest_start:
            earliest_start = start_year
            
        if latest_end is None or end_year > latest_end:
            latest_end = end_year
    
    # Format the resulting range
    return f"{earliest_start}-{latest_end}"