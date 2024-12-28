import asyncio
from ._client import supabase, document_id_from_seed

async def save_token(uid: str, data: dict):
    await supabase.table('users').update(data).eq('id', uid).execute()

async def get_token_only(uid: str):
    response = await supabase.table('users').select('fcm_token').eq('id', uid).execute()
    if response.data:
        return response.data[0].get('fcm_token')
    return None

async def remove_token(token: str):
    await supabase.table('users').update({
        'fcm_token': None,
        'time_zone': None
    }).eq('fcm_token', token).execute()

async def get_token(uid: str):
    response = await supabase.table('users').select('fcm_token, time_zone').eq('id', uid).execute()
    if response.data:
        user = response.data[0]
        return user.get('fcm_token'), user.get('time_zone')
    return None

async def get_users_token_in_timezones(timezones: list[str]):
    return await get_users_in_timezones(timezones, 'fcm_token')

async def get_users_id_in_timezones(timezones: list[str]):
    return await get_users_in_timezones(timezones, 'id')

async def get_users_in_timezones(timezones: list[str], filter: str):
    users = []
    
    async def query_chunk(chunk):
        response = await supabase.table('users').select('id, fcm_token').in_('time_zone', chunk).execute()
        chunk_users = []
        for user in response.data:
            if filter == 'fcm_token':
                token = user.get('fcm_token')
                if token:
                    chunk_users.append(token)
            else:
                token = (user.get('id'), user.get('fcm_token'))
                if token[1]:
                    chunk_users.append(token)
        return chunk_users

    # Supabase doesn't have a limit on 'in' queries, but we'll keep the chunking for consistency
    timezone_chunks = [timezones[i:i + 30] for i in range(0, len(timezones), 30)]
    tasks = [query_chunk(chunk) for chunk in timezone_chunks]
    results = await asyncio.gather(*tasks)

    for chunk_users in results:
        users.extend(chunk_users)

    return users
