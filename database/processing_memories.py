from ._client import supabase


def upsert_processing_memory(uid: str, processing_memory_data: dict):
    processing_memory_data['user_id'] = uid
    supabase.table('processing_memories').upsert(processing_memory_data).execute()

def update_processing_memory(uid: str, processing_memory_id: str, memory_data: dict):
    supabase.table('processing_memories').update(memory_data).eq('id', processing_memory_id).eq('user_id', uid).execute()

def delete_processing_memory(uid: str, processing_memory_id: str):
    supabase.table('processing_memories').update({'deleted': True}).eq('id', processing_memory_id).eq('user_id', uid).execute()

def get_processing_memories_by_id(uid: str, processing_memory_ids: list):
    response = supabase.table('processing_memories').select('*').eq('user_id', uid).in_('id', processing_memory_ids).execute()
    return response.data
