from flask import Blueprint, jsonify, request, Response
from app.services.db_services import get_db_connection, parse_resume_from_file, serialize_datetime_in_obj
from app.services.ai_services import get_llm, build_interview_messages, process_interview_results, get_openai_client, \
    is_valid_resume
import datetime
import os
import json
import base64
import traceback
from flask import current_app
import uuid
import re
import io

interview_bp = Blueprint('interview_bp', __name__)


@interview_bp.route('/initiate/<invitation_link_guid>', methods=['GET'])
def get_interview_by_link(invitation_link_guid):
    conn = get_db_connection()
    if not conn: return jsonify({"message": "Database connection failed"}), 500
    try:
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT 
                i.id as interview_id, i.status as interview_status, 
                i.transcript_json, i.buffered_question_json,
                j.title as job_title, j.company_id, j.number_of_questions,
                co.name as company_name
            FROM interviews i 
            JOIN jobs j ON i.job_id = j.id 
            JOIN companies co ON j.company_id = co.id
            WHERE i.invitation_link = %s
        """
        cursor.execute(query, (invitation_link_guid,))
        data = cursor.fetchone()

        if not data:
            return jsonify({"message": "Invalid invitation link"}), 404

        status = data['interview_status']

        if status in ['Completed', 'Pending Review', 'Reviewed', 'Analysis Failed']:
            return jsonify({"message": "This interview has already been completed."}), 403

        if status == 'In Progress':
            data['resume'] = True
            if data.get('transcript_json') and isinstance(data['transcript_json'], str):
                data['transcript_json'] = json.loads(data['transcript_json'])
            if data.get('buffered_question_json') and isinstance(data['buffered_question_json'], str):
                data['buffered_question_json'] = json.loads(data['buffered_question_json'])
        else:
            data['resume'] = False

        return jsonify(serialize_datetime_in_obj(data)), 200

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
        if 'resumeFile' not in request.files:
            return jsonify({"message": "Resume file is required."}), 400

        resume_file = request.files['resumeFile']

        if resume_file.filename == '':
            return jsonify({"message": "No resume file selected."}), 400

        if not resume_file.filename.lower().endswith('.pdf'):
            return jsonify({"message": "Invalid file type. Only PDF resumes are accepted."}), 400

        email = request.form.get('candidateEmail')
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            return jsonify({"message": "Invalid email address format."}), 400

        is_valid, validation_message = is_valid_resume(resume_file)
        if not is_valid:
            return jsonify({"message": validation_message}), 400

        resume_file.seek(0)

        cursor = conn.cursor(dictionary=True)
        secure_name = str(uuid.uuid4()) + '.pdf'
        resume_save_path = os.path.join(current_app.config['RESUME_FOLDER'], secure_name)
        resume_file.save(resume_save_path)
        resume_filepath_db = f"resumes/{secure_name}"

        now_utc = datetime.datetime.utcnow()

        cursor.execute(
            "INSERT INTO candidates (name, email, resume_filename, created_at) VALUES (%s, %s, %s, %s)",
            (request.form['candidateName'], email, resume_filepath_db, now_utc))

        candidate_id = cursor.lastrowid

        cursor.execute("UPDATE interviews SET candidate_id=%s, status='Resume Submitted', updated_at=%s WHERE id=%s",
                       (candidate_id, now_utc, interview_id))
        conn.commit()
        return jsonify({"message": "Details submitted.", "candidateId": candidate_id}), 200
    except Exception as e:
        current_app.logger.error(f"Error in submit-details: {e}\n{traceback.format_exc()}")
        if conn and conn.is_connected(): conn.rollback()
        return jsonify({"message": "An error occurred during detail submission."}), 500
    finally:
        if conn and conn.is_connected(): conn.close()


@interview_bp.route('/<interview_id>/start', methods=['POST'])
def start_ai_interview(interview_id):
    llm = get_llm(temperature=0.8, json_mode=True)
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

        try:
            initial_questions_data = json.loads(ai_response.content)
            questions = initial_questions_data.get("initial_questions", [])
            if len(questions) < 2:
                raise ValueError("AI did not generate two initial questions.")

            first_question = questions[0]
            buffered_question = questions[1]
        except (json.JSONDecodeError, ValueError) as e:
            current_app.logger.error(f"Failed to parse initial questions from AI for interview {interview_id}: {e}")
            llm_fallback = get_llm()
            ai_response_fallback = llm_fallback.invoke(messages)
            first_question = ai_response_fallback.content.strip().replace("[INTERVIEW_COMPLETE]", "")
            buffered_question = "Can you tell me about a challenging project you've worked on?"

        # Add the first AI question to the transcript immediately.
        transcript = [{
            "actor": "ai",
            "text": first_question,
            "timestamp": datetime.datetime.utcnow().isoformat()
        }]

        update_query = "UPDATE interviews SET status='In Progress', transcript_json=%s, buffered_question_json=%s, updated_at=%s WHERE id=%s"
        cursor.execute(update_query,
                       (json.dumps(transcript), json.dumps({"question": buffered_question}), datetime.datetime.utcnow(),
                        interview_id))
        conn.commit()

        return jsonify({"question": {"text": first_question}}), 200
    except Exception as e:
        current_app.logger.error(f"Error starting interview {interview_id}: {e}\n{traceback.format_exc()}")
        return jsonify({"message": "An unexpected error occurred while starting the interview"}), 500
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
        query = "SELECT i.transcript_json, i.buffered_question_json, j.description, j.number_of_questions, j.must_ask_topics, c.name as candidate_name, c.resume_filename FROM interviews i JOIN jobs j ON i.job_id = j.id JOIN candidates c ON i.candidate_id = c.id WHERE i.id = %s"
        cursor.execute(query, (interview_id,))
        interview = cursor.fetchone()

        transcript = json.loads(interview['transcript_json']) if isinstance(interview['transcript_json'], str) else \
            interview['transcript_json'] or []

        # 1. Add candidate's response to transcript.
        transcript.append({
            "actor": "candidate",
            "text": data['response_text'],
            "timestamp": datetime.datetime.utcnow().isoformat()
        })

        # 2. Get the question for THIS turn from the buffer.
        buffered_question_data = json.loads(interview['buffered_question_json']) if interview.get(
            'buffered_question_json') else {}
        question_to_ask_now = buffered_question_data.get("question", "Could you elaborate on that?")

        # 3. Add the question for THIS turn to the transcript.
        transcript.append({
            "actor": "ai",
            "text": question_to_ask_now,
            "timestamp": datetime.datetime.utcnow().isoformat()
        })

        # 4. Now, with the complete history, generate the question for the NEXT turn.
        resume_summary = parse_resume_from_file(interview.get('resume_filename'))
        messages_for_next_q = build_interview_messages(interview, resume_summary, interview['candidate_name'],
                                                       transcript)
        ai_response = llm.invoke(messages_for_next_q)
        new_buffered_question_text = ai_response.content.strip()

        # 5. Check if the AI has signaled the end of the interview.
        if "[INTERVIEW_COMPLETE]" in new_buffered_question_text:
            final_statement = new_buffered_question_text.replace("[INTERVIEW_COMPLETE]", "").strip()
            transcript[-1]['text'] = final_statement  # The question we just added becomes the final statement.
            cursor.execute(
                "UPDATE interviews SET transcript_json=%s, status=%s, buffered_question_json=NULL WHERE id=%s",
                (json.dumps(transcript), 'Completed', interview_id))
            conn.commit()
            process_interview_results(interview_id)
            return jsonify({"question": {"text": final_statement}, "interview_status": "Completed"}), 200
        else:
            # 6. Update DB with full transcript and the NEW buffered question for the next turn.
            cursor.execute("UPDATE interviews SET transcript_json=%s, buffered_question_json=%s WHERE id=%s",
                           (json.dumps(transcript), json.dumps({"question": new_buffered_question_text}), interview_id))
            conn.commit()
            # 7. Send the question for the CURRENT turn to the frontend.
            return jsonify({"question": {"text": question_to_ask_now}, "interview_status": "In Progress"}), 200

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

        db_path = f"screenshots/{filename}"

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
