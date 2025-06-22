from flask import Blueprint, jsonify, request, current_app, abort
from flask_login import login_required, current_user
from app.services.db_services import get_db_connection, serialize_datetime_in_obj
from flask_mail import Message
from app import mail
import datetime
import traceback
import json
import uuid
from functools import wraps

admin_bp = Blueprint('admin_bp', __name__)


# --- Decorator for Super Admin Access ---
def super_admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'super_admin':
            abort(403)  # Forbidden
        return f(*args, **kwargs)

    return decorated_function


@admin_bp.route('/jobs', methods=['GET', 'POST'])
@login_required
def manage_jobs():
    conn = get_db_connection()
    if not conn: return jsonify({"message": "Database connection failed"}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        # Super admin can see all jobs, others see their company's jobs
        if current_user.role == 'super_admin':
            base_query = "SELECT j.*, c.name as company_name FROM jobs j JOIN companies c ON j.company_id = c.id ORDER BY j.created_at DESC"
            params = ()
        else:
            base_query = "SELECT j.*, c.name as company_name FROM jobs j JOIN companies c ON j.company_id = c.id WHERE j.company_id = %s ORDER BY j.created_at DESC"
            params = (current_user.company_id,)

        if request.method == 'GET':
            cursor.execute(base_query, params)
            return jsonify(serialize_datetime_in_obj(cursor.fetchall())), 200

        if request.method == 'POST':
            if not current_user.is_verified:
                return jsonify({"message": "Please verify your email address before creating jobs."}), 403

            data = request.json
            if not data or not all(k in data for k in ['title', 'department', 'description']):
                return jsonify({"message": "Missing required fields"}), 400

            query = """
                INSERT INTO jobs (title, department, description, status, created_at, created_by, company_id, number_of_questions, must_ask_topics) 
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """
            cursor.execute(query, (
                data['title'], data['department'], data['description'],
                data.get('status', 'Open'), datetime.datetime.utcnow(),
                current_user.id, current_user.company_id,
                data.get('number_of_questions', 5), data.get('must_ask_topics')
            ))
            conn.commit()
            new_job_id = cursor.lastrowid
            cursor.execute("SELECT * FROM jobs WHERE id = %s", (new_job_id,))
            return jsonify(serialize_datetime_in_obj(cursor.fetchone())), 201

    except Exception as err:
        current_app.logger.error(f"DB error in manage_jobs: {err}\n{traceback.format_exc()}")
        if conn.is_connected(): conn.rollback()
        return jsonify({"message": "An unexpected error occurred"}), 500
    finally:
        if conn and conn.is_connected(): conn.close()


@admin_bp.route('/jobs/<job_id>', methods=['GET', 'PUT', 'DELETE'])
@login_required
def manage_job_detail(job_id):
    conn = get_db_connection()
    if not conn: return jsonify({"message": "Database connection failed"}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        # Security check: Regular admins can only access jobs in their company. Super admins can access any.
        if current_user.role == 'super_admin':
            query = "SELECT * FROM jobs WHERE id = %s"
            params = (job_id,)
        else:
            query = "SELECT * FROM jobs WHERE id = %s AND company_id = %s"
            params = (job_id, current_user.company_id)

        cursor.execute(query, params)
        job = cursor.fetchone()
        if not job: return jsonify({"message": "Job not found or access denied"}), 404

        if request.method == 'GET':
            return jsonify(serialize_datetime_in_obj(job)), 200

        if request.method == 'PUT':
            data = request.json
            if not data: return jsonify({"message": "No data for update"}), 400

            fields_to_update = []
            values = []
            allowed = ['title', 'department', 'description', 'status', 'number_of_questions', 'must_ask_topics']

            for field in allowed:
                if field in data:
                    fields_to_update.append(f"{field} = %s")
                    values.append(data[field])

            if not fields_to_update: return jsonify({"message": "No valid fields to update"}), 400

            values.append(datetime.datetime.utcnow())
            values.append(job_id)

            update_query = f"UPDATE jobs SET {', '.join(fields_to_update)}, updated_at = %s WHERE id = %s"
            cursor.execute(update_query, tuple(values));
            conn.commit()

            cursor.execute(query, params)  # Re-fetch the updated job
            return jsonify(serialize_datetime_in_obj(cursor.fetchone())), 200

        if request.method == 'DELETE':
            cursor.execute("DELETE FROM jobs WHERE id = %s", (job_id,))
            conn.commit()
            return jsonify({"message": "Job deleted successfully"}), 200

    except Exception as err:
        current_app.logger.error(f"DB error in manage_job_detail for {job_id}: {err}\n{traceback.format_exc()}")
        if request.method in ['PUT', 'DELETE'] and conn.is_connected(): conn.rollback()
        return jsonify({"message": "An unexpected error occurred"}), 500
    finally:
        if conn and conn.is_connected(): conn.close()


@admin_bp.route('/jobs/<job_id>/send-invites', methods=['POST'])
@login_required
def send_invites(job_id):
    if not current_user.is_verified:
        return jsonify({"message": "You must verify your email address before sending invites."}), 403

    conn = get_db_connection()
    if not conn: return jsonify({"message": "Database connection failed."}), 500

    try:
        cursor = conn.cursor(dictionary=True)

        if current_user.role != 'super_admin':
            cursor.execute("SELECT COUNT(id) as count FROM interviews WHERE created_by = %s", (current_user.id,))
            interview_count = cursor.fetchone()['count']

            emails_to_send = [email.strip() for email in request.json.get('emails', '').split(',') if email.strip()]

            if interview_count + len(emails_to_send) > current_user.interview_limit:
                return jsonify({
                    "message": f"You have reached your interview limit of {current_user.interview_limit}. To increase your limit, please contact support.",
                    "support_email": "chandrakant7892@gmail.com"
                }), 403

        data = request.json
        emails = [email.strip() for email in data.get('emails', '').split(',') if email.strip()]
        if not emails:
            return jsonify({"message": "No valid email addresses provided"}), 400

        cursor.execute(
            "SELECT j.title, c.name as company_name FROM jobs j JOIN companies c ON j.company_id = c.id WHERE j.id = %s",
            (job_id,))
        job_info = cursor.fetchone()
        if not job_info: return jsonify({"message": "Job not found"}), 404

        sent_count = 0
        failed_emails = []
        for email in emails:
            try:
                invitation_link_guid = str(uuid.uuid4())
                cursor.execute(
                    "INSERT INTO interviews (job_id, company_id, invitation_link, status, created_by) VALUES (%s, %s, %s, %s, %s)",
                    (job_id, current_user.company_id, invitation_link_guid, 'Invited', current_user.id)
                )
                # ... (email sending logic)
                sent_count += 1
            except Exception as e:
                failed_emails.append(email)
                current_app.logger.error(f"Failed to send invite to {email}: {e}")

        conn.commit()

        message = f"Successfully sent {sent_count} invites."
        if failed_emails: message += f" Failed to send to: {', '.join(failed_emails)}."

        return jsonify({"message": message}), 200

    except Exception as e:
        current_app.logger.error(f"Error sending invites for job {job_id}: {e}\n{traceback.format_exc()}")
        if conn.is_connected(): conn.rollback()
        return jsonify({"message": "An unexpected error occurred"}), 500
    finally:
        if conn and conn.is_connected(): conn.close()


@admin_bp.route('/interviews', methods=['GET'])
@login_required
def get_admin_interviews():
    conn = get_db_connection()
    if not conn: return jsonify({"message": "Database connection failed"}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        base_query = "FROM interviews i JOIN jobs j ON i.job_id = j.id LEFT JOIN candidates c ON i.candidate_id = c.id"

        params = []
        conditions = []

        if current_user.role != 'super_admin':
            conditions.append("i.company_id = %s")
            params.append(current_user.company_id)

        job_id_filter = request.args.get('job_id')
        if job_id_filter:
            conditions.append("i.job_id = %s")
            params.append(job_id_filter)

        where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""

        count_query = f"SELECT COUNT(i.id) as total {base_query}{where_clause}"
        cursor.execute(count_query, tuple(params))
        total_records = cursor.fetchone()['total']

        data_query = f"SELECT i.id, i.status, i.score, i.updated_at as interview_date, j.title as job_title, c.name as candidate_name {base_query}{where_clause} ORDER BY i.updated_at DESC"
        cursor.execute(data_query, tuple(params))
        interviews = cursor.fetchall()

        return jsonify({"total": total_records, "interviews": serialize_datetime_in_obj(interviews)}), 200

    except Exception as err:
        current_app.logger.error(f"DB error in get_admin_interviews: {err}\n{traceback.format_exc()}")
        return jsonify({"message": "An unexpected error occurred"}), 500
    finally:
        if conn and conn.is_connected(): conn.close()


@admin_bp.route('/interviews/<interview_id>', methods=['GET'])
@login_required
def get_admin_interview_detail(interview_id):
    conn = get_db_connection()
    if not conn: return jsonify({"message": "Database connection failed"}), 500

    try:
        cursor = conn.cursor(dictionary=True)

        if current_user.role == 'super_admin':
            query = "SELECT i.*, j.title as job_title, j.department as job_department, c.name as candidate_name, c.email as candidate_email FROM interviews i JOIN jobs j ON i.job_id = j.id LEFT JOIN candidates c ON i.candidate_id = c.id WHERE i.id = %s"
            params = (interview_id,)
        else:
            query = "SELECT i.*, j.title as job_title, j.department as job_department, c.name as candidate_name, c.email as candidate_email FROM interviews i JOIN jobs j ON i.job_id = j.id LEFT JOIN candidates c ON i.candidate_id = c.id WHERE i.id = %s AND i.company_id = %s"
            params = (interview_id, current_user.company_id)

        cursor.execute(query, params)
        interview = cursor.fetchone()
        if not interview: return jsonify({"message": "Interview not found or access denied"}), 404

        for key in ['transcript_json', 'ai_questions_json', 'screenshot_paths_json', 'detailed_scorecard_json']:
            if interview.get(key) and isinstance(interview[key], str):
                try:
                    interview[key] = json.loads(interview[key])
                except json.JSONDecodeError:
                    interview[key] = None

        interview['transcript'] = interview.get('transcript_json')
        interview['questions'] = interview.get('ai_questions_json')
        interview['screenshots'] = interview.get('screenshot_paths_json') or []

        return jsonify(serialize_datetime_in_obj(interview)), 200
    except Exception as err:
        current_app.logger.error(
            f"DB error in get_admin_interview_detail for {interview_id}: {err}\n{traceback.format_exc()}")
        return jsonify({"message": "An unexpected error occurred"}), 500
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


@admin_bp.route('/dashboard-stats', methods=['GET'])
@login_required
def get_dashboard_stats():
    conn = get_db_connection()
    if not conn: return jsonify({"message": "Database connection failed"}), 500

    try:
        cursor = conn.cursor(dictionary=True)

        params = ()
        interviews_conditions = []
        jobs_conditions = []

        if current_user.role != 'super_admin':
            params = (current_user.company_id,)
            interviews_conditions.append("i.company_id = %s")
            jobs_conditions.append("j.company_id = %s")  # Note the alias 'j' for jobs table

        interviews_where = "WHERE " + " AND ".join(interviews_conditions) if interviews_conditions else ""
        jobs_where = "WHERE " + " AND ".join(jobs_conditions) if jobs_conditions else ""

        # --- Key Metrics ---
        cursor.execute(f"SELECT COUNT(*) as count FROM interviews i {interviews_where}", params)
        total_interviews = cursor.fetchone()['count']

        avg_score_conditions = ["score IS NOT NULL"] + interviews_conditions
        avg_score_query = "SELECT AVG(score) as avg_score FROM interviews i WHERE " + " AND ".join(avg_score_conditions)
        cursor.execute(avg_score_query, params)
        average_score = cursor.fetchone()['avg_score'] or 0

        open_pos_conditions = ["status = 'Open'"] + jobs_conditions
        open_pos_query = "SELECT COUNT(*) as count FROM jobs j WHERE " + " AND ".join(open_pos_conditions)
        cursor.execute(open_pos_query, params)
        open_positions = cursor.fetchone()['count']

        pending_rev_conditions = ["status = 'Pending Review'"] + interviews_conditions
        pending_rev_query = "SELECT COUNT(*) as count FROM interviews i WHERE " + " AND ".join(pending_rev_conditions)
        cursor.execute(pending_rev_query, params)
        pending_review = cursor.fetchone()['count']

        # --- Recent Activity (Fix for ambiguity) ---
        recent_activity_query = f"""
            SELECT i.id, c.name as candidate_name, j.title as job_title, i.updated_at
            FROM interviews i
            JOIN candidates c ON i.candidate_id = c.id
            JOIN jobs j ON i.job_id = j.id
            {interviews_where}
            ORDER BY i.updated_at DESC
            LIMIT 5
        """
        cursor.execute(recent_activity_query, params)
        recent_activity = cursor.fetchall()

        stats = {
            "key_metrics": {
                "total_interviews": total_interviews,
                "average_score": round(average_score, 1),
                "open_positions": open_positions,
                "pending_review": pending_review
            },
            # Charts would need similar filtering logic
            "charts": {},
            "recent_activity": [
                {
                    "interview_id": row['id'],
                    "text": f"Interview with {row['candidate_name']} for {row['job_title']} completed.",
                    "timestamp": row['updated_at'].isoformat()
                } for row in recent_activity
            ]
        }
        return jsonify(stats)

    except Exception as e:
        current_app.logger.error(f"Error fetching dashboard stats: {e}\n{traceback.format_exc()}")
        return jsonify({"message": "An internal error occurred"}), 500
    finally:
        if conn and conn.is_connected(): conn.close()


# --- Super Admin User Management ---
@admin_bp.route('/users', methods=['GET'])
@super_admin_required
def get_all_users():
    conn = get_db_connection()
    if not conn: return jsonify({"message": "Database connection failed"}), 500
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, name, email, role, interview_limit, is_verified, company_id FROM admins WHERE role != 'super_admin'")
        users = cursor.fetchall()
        return jsonify(users), 200
    finally:
        if conn.is_connected(): conn.close()


@admin_bp.route('/users/<int:user_id>/limit', methods=['PUT'])
@super_admin_required
def update_user_limit(user_id):
    data = request.json
    new_limit = data.get('interview_limit')
    if new_limit is None or not isinstance(new_limit, int) or new_limit < 0:
        return jsonify({"message": "Invalid limit provided."}), 400

    conn = get_db_connection()
    if not conn: return jsonify({"message": "Database connection failed"}), 500
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE admins SET interview_limit = %s WHERE id = %s", (new_limit, user_id))
        conn.commit()
        return jsonify({"message": "User's interview limit updated successfully."}), 200
    except Exception as e:
        current_app.logger.error(f"Error updating user limit: {e}")
        if conn.is_connected(): conn.rollback()
        return jsonify({"message": "Failed to update limit."}), 500
    finally:
        if conn.is_connected(): conn.close()
