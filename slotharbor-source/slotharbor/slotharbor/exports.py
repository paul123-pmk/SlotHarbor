"""Portable reservation exports. No live links or spreadsheet formulas are emitted."""
import csv
import io
from .times import utc_stamp, local_label


def safe_cell(value) -> str:
    value = str(value)
    if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


def reservations_csv(rows) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["id", "resource", "purpose", "username", "starts_local", "ends_local", "timezone",
                     "party_size", "status", "series_id"])
    for row in rows:
        writer.writerow([safe_cell(v) for v in [row["id"],row["resource_name"],row["title"],row["username"],
            local_label(row["start_at"],row["timezone"]),local_label(row["end_at"],row["timezone"]),
            row["timezone"],row["attendees"],row["status"],row["series_id"]]])
    return output.getvalue()


def ical_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n").replace(";", "\\;").replace(",", "\\,")


def folded(line: str) -> str:
    """Fold at 75 UTF-8 octets without splitting a character; continuation consumes one."""
    parts, current, used = [], "", 0
    for character in line:
        size = len(character.encode("utf-8"))
        if used + size > 75:
            parts.append(current)
            current, used = " ", 1
        current += character
        used += size
    parts.append(current)
    return "\r\n".join(parts)


def calendar_ics(rows) -> str:
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//SlotHarbor//Reservations 0.1//EN", "CALSCALE:GREGORIAN"]
    for row in rows:
        status = {"pending":"TENTATIVE", "confirmed":"CONFIRMED", "cancelled":"CANCELLED", "rejected":"CANCELLED"}[row["status"]]
        lines.extend(["BEGIN:VEVENT", f"UID:reservation-{row['id']}-{row['series_id']}@slotharbor.local",
            "DTSTAMP:"+utc_stamp(row["updated_at"]), "DTSTART:"+utc_stamp(row["start_at"]),
            "DTEND:"+utc_stamp(row["end_at"]), "SUMMARY:"+ical_text(row["title"]),
            "LOCATION:"+ical_text(row["resource_name"]), "STATUS:"+status,
            "SEQUENCE:"+str(row["version"]-1), "END:VEVENT"])
    lines.append("END:VCALENDAR")
    return "\r\n".join(folded(line) for line in lines)+"\r\n"
