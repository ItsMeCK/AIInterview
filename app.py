from flask import Flask, jsonify, request, send_from_directory, abort, Response
from flask_cors import CORS
import mysql.connector
import datetime
import uuid
import os
import json

# --- Langchain and OpenAI Imports ---
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate, HumanMessagePromptTemplate, SystemMessagePromptTemplate
from langchain.schema import HumanMessage, SystemMessage
from openai import OpenAI  # Import the OpenAI client directly for TTS

# --- Flask App Initialization ---
app = Flask(__name__)
CORS(app)

# --- Configuration ---
DB_CONFIG = {
    'host': 'localhost',
    'user': 'your_mysql_user',
    'password': 'your_mysql_password',
    'database': 'ai_interview_portal_db'
}

# IMPORTANT: Use environment variables for sensitive keys in production
# Example: OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if OPENAI_API_KEY == "YOUR_OPENAI_API_KEY":
    print("WARNING: OpenAI API Key is not set. AI features will not work.")

# Initialize OpenAI client for TTS
try:
    openai_client = OpenAI(api_key=OPENAI_API_KEY)
except Exception as e:
    openai_client = None
    print(f"Could not initialize OpenAI client: {e}")

# --- File Upload Configuration ---
UPLOAD_FOLDER = 'uploads'
RESUME_FOLDER = os.path.join(UPLOAD_FOLDER, 'resumes')
SCREENSHOT_FOLDER = os.path.join(UPLOAD_FOLDER, 'screenshots')
SYSTEM_FOLDER = os.path.join(UPLOAD_FOLDER, 'system')

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['RESUME_FOLDER'] = RESUME_FOLDER
app.config['SCREENSHOT_FOLDER'] = SCREENSHOT_FOLDER
app.config['SYSTEM_FOLDER'] = SYSTEM_FOLDER

ALLOWED_RESUME_EXTENSIONS = {'pdf', 'docx', 'doc', 'txt'}

if not os.path.exists(UPLOAD_FOLDER): os.makedirs(UPLOAD_FOLDER)
if not os.path.exists(RESUME_FOLDER): os.makedirs(RESUME_FOLDER)
if not os.path.exists(SCREENSHOT_FOLDER): os.makedirs(SCREENSHOT_FOLDER)
if not os.path.exists(SYSTEM_FOLDER): os.makedirs(SYSTEM_FOLDER)


def allowed_file(filename, allowed_extensions_set):
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in allowed_extensions_set


# --- Database Connection Helper & Other Helpers ---
def get_db_connection():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except mysql.connector.Error as err:
        print(f"Error connecting to MySQL: {err}")
        return None


def generate_id(prefix="item_"): return prefix + str(uuid.uuid4())


def serialize_datetime_in_obj(obj):
    if isinstance(obj, dict): return {k: serialize_datetime_in_obj(v) for k, v in obj.items()}
    if isinstance(obj, list): return [serialize_datetime_in_obj(elem) for elem in obj]
    if isinstance(obj, datetime.datetime): return obj.isoformat()
    return obj


def parse_resume_from_file(resume_filepath_db):
    if not resume_filepath_db: return "No resume provided."
    filename = os.path.basename(resume_filepath_db)
    # In a real app, this would use libraries like PyPDF2 or python-docx to extract text.
    return f"Resume content from '{filename}' would be extracted here. For this demo, we are using this placeholder text to represent the candidate's skills and experiences mentioned in their resume. Key skills include Python, Flask, and project management."


def get_llm():
    if not openai_client or OPENAI_API_KEY == "YOUR_OPENAI_API_KEY": return None
    return ChatOpenAI(temperature=0.6, openai_api_key=OPENAI_API_KEY, model_name="gpt-3.5-turbo")


# --- Admin API Endpoints ---
@app.route('/api/admin/jobs', methods=['GET', 'POST'])
def manage_jobs():
    conn = get_db_connection()
    if not conn: return jsonify({"message": "Database connection failed"}), 500

    # TODO: Get company_id/admin_user_id from auth token/session
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
            query = "INSERT INTO jobs (id, title, department, description, status, created_at, created_by, company_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)"
            cursor.execute(query, (new_job_id, data['title'], data['department'], data['description'],
                                   data.get('status', 'Open'), datetime.datetime.utcnow(), placeholder_admin_user_id,
                                   placeholder_company_id))
            conn.commit()
            cursor.execute("SELECT * FROM jobs WHERE id = %s", (new_job_id,))
            return jsonify(serialize_datetime_in_obj(cursor.fetchone())), 201
    except mysql.connector.Error as err:
        if conn.is_connected(): conn.rollback()
        return jsonify({"message": f"DB error: {err.msg}"}), 500
    finally:
        if conn.is_connected(): cursor.close(); conn.close()


