import logging
import log
import sys
import os
import signal
from datetime import datetime, timezone
from flask import Flask, request, render_template, abort
from markupsafe import Markup
import mistune
import uuid
import database
import orchestrator

# otel
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.botocore import BotocoreInstrumentor


def signal_handler(signal, frame):
    logging.warning('SIGTERM received, exiting...')
    sys.exit(0)


signal.signal(signal.SIGTERM, signal_handler)
app = Flask(__name__)

# Setup OpenTelemetry
tracer_provider = TracerProvider()
tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(tracer_provider)
FlaskInstrumentor().instrument_app(app)
BotocoreInstrumentor().instrument()


@app.before_request
def before_request():
    """log http request (except for health checks)"""
    if request.path != "/health":
        logging.info(f"HTTP {request.method} {request.url}")


@app.after_request
def after_request(response):
    """log http response (except for health checks)"""
    if request.path != "/health":
        logging.info(
            f"HTTP {request.method} {request.url} {response.status_code}")
    return response


# Validate required environment variables at startup
def validate_environment():
    """Validate that all required environment variables are set"""
    required_vars = {
        'AGENT_RUNTIME': os.getenv('AGENT_RUNTIME'),
        'AWS_REGION': os.getenv('AWS_REGION'),
        'MEMORY_ID': os.getenv('MEMORY_ID')
    }
    
    missing_vars = [var for var, value in required_vars.items() if not value]
    
    if missing_vars:
        error_msg = f"Missing required environment variables: {', '.join(missing_vars)}"
        logging.error(error_msg)
        logging.error("Please set the following environment variables:")
        for var in missing_vars:
            logging.error(f"  export {var}=<value>")
        raise Exception(error_msg)
    
    logging.info("Environment validation passed")
    for var, value in required_vars.items():
        logging.info(f"  {var}: {value[:20]}..." if len(value) > 20 else f"  {var}: {value}")

# Validate environment before initializing services
validate_environment()

# initialize database client
db = database.Database()


@app.template_filter('markdown')
def render_markdown(text):
    """Render Markdown text to HTML"""
    renderer = mistune.create_markdown(
        escape=False,
        plugins=['strikethrough', 'footnotes', 'table']
    )

    # Render the markdown as-is - let mistune handle proper formatting
    return Markup(renderer(text))


@app.route("/health")
def health_check():
    return "healthy"


def get_current_user_id():
    """get the currently logged in user"""
    # TODO: get current user id from auth
    # Using a valid actorId format that meets bedrock-agentcore requirements
    return "user-1"


def get_chat_history(user_id):
    """
    fetches the user's latest chat history
    """
    logging.info(f"fetching chat history for user {user_id}")

    # fetch last 10 questions from db
    return db.list_by_user(user_id, 10)


@app.route("/")
def index():
    """home page"""
    return render_template("index.html", conversation={})


@app.route("/new", methods=["POST"])
def new():
    """POST /new starts a new conversation"""
    return render_template("chat.html", conversation={})


@app.route("/conversations")
def conversations():
    """GET /conversations returns just the conversation history"""
    user_id = get_current_user_id()
    return render_template("conversations.html", chat_history=get_chat_history(user_id))


