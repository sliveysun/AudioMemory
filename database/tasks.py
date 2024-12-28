from ._client import supabase

def create(task_data: dict):
    task_id = task_data['id']
    supabase.table('tasks').insert(task_data).execute()

def update(task_id: str, task_data: dict):
    supabase.table('tasks').update(task_data).eq('id', task_id).execute()

def get_task_by_action_request(action: str, request_id: str):
    response = supabase.table('tasks').select('*').eq('action', action).eq('request_id', request_id).limit(1).execute()
    tasks = response.data
    if len(tasks) > 0:
        return tasks[0]

    return None