@app.route('/api/admin/jobs/<job_id>', methods=['GET', 'PUT', 'DELETE'])
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
            fields_to_update, values, allowed = [], [], ['title', 'department', 'description', 'status']
            for field in allowed:
                if field in data:
                    fields_to_update.append(f"{field} = %s");
                    values.append(data[field])
            if not fields_to_update: return jsonify({"message": "No valid fields to update"}), 400
            values.append(datetime.datetime.utcnow());
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
    except mysql.connector.Error as err:
        if request.method in ['PUT', 'DELETE'] and conn.is_connected(): conn.rollback()
        return jsonify({"message": f"DB error: {err.msg}"}), 500
    finally:
        if conn.is_connected(): cursor.close(); conn.close()


@app.route('/api/admin/interviews', methods=['GET'])
def get_admin_interviews():
    conn = get_db_connection()
    if not conn: return jsonify({"message": "Database connection failed"}), 500
    job_id_filter, status_filter = request.args.get('job_id'), request.args.get('status')
    try:
        cursor = conn.cursor(dictionary=True)
        query = "SELECT i.*, j.title as job_title, c.name as candidate_name FROM interviews i JOIN jobs j ON i.job_id = j.id LEFT JOIN candidates c ON i.candidate_id = c.id"
        conditions, params = [], []
        if job_id_filter: conditions.append("i.job_id = %s"); params.append(job_id_filter)
        if status_filter: conditions.append("i.status = %s"); params.append(status_filter)
        if conditions: query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY i.created_at DESC"
        cursor.execute(query, tuple(params))
        interviews = cursor.fetchall()
        for interview in interviews:
            for key in ['transcript_json', 'ai_questions_json', 'screenshot_paths_json']:
                if interview.get(key) and isinstance(interview[key], str):
                    try:
                        interview[key] = json.loads(interview[key])
                    except json.JSONDecodeError:
                        interview[key] = None
        return jsonify(serialize_datetime_in_obj(interviews)), 200
    except mysql.connector.Error as err:
        return jsonify({"message": f"DB error: {err.msg}"}), 500
    finally:
        if conn.is_connected(): cursor.close(); conn.close()


@app.route('/api/admin/interviews/<interview_id>', methods=['GET'])
def get_admin_interview_detail(interview_id):
    conn = get_db_connection()
    if not conn: return jsonify({"message": "Database connection failed"}), 500
    try:
        cursor = conn.cursor(dictionary=True)
        query = "SELECT i.*, j.title as job_title, j.department as job_department, c.name as candidate_name, c.email as candidate_email FROM interviews i LEFT JOIN jobs j ON i.job_id = j.id LEFT JOIN candidates c ON i.candidate_id = c.id WHERE i.id = %s"
        cursor.execute(query, (interview_id,))
        interview = cursor.fetchone()
        if not interview: return jsonify({"message": "Interview not found"}), 404
        for key in ['transcript_json', 'ai_questions_json', 'screenshot_paths_json']:
            if interview.get(key) and isinstance(interview[key], str):
                try:
                    interview[key] = json.loads(interview[key])
                except json.JSONDecodeError:
                    interview[key] = None
        interview['transcript'] = interview.get('transcript_json')
        interview['questions'] = interview.get('ai_questions_json')
        interview['screenshots'] = interview.get('screenshot_paths_json') or []
        return jsonify(serialize_datetime_in_obj(interview)), 200
    except mysql.connector.Error as err:
        return jsonify({"message": f"DB error: {err.msg}"}), 500
    finally:
        if conn.is_connected(): cursor.close(); conn.close()


