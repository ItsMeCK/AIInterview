from flask import Blueprint, jsonify, request
from app.services.db_services import get_db_connection, serialize_datetime_in_obj, generate_id
from flask import current_app
import datetime
import traceback
import json

admin_bp = Blueprint('admin_bp', __name__)


@admin_bp.route('/jobs', methods=['GET', 'POST'])
def manage_jobs():
    conn = get_db_connection()
    if not conn: return jsonify({"message": "Database connection failed"}), 500

    # In a real app, these would come from an authentication system
    placeholder_company_id = "company_innovatech"
    placeholder_admin_user_id = "admin_user_123"

    try:
        cursor = conn.cursor(dictionary=True)
        if request.method == 'GET':
            cursor.execute("SELECT * FROM jobs ORDER BY created_at DESC")
            return jsonify(serialize_datetime_in_obj(cursor.fetchall())), 200

        if request.method == 'POST':
            data = request.json
            if not data or not all(k in data for k in ['title', 'department', 'description']):
                return jsonify({"message": "Missing required fields"}), 400

            new_job_id = generate_id("job_")
            query = """
                INSERT INTO jobs (id, title, department, description, status, created_at, created_by, company_id, number_of_questions, must_ask_topics) 
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """
            cursor.execute(query, (
                new_job_id, data['title'], data['department'], data['description'],
                data.get('status', 'Open'), datetime.datetime.utcnow(),
                placeholder_admin_user_id, placeholder_company_id,
                data.get('number_of_questions', 5), data.get('must_ask_topics')
            ))
            conn.commit()

            cursor.execute("SELECT * FROM jobs WHERE id = %s", (new_job_id,))
            return jsonify(serialize_datetime_in_obj(cursor.fetchone())), 201

    except Exception as err:
        current_app.logger.error(f"DB error in manage_jobs: {err}\n{traceback.format_exc()}")
        if conn.is_connected(): conn.rollback()
        return jsonify({"message": "An unexpected error occurred"}), 500
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


@admin_bp.route('/jobs/<job_id>', methods=['GET', 'PUT', 'DELETE'])
def manage_job_detail(job_id):
    conn = get_db_connection()
    if not conn: return jsonify({"message": "Database connection failed"}), 500
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM jobs WHERE id = %s", (job_id,))
        job = cursor.fetchone()
        if not job: return jsonify({"message": "Job not found"}), 404

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
            query = f"UPDATE jobs SET {', '.join(fields_to_update)}, updated_at = %s WHERE id = %s"
            cursor.execute(query, tuple(values));
            conn.commit()

            cursor.execute("SELECT * FROM jobs WHERE id = %s", (job_id,))
            return jsonify(serialize_datetime_in_obj(cursor.fetchone())), 200

        if request.method == 'DELETE':
            cursor.execute("DELETE FROM jobs WHERE id = %s", (job_id,))
            conn.commit()
            if cursor.rowcount == 0: return jsonify({"message": "Job not found"}), 404
            return jsonify({"message": "Job deleted successfully"}), 200

    except Exception as err:
        current_app.logger.error(f"DB error in manage_job_detail for {job_id}: {err}\n{traceback.format_exc()}")
        if request.method in ['PUT', 'DELETE'] and conn.is_connected(): conn.rollback()
        return jsonify({"message": "An unexpected error occurred"}), 500
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


@admin_bp.route('/interviews', methods=['GET'])
def get_admin_interviews():
    conn = get_db_connection()
    if not conn: return jsonify({"message": "Database connection failed"}), 500

    job_id_filter = request.args.get('job_id')
    status_filter = request.args.get('status')
    limit = request.args.get('limit', type=int)
    offset = request.args.get('offset', type=int)
    sort_by = request.args.get('sort_by', 'score')
    sort_order = request.args.get('sort_order', 'desc')
    search_query = request.args.get('search', '')

    allowed_sort_columns = ['score', 'interview_date', 'status']
    if sort_by not in allowed_sort_columns:
        sort_by = 'score'
    if sort_order.lower() not in ['asc', 'desc']:
        sort_order = 'desc'

    try:
        cursor = conn.cursor(dictionary=True)
        base_query = "FROM interviews i JOIN jobs j ON i.job_id = j.id LEFT JOIN candidates c ON i.candidate_id = c.id"
        conditions = []
        params = []

        if job_id_filter:
            conditions.append("i.job_id = %s")
            params.append(job_id_filter)
        if status_filter:
            conditions.append("i.status = %s")
            params.append(status_filter)
        if search_query:
            conditions.append("c.name LIKE %s")
            params.append(f"%{search_query}%")

        where_clause = ""
        if conditions:
            where_clause = " WHERE " + " AND ".join(conditions)

        is_paginated_request = limit is not None and offset is not None

        total_records = 0
        if is_paginated_request:
            count_query = f"SELECT COUNT(i.id) as total {base_query}{where_clause}"
            cursor.execute(count_query, tuple(params))
            total_records = cursor.fetchone()['total']

        data_query_builder = [
            f"SELECT i.*, j.title as job_title, c.name as candidate_name, c.email as candidate_email {base_query}{where_clause}",
            f"ORDER BY {sort_by} {sort_order}"
        ]

        final_params = list(params)
        if is_paginated_request:
            data_query_builder.append("LIMIT %s OFFSET %s")
            final_params.extend([limit, offset])

        data_query = " ".join(data_query_builder)
        cursor.execute(data_query, tuple(final_params))
        interviews = cursor.fetchall()

        for interview in interviews:
            for key in ['transcript_json', 'ai_questions_json', 'screenshot_paths_json', 'detailed_scorecard_json']:
                if interview.get(key) and isinstance(interview[key], str):
                    try:
                        interview[key] = json.loads(interview[key])
                    except json.JSONDecodeError:
                        interview[key] = None

        if is_paginated_request:
            return jsonify({"total": total_records, "interviews": serialize_datetime_in_obj(interviews)}), 200
        else:
            return jsonify(serialize_datetime_in_obj(interviews)), 200
    except Exception as err:
        current_app.logger.error(f"DB error in get_admin_interviews: {err}\n{traceback.format_exc()}")
        return jsonify({"message": "An unexpected error occurred"}), 500
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


