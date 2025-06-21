from flask import Flask, jsonify, request, send_from_directory, abort, Response
from flask_cors import CORS
import mysql.connector
import datetime
import uuid
import os
import json
import logging
import base64
import traceback

# --- Langchain and OpenAI Imports ---
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.schema.messages import HumanMessage, SystemMessage

from openai import OpenAI  # Import the OpenAI client directly for TTS

# --- Flask App Initialization ---
app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)

# --- Configuration ---
DB_CONFIG = {
    'host': 'localhost',
    'user': 'your_mysql_user',
    'password': 'your_mysql_password',
    'database': 'ai_interview_portal_db'
}

# IMPORTANT: Use environment variables for sensitive keys in production
if OPENAI_API_KEY == "YOUR_OPENAI_API_KEY":
    app.logger.warning("OpenAI API Key is not set. AI features will not work.")

# Initialize OpenAI client for TTS
try:
    openai_client = OpenAI(api_key=OPENAI_API_KEY)
except Exception as e:
    openai_client = None
    app.logger.error(f"Could not initialize OpenAI client: {e}\n{traceback.format_exc()}")

# --- File Upload Configuration ---
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['RESUME_FOLDER'] = os.path.join(UPLOAD_FOLDER, 'resumes')
app.config['SCREENSHOT_FOLDER'] = os.path.join(UPLOAD_FOLDER, 'screenshots')

for folder in [app.config['UPLOAD_FOLDER'], app.config['RESUME_FOLDER'], app.config['SCREENSHOT_FOLDER']]:
    if not os.path.exists(folder):
        os.makedirs(folder)

# --- Prompts ---
INTERVIEW_SYSTEM_PROMPT = """
You are 'Alex', an expert technical interviewer for a top-tier tech company. Your persona is sharp, professional, insightful, and friendly. Your goal is to conduct a highly effective technical screening interview.

**Core Instructions:**
1.  **Role & Context:** You will be given a Job Description (JD), the candidate's resume summary, a total number of questions to ask, and specific "must-ask" topics.
2.  **Technical Depth:** This is a technical interview. Your questions must go beyond surface-level experience. Ask probing, open-ended technical questions that assess the candidate's problem-solving abilities, depth of knowledge, and practical skills. Examples: "Can you explain the concept of supernodes in LangGraph and a scenario where you'd use them?" or "Describe a strategy for sharing state between parallel nodes in a complex graph."
3.  **Interview Flow:**
    - Start with a brief, warm greeting. Introduce yourself and the role.
    - Your first question should be a relevant technical opener based on the JD and resume.
    - Ask ONE question at a time.
    - Listen carefully to the candidate's response. Your follow-up question must be logically derived from their answer, drilling down into their explanation or pivoting to a related topic.
    - Seamlessly integrate the "must-ask" topics into the conversation.
    - Adhere to the specified total number of questions.
4.  **Handling Candidate Queries:** If the candidate asks for clarification, provide a concise explanation and then re-engage them with the question.
5.  **Conclusion:** Once you have asked the specified number of questions, conclude the interview professionally. Thank the candidate for their time and explain the next steps.
6.  **Termination Signal:** After your final closing statement, and only then, output the special token `[INTERVIEW_COMPLETE]` on a new line.
"""

ANALYSIS_SYSTEM_PROMPT = """
You are an expert AI hiring assistant. Your task is to analyze an interview transcript and provide a structured assessment of the candidate.
Based on the Job Description, Resume Summary, and full Transcript, provide a detailed scorecard.

**Instructions:**
1.  For each of the three categories below, provide a score from 0 to 10 and a concise justification (1-2 sentences) for your rating.
    - **Technical Proficiency**: How well does the candidate's experience and their answers align with the technical requirements of the job?
    - **Communication Skills**: How clearly and effectively did the candidate articulate their thoughts and experiences?
    - **Alignment with Company Values**: Based on the conversation, how well does the candidate seem to align with values like collaboration, problem-solving, and proactiveness? (Make reasonable inferences).
2.  Calculate an **Overall Score** (0-100) based on a weighted average (Technical: 60%, Communication: 25%, Alignment: 15%).
3.  Write a final **Overall Summary** (2-3 sentences) concluding your assessment.

**Output Format**:
You must respond with a single, valid JSON object only. Do not include any other text, explanation, or markdown formatting like ```json.
{
  "scorecard": {
    "technical_proficiency": {
      "score": your_score_here,
      "justification": "Your justification here."
    },
    "communication_skills": {
      "score": your_score_here,
      "justification": "Your justification here."
    },
    "alignment_with_values": {
      "score": your_score_here,
      "justification": "Your justification here."
    }
  },
  "overall_score": your_weighted_overall_score_here,
  "overall_summary": "Your final summary and recommendation here."
}
"""


