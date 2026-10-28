"""Download Bytebase's MySQL dataset_large and print import instructions."""
from pathlib import Path
from urllib.request import urlopen
from zipfile import ZipFile
from io import BytesIO

ROOT = Path(__file__).resolve().parents[1]
URL = "https://github.com/bytebase/employee-sample-database/archive/refs/heads/main.zip"
DEST = ROOT / "data" / "employee-sample-database"


def main():
    print(f"Downloading dataset from {URL}")
    with urlopen(URL, timeout=60) as response:
        payload = response.read()
    with ZipFile(BytesIO(payload)) as archive:
        prefix = next(name.split("/")[0] for name in archive.namelist()
                      if "/mysql/dataset_large/employee.sql" in name)
        members = [name for name in archive.namelist()
                   if name.startswith(prefix + "/mysql/dataset_large/")]
        for name in members:
            relative = Path(*name.split("/")[3:])
            if not relative.parts:
                continue
            target = DEST / relative
            if name.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(name))
    print(f"Downloaded dataset_large files to: {DEST}")
    print("Import with: mysql -u root -p < data/employee-sample-database/employee.sql")
    print("Then verify with: mysql -u root -p < data/employee-sample-database/test_employee_md5.sql")


if __name__ == "__main__":
    main()
