from flask import Blueprint, jsonify, request, Response
from app.services.db_services import get_db_connection, generate_id, parse_resume_from_file
from app.services.ai_services import get_llm, build_interview_messages, process_interview_results, get_openai_client
import datetime
import os
import json
import base64
import traceback
from flask import current_app
import uuid

interview_bp = Blueprint('interview_bp', __name__)


@interview_bp.route('/initiate/<invitation_link_guid>', methods=['GET'])
def get_interview_by_link(invitation_link_guid):
    conn = get_db_connection()
    if not conn: return jsonify({"message": "Database connection failed"}), 500
    try:
        cursor = conn.cursor(dictionary=True)
        # Fetch company_id as well to display company-specific branding if needed
        query = "SELECT i.id as interview_id, i.status as interview_status, j.title as job_title, j.company_id FROM interviews i JOIN jobs j ON i.job_id = j.id WHERE i.invitation_link = %s"
        cursor.execute(query, (invitation_link_guid,))
        data = cursor.fetchone()
        if not data: return jsonify({"message": "Invalid invitation link"}), 404

        # In a real multi-tenant app, you'd fetch the company name from the companies table
        # For now, we can use a placeholder or assume a single company for the demo
        data['company_name'] = "Innovatech"  # Placeholder
        return jsonify(data), 200
    except Exception as e:
        current_app.logger.error(f"Error initiating interview: {e}\n{traceback.format_exc()}")
        return jsonify({"message": "An error occurred"}), 500
    finally:
        if conn and conn.is_connected(): conn.close()


@interview_bp.route('/<interview_id>/submit-details', methods=['POST'])
def submit_candidate_details_and_resume(interview_id):
    conn = get_db_connection()
    if not conn: return jsonify({"message": "Database connection failed"}), 500
    try:
        cursor = conn.cursor(dictionary=True)
        if 'resumeFile' not in request.files: return jsonify({"message": "Resume file missing."}), 400
        resume_file = request.files['resumeFile']
        secure_name = str(uuid.uuid4()) + os.path.splitext(resume_file.filename)[1]
        resume_save_path = os.path.join(current_app.config['RESUME_FOLDER'], secure_name)
        resume_file.save(resume_save_path)
        resume_filepath_db = f"/uploads/resumes/{secure_name}"

        candidate_id = generate_id("cand_")
        now_utc = datetime.datetime.utcnow()

        cursor.execute(
            "INSERT INTO candidates (id, name, email, resume_filename, created_at) VALUES (%s, %s, %s, %s, %s)",
            (candidate_id, request.form['candidateName'], request.form['candidateEmail'], resume_filepath_db, now_utc))
        cursor.execute("UPDATE interviews SET candidate_id=%s, status='Resume Submitted', updated_at=%s WHERE id=%s",
                       (candidate_id, now_utc, interview_id))
        conn.commit()
        return jsonify({"message": "Details submitted.", "candidateId": candidate_id}), 200
    except Exception as e:
        current_app.logger.error(f"Error in submit-details: {e}\n{traceback.format_exc()}")
        if conn.is_connected(): conn.rollback()
        return jsonify({"message": "An error occurred."}), 500
    finally:
        if conn and conn.is_connected(): conn.close()


