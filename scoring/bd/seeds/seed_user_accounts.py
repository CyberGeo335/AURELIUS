
import csv
import os
import random
import secrets
import string
from pathlib import Path

import psycopg
from psycopg.rows import dict_row


# ============================================================
# НАСТРОЙКИ
# ============================================================

DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 5433,
    "dbname": "business_scoring",
    "user": "postgres",
    "password": os.getenv(
        "admin",
        "admin"
    ),
}

CLIENT_COUNT = 30
BANK_EMPLOYEE_COUNT = 2
TOTAL_USERS = CLIENT_COUNT + BANK_EMPLOYEE_COUNT

FEMALE_COUNT = 16
MALE_COUNT = 16

RANDOM_SEED = 42

OUTPUT_CSV = (
    Path(__file__).resolve().parent
    / "generated_credentials.csv"
)


# ============================================================
# ЗАДАННЫЕ ПОЛЬЗОВАТЕЛИ
# ============================================================

SPECIAL_USERS = [
    ("Демина", "Ева", "Александровна", "F"),
    ("Козин", "Георгий", "Сергеевич", "M"),
    ("Глебко", "Данил", "Андреевич", "M"),
]


# ============================================================
# СПРАВОЧНИКИ ФИО
# ============================================================

MALE_FIRST_NAMES = [
    "Александр", "Дмитрий", "Максим", "Андрей",
    "Сергей", "Алексей", "Иван", "Михаил",
    "Николай", "Павел", "Артем", "Владимир",
    "Кирилл", "Роман", "Егор", "Денис",
    "Виктор", "Илья",
]

MALE_LAST_NAMES = [
    "Иванов", "Петров", "Сидоров", "Смирнов",
    "Кузнецов", "Попов", "Васильев", "Соколов",
    "Михайлов", "Новиков", "Федоров", "Морозов",
    "Волков", "Алексеев", "Лебедев",
]

MALE_MIDDLE_NAMES = [
    "Александрович", "Дмитриевич", "Сергеевич",
    "Андреевич", "Иванович", "Михайлович",
    "Николаевич", "Павлович", "Владимирович",
    "Алексеевич",
]

FEMALE_FIRST_NAMES = [
    "Анна", "Мария", "Екатерина", "Анастасия",
    "Ольга", "Елена", "Дарья", "Алина",
    "Полина", "София", "Виктория", "Ксения",
    "Татьяна", "Наталья", "Ирина", "Юлия",
    "Валерия", "Вероника",
]

FEMALE_LAST_NAMES = [
    "Иванова", "Петрова", "Сидорова", "Смирнова",
    "Кузнецова", "Попова", "Васильева", "Соколова",
    "Михайлова", "Новикова", "Федорова", "Морозова",
    "Волкова", "Алексеева", "Лебедева",
]

FEMALE_MIDDLE_NAMES = [
    "Александровна", "Дмитриевна", "Сергеевна",
    "Андреевна", "Ивановна", "Михайловна",
    "Николаевна", "Павловна", "Владимировна",
    "Алексеевна",
]


# ============================================================
# ГЕНЕРАЦИЯ ПАРОЛЕЙ
# ============================================================

def generate_password(length=12):
    """
    Генерация случайного пароля для тестового MVP.
    """

    alphabet = string.ascii_letters + string.digits

    return "".join(
        secrets.choice(alphabet)
        for _ in range(length)
    )


# ============================================================
# ГЕНЕРАЦИЯ ФИО
# ============================================================

def generate_person(gender, rng):

    if gender == "M":
        return {
            "last_name": rng.choice(MALE_LAST_NAMES),
            "first_name": rng.choice(MALE_FIRST_NAMES),
            "middle_name": rng.choice(MALE_MIDDLE_NAMES),
            "gender": "M",
        }

    if gender == "F":
        return {
            "last_name": rng.choice(FEMALE_LAST_NAMES),
            "first_name": rng.choice(FEMALE_FIRST_NAMES),
            "middle_name": rng.choice(FEMALE_MIDDLE_NAMES),
            "gender": "F",
        }

    raise ValueError(f"Неизвестный пол: {gender}")


# ============================================================
# ПОДГОТОВКА 32 ПОЛЬЗОВАТЕЛЕЙ
# ============================================================

def build_users():

    rng = random.Random(RANDOM_SEED)

    users = []

    for last_name, first_name, middle_name, gender in SPECIAL_USERS:
        users.append({
            "last_name": last_name,
            "first_name": first_name,
            "middle_name": middle_name,
            "gender": gender,
        })

    existing_female = sum(
        user["gender"] == "F" for user in users
    )

    existing_male = sum(
        user["gender"] == "M" for user in users
    )

    remaining_female = FEMALE_COUNT - existing_female
    remaining_male = MALE_COUNT - existing_male

    genders = (
        ["F"] * remaining_female
        + ["M"] * remaining_male
    )

    rng.shuffle(genders)

    used_names = {
        (
            user["last_name"],
            user["first_name"],
            user["middle_name"],
        )
        for user in users
    }

    for gender in genders:

        for _ in range(1000):

            person = generate_person(gender, rng)

            name_key = (
                person["last_name"],
                person["first_name"],
                person["middle_name"],
            )

            if name_key not in used_names:
                users.append(person)
                used_names.add(name_key)
                break

        else:
            raise RuntimeError(
                "Не удалось создать уникальное ФИО"
            )

    if len(users) != TOTAL_USERS:
        raise RuntimeError(
            f"Ожидалось {TOTAL_USERS} аккаунта, "
            f"получено {len(users)}"
        )

    for index, user in enumerate(users):

        if index < CLIENT_COUNT:
            user["role"] = "CLIENT"
            user["login"] = f"client_{index + 1:03d}"

        else:
            bank_number = index - CLIENT_COUNT + 1
            user["role"] = "BANK_EMPLOYEE"
            user["login"] = f"bank_{bank_number:03d}"

        user["password"] = generate_password()

    return users


