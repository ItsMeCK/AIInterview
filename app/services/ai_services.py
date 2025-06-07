from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.schema.messages import HumanMessage, SystemMessage
from openai import OpenAI
from flask import current_app
import json
import traceback
from app.services.db_services import get_db_connection, parse_resume_from_file

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


def get_llm(temperature=0.7, json_mode=False):
    """Initializes and returns the Langchain ChatOpenAI model."""
    if not current_app.config.get('OPENAI_API_KEY') or current_app.config['OPENAI_API_KEY'] == "YOUR_OPENAI_API_KEY":
        return None

    model_kwargs = {}
    if json_mode:
        model_kwargs["response_format"] = {"type": "json_object"}

    return ChatOpenAI(
        temperature=temperature,
        openai_api_key=current_app.config['OPENAI_API_KEY'],
        model_name="gpt-4-turbo-preview",
        model_kwargs=model_kwargs
    )


def get_openai_client():
    """Initializes and returns the direct OpenAI client for TTS."""
    try:
        return OpenAI(api_key=current_app.config['OPENAI_API_KEY'])
    except Exception:
        return None


def build_interview_messages(job_data, resume_summary, candidate_name, conversation_history):
    messages = [SystemMessage(content=INTERVIEW_SYSTEM_PROMPT)]

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
            current_app.logger.error("LLM not available for analysis.")
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
