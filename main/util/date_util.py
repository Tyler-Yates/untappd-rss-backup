from datetime import datetime


def parse_checkin_date(date_str: str) -> datetime:
    """
    Parse checkin date string in either old or new format.
    
    Old format: "Mon, 26 Jun 2025 14:30:00 +0000"
    New format: "06/26/25"
    Check-in page format: "Sat, 28 Jun 2025 00:20:00 +0000"
    """
    date_str = date_str.strip()
    
    # Try old format first (with timezone)
    try:
        return datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S %z")
    except ValueError:
        pass
    
    # Try old format without timezone
    try:
        return datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S")
    except ValueError:
        pass
    
    # Try new format (MM/DD/YY)
    try:
        return datetime.strptime(date_str, "%m/%d/%y")
    except ValueError:
        pass
    
    # Try new format with full year (MM/DD/YYYY)
    try:
        return datetime.strptime(date_str, "%m/%d/%Y")
    except ValueError:
        pass
    
    # If all formats fail, raise an error with the problematic string
    raise ValueError(f"Could not parse date string: {date_str}") 