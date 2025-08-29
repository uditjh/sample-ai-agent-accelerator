import os
import log
import uuid
import logging
import json
import psycopg
import boto3
from bedrock_agentcore.memory import MemoryClient

memory_client = MemoryClient(region_name=os.getenv("AWS_REGION"))
memory_id = os.getenv("MEMORY_ID")
memory_data_client = boto3.client("bedrock-agentcore")


class Database():
    """Memory database abstraction"""

    def get(self, conversation_id, user_id):
        """fetch a conversation by id and user"""

        try:
            logging.info(f"Checking memory_id: {memory_id}")
            if not memory_id:
                raise Exception("MEMORY_ID environment variable is not set")
                
            logging.info(f"Fetching events for conversation_id: {conversation_id}, user_id: {user_id}")
            events = memory_client.list_events(memory_id, user_id, conversation_id)
            logging.info(f"found {len(events)} events")
            log.info(events)
        except Exception as e:
            # Handle the case where the actor or session doesn't exist yet (new user/conversation)
            if ("ResourceNotFoundException" in str(type(e).__name__) or 
                "ValidationException" in str(type(e).__name__)) and (
                "Actor" in str(e) and "not found" in str(e) or
                "Session" in str(e) and "not found" in str(e)):
                logging.info(f"Actor {user_id} or session {conversation_id} not found - this is expected for new users/conversations")
                events = []  # Return empty events list for new users/conversations
            else:
                logging.error(f"Error fetching events from memory client: {str(e)}")
                logging.error(f"Exception type: {type(e).__name__}")
                import traceback
                logging.error(f"Traceback: {traceback.format_exc()}")
                raise

        # translate list of events into a conversation with question/answer groupings
        # iterate the list of events backwards
        questions = []
        current_question = None
        current_answer = None

        # Process events in reverse chronological order (oldest first)
        for event in reversed(events):
            if 'payload' in event and event['payload']:
                for payload_item in event['payload']:
                    if 'conversational' in payload_item:
                        conv = payload_item['conversational']
                        role = conv.get('role')
                        content = conv.get('content', {}).get('text', '')

                        if role == 'USER':
                            # If we have a complete Q&A pair, save it
                            if current_question and current_answer:
                                questions.append({
                                    "q": current_question,
                                    "a": current_answer
                                })
                            # Start new question
                            current_question = content
                            current_answer = None

                        elif role == 'ASSISTANT':
                            # Set the answer for current question
                            current_answer = content

                        # Skip TOOL role messages as they're intermediate

        # Add the last Q&A pair if it exists
        if current_question and current_answer:
            questions.append({
                "q": current_question,
                "a": current_answer
            })

        # For now, return empty sources array - this could be enhanced
        # to extract source information from tool calls or other metadata
        result = {
            "conversationId": conversation_id,
            "user_id": user_id,
            "questions": questions,
            "sources": []
        }
        log.info("translated data...")
        log.info(result)
        return result

    def list_by_user(self, user_id, top):
        """fetch a list of conversations by user, sorted by latest activity"""

        try:
            logging.info(f"Listing sessions for user_id: {user_id}, memory_id: {memory_id}")
            if not memory_id:
                raise Exception("MEMORY_ID environment variable is not set")
                
            response = memory_data_client.list_sessions(
                memoryId=memory_id,
                actorId=user_id,
            )
            logging.info(f"Successfully retrieved sessions response")
        except Exception as e:
            # Handle the case where the actor doesn't exist yet (new user)
            if "ResourceNotFoundException" in str(type(e).__name__) and "Actor" in str(e) and "not found" in str(e):
                logging.info(f"Actor {user_id} not found - this is expected for new users")
                return []
            else:
                logging.error(f"Error listing sessions: {str(e)}")
                logging.error(f"Exception type: {type(e).__name__}")
                import traceback
                logging.error(f"Traceback: {traceback.format_exc()}")
                return []

        sessions_with_events = []
        logging.info(
            f"Found {len(response['sessionSummaries'])} total sessions")

        for session in response["sessionSummaries"]:
            session_id = session['sessionId']
            # logging.info(f"Processing session: {session_id}")

            events_response = memory_data_client.list_events(
                memoryId=memory_id,
                actorId=user_id,
                sessionId=session_id,
                includePayloads=True,
                maxResults=100,
            )
            events = events_response.get('events', [])
            # logging.info(f"Session {session_id} has {len(events)} events")

            if events:
                # Sort events by eventTimestamp (convert to datetime for proper sorting)
                from datetime import datetime

                def parse_timestamp(event):
                    ts = event['eventTimestamp']
                    if isinstance(ts, str):
                        # Parse ISO format timestamp
                        return datetime.fromisoformat(ts.replace('Z', '+00:00'))
                    return ts

                sorted_events = sorted(events, key=parse_timestamp)

                latest_ts = parse_timestamp(sorted_events[-1])

                # Add session with first and latest events
                sessions_with_events.append({
                    'session': session,
                    'first_event': sorted_events[0],
                    'latest_event': sorted_events[-1],
                    'latest_timestamp': latest_ts
                })

        # Sort sessions by latest event timestamp (most recent first)
        sessions_with_events.sort(
            key=lambda x: x['latest_timestamp'], reverse=True)

        # Convert to the requested format
        chat_history = []
        for session_data in sessions_with_events[:top]:
            first_event = session_data['first_event']

            # Extract initial question from first event
            initial_question = "No question found"
            if 'payload' in first_event and first_event['payload']:
                payload = first_event['payload'][0]
                if 'conversational' in payload:
                    content = payload['conversational'].get('content', {})
                    if 'text' in content:
                        initial_question = content['text']

            # Format timestamp as M/D/YY H:MM AM/PM
            created_dt = session_data['latest_timestamp']

            # Manual 12-hour format conversion
            hour = created_dt.hour
            am_pm = "AM" if hour < 12 else "PM"
            hour_12 = hour if hour == 0 or hour == 12 else hour % 12
            if hour_12 == 0:
                hour_12 = 12

            created = f"{created_dt.month}/{created_dt.day}/{created_dt.year} {hour_12}:{created_dt.minute:02d} {am_pm}"

            chat_history.append({
                "conversationId": session_data['session']['sessionId'],
                "initial_question": initial_question,
                "created": created
            })

        return chat_history
