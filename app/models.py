from flask_login import UserMixin
from app.services.db_services import get_db_connection

class Admin(UserMixin):
    def __init__(self, id, email, name, company_id, role, interview_limit, is_verified):
        self.id = id
        self.email = email
        self.name = name
        self.company_id = company_id
        self.role = role
        self.interview_limit = interview_limit
        self.is_verified = is_verified

    @staticmethod
    def get(admin_id):
        conn = get_db_connection()
        if not conn:
            return None
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM admins WHERE id = %s", (admin_id,))
        admin_data = cursor.fetchone()
        conn.close()
        if admin_data:
            return Admin(
                id=admin_data['id'],
                email=admin_data['email'],
                name=admin_data['name'],
                company_id=admin_data['company_id'],
                role=admin_data['role'],
                interview_limit=admin_data['interview_limit'],
                is_verified=admin_data['is_verified']
            )
        return None
