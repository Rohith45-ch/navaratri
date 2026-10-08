import csv
from pathlib import Path
from config import BASE_DIR, get_db


def generate_report():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) AS total FROM tickets")
    total = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) AS entered FROM tickets WHERE used = 1")
    entered = cursor.fetchone()["entered"]

    cursor.execute("SELECT COUNT(*) AS not_entered FROM tickets WHERE used = 0")
    not_entered = cursor.fetchone()["not_entered"]

    print("=" * 60)
    print("EVENT ENTRY SUMMARY REPORT")
    print("=" * 60)
    print(f"Total Attendees Registered : {total}")
    print(f"Attendees Entered          : {entered}")
    print(f"Attendees Not Yet Entered  : {not_entered}")
    print("=" * 60)

    cursor.execute("SELECT name, email FROM tickets WHERE used = 0 ORDER BY name COLLATE NOCASE ASC")
    unentered_list = cursor.fetchall()
    conn.close()

    print("\nAttendees Who Have Not Entered Yet:")
    if not unentered_list:
        print("  None! All registered attendees have entered.")
    else:
        for idx, attendee in enumerate(unentered_list, 1):
            print(f"  {idx:2d}. {attendee['name']} <{attendee['email']}>")

    # Save to not_entered.csv
    csv_out_path = BASE_DIR / "not_entered.csv"
    with open(csv_out_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "email"])
        for attendee in unentered_list:
            writer.writerow([attendee["name"], attendee["email"]])

    print(f"\nSaved {len(unentered_list)} unentered attendee(s) to '{csv_out_path.name}'.")


if __name__ == "__main__":
    generate_report()
