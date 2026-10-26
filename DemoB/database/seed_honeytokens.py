import os
import random
from datetime import date, timedelta

import mysql.connector
from dotenv import load_dotenv
from faker import Faker

load_dotenv()
SECURITY_DB = os.getenv("SECURITY_DB_NAME", "honeytoken_security_b")
DATASET_DB = os.getenv("DB_NAME", "employee")
if SECURITY_DB != "honeytoken_security_b" or DATASET_DB not in {"employee", "employee_ab"}:
    raise ValueError("Demo B requires SECURITY_DB_NAME=honeytoken_security_b and DB_NAME=employee or employee_ab")

SEED = 42
TOKEN_COUNT = 50
TOKEN_START = int(os.getenv("TOKEN_START", "900001"))

fake = Faker("en_US")
Faker.seed(SEED)
rng = random.Random(SEED)


def connect():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        database=DATASET_DB,
    )


def generate_employee(emp_no):
    birth_date = fake.date_between(
        start_date=date(1950, 1, 1),
        end_date=date(1970, 12, 31),
    )

    hire_date = fake.date_between(
        start_date=date(1985, 1, 1),
        end_date=date(1999, 12, 31),
    )

    return (
        emp_no,
        birth_date,
        fake.first_name()[:14],
        fake.last_name()[:16],
        rng.choice(["M", "F"]),
        hire_date,
    )


def main():
    connection = connect()
    cursor = connection.cursor()

    try:
        # Existing department identifiers
        cursor.execute(
            "SELECT dept_no FROM department ORDER BY dept_no"
        )
        departments = [row[0] for row in cursor.fetchall()]

        if not departments:
            raise RuntimeError("No departments found")

        # Prevent overwriting existing employee identifiers
        cursor.execute(
            """
            SELECT emp_no
            FROM employee
            WHERE emp_no BETWEEN %s AND %s
            """,
            (TOKEN_START, TOKEN_START + TOKEN_COUNT - 1),
        )
        existing_employees = cursor.fetchall()

        cursor.execute(
            f"""
            SELECT emp_no
            FROM {SECURITY_DB}.honeytoken_registry
            WHERE emp_no BETWEEN %s AND %s
            """,
            (TOKEN_START, TOKEN_START + TOKEN_COUNT - 1),
        )
        existing_registry = cursor.fetchall()

        if existing_employees or existing_registry:
            raise RuntimeError(
                "Token ID range already occupied. No changes made."
            )

        for index in range(TOKEN_COUNT):
            emp_no = TOKEN_START + index
            employee = generate_employee(emp_no)
            hire_date = employee[5]
            dept_no = rng.choice(departments)

            # Employee
            cursor.execute(
                """
                INSERT INTO employee
                (emp_no, birth_date, first_name,
                 last_name, gender, hire_date)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                employee,
            )

            # Salary
            salary_amount = rng.randint(40000, 120000)

            cursor.execute(
                """
                INSERT INTO salary
                (emp_no, amount, from_date, to_date)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    emp_no,
                    salary_amount,
                    hire_date,
                    date(9999, 1, 1),
                ),
            )

            # Department assignment
            cursor.execute(
                """
                INSERT INTO dept_emp
                (emp_no, dept_no, from_date, to_date)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    emp_no,
                    dept_no,
                    hire_date,
                    date(9999, 1, 1),
                ),
            )

            # Privileged honeytoken registry
            cursor.execute(
                f"""
                INSERT INTO
                    {SECURITY_DB}.honeytoken_registry
                (emp_no, placement_strategy, placement_version)
                VALUES (%s, %s, %s)
                """,
                (
                    emp_no,
                    "STATIC",
                    "baseline_v1",
                ),
            )

        connection.commit()
        print(f"Successfully inserted {TOKEN_COUNT} honeytokens.")
        print(f"Token range: {TOKEN_START}–{TOKEN_START + TOKEN_COUNT - 1}")

    except Exception:
        connection.rollback()
        print("Transaction rolled back.")
        raise

    finally:
        cursor.close()
        connection.close()


if __name__ == "__main__":
    main()
