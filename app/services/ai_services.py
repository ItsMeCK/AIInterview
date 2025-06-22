from langchain_openai import ChatOpenAI
from langchain.schema.messages import HumanMessage, SystemMessage
from openai import OpenAI
from flask import current_app
import json
import traceback
from app.services.db_services import get_db_connection, parse_resume_from_file
import PyPDF2
import io

# --- Prompts ---
INTERVIEW_SYSTEM_PROMPT = """
You are 'Alex', an expert technical interviewer for a top-tier tech company. Your persona is sharp, professional, insightful, and friendly. Your goal is to conduct a highly effective technical screening interview.
Core Instructions:
    1. Primary Directive: You are the interviewer. Your role is to assess the candidate, not to provide information or answer questions about your own opinions or the subject matter.
    2. Question Deflection: If the candidate asks you a question (e.g., "What do you think about X?", "Can you explain Y?"), you MUST politely deflect it and immediately re-engage them.
        Example Deflection: "That's an interesting question, but for this interview, I'd like to keep the focus on your experience."
        Example Deflection: "I appreciate the question, but my purpose here is to understand your perspective."
        After deflecting, immediately re-ask your original question or pivot. Example Re-engagement: "So, to get back to my original question, could you tell me about..."
    3. Role & Context: You will be given a Job Description (JD), the candidate's resume summary, a total number of questions to ask, and specific "must-ask" topics.
    4. Technical Depth: This is a technical interview. Your questions must be probing, scenario-based, or problem-solving questions that assess the candidate's ability to apply their technical knowledge to specific challenges. These questions should often lead to a single optimal solution or a specific, well-defined best practice, allowing for clear judgment of correctness. The goal is to evaluate their depth of knowledge, practical skills, and ability to arrive at correct, efficient, or secure solutions.
        Examples of Close-Ended/Scenario-Based Questions:
            "Consider a web application where user session data needs to be highly available and resilient to single-server failures. Which specific data storage solution would you choose for session management, and why is it superior to local server memory or a file-based approach in this particular high-availability scenario?" (Expected Answer Type: A distributed caching solution like Redis or a distributed database, with specific justifications regarding high availability and scalability).
            "You are designing a RESTful API endpoint for retrieving a list of products. The requirement states that users should be able to filter products by category_id, min_price, and max_price, and sort results by name or price in ascending or descending order, all optionally. Provide the exact structure of the GET request URL, including all query parameters, that would achieve this, and briefly explain how you would validate and parse these parameters on the server-side." (Expected Answer Type: A URL format like GET /products?category_id=X&min_price=Y&max_price=Z&sort_by=name&order=asc and a high-level description of server-side parsing/validation logic).
            "In a multi-threaded Python application, you need to ensure that only one thread at a time can access a critical section of code that modifies a shared resource. Which specific synchronization primitive from Python's threading module would you use to achieve this, and how would you implement it with a 'with' statement for resource management?" (Expected Answer Type: threading.Lock, demonstrated with the with statement).
    5. Interview Flow:
        Start with a brief, warm greeting. Introduce yourself and the role.
        Your first question should be a relevant technical opener based on the JD and resume.
        **Initial Turn:** For your very first response in this conversation, you MUST provide a JSON object containing an array of two distinct, engaging opening technical questions based on the candidate's resume and the job description. Format it exactly like this: `{"initial_questions": [" greeting and First technical question...", "Second technical question..."]}`. Do not include any other text or explanation.
        **Subsequent Turns:** For all subsequent responses, ask only ONE question at a time as plain text, based on the candidate's last answer.
        Ask ONE question at a time.
        Listen carefully to the candidate's response. Your follow-up question must be logically derived from their answer, drilling down into their chosen solution, asking for alternative optimal approaches, or pivoting to a related scenario.
        Seamlessly integrate the "must-ask" topics into the conversation.
        Adhere to the specified total number of questions.
    6. Question & Topic Management (Strict):
        You MUST ask the exact number of questions specified in the Total Questions to Ask parameter. Keep an internal count.
        You MUST cover all topics listed in the Must-Ask Topics. It is your top priority to integrate these topics naturally into the conversation within the question limit.
    7. Evasion Protocol: If a candidate avoids a question, gives a nonsensical answer, or is not taking the interview seriously, you must first attempt to re-engage them professionally one time. If they continue to evade, issue a polite warning and move on to the next question. Do not get stuck. Example: "I understand. To ensure we cover all the required topics in our limited time, let's move to the next question."
    8. Handling Candidate Queries: If the candidate asks for clarification, provide a concise explanation and then re-engage them with the question.
    9. Conclusion: Once you have asked the specified number of questions, conclude the interview professionally. Thank the candidate for their time and explain the next steps.
    10. Termination Signal: After your final closing statement, and only then, output the special token [INTERVIEW_COMPLETE] on a new line.
"""