# --- Helper Functions ---
def get_db_connection():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except mysql.connector.Error as err:
        app.logger.error(f"Error connecting to MySQL: {err}")
        return None


def generate_id(prefix="item_"):
    return prefix + str(uuid.uuid4())


def serialize_datetime_in_obj(obj):
    if isinstance(obj, dict):
        return {k: serialize_datetime_in_obj(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [serialize_datetime_in_obj(elem) for elem in obj]
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    return obj


def get_llm(temperature=0.7, json_mode=False):
    if not openai_client or OPENAI_API_KEY == "YOUR_OPENAI_API_KEY": return None

    model_kwargs = {}
    if json_mode:
        model_kwargs["response_format"] = {"type": "json_object"}

    return ChatOpenAI(
        temperature=temperature,
        openai_api_key=OPENAI_API_KEY,
        model_name="gpt-4-turbo-preview",
        model_kwargs=model_kwargs
    )


def build_interview_messages(job_data, resume_summary, candidate_name, conversation_history):
    messages = [SystemMessage(content=INTERVIEW_SYSTEM_PROMPT)]

    # Construct the initial context for the AI.
    context = (
        f"Job Description:\n{job_data.get('description', '')}\n\n"
        f"Candidate Resume Summary:\n{resume_summary}\n\n"
        f"Candidate Name: {candidate_name}\n\n"
        f"**Interview Parameters**\n"
        f"- Total Questions to Ask: {job_data.get('number_of_questions', 5)}\n"
        f"- Must-Ask Topics: {job_data.get('must_ask_topics', 'N/A')}\n\n"
        f"Conversation History:\n"
    )

    if not conversation_history:
        context += "The interview is just beginning. Greet the candidate and ask your first question based on the parameters."
    else:
        history_str = "\n".join([f"{msg['actor']}: {msg['text']}" for msg in conversation_history])
        context += history_str

    messages.append(HumanMessage(content=context))
    return messages


def parse_resume_from_file(resume_filepath_db):
    if not resume_filepath_db: return "No resume provided."
    return f"The candidate's resume indicates strong skills in Python, Flask, and project management. They have 5 years of experience in backend development."


# --- Post-Interview Processing ---
def process_interview_results(interview_id):
    app.logger.info(f"Starting post-interview analysis for interview_id: {interview_id}")
    conn = get_db_connection()
    if not conn: return

    cursor = conn.cursor(dictionary=True)
    try:
        query = "SELECT i.transcript_json, j.description as jd, c.resume_filename FROM interviews i JOIN jobs j ON i.job_id = j.id LEFT JOIN candidates c ON i.candidate_id = c.id WHERE i.id = %s"
        cursor.execute(query, (interview_id,))
        interview_data = cursor.fetchone()

        if not interview_data or not interview_data.get('transcript_json'):
            app.logger.warning(f"No transcript found for interview {interview_id}. Aborting analysis.")
            return

        transcript = interview_data['transcript_json']
        if isinstance(transcript, str):
            transcript = json.loads(transcript)

        questions_and_answers = []
        for i, turn in enumerate(transcript):
            if turn['actor'] == 'ai' and i + 1 < len(transcript) and transcript[i + 1]['actor'] == 'candidate':
                questions_and_answers.append({"q": turn['text'], "a": transcript[i + 1]['text']})

        llm = get_llm(temperature=0.2, json_mode=True)
        if not llm:
            app.logger.error("LLM not available for analysis.")
            return

        resume_summary = parse_resume_from_file(interview_data.get('resume_filename'))
        full_transcript_text = "\n".join([f"{t['actor']}: {t['text']}" for t in transcript])

        analysis_context = (
            f"Job Description:\n{interview_data['jd']}\n\nCandidate Resume Summary:\n{resume_summary}\n\nFull Interview Transcript:\n{full_transcript_text}")
        analysis_messages = [SystemMessage(content=ANALYSIS_SYSTEM_PROMPT), HumanMessage(content=analysis_context)]

        ai_response = llm.invoke(analysis_messages)

        try:
            analysis_result = json.loads(ai_response.content)
            scorecard_json = json.dumps(analysis_result.get("scorecard"))
            overall_score = analysis_result.get("overall_score")
            overall_summary = analysis_result.get("overall_summary")

            update_query = "UPDATE interviews SET ai_summary = %s, score = %s, ai_questions_json = %s, detailed_scorecard_json = %s, status = %s WHERE id = %s"
            params = (overall_summary, overall_score, json.dumps(questions_and_answers), scorecard_json,
                      'Pending Review', interview_id)
            cursor.execute(update_query, params)
            conn.commit()
            app.logger.info(f"Successfully analyzed and updated interview {interview_id}")

        except (json.JSONDecodeError, TypeError) as e:
            app.logger.error(
                f"Failed to decode AI analysis for {interview_id}. Raw Response: '{ai_response.content}'\n{traceback.format_exc()}")
            cursor.execute("UPDATE interviews SET status = %s WHERE id = %s", ('Analysis Failed', interview_id))
            conn.commit()

    except Exception as e:
        app.logger.error(
            f"Critical error during post-interview processing for {interview_id}: {e}\n{traceback.format_exc()}")
        if conn.is_connected(): conn.rollback()
    finally:
        if conn.is_connected(): cursor.close(); conn.close()


# --- Admin Endpoints ---
@app.route('/api/admin/jobs', methods=['GET', 'POST'])
def manage_jobs():
    conn = get_db_connection()
    if not conn: return jsonify({"message": "Database connection failed"}), 500

    placeholder_company_id = "company_innovatech"  # Replace with auth logic
    placeholder_admin_user_id = "admin_user_123"  # Replace with auth logic

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
            query = """INSERT INTO jobs (id, title, department, description, status, created_at, created_by, company_id, number_of_questions, must_ask_topics) 
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
            cursor.execute(query, (
                new_job_id, data['title'], data['department'], data['description'],
                data.get('status', 'Open'), datetime.datetime.utcnow(),
                placeholder_admin_user_id, placeholder_company_id,
                data.get('number_of_questions', 5), data.get('must_ask_topics')
            ))
            conn.commit()
            cursor.execute("SELECT * FROM jobs WHERE id = %s", (new_job_id,))
            return jsonify(serialize_datetime_in_obj(cursor.fetchone())), 201
    except mysql.connector.Error as err:
        app.logger.error(f"DB error in manage_jobs: {err}\n{traceback.format_exc()}")
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
    except mysql.connector.Error as err:
        app.logger.error(f"DB error in manage_job_detail for {job_id}: {err}\n{traceback.format_exc()}")
        if request.method in ['PUT', 'DELETE'] and conn.is_connected(): conn.rollback()
        return jsonify({"message": f"DB error: {err.msg}"}), 500
    finally:
        if conn.is_connected(): cursor.close(); conn.close()


@app.route('/api/admin/interviews', methods=['GET'])
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
    except mysql.connector.Error as err:
        app.logger.error(f"DB error in get_admin_interviews: {err}\n{traceback.format_exc()}")
        return jsonify({"message": f"DB error: {err.msg}"}), 500
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


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
    except mysql.connector.Error as err:
        app.logger.error(f"DB error in get_admin_interview_detail for {interview_id}: {err}\n{traceback.format_exc()}")
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

        update_fields = ["status = %s", "updated_at = %s"]
        params = ["Reviewed", datetime.datetime.utcnow()]

        if data.get('score') is not None:
            score_int = int(data['score'])
            if not (0 <= score_int <= 100): raise ValueError("Score out of range")
            update_fields.append("score = %s")
            params.append(score_int)
        else:
            update_fields.append("score = %s");
            params.append(None)

        if 'feedback' in data:
            update_fields.append("admin_feedback = %s")
            params.append(data.get('feedback', ''))

        params.append(interview_id)
        query = f"UPDATE interviews SET {', '.join(update_fields)} WHERE id = %s"
        cursor.execute(query, tuple(params));
        conn.commit()

        query_details = "SELECT i.*, j.title as job_title, c.name as candidate_name FROM interviews i JOIN jobs j ON i.job_id = j.id LEFT JOIN candidates c ON i.candidate_id = c.id WHERE i.id = %s"
        cursor.execute(query_details, (interview_id,))
        updated_interview = cursor.fetchone()

        if updated_interview:
            for key in ['transcript_json', 'ai_questions_json', 'screenshot_paths_json', 'detailed_scorecard_json']:
                if updated_interview.get(key) and isinstance(updated_interview[key], str):
                    try:
                        updated_interview[key] = json.loads(updated_interview[key])
                    except json.JSONDecodeError:
                        updated_interview[key] = None

        return jsonify(serialize_datetime_in_obj(updated_interview)), 200
    except (mysql.connector.Error, ValueError) as err:
        app.logger.error(f"Error in score_interview for {interview_id}: {err}\n{traceback.format_exc()}")
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
        total_applications = (cursor.fetchone().get('total_apps') or 0)
        cursor.execute("SELECT COUNT(*) as count FROM interviews WHERE status = 'Scheduled'")
        interviews_scheduled = cursor.fetchone()['count']
        cursor.execute("SELECT COUNT(*) as count FROM interviews WHERE status = 'Pending Review'")
        pending_reviews = cursor.fetchone()['count']
        return jsonify({"open_positions": open_jobs, "total_applications": total_applications,
                        "interviews_scheduled": interviews_scheduled, "pending_reviews": pending_reviews}), 200
    except mysql.connector.Error as err:
        app.logger.error(f"DB error in get_dashboard_summary: {err}\n{traceback.format_exc()}")
        return jsonify({"message": f"DB error: {err.msg}"}), 500
    finally:
        if conn.is_connected(): cursor.close(); conn.close()


# --- Candidate Facing Endpoints ---
@app.route('/api/interview/initiate/<invitation_link_guid>', methods=['GET'])
def get_interview_by_link(invitation_link_guid):
    conn = get_db_connection()
    if not conn: return jsonify({"message": "Database connection failed"}), 500
    try:
        cursor = conn.cursor(dictionary=True)
        query = "SELECT i.id as interview_id, i.status as interview_status, j.title as job_title, j.company_id FROM interviews i JOIN jobs j ON i.job_id = j.id WHERE i.invitation_link = %s"
        cursor.execute(query, (invitation_link_guid,))
        data = cursor.fetchone()
        if not data: return jsonify({"message": "Invalid invitation link"}), 404

        # In a real multi-tenant app, you'd get company name from the companies table
        data['company_name'] = "Innovatech"  # Placeholder
        return jsonify(data), 200
    finally:
        if conn and conn.is_connected(): conn.close()


@app.route('/api/interview/<interview_id>/submit-details', methods=['POST'])
def submit_candidate_details_and_resume(interview_id):
    conn = get_db_connection()
    if not conn: return jsonify({"message": "Database connection failed"}), 500
    try:
        cursor = conn.cursor(dictionary=True)
        if 'resumeFile' not in request.files: return jsonify({"message": "Resume file missing."}), 400
        resume_file = request.files['resumeFile']
        secure_name = str(uuid.uuid4()) + os.path.splitext(resume_file.filename)[1]
        resume_save_path = os.path.join(app.config['RESUME_FOLDER'], secure_name)
        resume_file.save(resume_save_path)
        resume_filepath_db = f"/uploads/resumes/{secure_name}"

        candidate_id = str(uuid.uuid4())
        now_utc = datetime.datetime.utcnow()

        cursor.execute(
            "INSERT INTO candidates (id, name, email, resume_filename, created_at) VALUES (%s, %s, %s, %s, %s)",
            (candidate_id, request.form['candidateName'], request.form['candidateEmail'], resume_filepath_db, now_utc))
        cursor.execute("UPDATE interviews SET candidate_id=%s, status='Resume Submitted', updated_at=%s WHERE id=%s",
                       (candidate_id, now_utc, interview_id))
        conn.commit()
        return jsonify({"message": "Details submitted.", "candidateId": candidate_id}), 200
    except Exception as e:
        app.logger.error(f"Error in submit-details: {e}\n{traceback.format_exc()}")
        if conn.is_connected(): conn.rollback()
        return jsonify({"message": "An error occurred."}), 500
    finally:
        if conn.is_connected(): conn.close()


@app.route('/api/interview/<interview_id>/start', methods=['POST'])
def start_ai_interview(interview_id):
    llm = get_llm()
    if not llm: return jsonify({"message": "AI service not available."}), 503

    conn = get_db_connection()
    if not conn: return jsonify({"message": "Database connection failed"}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        query = "SELECT j.description, j.number_of_questions, j.must_ask_topics, c.name as candidate_name, c.resume_filename FROM interviews i JOIN jobs j ON i.job_id = j.id JOIN candidates c ON i.candidate_id = c.id WHERE i.id = %s"
        cursor.execute(query, (interview_id,))
        data = cursor.fetchone()

        if not data: return jsonify({"message": "Interview data not found"}), 404

        resume_summary = parse_resume_from_file(data.get('resume_filename'))
        messages = build_interview_messages(data, resume_summary, data['candidate_name'], [])
        ai_response = llm.invoke(messages)
        first_question = ai_response.content.strip()

        transcript = [{"actor": "ai", "text": first_question, "timestamp": datetime.datetime.utcnow().isoformat()}]

        cursor.execute("UPDATE interviews SET status='In Progress', transcript_json=%s, updated_at=%s WHERE id=%s",
                       (json.dumps(transcript), datetime.datetime.utcnow(), interview_id))
        conn.commit()

        return jsonify({"question": {"text": first_question}}), 200
    finally:
        if conn.is_connected(): conn.close()


@app.route('/api/interview/<interview_id>/next-question', methods=['POST'])
def process_candidate_response(interview_id):
    llm = get_llm()
    if not llm: return jsonify({"message": "AI service not available."}), 503

    data = request.json
    if not data.get('response_text'): return jsonify({"message": "Response missing"}), 400

    conn = get_db_connection()
    if not conn: return jsonify({"message": "Database connection failed"}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        query = "SELECT i.transcript_json, j.description, j.number_of_questions, j.must_ask_topics, c.name as candidate_name, c.resume_filename FROM interviews i JOIN jobs j ON i.job_id = j.id JOIN candidates c ON i.candidate_id = c.id WHERE i.id = %s"
        cursor.execute(query, (interview_id,))
        interview = cursor.fetchone()

        transcript = json.loads(interview['transcript_json']) if isinstance(interview['transcript_json'], str) else \
        interview['transcript_json'] or []
        transcript.append(
            {"actor": "candidate", "text": data['response_text'], "timestamp": datetime.datetime.utcnow().isoformat()})

        resume_summary = parse_resume_from_file(interview.get('resume_filename'))
        messages = build_interview_messages(interview, resume_summary, interview['candidate_name'], transcript)
        ai_response = llm.invoke(messages)
        response_text = ai_response.content.strip()

        if "[INTERVIEW_COMPLETE]" in response_text:
            next_question = response_text.replace("[INTERVIEW_COMPLETE]", "").strip()
            new_status = 'Completed'
            transcript.append(
                {"actor": "ai", "text": next_question, "timestamp": datetime.datetime.utcnow().isoformat()})
            cursor.execute("UPDATE interviews SET transcript_json=%s, status=%s WHERE id=%s",
                           (json.dumps(transcript), new_status, interview_id))
            conn.commit()
            process_interview_results(interview_id)
        else:
            next_question = response_text
            new_status = 'In Progress'
            transcript.append(
                {"actor": "ai", "text": next_question, "timestamp": datetime.datetime.utcnow().isoformat()})
            cursor.execute("UPDATE interviews SET transcript_json=%s WHERE id=%s",
                           (json.dumps(transcript), interview_id))
            conn.commit()

        return jsonify({"question": {"text": next_question}, "interview_status": new_status}), 200
    finally:
        if conn.is_connected(): conn.close()


@app.route('/api/interview/<interview_id>/end', methods=['POST'])
def end_interview_manually(interview_id):
    app.logger.info(f"Manual end triggered for interview_id: {interview_id}")
    conn = get_db_connection()
    if not conn: return jsonify({"message": "Database connection failed"}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT status FROM interviews WHERE id = %s", (interview_id,))
        result = cursor.fetchone()
        if result and result['status'] in ['Completed', 'Pending Review', 'Reviewed']:
            app.logger.warning(f"Interview {interview_id} already completed. No action taken.")
            return jsonify({"message": "Interview already completed."}), 200

        cursor.execute("UPDATE interviews SET status=%s, updated_at=%s WHERE id=%s",
                       ('Completed', datetime.datetime.utcnow(), interview_id))
        conn.commit()

        process_interview_results(interview_id)

        return jsonify({"message": "Interview ended. Analysis initiated."}), 200
    except Exception as e:
        app.logger.error(f"Error manually ending interview {interview_id}: {e}\n{traceback.format_exc()}")
        return jsonify({"message": "Failed to end interview."}), 500
    finally:
        if conn and conn.is_connected():
            conn.close()


@app.route('/api/interview/<interview_id>/screenshot', methods=['POST'])
def save_screenshot(interview_id):
    conn = get_db_connection()
    if not conn: return jsonify({"message": "Database connection failed"}), 500

    try:
        data = request.json
        if not data or 'image' not in data:
            return jsonify({"message": "No image data provided"}), 400

        image_data = data['image'].split(',')[1]
        image_bytes = base64.b64decode(image_data)

        filename = f"{interview_id}_{uuid.uuid4()}.jpg"
        filepath = os.path.join(app.config['SCREENSHOT_FOLDER'], filename)
        with open(filepath, 'wb') as f:
            f.write(image_bytes)

        db_path = f"/uploads/screenshots/{filename}"

        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT screenshot_paths_json FROM interviews WHERE id = %s", (interview_id,))
        interview = cursor.fetchone()

        if interview is None:
            return jsonify({"message": "Interview not found"}), 404

        paths = json.loads(interview['screenshot_paths_json']) if interview['screenshot_paths_json'] else []
        paths.append(db_path)

        cursor.execute("UPDATE interviews SET screenshot_paths_json = %s WHERE id = %s",
                       (json.dumps(paths), interview_id))
        conn.commit()

        return jsonify({"message": "Screenshot saved"}), 200
    except Exception as e:
        app.logger.error(f"Error saving screenshot for interview {interview_id}: {e}\n{traceback.format_exc()}")
        if conn.is_connected(): conn.rollback()
        return jsonify({"message": "Error saving screenshot"}), 500
    finally:
        if conn.is_connected(): cursor.close(); conn.close()


@app.route('/api/interview/text-to-speech', methods=['POST'])
def text_to_speech():
    if not openai_client: return jsonify({"message": "TTS service not available."}), 503
    text = request.json.get('text')
    if not text: return jsonify({"message": "No text provided"}), 400
    try:
        response = openai_client.audio.speech.create(model="tts-1", voice="alloy", input=text, response_format="mp3")
        return Response(response.iter_bytes(chunk_size=4096), mimetype="audio/mpeg")
    except Exception as e:
        app.logger.error(f"TTS API call failed: {e}\n{traceback.format_exc()}")
        return jsonify({"message": "Failed to generate audio."}), 500


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

