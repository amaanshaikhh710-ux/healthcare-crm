import os

import mysql.connector
from mysql.connector import Error


def get_db_connection():
    """Return a MySQL connection for the healthcare CRM database."""
    try:
        return mysql.connector.connect(
            host=os.getenv("DB_HOST", "localhost"),
            user=os.getenv("DB_USER", "root"),
            password=os.getenv("DB_PASSWORD", "Amaan@123"),
            database=os.getenv("DB_NAME", "healthcare_crm"),
        )
    except Error:
        raise