@interview_bp.route('/<interview_id>/start', methods=['POST'])
def start_ai_interview(interview_id):
    llm = get_llm()
    if not llm: return jsonify({"message": "AI service not available."}), 503

    conn = get_db_connection()
    if not conn: return jsonify({"message": "Database connection failed"}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        query = "SELECT j.description, j.number_of_questions, j.must_ask_topics, c.name as candidate_name, c.resume_filename FROM interviews i JOIN jobs j ON i.job_id = j.id JOIN candidates c ON i.candidate_id = c.id WHERE i.id = %s"
        cursor.execute(query, (interview_id,))
        job_data = cursor.fetchone()

        if not job_data: return jsonify({"message": "Interview data not found"}), 404

        resume_summary = parse_resume_from_file(job_data.get('resume_filename'))
        messages = build_interview_messages(job_data, resume_summary, job_data['candidate_name'], [])
        ai_response = llm.invoke(messages)
        first_question = ai_response.content.strip()

        transcript = [{"actor": "ai", "text": first_question, "timestamp": datetime.datetime.utcnow().isoformat()}]

        cursor.execute("UPDATE interviews SET status='In Progress', transcript_json=%s, updated_at=%s WHERE id=%s",
                       (json.dumps(transcript), datetime.datetime.utcnow(), interview_id))
        conn.commit()

        return jsonify({"question": {"text": first_question}}), 200
    finally:
        if conn and conn.is_connected(): conn.close()


@interview_bp.route('/<interview_id>/next-question', methods=['POST'])
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
        if conn and conn.is_connected(): conn.close()


@interview_bp.route('/<interview_id>/end', methods=['POST'])
def end_interview_manually(interview_id):
    current_app.logger.info(f"Manual end triggered for interview_id: {interview_id}")
    conn = get_db_connection()
    if not conn: return jsonify({"message": "Database connection failed"}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT status FROM interviews WHERE id = %s", (interview_id,))
        result = cursor.fetchone()
        if result and result['status'] in ['Completed', 'Pending Review', 'Reviewed']:
            return jsonify({"message": "Interview already completed."}), 200

        cursor.execute("UPDATE interviews SET status=%s, updated_at=%s WHERE id=%s",
                       ('Completed', datetime.datetime.utcnow(), interview_id))
        conn.commit()

        process_interview_results(interview_id)

        return jsonify({"message": "Interview ended. Analysis initiated."}), 200
    except Exception as e:
        current_app.logger.error(f"Error manually ending interview {interview_id}: {e}\n{traceback.format_exc()}")
        return jsonify({"message": "Failed to end interview."}), 500
    finally:
        if conn and conn.is_connected(): conn.close()


@interview_bp.route('/<interview_id>/screenshot', methods=['POST'])
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
        filepath = os.path.join(current_app.config['SCREENSHOT_FOLDER'], filename)
        with open(filepath, 'wb') as f:
            f.write(image_bytes)

        db_path = f"/uploads/screenshots/{filename}"

        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT screenshot_paths_json FROM interviews WHERE id = %s", (interview_id,))
        interview = cursor.fetchone()

        if interview is None: return jsonify({"message": "Interview not found"}), 404

        paths = json.loads(interview['screenshot_paths_json']) if interview['screenshot_paths_json'] else []
        paths.append(db_path)

        cursor.execute("UPDATE interviews SET screenshot_paths_json = %s WHERE id = %s",
                       (json.dumps(paths), interview_id))
        conn.commit()

        return jsonify({"message": "Screenshot saved"}), 200
    except Exception as e:
        current_app.logger.error(f"Error saving screenshot for interview {interview_id}: {e}\n{traceback.format_exc()}")
        if conn.is_connected(): conn.rollback()
        return jsonify({"message": "Error saving screenshot"}), 500
    finally:
        if conn and conn.is_connected(): conn.close()


@interview_bp.route('/text-to-speech', methods=['POST'])
def text_to_speech():
    openai_client = get_openai_client()
    if not openai_client: return jsonify({"message": "TTS service not available."}), 503

    text = request.json.get('text')
    if not text: return jsonify({"message": "No text provided"}), 400
    try:
        response = openai_client.audio.speech.create(model="tts-1", voice="alloy", input=text, response_format="mp3")
        return Response(response.iter_bytes(chunk_size=4096), mimetype="audio/mpeg")
    except Exception as e:
        current_app.logger.error(f"TTS API call failed: {e}\n{traceback.format_exc()}")
        return jsonify({"message": "Failed to generate audio."}), 500
