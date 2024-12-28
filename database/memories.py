import asyncio
import json
import uuid
from datetime import datetime
from typing import List, Tuple

import utils.hume as hume
from models.memory import MemoryPhoto, PostProcessingStatus, PostProcessingModel
from models.transcript_segment import TranscriptSegment
from ._client import supabase, document_id_from_seed


def upsert_memory(uid: str, memory_data: dict):
    if 'audio_base64_url' in memory_data:
        del memory_data['audio_base64_url']
    if 'photos' in memory_data:
        del memory_data['photos']

    #print(f"memory data dict : {memory_data}")
    supabase.table('memories').upsert({
        'user_id': uid,
        'id': memory_data['id'],
        **memory_data
    }).execute()


def get_memory(uid, memory_id):
    response = supabase.table('memories').select('*').eq('user_id', uid).eq('id', memory_id).execute()
    return response.data[0] if response.data else None


def get_memories(uid: str, limit: int = 100, offset: int = 0, include_discarded: bool = False):
    query = supabase.table('memories').select('*').eq('user_id', uid).eq('deleted', False)
    if not include_discarded:
        query = query.eq('discarded', False)
    query = query.order('created_at', desc=True).limit(limit).offset(offset)
    response = query.execute()
    return response.data


def update_memory(uid: str, memory_id: str, memory_data: dict):
    supabase.table('memories').update(memory_data).eq('user_id', uid).eq('id', memory_id).execute()


def delete_memory(uid, memory_id):
    supabase.table('memories').update({'deleted': True}).eq('user_id', uid).eq('id', memory_id).execute()


def filter_memories_by_date(uid, start_date, end_date):
    response = supabase.table('memories').select('*')\
        .eq('user_id', uid)\
        .gte('created_at', start_date.isoformat())\
        .lte('created_at', end_date.isoformat())\
        .eq('discarded', False)\
        .order('created_at', desc=True)\
        .execute()
    return response.data


def get_memories_by_id(uid, memory_ids):
    response = supabase.table('memories').select('*')\
        .eq('user_id', uid)\
        .in_('id', memory_ids)\
        .execute()
    return response.data


# Open Glass

def store_memory_photos(uid: str, memory_id: str, photos: List[MemoryPhoto]):
    photo_data = []
    for photo in photos:
        photo_id = str(uuid.uuid4())
        data = photo.dict()
        data['id'] = photo_id
        data['user_id'] = uid
        data['memory_id'] = memory_id
        photo_data.append(data)
    
    supabase.table('memory_photos').insert(photo_data).execute()


def get_memory_photos(uid: str, memory_id: str):
    response = supabase.table('memory_photos').select('*')\
        .eq('user_id', uid)\
        .eq('memory_id', memory_id)\
        .execute()
    return response.data


def update_memory_events(uid: str, memory_id: str, events: List[dict]):
    supabase.table('memories').update({'structured': {'events': events}})\
        .eq('user_id', uid)\
        .eq('id', memory_id)\
        .execute()


# VISIBILITY

def set_memory_visibility(uid: str, memory_id: str, visibility: str):
    supabase.table('memories').update({'visibility': visibility})\
        .eq('user_id', uid)\
        .eq('id', memory_id)\
        .execute()


# claude outputs

async def _get_public_memory(uid: str, memory_id: str):
    response = supabase.table('memories').select('*')\
        .eq('user_id', uid)\
        .eq('id', memory_id)\
        .eq('visibility', 'public')\
        .eq('deleted', False)\
        .execute()
    return response.data[0] if response.data else None


async def _get_public_memories(data: List[Tuple[str, str]]):
    tasks = [_get_public_memory(uid, memory_id) for uid, memory_id in data]
    memories = await asyncio.gather(*tasks)
    return [memory for memory in memories if memory is not None]


def run_get_public_memories(data: List[Tuple[str, str]]):
    return asyncio.run(_get_public_memories(data))


# POST PROCESSING

def set_postprocessing_status(
        uid: str, memory_id: str, status: PostProcessingStatus, fail_reason: str = None,
        model: PostProcessingModel = PostProcessingModel.fal_whisperx
):
    supabase.table('memories').update({
        'postprocessing': {
            'status': status,
            'model': model,
            'fail_reason': fail_reason
        }
    }).eq('user_id', uid).eq('id', memory_id).execute()


def store_model_segments_result(uid: str, memory_id: str, model_name: str, segments: List[TranscriptSegment]):
    segment_data = []
    for segment in segments:
        segment_id = str(uuid.uuid4())
        data = segment.dict()
        data['id'] = segment_idm 
        data['user_id'] = uid
        data['memory_id'] = memory_id
        data['model_name'] = model_name
        segment_data.append(data)
    
    supabase.table('memory_segments').insert(segment_data).execute()


def update_memory_segments(uid: str, memory_id: str, segments: List[dict]):
    supabase.table('memories').update({'transcript_segments': segments})\
        .eq('user_id', uid)\
        .eq('id', memory_id)\
        .execute()


def store_model_emotion_predictions_result(
        uid: str, memory_id: str, model_name: str,
        predictions: List[hume.HumeJobModelPredictionResponseModel]
):
    now = datetime.now()
    prediction_data = []
    for prediction in predictions:
        prediction_id = str(uuid.uuid4())
        data = {
            "id": prediction_id,
            "user_id": uid,
            "memory_id": memory_id,
            "model_name": model_name,
            "created_at": now,
            "start": prediction.time[0],
            "end": prediction.time[1],
            "emotions": json.dumps(hume.HumePredictionEmotionResponseModel.to_multi_dict(prediction.emotions)),
        }
        prediction_data.append(data)
    
    supabase.table('emotion_predictions').insert(prediction_data).execute()