@app.route('/api/admin/interviews/<interview_id>/score', methods=['POST'])
def score_interview(interview_id):
    conn = get_db_connection()
    if not conn: return jsonify({"message": "Database connection failed"}), 500
    data = request.json
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM interviews WHERE id = %s", (interview_id,))
        if not cursor.fetchone(): return jsonify({"message": "Interview not found"}), 404
        update_fields, params = ["status = %s", "updated_at = %s"], ["Reviewed", datetime.datetime.utcnow()]
        if data.get('score') is not None:
            score_int = int(data['score'])
            if not (0 <= score_int <= 100): raise ValueError("Score out of range")
            update_fields.append("score = %s");
            params.append(score_int)
        else:
            update_fields.append("score = %s"); params.append(None)
        if 'feedback' in data: update_fields.append("admin_feedback = %s"); params.append(data.get('feedback', ''))
        params.append(interview_id)
        query = f"UPDATE interviews SET {', '.join(update_fields)} WHERE id = %s"
        cursor.execute(query, tuple(params));
        conn.commit()
        query_details = "SELECT i.*, j.title as job_title, c.name as candidate_name FROM interviews i JOIN jobs j ON i.job_id = j.id LEFT JOIN candidates c ON i.candidate_id = c.id WHERE i.id = %s"
        cursor.execute(query_details, (interview_id,))
        updated_interview = cursor.fetchone()
        if updated_interview:
            for key in ['transcript_json', 'ai_questions_json', 'screenshot_paths_json']:
                if updated_interview.get(key) and isinstance(updated_interview[key], str):
                    try:
                        updated_interview[key] = json.loads(updated_interview[key])
                    except json.JSONDecodeError:
                        updated_interview[key] = None
            updated_interview['transcript'] = updated_interview.get('transcript_json')
            updated_interview['questions'] = updated_interview.get('ai_questions_json')
            updated_interview['screenshots'] = updated_interview.get('screenshot_paths_json') or []
        return jsonify(serialize_datetime_in_obj(updated_interview)), 200
    except (mysql.connector.Error, ValueError) as err:
        if conn.is_connected(): conn.rollback()
        return jsonify({"message": f"Operation failed: {str(err)}"}), 500
    finally:
        if conn.is_connected(): cursor.close(); conn.close()


@app.route('/api/admin/dashboard-summary', methods=['GET'])
def get_dashboard_summary():
    conn = get_db_connection()
    if not conn: return jsonify({"message": "Database connection failed"}), 500
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT COUNT(*) as count FROM jobs WHERE status = 'Open'")
        open_jobs = cursor.fetchone()['count']
        cursor.execute("SELECT SUM(applications_count) as total_apps FROM jobs")
        total_applications = (cursor.fetchone()['total_apps'] or 0)
        cursor.execute("SELECT COUNT(*) as count FROM interviews WHERE status = 'Scheduled'")
        interviews_scheduled = cursor.fetchone()['count']
        cursor.execute("SELECT COUNT(*) as count FROM interviews WHERE status = 'Pending Review'")
        pending_reviews = cursor.fetchone()['count']
        return jsonify({"open_positions": open_jobs, "total_applications": total_applications,
                        "interviews_scheduled": interviews_scheduled, "pending_reviews": pending_reviews}), 200
    except mysql.connector.Error as err:
        return jsonify({"message": f"DB error: {err.msg}"}), 500
    finally:
        if conn.is_connected(): cursor.close(); conn.close()


# --- Candidate Facing API Endpoints ---
@app.route('/api/interview/initiate/<invitation_link_guid>', methods=['GET'])
def get_interview_by_link(invitation_link_guid):
    conn = get_db_connection()
    if not conn: return jsonify({"message": "Database connection failed"}), 500
    try:
        cursor = conn.cursor(dictionary=True)
        query = "SELECT i.id as interview_id, i.status as interview_status, i.candidate_id, j.id as job_id, j.title as job_title, j.description as job_description, co.name as company_name FROM interviews i JOIN jobs j ON i.job_id = j.id LEFT JOIN companies co ON j.company_id = co.id WHERE i.invitation_link = %s"
        cursor.execute(query, (invitation_link_guid,))
        interview_data = cursor.fetchone()
        if not interview_data: return jsonify({"message": "Invalid or expired invitation link"}), 404
        allowed_statuses = ['Invited', 'Resume Submitted', 'In Progress']
        if interview_data['interview_status'] not in allowed_statuses:
            return jsonify(
                {"message": f"Interview cannot be accessed. Status: {interview_data['interview_status']}"}), 403
        return jsonify(serialize_datetime_in_obj(interview_data)), 200
    except mysql.connector.Error as err:
        return jsonify({"message": f"DB error: {err.msg}"}), 500
    finally:
        if conn.is_connected(): cursor.close(); conn.close()


