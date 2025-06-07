from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import mysql.connector
import datetime
import uuid
import os

# --- Flask App Initialization ---
app = Flask(__name__)
CORS(app) # Enable CORS for all routes

# --- Database Configuration ---
# IMPORTANT: Replace with your actual MySQL connection details
DB_CONFIG = {
    'host': '127.0.0.1',
    'user': 'your_mysql_user',       # Replace with your MySQL username
    'password': 'your_mysql_password', # Replace with your MySQL password
    'database': 'ai_interview_portal_db' # Replace with your database name
}

# --- File Upload Configuration ---
UPLOAD_FOLDER = 'uploads' # Folder to store uploaded files (e.g., screenshots, resumes)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Database Connection Helper ---
def get_db_connection():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except mysql.connector.Error as err:
        print(f"Error connecting to MySQL: {err}")
        # In a production app, you might want to handle this more gracefully
        # or raise the exception to be caught by a global error handler.
        return None

# --- Helper Functions ---
def generate_id(prefix="item_"):
    return prefix + str(uuid.uuid4())

# --- API Endpoints ---

# --- Job Management ---
@app.route('/api/admin/jobs', methods=['GET', 'POST'])
def manage_jobs():
    conn = get_db_connection()
    if not conn:
        return jsonify({"message": "Database connection failed"}), 500
    cursor = conn.cursor(dictionary=True) # dictionary=True returns rows as dicts

    # TODO: Add authentication and authorization (e.g., based on company_id from JWT)
    # For now, we assume a single company or admin context.
    # admin_user_id = "admin_user_123" # Get from auth token
    # company_id = "company_innovatech" # Get from auth token or user profile

    if request.method == 'GET':
        try:
            # Assuming a 'company_id' field in your jobs table if multi-tenant
            # cursor.execute("SELECT * FROM jobs WHERE company_id = %s ORDER BY created_at DESC", (company_id,))
            cursor.execute("SELECT * FROM jobs ORDER BY created_at DESC")
            jobs = cursor.fetchall()
            return jsonify(jobs), 200
        except mysql.connector.Error as err:
            print(f"MySQL Error (GET /jobs): {err}")
            return jsonify({"message": "Failed to retrieve jobs"}), 500
        finally:
            cursor.close()
            conn.close()

    if request.method == 'POST':
        data = request.json
        if not data or not all(k in data for k in ['title', 'department', 'description']):
            return jsonify({"message": "Missing required fields: title, department, description"}), 400

        new_job_id = generate_id("job_")
        try:
            query = """
                INSERT INTO jobs (id, title, department, description, status, applications_count, created_at, created_by, company_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            # Replace 'admin_user_123' and 'company_innovatech' with actual authenticated user/company info
            created_at_ts = datetime.datetime.utcnow()
            cursor.execute(query, (
                new_job_id, data['title'], data['department'], data['description'],
                data.get('status', 'Open'), 0, created_at_ts,
                data.get('created_by', 'admin_user_123'), # Placeholder
                data.get('company_id', 'company_innovatech') # Placeholder
            ))
            conn.commit()
            # Fetch the newly created job to return it
            cursor.execute("SELECT * FROM jobs WHERE id = %s", (new_job_id,))
            new_job = cursor.fetchone()
            return jsonify(new_job), 201
        except mysql.connector.Error as err:
            print(f"MySQL Error (POST /jobs): {err}")
            conn.rollback()
            return jsonify({"message": "Failed to create job"}), 500
        finally:
            cursor.close()
            conn.close()

@app.route('/api/admin/jobs/<job_id>', methods=['GET', 'PUT', 'DELETE'])
def manage_job_detail(job_id):
    conn = get_db_connection()
    if not conn:
        return jsonify({"message": "Database connection failed"}), 500
    cursor = conn.cursor(dictionary=True)

    # TODO: Authentication and ensure job belongs to admin's company

    if request.method == 'GET':
        try:
            cursor.execute("SELECT * FROM jobs WHERE id = %s", (job_id,))
            job = cursor.fetchone()
            if job:
                return jsonify(job), 200
            else:
                return jsonify({"message": "Job not found"}), 404
        except mysql.connector.Error as err:
            print(f"MySQL Error (GET /jobs/{job_id}): {err}")
            return jsonify({"message": "Failed to retrieve job details"}), 500
        finally:
            cursor.close()
            conn.close()

    if request.method == 'PUT':
        data = request.json
        if not data:
            return jsonify({"message": "No data provided for update"}), 400

        fields_to_update = []
        values = []
        allowed_fields = ['title', 'department', 'description', 'status'] # Define updatable fields

        for field in allowed_fields:
            if field in data:
                fields_to_update.append(f"{field} = %s")
                values.append(data[field])

        if not fields_to_update:
            return jsonify({"message": "No valid fields to update"}), 400

        values.append(job_id) # For the WHERE clause
        query = f"UPDATE jobs SET {', '.join(fields_to_update)} WHERE id = %s"

        try:
            cursor.execute(query, tuple(values))
            conn.commit()
            if cursor.rowcount == 0:
                return jsonify({"message": "Job not found or no changes made"}), 404

            cursor.execute("SELECT * FROM jobs WHERE id = %s", (job_id,)) # Fetch updated job
            updated_job = cursor.fetchone()
            return jsonify(updated_job), 200
        except mysql.connector.Error as err:
            print(f"MySQL Error (PUT /jobs/{job_id}): {err}")
            conn.rollback()
            return jsonify({"message": "Failed to update job"}), 500
        finally:
            cursor.close()
            conn.close()

    if request.method == 'DELETE':
        try:
            # Optional: Check for associated interviews before deleting or handle cascading deletes in DB
            cursor.execute("DELETE FROM jobs WHERE id = %s", (job_id,))
            conn.commit()
            if cursor.rowcount == 0:
                return jsonify({"message": "Job not found"}), 404
            return jsonify({"message": "Job deleted successfully"}), 200
        except mysql.connector.Error as err:
            print(f"MySQL Error (DELETE /jobs/{job_id}): {err}")
            conn.rollback()
            return jsonify({"message": "Failed to delete job"}), 500
        finally:
            cursor.close()
            conn.close()


# --- Interview Management (Read-only for now from Admin perspective, more to come) ---
@app.route('/api/admin/interviews', methods=['GET'])
def get_admin_interviews():
    conn = get_db_connection()
    if not conn:
        return jsonify({"message": "Database connection failed"}), 500
    cursor = conn.cursor(dictionary=True)

    # TODO: Authentication and filter by company_id
    # company_id = "company_innovatech" # from auth
    job_id_filter = request.args.get('job_id')
    status_filter = request.args.get('status')

    query = "SELECT i.*, j.title as job_title FROM interviews i JOIN jobs j ON i.job_id = j.id"
    conditions = []
    params = []

    # if company_id:
    #     conditions.append("i.company_id = %s")
    #     params.append(company_id)
    if job_id_filter:
        conditions.append("i.job_id = %s")
        params.append(job_id_filter)
    if status_filter:
        conditions.append("i.status = %s")
        params.append(status_filter)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY interview_date DESC"

    try:
        cursor.execute(query, tuple(params))
        interviews = cursor.fetchall()
        # Convert datetime objects to ISO format strings for JSON serialization
        for interview in interviews:
            if isinstance(interview.get('interview_date'), datetime.datetime):
                interview['interview_date'] = interview['interview_date'].isoformat()
            if isinstance(interview.get('created_at'), datetime.datetime):
                interview['created_at'] = interview['created_at'].isoformat()
            # Handle other datetime fields if any
        return jsonify(interviews), 200
    except mysql.connector.Error as err:
        print(f"MySQL Error (GET /interviews): {err}")
        return jsonify({"message": "Failed to retrieve interviews"}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/admin/interviews/<interview_id>', methods=['GET'])
def get_admin_interview_detail(interview_id):
    conn = get_db_connection()
    if not conn:
        return jsonify({"message": "Database connection failed"}), 500
    cursor = conn.cursor(dictionary=True)

    # TODO: Authentication and ensure interview belongs to admin's company
    try:
        # Query to get interview details, potentially join with jobs and candidates
        query = """
            SELECT
                i.*,
                j.title as job_title, j.department as job_department,
                c.name as candidate_name, c.email as candidate_email
            FROM interviews i
            LEFT JOIN jobs j ON i.job_id = j.id
            LEFT JOIN candidates c ON i.candidate_id = c.id
            WHERE i.id = %s
        """
        cursor.execute(query, (interview_id,))
        interview = cursor.fetchone()

        if not interview:
            return jsonify({"message": "Interview not found"}), 404

        # Convert datetime objects to ISO format strings
        for key, value in interview.items():
            if isinstance(value, datetime.datetime):
                interview[key] = value.isoformat()

        # Placeholder for transcript, questions, summary, screenshots
        # These would typically be fetched from related tables or JSON fields
        interview['transcript'] = "AI: Hello!\nCandidate: Hi there..." # Placeholder
        interview['questions'] = [{"q": "Q1 from DB?", "a": "A1 from DB?"}] # Placeholder
        interview['summary'] = "Summary from DB..." # Placeholder
        # Screenshots would be a list of URLs pointing to files served by /uploads endpoint
        interview['screenshots'] = [
            f"/uploads/screenshot_placeholder1.jpg", # Example
            f"/uploads/screenshot_placeholder2.jpg"  # Example
        ]

        return jsonify(interview), 200
    except mysql.connector.Error as err:
        print(f"MySQL Error (GET /interviews/{interview_id}): {err}")
        return jsonify({"message": "Failed to retrieve interview details"}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/admin/interviews/<interview_id>/score', methods=['POST'])
def score_interview(interview_id):
    conn = get_db_connection()
    if not conn:
        return jsonify({"message": "Database connection failed"}), 500
    cursor = conn.cursor(dictionary=True)

    data = request.json
    score_val = data.get('score')
    admin_feedback_val = data.get('feedback')
    new_status = "Reviewed" # Or based on workflow

    if score_val is None and admin_feedback_val is None:
        return jsonify({"message": "No score or feedback provided"}), 400

    update_fields = []
    params = []
    if score_val is not None:
        try:
            update_fields.append("score = %s")
            params.append(int(score_val))
        except ValueError:
            return jsonify({"message": "Invalid score format, must be an integer"}), 400

    if admin_feedback_val is not None:
        update_fields.append("admin_feedback = %s")
        params.append(admin_feedback_val)

    update_fields.append("status = %s")
    params.append(new_status)

    params.append(interview_id) # For WHERE clause

    query = f"UPDATE interviews SET {', '.join(update_fields)} WHERE id = %s"

    try:
        cursor.execute(query, tuple(params))
        conn.commit()
        if cursor.rowcount == 0:
            return jsonify({"message": "Interview not found or no update made"}), 404

        cursor.execute("SELECT * FROM interviews WHERE id = %s", (interview_id,)) # Fetch updated
        updated_interview = cursor.fetchone()
        if updated_interview and isinstance(updated_interview.get('interview_date'), datetime.datetime):
             updated_interview['interview_date'] = updated_interview['interview_date'].isoformat()
        return jsonify(updated_interview), 200
    except mysql.connector.Error as err:
        print(f"MySQL Error (POST /interviews/{interview_id}/score): {err}")
        conn.rollback()
        return jsonify({"message": "Failed to update interview score/feedback"}), 500
    finally:
        cursor.close()
        conn.close()


# --- File Serving Endpoint ---
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    """Serves files from the UPLOAD_FOLDER."""
    # TODO: Add security checks if these files should be protected
    try:
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
    except FileNotFoundError:
        return jsonify({"message": "File not found"}), 404


# --- Placeholder for other routes (Candidate, AI interaction, etc.) ---
# These will be developed in subsequent steps.

@app.route('/api/admin/dashboard-summary', methods=['GET'])
def get_dashboard_summary():
    conn = get_db_connection()
    if not conn:
        return jsonify({"message": "Database connection failed"}), 500
    cursor = conn.cursor(dictionary=True)
    # company_id = "company_innovatech" # Get from auth

    try:
        # Query for open positions
        # cursor.execute("SELECT COUNT(*) as count FROM jobs WHERE status = 'Open' AND company_id = %s", (company_id,))
        cursor.execute("SELECT COUNT(*) as count FROM jobs WHERE status = 'Open'")
        open_jobs = cursor.fetchone()['count']

        # Query for total applications (assuming applications_count is on jobs table)
        # cursor.execute("SELECT SUM(applications_count) as total_apps FROM jobs WHERE company_id = %s", (company_id,))
        cursor.execute("SELECT SUM(applications_count) as total_apps FROM jobs")
        total_applications = cursor.fetchone()['total_apps'] or 0

        # Query for interviews scheduled
        # cursor.execute("SELECT COUNT(*) as count FROM interviews WHERE status = 'Scheduled' AND company_id = %s", (company_id,))
        cursor.execute("SELECT COUNT(*) as count FROM interviews WHERE status = 'Scheduled'")
        interviews_scheduled = cursor.fetchone()['count']

        # Query for pending reviews
        # cursor.execute("SELECT COUNT(*) as count FROM interviews WHERE status = 'Pending Review' AND company_id = %s", (company_id,))
        cursor.execute("SELECT COUNT(*) as count FROM interviews WHERE status = 'Pending Review'")
        pending_reviews = cursor.fetchone()['count']

        return jsonify({
            "open_positions": open_jobs,
            "total_applications": total_applications,
            "interviews_scheduled": interviews_scheduled,
            "pending_reviews": pending_reviews
        }), 200
    except mysql.connector.Error as err:
        print(f"MySQL Error (GET /dashboard-summary): {err}")
        return jsonify({"message": "Failed to retrieve dashboard summary"}), 500
    finally:
        cursor.close()
        conn.close()


if __name__ == '__main__':
    # Ensure the UPLOAD_FOLDER exists
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    # For development, run with debug=True. For production, use a WSGI server.
    app.run(debug=True, port=5001)

