"""Create safe import scripts targeting employee_ab, preserving raw downloads."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "employee-sample-database"
DEST = ROOT / "data" / "employee_ab"


def main():
    if not (SOURCE / "employee.sql").exists():
        raise SystemExit("Dataset missing. Run: python evaluation/download_employee_dataset.py")
    DEST.mkdir(parents=True, exist_ok=True)
    for path in SOURCE.iterdir():
        if path.is_file():
            content = path.read_text(encoding="utf-8")
            if path.name in {"employee.sql", "test_employee_md5.sql"}:
                content = content.replace("DROP DATABASE IF EXISTS employee;",
                                          "DROP DATABASE IF EXISTS employee_ab;")
                content = content.replace("CREATE DATABASE IF NOT EXISTS employee;",
                                          "CREATE DATABASE IF NOT EXISTS employee_ab;")
                content = content.replace("USE employee;", "USE employee_ab;")
            (DEST / path.name).write_text(content, encoding="utf-8")
    print(f"Created isolated import scripts in {DEST}")
    print("Import by running from that directory: mysql -u root -p < employee.sql")
    print("Verify from that directory: mysql -u root -p < test_employee_md5.sql")
    print("This only drops/recreates employee_ab, leaving Demo A's employee database intact.")


if __name__ == "__main__":
    main()