@app.route('/api/interview/<interview_id>/submit-details', methods=['POST'])
def submit_candidate_details_and_resume(interview_id):
    conn = get_db_connection()
    if not conn: return jsonify({"message": "Database connection failed"}), 500
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, status, candidate_id FROM interviews WHERE id = %s", (interview_id,))
        interview = cursor.fetchone()
        if not interview: return jsonify({"message": "Interview not found"}), 404
        if interview['status'] != 'Invited':
            if interview['status'] == 'Resume Submitted' and interview['candidate_id']:
                return jsonify({"message": "Details already submitted.", "candidateId": interview['candidate_id']}), 200
            return jsonify({"message": f"Cannot submit details. Status: {interview['status']}"}), 403
        if not all(k in request.form for k in ['candidateName', 'candidateEmail']) or 'resumeFile' not in request.files:
            return jsonify({"message": "Missing required form fields."}), 400

        resume_file = request.files['resumeFile']
        if not allowed_file(resume_file.filename, ALLOWED_RESUME_EXTENSIONS):
            return jsonify({"message": "Invalid resume file type."}), 400

        secure_name = str(uuid.uuid4()) + os.path.splitext(resume_file.filename)[1]
        resume_save_path = os.path.join(app.config['RESUME_FOLDER'], secure_name)
        resume_file.save(resume_save_path)
        resume_filepath_db = f"/uploads/resumes/{secure_name}"

        candidate_id = interview.get('candidate_id') or generate_id("cand_")
        now_utc = datetime.datetime.utcnow()
        cursor.execute("SELECT id FROM candidates WHERE id = %s", (candidate_id,))
        if cursor.fetchone():
            cursor.execute("UPDATE candidates SET name=%s,email=%s,resume_filename=%s,updated_at=%s WHERE id=%s",
                           (request.form['candidateName'], request.form['candidateEmail'], resume_filepath_db, now_utc,
                            candidate_id))
        else:
            cursor.execute(
                "INSERT INTO candidates (id,name,email,resume_filename,created_at,updated_at) VALUES (%s,%s,%s,%s,%s,%s)",
                (candidate_id, request.form['candidateName'], request.form['candidateEmail'], resume_filepath_db,
                 now_utc, now_utc))
        cursor.execute("UPDATE interviews SET candidate_id=%s,status='Resume Submitted',updated_at=%s WHERE id=%s",
                       (candidate_id, now_utc, interview_id))
        conn.commit()
        return jsonify({"message": "Details submitted. Ready for interview.", "candidateId": candidate_id}), 200
    except Exception as e:
        if conn.is_connected(): conn.rollback()
        return jsonify({"message": f"An error occurred: {str(e)}"}), 500
    finally:
        if conn.is_connected(): cursor.close(); conn.close()


@app.route('/api/interview/<interview_id>/start', methods=['POST'])
def start_ai_interview(interview_id):
    llm = get_llm()
    if not llm: return jsonify({"message": "AI service not available. Cannot start."}), 503
    conn = get_db_connection()
    if not conn: return jsonify({"message": "Database connection failed"}), 500
    try:
        cursor = conn.cursor(dictionary=True)
        query = "SELECT i.status, j.description as jd, c.resume_filename FROM interviews i JOIN jobs j ON i.job_id = j.id LEFT JOIN candidates c ON i.candidate_id = c.id WHERE i.id = %s"
        cursor.execute(query, (interview_id,))
        interview_data = cursor.fetchone()
        if not interview_data: return jsonify({"message": "Interview not found"}), 404
        if interview_data['status'] != 'Resume Submitted':
            return jsonify({"message": f"Interview cannot be started. Status: {interview_data['status']}"}), 403

        resume_content = parse_resume_from_file(interview_data.get('resume_filename'))
        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(
                content="You are an AI interviewer. Ask one insightful, concise opening question (under 40 words) based on the provided job description and resume summary. Do not ask 'Tell me about yourself' unless it's highly contextualized."),
            HumanMessage(
                content="Job Description:\n{jd}\n\nCandidate Resume Summary:\n{resume}\n\nGenerate one opening question:")
        ])
        formatted_prompt = prompt.format_messages(jd=interview_data['jd'], resume=resume_content)
        ai_response = llm.invoke(formatted_prompt)
        first_question_text = ai_response.content.strip()

        transcript = [{"actor": "ai", "text": first_question_text, "timestamp": datetime.datetime.utcnow().isoformat()}]
        cursor.execute("UPDATE interviews SET status='In Progress', transcript_json=%s, updated_at=%s WHERE id=%s",
                       (json.dumps(transcript), datetime.datetime.utcnow(), interview_id))
        conn.commit()
        return jsonify({"message": "Interview started.", "question": {"text": first_question_text}}), 200
    except Exception as e:
        if conn.is_connected(): conn.rollback()
        return jsonify({"message": f"An error occurred: {str(e)}"}), 500
    finally:
        if conn.is_connected(): cursor.close(); conn.close()