@admin_bp.route('/interviews/<interview_id>', methods=['GET'])
def get_admin_interview_detail(interview_id):
    conn = get_db_connection()
    if not conn: return jsonify({"message": "Database connection failed"}), 500
    try:
        cursor = conn.cursor(dictionary=True)
        query = "SELECT i.*, j.title as job_title, j.department as job_department, c.name as candidate_name, c.email as candidate_email FROM interviews i LEFT JOIN jobs j ON i.job_id = j.id LEFT JOIN candidates c ON i.candidate_id = c.id WHERE i.id = %s"
        cursor.execute(query, (interview_id,))
        interview = cursor.fetchone()
        if not interview: return jsonify({"message": "Interview not found"}), 404

        # This is the corrected section to parse all JSON fields
        for key in ['transcript_json', 'ai_questions_json', 'screenshot_paths_json', 'detailed_scorecard_json']:
            if interview.get(key) and isinstance(interview[key], str):
                try:
                    interview[key] = json.loads(interview[key])
                except json.JSONDecodeError:
                    interview[key] = None

        # For easier frontend access, we can alias these
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


@admin_bp.route('/interviews/<interview_id>/score', methods=['POST'])
def score_interview(interview_id):
    conn = get_db_connection()
    if not conn: return jsonify({"message": "Database connection failed"}), 500
    data = request.json
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM interviews WHERE id = %s", (interview_id,))
        if not cursor.fetchone(): return jsonify({"message": "Interview not found"}), 404

        update_fields = ["status = %s", "updated_at = %s"]
        params = ["Reviewed", datetime.datetime.utcnow()]

        if data.get('score') is not None:
            update_fields.append("score = %s")
            params.append(int(data['score']))

        if 'feedback' in data:
            update_fields.append("admin_feedback = %s")
            params.append(data.get('feedback', ''))

        params.append(interview_id)
        query = f"UPDATE interviews SET {', '.join(update_fields)} WHERE id = %s"
        cursor.execute(query, tuple(params));
        conn.commit()

        cursor.execute("SELECT * FROM interviews WHERE id = %s", (interview_id,))
        updated_interview = cursor.fetchone()

        return jsonify(serialize_datetime_in_obj(updated_interview)), 200
    except Exception as err:
        current_app.logger.error(f"Error in score_interview for {interview_id}: {err}\n{traceback.format_exc()}")
        if conn.is_connected(): conn.rollback()
        return jsonify({"message": "An unexpected error occurred"}), 500
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


@admin_bp.route('/dashboard-summary', methods=['GET'])
def get_dashboard_summary():
    conn = get_db_connection()
    if not conn: return jsonify({"message": "Database connection failed"}), 500
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT COUNT(*) as count FROM jobs WHERE status = 'Open'")
        open_jobs = cursor.fetchone()['count']
        cursor.execute("SELECT COUNT(*) as total_apps FROM interviews")
        total_applications = cursor.fetchone()['total_apps']
        cursor.execute("SELECT COUNT(*) as count FROM interviews WHERE status = 'Scheduled'")
        interviews_scheduled = cursor.fetchone()['count']
        cursor.execute("SELECT COUNT(*) as count FROM interviews WHERE status = 'Pending Review'")
        pending_reviews = cursor.fetchone()['count']
        return jsonify({"open_positions": open_jobs, "total_applications": total_applications,
                        "interviews_scheduled": interviews_scheduled, "pending_reviews": pending_reviews}), 200
    except Exception as err:
        current_app.logger.error(f"DB error in get_dashboard_summary: {err}\n{traceback.format_exc()}")
        return jsonify({"message": "An unexpected error occurred"}), 500
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()
