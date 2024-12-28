import hashlib
import json
import os
import uuid

from supabase import create_client, Client

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
print(f"key:{key}, url:{url}")
supabase: Client = create_client(url, key)

def get_users_uid():
    response = supabase.table('users').select('id').execute()
    return [user['id'] for user in response.data]

def document_id_from_seed(seed: str) -> uuid.UUID:
    """Avoid repeating the same data"""
    seed_hash = hashlib.sha256(seed.encode('utf-8')).digest()
    generated_uuid = uuid.UUID(bytes=seed_hash[:16], version=4)
    return str(generated_uuid)