@app.route('/api/interview/<interview_id>/next-question', methods=['POST'])
def process_candidate_response_and_get_next_question(interview_id):
    llm = get_llm()
    if not llm: return jsonify({"message": "AI service not available."}), 503
    data = request.json
    if not data.get('response_text'): return jsonify({"message": "Candidate response missing"}), 400
    conn = get_db_connection()
    if not conn: return jsonify({"message": "Database connection failed"}), 500
    try:
        cursor = conn.cursor(dictionary=True)
        query = "SELECT i.status, i.transcript_json, j.description as jd, c.resume_filename FROM interviews i JOIN jobs j ON i.job_id = j.id LEFT JOIN candidates c ON i.candidate_id = c.id WHERE i.id = %s"
        cursor.execute(query, (interview_id,))
        interview = cursor.fetchone()
        if not interview: return jsonify({"message": "Interview not found"}), 404
        if interview['status'] != 'In Progress': return jsonify(
            {"message": f"Interview not in progress. Status: {interview['status']}"}), 403

        transcript_str = interview.get('transcript_json', '[]')
        transcript = json.loads(transcript_str) if isinstance(transcript_str, str) else (transcript_str or [])
        transcript.append(
            {"actor": "candidate", "text": data['response_text'], "timestamp": datetime.datetime.utcnow().isoformat()})

        ai_questions_count = sum(1 for seg in transcript if seg['actor'] == 'ai')
        MAX_QUESTIONS = 5
        if ai_questions_count >= MAX_QUESTIONS:
            next_question_text, new_status = "Thank you. This concludes the interview.", 'Completed'
        else:
            resume_content = parse_resume_from_file(interview.get('resume_filename'))
            history = "\n".join([f"{entry['actor'].capitalize()}: {entry['text']}" for entry in transcript])
            prompt = ChatPromptTemplate.from_messages([
                SystemMessage(
                    content=f"You are an AI interviewer. You have the JD, resume, and conversation history. Generate a concise (under 40 words) follow-up question. This is question {ai_questions_count + 1} of {MAX_QUESTIONS}."),
                HumanMessage(
                    content="Job Description:\n{jd}\n\nResume Summary:\n{resume}\n\nConversation History:\n{history}\n\nGenerate one follow-up question:")
            ])
            formatted_prompt = prompt.format_messages(jd=interview['jd'], resume=resume_content, history=history)
            ai_response = llm.invoke(formatted_prompt)
            next_question_text, new_status = ai_response.content.strip(), 'In Progress'

        transcript.append(
            {"actor": "ai", "text": next_question_text, "timestamp": datetime.datetime.utcnow().isoformat()})
        cursor.execute("UPDATE interviews SET status=%s, transcript_json=%s, updated_at=%s WHERE id=%s",
                       (new_status, json.dumps(transcript), datetime.datetime.utcnow(), interview_id))
        conn.commit()
        return jsonify({"question": {"text": next_question_text}, "interview_status": new_status}), 200
    except Exception as e:
        if conn.is_connected(): conn.rollback()
        return jsonify({"message": f"An error occurred: {str(e)}"}), 500
    finally:
        if conn.is_connected(): cursor.close(); conn.close()


# --- NEW ENDPOINT for Text-to-Speech ---
@app.route('/api/interview/text-to-speech', methods=['POST'])
def text_to_speech():
    if not openai_client: return jsonify({"message": "AI service (TTS) not available."}), 503
    data = request.json
    text_to_speak = data.get('text')
    if not text_to_speak: return jsonify({"message": "No text provided for speech."}), 400
    try:
        response = openai_client.audio.speech.create(
            model="tts-1", voice="alloy", input=text_to_speak, response_format="mp3")

        def generate_audio_chunks():
            for chunk in response.iter_bytes(chunk_size=4096):
                yield chunk

        return Response(generate_audio_chunks(), mimetype="audio/mpeg")
    except Exception as e:
        print(f"OpenAI TTS API call failed: {e}")
        return jsonify({"message": "Failed to generate audio from text."}), 500


# --- File Serving Endpoint ---
@app.route('/uploads/<path:folder>/<path:filename>')
def serve_uploaded_file(folder, filename):
    if '..' in folder or '..' in filename: abort(404)
    safe_folder_path = os.path.abspath(os.path.join(app.config['UPLOAD_FOLDER'], folder))
    if not safe_folder_path.startswith(os.path.abspath(app.config['UPLOAD_FOLDER'])): abort(403)
    try:
        return send_from_directory(safe_folder_path, filename)
    except FileNotFoundError:
        abort(404)


if __name__ == '__main__':
    app.run(debug=True, port=5001)

