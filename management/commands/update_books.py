from libapp.models import Book

def book_type(new):
    newstring = new.accession_number.replace(" ", "").upper()  # Normalize input
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
        "SHS-REF": "shsreference",
        "REF": "reference",
        "PER": "periodicals",
        "ARC": "archives",
    }

    return mapping.get(letter_type, None)  # Return None if not found

    