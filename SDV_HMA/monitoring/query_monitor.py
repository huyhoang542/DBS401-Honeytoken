
import os
import sys

import mysql.connector
from dotenv import load_dotenv

load_dotenv()


def connect_as(user, password):
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=user,
        password=password,
        database="employee",
    )


def query_employee(emp_no):
    reader = None
    monitor = None

    try:
        reader = connect_as(
            os.environ["READER_USER"],
            os.environ["READER_PASSWORD"],
        )
        monitor = connect_as(
            os.environ["MONITOR_USER"],
            os.environ["MONITOR_PASSWORD"],
        )

        reader_cursor = reader.cursor(dictionary=True)
        monitor_cursor = monitor.cursor(dictionary=True)

        # 1. Execute user query
        sql = """
            SELECT emp_no, first_name, last_name, hire_date
            FROM employee
            WHERE emp_no = %s
        """

        reader_cursor.execute(sql, (emp_no,))
        rows = reader_cursor.fetchall()

        # 2. Check privileged honeytoken registry
        monitor_cursor.execute(
            """
            SELECT token_id
            FROM honeytoken_security.honeytoken_registry
            WHERE emp_no = %s AND is_active = TRUE
            """,
            (emp_no,),
        )

        token = monitor_cursor.fetchone()
        is_hit = bool(rows) and token is not None

        # 3. Record access event
        monitor_cursor.execute(
            """
            INSERT INTO honeytoken_security.access_events
                (username, query_type, target_table,
                 query_text, returned_rows, honeytoken_hit)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                os.environ["READER_USER"],
                "SELECT",
                "employee",
                f"SELECT employee WHERE emp_no = {emp_no}",
                len(rows),
                is_hit,
            ),
        )

        event_id = monitor_cursor.lastrowid

        # 4. Create alert if honeytoken is accessed
        if is_hit:
            monitor_cursor.execute(
                """
                INSERT INTO honeytoken_security.security_alerts
                    (event_id, token_id, severity, message)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    event_id,
                    token["token_id"],
                    "HIGH",
                    "Honeytoken employee record accessed",
                ),
            )

        monitor.commit()

        print(f"Returned rows: {len(rows)}")

        if is_hit:
            print("ALERT: Honeytoken accessed!")
        else:
            print("No honeytoken detected.")

        for row in rows:
            print(row)

    except Exception:
        if monitor is not None:
            monitor.rollback()
        raise

    finally:
        if reader is not None:
            reader.close()
        if monitor is not None:
            monitor.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python monitoring/query_monitor.py EMP_NO")
        sys.exit(1)

    try:
        employee_id = int(sys.argv[1])
    except ValueError:
        print("EMP_NO must be an integer.")
        sys.exit(1)

    query_employee(employee_id)

