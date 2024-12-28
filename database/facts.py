from datetime import datetime, timezone
from typing import List

from ._client import supabase, document_id_from_seed

def get_facts(uid: str, limit: int = 100, offset: int = 0):
    # TODO: how to query more
    response = (
        supabase.table('facts')
        .select('*')
        .eq('user_id', uid)
        .eq('deleted', False)
        .order('created_at', desc=True)
        .limit(limit)
        .offset(offset)
        .execute()
    )
    facts = response.data
    print('get_facts', len(facts))
    result = [fact for fact in facts if fact['user_review'] is not False]
    print('get_facts', len(result))
    return result

def create_fact(uid: str, data: dict):
    data['user_id'] = uid
    supabase.table('facts').insert(data).execute()

def save_facts(uid: str, data: List[dict]):
    if not data or len(data) == 0:
        return
        
    print(f"data: {data}")
    for fact in data:
        fact['user_id'] = uid
    supabase.table('facts').insert(data).execute()

def delete_facts(uid: str):
    supabase.table('facts').delete().eq('user_id', uid).execute()

def get_fact(uid: str, fact_id: str):
    response = (
        supabase.table('facts')
        .select('*')
        .eq('user_id', uid)
        .eq('id', fact_id)
        .limit(1)
        .execute()
    )
    return response.data[0] if response.data else None

def review_fact(uid: str, fact_id: str, value: bool):
    supabase.table('facts').update({
        'reviewed': True,
        'user_review': value
    }).eq('user_id', uid).eq('id', fact_id).execute()

def edit_fact(uid: str, fact_id: str, value: str):
    supabase.table('facts').update({
        'content': value,
        'edited': True,
        'updated_at': datetime.now(timezone.utc).isoformat()
    }).eq('user_id', uid).eq('id', fact_id).execute()

def delete_fact(uid: str, fact_id: str):
    supabase.table('facts').update({
        'deleted': True
    }).eq('user_id', uid).eq('id', fact_id).execute()

def delete_facts_for_memory(uid: str, memory_id: str):
    response = (
        supabase.table('facts')
        .update({'deleted': True})
        .eq('user_id', uid)
        .eq('memory_id', memory_id)
        .eq('deleted', False)
        .execute()
    )
    removed_ids = [fact['id'] for fact in response.data]
    print('delete_facts_for_memory', memory_id, len(removed_ids))
