import uuid
from datetime import datetime, timezone
from typing import Optional

from models.chat import Message
from ._client import supabase, document_id_from_seed


def add_message(uid: str, message_data: dict):
    del message_data['memories']
    response = supabase.table('messages').insert(
        {**message_data, 'user_id': uid}
    ).execute()
    return response.data[0] if response.data else None


def add_plugin_message(text: str, plugin_id: str, uid: str, memory_id: Optional[str] = None) -> Message:
    ai_message = Message(
        id=str(uuid.uuid4()),
        text=text,
        created_at=datetime.now(timezone.utc),
        sender='ai',
        plugin_id=plugin_id,
        from_external_integration=False,
        type='text',
        memories_id=[memory_id] if memory_id else [],
    )
    add_message(uid, ai_message.dict())
    return ai_message


def add_summary_message(text: str, uid: str) -> Message:
    ai_message = Message(
        id=str(uuid.uuid4()),
        text=text,
        created_at=datetime.now(timezone.utc),
        sender='ai',
        plugin_id=None,
        from_external_integration=False,
        type='day_summary',
        memories_id=[],
    )
    add_message(uid, ai_message.dict())
    return ai_message


def get_messages(uid: str, limit: int = 20, offset: int = 0, include_memories: bool = False):
    response = supabase.table('messages').select('*').eq('user_id', uid).order('created_at', desc=True).limit(limit).offset(offset).execute()
    messages = response.data

    if not include_memories:
        return messages

    memories_id = set()
    for message in messages:
        memories_id.update(message.get('memories_id', []))

    # Fetch all memories at once
    memories = {}
    if memories_id:
        memory_response = supabase.table('memories').select('*').in_('id', list(memories_id)).execute()
        for memory in memory_response.data:
            memories[memory['id']] = memory

    # Attach memories to messages
    for message in messages:
        message['memories'] = [
            memories[memory_id] for memory_id in message.get('memories_id', []) if memory_id in memories
        ]

    return messages
