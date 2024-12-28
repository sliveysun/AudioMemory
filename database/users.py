from ._client import supabase

def get_user_store_recording_permission(uid: str):
    response = supabase.table('users').select('store_recording_permission').eq('id', uid).execute()
    if response.data:
        return response.data[0].get('store_recording_permission', False)
    return False

def set_user_store_recording_permission(uid: str, value: bool):
    supabase.table('users').update({'store_recording_permission': value}).eq('id', uid).execute()

def create_person(uid: str, data: dict):
    data['user_id'] = uid
    response = supabase.table('people').insert(data).execute()
    return response.data[0] if response.data else None

def get_person(uid: str, person_id: str):
    response = supabase.table('people').select('*').eq('id', person_id).eq('user_id', uid).execute()
    return response.data[0] if response.data else None

def get_people(uid: str):
    response = supabase.table('people').select('*').eq('user_id', uid).eq('deleted', False).execute()
    return response.data

def update_person(uid: str, person_id: str, name: str):
    supabase.table('people').update({'name': name}).eq('id', person_id).eq('user_id', uid).execute()

def delete_person(uid: str, person_id: str):
    supabase.table('people').update({'deleted': True}).eq('id', person_id).eq('user_id', uid).execute()