@app.route("/ask", methods=["POST"])
def ask():
    """POST /ask adds a new Q&A to the conversation"""
    
    try:
        # get conversation id and question from form
        if "conversation_id" not in request.values:
            m = "missing required form data: conversation_id"
            logging.error(m)
            abort(400, m)
        id = request.values["conversation_id"]
        logging.info(f"conversation id: {id}")

        if "question" not in request.values:
            m = "missing required form data: question"
            logging.error(m)
            abort(400, m)
        question = request.values["question"]
        question = question.rstrip()
        logging.info(f"question: {question}")
        logging.info(f"id: {id}")

        user_id = get_current_user_id()
        logging.info(f"user_id: {user_id}")

        is_new_conversation = (id == "")
        if is_new_conversation:
            id = str(uuid.uuid4())
            logging.info(f"created new conversation id: {id}")

        conversation = {
            "conversationId": id,
            "userId": user_id,
            "questions": [],
        }

        logging.info("calling ask_internal...")
        _, conversation, sources = ask_internal(conversation, question)
        logging.info("ask_internal completed successfully")

        # Only render the chat content, not the entire body
        response = render_template("chat.html",
                                   conversation=conversation,
                                   sources=sources)

        # If this is a new conversation, also update the conversation history
        if is_new_conversation:

            utc_datetime = datetime.now(timezone.utc)
            local_datetime = utc_datetime.astimezone()

            # Manual 12-hour format conversion
            hour = local_datetime.hour
            am_pm = "AM" if hour < 12 else "PM"
            hour_12 = hour if hour == 0 or hour == 12 else hour % 12
            if hour_12 == 0:
                hour_12 = 12

            current_datetime = f"{local_datetime.month}/{local_datetime.day}/{local_datetime.year} {hour_12}:{local_datetime.minute:02d} {am_pm}"

            new_history_item = {
                "conversationId": id,
                "initial_question": question,
                "created": current_datetime,
            }
            conversation_item = render_template(
                "conversation_item.html", item=new_history_item)

            # Use out-of-band swap to prepend to conversation list
            response += f'<div hx-swap-oob="afterbegin:#conversation-list">{conversation_item}</div>'

        return response
        
    except Exception as e:
        logging.error(f"Error in /ask endpoint: {str(e)}")
        logging.error(f"Exception type: {type(e).__name__}")
        import traceback
        logging.error(f"Traceback: {traceback.format_exc()}")
        abort(500, f"Internal server error: {str(e)}")


def ask_internal(conversation, question):
    """
    core ask implementation shared by app and api.
    """
    
    try:
        logging.info("Starting orchestrator.orchestrate...")
        # RAG orchestration to get answer
        answer, sources = orchestrator.orchestrate(conversation, question)
        logging.info(f"Orchestrator completed. Answer length: {len(answer) if answer else 0}")

        conversation_id = conversation["conversationId"]
        user_id = conversation["userId"]
        logging.info(f"Fetching conversation from database: {conversation_id}")

        # fetch latest conversation
        conversation = db.get(conversation_id, user_id)
        logging.info(f"Database fetch completed. Questions count: {len(conversation.get('questions', []))}")
        sources = []

        return answer, conversation, sources
        
    except Exception as e:
        logging.error(f"Error in ask_internal: {str(e)}")
        logging.error(f"Exception type: {type(e).__name__}")
        import traceback
        logging.error(f"Traceback: {traceback.format_exc()}")
        raise


if __name__ == '__main__':
    port = 8080
    print(f"listening on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port)


@app.route("/conversation/<id>", methods=["GET"])
def get_conversation(id):
    """GET /conversation/<id> fetches a conversation by id"""

    user_id = get_current_user_id()
    conversation = db.get(id, user_id)
    return render_template("chat.html", conversation=conversation)


@app.route("/api/ask", methods=["POST"])
def ask_api_new():
    """returns an answer to a question in a new conversation"""

    # get request json from body
    body = request.get_json()
    log.debug(body)
    if "question" not in body:
        m = "missing field: question"
        logging.error(m)
        abort(400, m)
    question = body["question"]

    conversation = {
        "conversationId": str(uuid.uuid4()),
        "userId": user_id,
        "questions": [],
    }

    answer, conversation, sources = ask_internal(conversation, question)

    return {
        "conversationId": conversation["conversationId"],
        "answer": answer,
        "sources": sources,
    }


@app.route("/api/ask/<id>", methods=["POST"])
def ask_api(id):
    """returns an answer to a question in a conversation"""

    # get request json from body
    body = request.get_json()
    log.debug(body)
    if "question" not in body:
        m = "missing field: question"
        logging.error(m)
        abort(400, m)
    question = body["question"]

    user_id = get_current_user_id()

    if id == "":
        m = "conversation id is required"
        logging.error(m)
        abort(400, m)
    else:
        conversation = db.get(id, user_id)
        logging.info("fetched conversation")
        log.debug(conversation)

    answer, _, sources = ask_internal(conversation, question)

    return {
        "conversationId": id,
        "answer": answer,
        "sources": sources,
    }


@app.route("/api/conversations/users/<user_id>")
def conversations_get_by_user(user_id):
    """fetch top 10 conversations for a user"""
    return db.list_by_user(user_id, 10)