# ============================================================
# СОХРАНЕНИЕ CSV
# ============================================================

def save_credentials(accounts):

    fieldnames = [
        "user_id",
        "last_name",
        "first_name",
        "middle_name",
        "login",
        "password",
        "role",
        "company_id",
    ]

    # Временный файл, чтобы не оставлять неполный CSV.
    temp_path = OUTPUT_CSV.with_suffix(".csv.tmp")

    with open(
        temp_path,
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
            delimiter=";",
        )

        writer.writeheader()

        for account in accounts:
            writer.writerow({
                key: account.get(key)
                for key in fieldnames
            })

    os.replace(temp_path, OUTPUT_CSV)


# ============================================================
# СОЗДАНИЕ АККАУНТОВ
# ============================================================

def create_accounts():

    print("=" * 65)
    print("AURELIUS — ГЕНЕРАЦИЯ АККАУНТОВ")
    print("=" * 65)

    users = build_users()

    print(f"Всего аккаунтов: {len(users)}")

    print(
        "Женщин:",
        sum(u["gender"] == "F" for u in users)
    )

    print(
        "Мужчин:",
        sum(u["gender"] == "M" for u in users)
    )

    created_accounts = []

    try:
        with psycopg.connect(**DB_CONFIG) as conn:

            with conn.cursor(row_factory=dict_row) as cur:

                # ----------------------------------------
                # Проверка компаний
                # ----------------------------------------

                cur.execute("""
                    SELECT company_id
                    FROM companies
                    ORDER BY company_id
                """)

                companies = cur.fetchall()

                if len(companies) != CLIENT_COUNT:
                    raise ValueError(
                        f"В таблице companies найдено "
                        f"{len(companies)} компаний. "
                        f"Ожидалось {CLIENT_COUNT}."
                    )

                # ----------------------------------------
                # Проверка существующих аккаунтов
                # ----------------------------------------

                cur.execute("""
                    SELECT COUNT(*) AS total
                    FROM user_accounts
                """)

                existing = cur.fetchone()["total"]

                if existing != 0:
                    raise ValueError(
                        f"В user_accounts уже есть "
                        f"{existing} аккаунтов. "
                        "Скрипт не изменяет существующие данные."
                    )

                # ----------------------------------------
                # Создание клиентов
                # ----------------------------------------

                for index in range(CLIENT_COUNT):

                    user = users[index]
                    company_id = companies[index]["company_id"]

                    cur.execute("""
                        INSERT INTO user_accounts (
                            last_name,
                            first_name,
                            middle_name,
                            login,
                            password,
                            role,
                            company_id,
                            is_active
                        )
                        VALUES (
                            %s, %s, %s, %s,
                            %s, %s, %s, TRUE
                        )
                        RETURNING user_id
                    """, (
                        user["last_name"],
                        user["first_name"],
                        user["middle_name"],
                        user["login"],
                        user["password"],
                        user["role"],
                        company_id,
                    ))

                    user_id = cur.fetchone()["user_id"]

                    created_accounts.append({
                        **user,
                        "user_id": user_id,
                        "company_id": company_id,
                    })

                # ----------------------------------------
                # Создание сотрудников банка
                # ----------------------------------------

                for index in range(
                    CLIENT_COUNT,
                    TOTAL_USERS,
                ):

                    user = users[index]

                    cur.execute("""
                        INSERT INTO user_accounts (
                            last_name,
                            first_name,
                            middle_name,
                            login,
                            password,
                            role,
                            company_id,
                            is_active
                        )
                        VALUES (
                            %s, %s, %s, %s,
                            %s, %s, NULL, TRUE
                        )
                        RETURNING user_id
                    """, (
                        user["last_name"],
                        user["first_name"],
                        user["middle_name"],
                        user["login"],
                        user["password"],
                        user["role"],
                    ))

                    user_id = cur.fetchone()["user_id"]

                    created_accounts.append({
                        **user,
                        "user_id": user_id,
                        "company_id": None,
                    })

                # ----------------------------------------
                # Сохранение CSV до фиксации транзакции
                # ----------------------------------------

                save_credentials(created_accounts)

            # При выходе из блока with conn
            # транзакция автоматически фиксируется.

    except psycopg.OperationalError as error:

        print("\nОшибка подключения к PostgreSQL.")
        print("Проверь DB_CONFIG.")
        print(error)
        return

    except Exception as error:

        print("\nОшибка генерации аккаунтов:")
        print(error)

        # Если CSV был создан, но транзакция откатилась,
        # удаляем CSV с несуществующими аккаунтами.
        if OUTPUT_CSV.exists():
            OUTPUT_CSV.unlink()

        raise

    # ========================================================
    # РЕЗУЛЬТАТ
    # ========================================================

    print("\nСозданные аккаунты:")
    print("-" * 100)

    for account in created_accounts:

        full_name = " ".join([
            account["last_name"],
            account["first_name"],
            account["middle_name"],
        ])

        print(
            f"{account['login']:<12} | "
            f"{full_name:<35} | "
            f"{account['role']:<15} | "
            f"company_id={account['company_id']}"
        )

    print("\n" + "=" * 65)
    print(f"Успешно создано: {len(created_accounts)}")
    print(f"CSV: {OUTPUT_CSV}")
    print("=" * 65)


# ============================================================
# ЗАПУСК
# ============================================================

if __name__ == "__main__":
    create_accounts()