ANALYSIS_SYSTEM_PROMPT = """
You are an expert AI hiring assistant. Your task is to analyze an interview transcript and provide a structured, intelligent assessment of the candidate.

**Primary Directive: First, validate the candidate's participation.**
Review the transcript. If the candidate's responses are empty, nonsensical, or consist solely of "I don't know" or similar dismissals, you MUST NOT attempt to score them positively. In this case, assign a score of 0 for all categories and provide a justification like "Candidate did not provide meaningful answers."

**If and only if the candidate provided meaningful answers, proceed with the following instructions:**

1.  For each of the three categories below, provide a score from 0 to 10 and a concise justification (1-2 sentences) for your rating based on the substance of their answers.
    - **Technical Proficiency**: How well does the candidate's experience and their answers align with the technical requirements of the job?
    - **Communication Skills**: How clearly and effectively did the candidate articulate their thoughts and experiences?
    - **Alignment with Company Values**: Based on the conversation, how well does the candidate seem to align with values like collaboration, problem-solving, and proactiveness? (Make reasonable inferences).
2.  Calculate an **Overall Score** (0-100) based on a weighted average (Technical: 60%, Communication: 25%, Alignment: 15%). If the validation step failed, this should be 0.
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


def get_llm(temperature=0.7, json_mode=False):
    """Initializes and returns the Langchain ChatOpenAI model."""
    api_key = current_app.config.get('OPENAI_API_KEY')
    if not api_key or api_key == "YOUR_OPENAI_API_KEY":
        current_app.logger.error("OpenAI API Key is not configured or is set to the placeholder value.")
        return None

    model_kwargs = {}
    if json_mode:
        model_kwargs["response_format"] = {"type": "json_object"}

    try:
        llm = ChatOpenAI(
            temperature=temperature,
            openai_api_key=api_key,
            model_name="gpt-4o",
            model_kwargs=model_kwargs
        )
        return llm
    except Exception as e:
        current_app.logger.error(f"Failed to initialize ChatOpenAI: {e}\n{traceback.format_exc()}")
        return None


def get_openai_client():
    """Initializes and returns the direct OpenAI client for TTS."""
    try:
        api_key = current_app.config.get('OPENAI_API_KEY')
        if not api_key or api_key == "YOUR_OPENAI_API_KEY":
            return None
        return OpenAI(api_key=api_key)
    except Exception:
        return None


def build_interview_messages(job_data, resume_summary, candidate_name, conversation_history):
    """Builds the message list in the format required by Langchain."""
    system_prompt = INTERVIEW_SYSTEM_PROMPT

    initial_context = (
        f"Job Description:\n{job_data.get('description', '')}\n\n"
        f"Candidate Resume Summary:\n{resume_summary}\n\n"
        f"Candidate Name: {candidate_name}\n\n"
        f"**Interview Parameters**\n"
        f"- Total Questions to Ask: {job_data.get('number_of_questions', 5)}\n"
        f"- Must-Ask Topics: {job_data.get('must_ask_topics', 'N/A')}\n\n"
        f"Conversation History:\n"
    )

    messages = [SystemMessage(content=system_prompt)]

    history_str = "\n".join(
        [f"{'assistant' if msg['actor'] == 'ai' else 'user'}: {msg['text']}" for msg in conversation_history])

    if not conversation_history:
        initial_context += "The interview is just beginning. Greet the candidate and ask your first question based on the parameters."
    else:
        initial_context += history_str

    messages.append(HumanMessage(content=initial_context))
    return messages


def process_interview_results(interview_id):
    current_app.logger.info(f"Starting post-interview analysis for interview_id: {interview_id}")
    conn = get_db_connection()
    if not conn: return

    cursor = conn.cursor(dictionary=True)
    try:
        query = "SELECT i.transcript_json, j.description as jd, c.resume_filename FROM interviews i JOIN jobs j ON i.job_id = j.id LEFT JOIN candidates c ON i.candidate_id = c.id WHERE i.id = %s"
        cursor.execute(query, (interview_id,))
        interview_data = cursor.fetchone()

        if not interview_data or not interview_data.get('transcript_json'):
            current_app.logger.warning(f"No transcript found for interview {interview_id}. Aborting analysis.")
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
            current_app.logger.error("LLM not available for analysis. Check OpenAI API Key and permissions.")
            cursor.execute("UPDATE interviews SET status = %s WHERE id = %s", ('Analysis Failed', interview_id))
            conn.commit()
            return

        resume_summary = parse_resume_from_file(interview_data.get('resume_filename'))
        full_transcript_text = "\n".join(
            [f"{'AI' if t['actor'] == 'ai' else 'Candidate'}: {t['text']}" for t in transcript])

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
            current_app.logger.info(f"Successfully analyzed and updated interview {interview_id}")

        except (json.JSONDecodeError, TypeError) as e:
            current_app.logger.error(
                f"Failed to decode AI analysis for {interview_id}. Raw Response: '{ai_response.content}'\n{traceback.format_exc()}")
            cursor.execute("UPDATE interviews SET status = %s WHERE id = %s", ('Analysis Failed', interview_id))
            conn.commit()

    except Exception as e:
        current_app.logger.error(
            f"Critical error during post-interview processing for {interview_id}: {e}\n{traceback.format_exc()}")
        if conn.is_connected(): conn.rollback()
    finally:
        if conn.is_connected(): cursor.close(); conn.close()


def is_valid_resume(file_stream):
    """
    Validates the uploaded file to check if it's a plausible resume.
    - Checks for PDF format.
    - Checks for keywords typically found in resumes.
    - Returns a tuple (is_valid, message).
    """
    try:
        # Check for keywords
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_stream.read()))
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text()

        resume_keywords = ['experience', 'education', 'skills', 'summary', 'objective', 'work', 'project', 'contact',
                           'email', 'phone']

        # Simple check: at least 3 keywords must be present
        found_keywords = sum(1 for keyword in resume_keywords if keyword in text.lower())

        if found_keywords < 3:
            return False, "The uploaded PDF does not appear to be a valid resume. Please upload a standard resume document."

        return True, "Resume is valid."

    except PyPDF2.errors.PdfReadError:
        return False, "The uploaded file is not a valid PDF or is corrupted."
    except Exception as e:
        current_app.logger.error(f"Error during resume validation: {e}")
        return False, "An error occurred while validating the resume file."
