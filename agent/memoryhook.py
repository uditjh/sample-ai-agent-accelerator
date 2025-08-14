import logging
import json
from strands.hooks import AgentInitializedEvent, HookProvider, HookRegistry, MessageAddedEvent
from bedrock_agentcore.memory import MemoryClient


class MemoryHookProvider(HookProvider):

    def __init__(self, memory_client: MemoryClient, memory_id: str, actor_id: str, session_id: str):
        self.memory_client = memory_client
        self.memory_id = memory_id
        self.actor_id = actor_id
        self.session_id = session_id

    def on_agent_initialized(self, event: AgentInitializedEvent):
        """Load recent conversation history when agent starts"""

        logging.warning("on_agent_initialized")
        try:
            # Load the last 5 conversation turns from memory
            logging.warning("get_last_k_turns()")
            recent_turns = self.memory_client.get_last_k_turns(
                memory_id=self.memory_id,
                actor_id=self.actor_id,
                session_id=self.session_id,
                k=5
            )
            if recent_turns:
                # Format conversation history for context
                context_messages = []
                for turn in recent_turns:
                    for message in turn:
                        role = message['role']
                        content = message['content']['text']
                        context_messages.append(f"{role}: {content}")

                context = "\n".join(context_messages)
                # Add context to agent's system prompt?
                event.agent.system_prompt += f"\n\nRecent conversation:\n{context}"
                logging.warning(
                    f"✅ Loaded {len(recent_turns)} conversation turns")

        except Exception as e:
            logging.error(f"Memory load error: {e}")

    def _is_tool_message(self, content):
        for msg in content:
            if "toolUse" in msg or "toolResult" in msg:
                return True
        return False

    def on_message_added(self, event: MessageAddedEvent):
        """Store messages in memory"""
        logging.warning("on_message_added")

        # get last message
        last_msg = event.agent.messages[-1]
        content = last_msg["content"]
        role = last_msg["role"]

        if self._is_tool_message(content):
            role = "TOOL"

        if "text" in content[0]:
            text = content[0]["text"]
            logging.warning(f'memory.create_event("{role}", "{text}")')
            self.memory_client.create_event(
                memory_id=self.memory_id,
                actor_id=self.actor_id,
                session_id=self.session_id,
                messages=[(text, role)]
            )
        else:
            logging.error("no text")

    def register_hooks(self, registry: HookRegistry):
        registry.add_callback(MessageAddedEvent, self.on_message_added)
        registry.add_callback(AgentInitializedEvent, self.on_agent_initialized)
