import os

import mysql.connector
from dotenv import load_dotenv

load_dotenv()

connection = mysql.connector.connect(
    host=os.getenv("DB_HOST"),
    port=int(os.getenv("DB_PORT", "3306")),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    database=os.getenv("DB_NAME"),
)

try:
    cursor = connection.cursor()
    cursor.execute("SELECT COUNT(*) FROM employee")

    total = cursor.fetchone()[0]

    print("MySQL connection OK")
    print(f"Total employees: {total:,}")

    cursor.close()
finally:
    connection.close()
