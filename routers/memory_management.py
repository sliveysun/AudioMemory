import time
import asyncio
import threading
from datetime import datetime, timezone
import uuid
import os
from models.processing_memory import ProcessingMemory, UpdateProcessingMemory
from models.memory import CreateMemory, PostProcessingModel, PostProcessingStatus, MemoryPostProcessing, TranscriptSegment
import database.processing_memories as processing_memories_db
from utils.location import get_google_maps_location
from .process_memory import process_memory
import database.memories as memories_db
from models.message_event import NewProcessingMemoryCreated, MessageEvent, NewMemoryCreated
#from routers.postprocessing import postprocess_memory_util
#from utils.processing_memories import create_memory_by_processing_memory
#from utils.audio import create_wav_from_bytes

class FackeSocket:
    async def send_message_event(self, msg):
        print(f"send_message_event: {msg}")

class MemoryContext:
    def __init__(self, ws_handler, uid, language):
        self.ws_handler = ws_handler
        self.uid = uid
        self.language = language  # Add other necessary attributes

        self.processing_memory = None

        self.memory_transcript_segments = []
        self.memory_transcript_segments_synced = 0

        self.session_id = ""
        self.timer_start = None


def setup_memory_context(ws_handler, uid, session_id, language):
    return MemoryContext(ws_handler, uid, session_id, language)

async def send_message_evnt(ws_handler, msg: MessageEvent):
    ws_handler.send_message_evnt(msg)

async def create_processing_memory(memory_context):
    print("create_processing_memory")
    memory_context.processing_memory = ProcessingMemory(
        id=str(uuid.uuid4()),
        session_id=memory_context.session_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        timer_start=memory_context.timer_start,
        language=memory_context.language,
    )

    #print(f"memory_context.processing_memory.dict() : {memory_context.processing_memory.dict()}")

    print("before upsert_processing_memory")
    processing_memories_db.upsert_processing_memory(
        memory_context.uid,
        memory_context.processing_memory.dict())
    print("after upsert_processing_memory")

    message = NewProcessingMemoryCreated(
        event_type="new_processing_memory_created",
        processing_memory_id=memory_context.processing_memory.id
    )
    await memory_context.ws_handler.send_message_event(message)

async def update_processing_memory(memory_context):
    print("update_processing_memory")

    segment_count = len(memory_context.memory_transcript_segments)
    memory_context.processing_memory.transcript_segments = list(
        map(lambda m: TranscriptSegment(**m),
        memory_context.memory_transcript_segments[:segment_count])
    )
    memory_context.memory_transcript_segments_synced = segment_count

    processing_memories_db.update_processing_memory(
        memory_context.uid,
        memory_context.processing_memory.id,
        memory_context.processing_memory.dict())



def should_create_memory(memory_context, should_validate_time): # Validate transcript
    min_seconds_limit = 10
    should_create_memory_time = time.time() - memory_context.timer_start >= min_seconds_limit

    # 1 words at least
    min_words_limit = 1
    wc = sum(len(segment["text"].split()) for segment in memory_context.memory_transcript_segments)
    should_create_memory_words = wc >= min_words_limit


    should_create_memory = not should_validate_time or (should_create_memory_time and should_create_memory_words)
    print(f"Should create memory {should_create_memory} - {memory_context.timer_start} {min_seconds_limit} - {wc} {min_words_limit} - {should_validate_time}, session {memory_context.session_id}")
    return should_create_memory

async def try_flush_new_memory_with_lock(memory_context, should_validate_time=True):
    #with memory_context.flush_new_memory_lock:
    return await try_flush_new_memory(memory_context, should_validate_time)

async def try_flush_new_memory(memory_context, should_validate_time=True):
    if not memory_context.timer_start:
        print("no timer start")
        return

    # Validate last segment
    if not memory_context.memory_transcript_segments or len(memory_context.memory_transcript_segments) == 0:
        #print("No memory transcript segments")
        return

    last_segment = memory_context.memory_transcript_segments[-1]
    if not last_segment or "end" not in last_segment:
        print("No last segment or last segment invalid")
        return

    # First chunk, create processing memory
    if not memory_context.processing_memory:
        await create_processing_memory(memory_context)

    #return

    if not memory_context.processing_memory:
        return

    if not should_create_memory(memory_context, should_validate_time):
        return
    
    await update_processing_memory(memory_context)
    print(f"after update_processing_memory")

    # memory, messages = await create_memory(memory_context)
    
    # Message: creating
    await memory_context.ws_handler.send_message_event(MessageEvent(event_type="new_memory_creating"))

    # Create memory
    (memory, messages, updated_processing_memory) = await create_memory_by_processing_memory(memory_context.uid,
                                                                                             memory_context.processing_memory.id)
    if not memory:
        print(f"Can not create new memory uid: {memory_context.uid}, processing memory: {memory_context.processing_memory.id if memory_context.processing_memory else 0}")
        await memory_context.ws_handler.send_message_event(MessageEvent(event_type="new_memory_create_failed"))
        return

    memory_context.processing_memory = updated_processing_memory

    # Post processing
    #new_memory = None # await post_process_memory(memory, memory_context)
    #if new_memory:
    #    memory = new_memory

    # Send memory data to App client with socket
    await send_new_memory_created_event(memory_context, memory, messages)
    
    # Clean
    await clean_memory_context(memory_context)

async def post_process_memory(memory, memory_context):
    emotional_feedback = memory_context.processing_memory.emotional_feedback
    (status, new_memory) = postprocess_memory_util(memory.id, file_path, memory_context.uid, emotional_feedback)
    if status == 200:
        memory = new_memory
    else:
        print(f"Post processing failed {memory.id}")

    os.remove(file_path)

    return memory

async def create_memory_by_processing_memory(uid: str, processing_memory_id: str):
    # Fetch new
    processing_memories = processing_memories_db.get_processing_memories_by_id(uid, [processing_memory_id])
    if len(processing_memories) == 0:
        print("processing memory is not found")
        return
    processing_memory = ProcessingMemory(**processing_memories[0])

    # Create memory
    transcript_segments = processing_memory.transcript_segments
    if not transcript_segments or len(transcript_segments) == 0:
        print("Transcript segments is invalid")
        return
    
    timer_start = processing_memory.timer_start
    segment_end = transcript_segments[-1].end
    new_memory = CreateMemory(
        started_at=datetime.fromtimestamp(timer_start, timezone.utc),
        finished_at=datetime.fromtimestamp(timer_start + segment_end, timezone.utc),
        language=processing_memory.language,
        transcript_segments=transcript_segments,
    )

    # Geolocation
    geolocation = processing_memory.geolocation
    if geolocation and not geolocation.google_place_id:
        new_memory.geolocation = get_google_maps_location(geolocation.latitude, geolocation.longitude)

    language_code = new_memory.language
    memory = process_memory(uid, language_code, new_memory)

    if not memory.discarded:
        memories_db.set_postprocessing_status(uid, memory.id, PostProcessingStatus.not_started)
        # TODO: thinh, check why we need populate postprocessing to client
        memory.postprocessing = MemoryPostProcessing(status=PostProcessingStatus.not_started,
                                                     model=PostProcessingModel.fal_whisperx)

    #messages = trigger_external_integrations(uid, memory)
    messages = []

    # update
    processing_memory.memory_id = memory.id
    processing_memory.message_ids = list(map(lambda m: m.id, messages))
    processing_memories_db.update_processing_memory(uid, processing_memory.id, processing_memory.dict())

    return (memory, messages, processing_memory)

async def send_new_memory_created_event(memory_context, memory, messages):
    msg = NewMemoryCreated(
        event_type="new_memory_created",
        processing_memory_id=memory_context.processing_memory.id,
        memory_id=memory.id,
        memory=memory,
        messages=messages
    )
    await memory_context.ws_handler.send_message_event(msg)

async def clean_memory_context(memory_context):
    # Clean
    memory_context.memory_transcript_segments = memory_context.memory_transcript_segments[memory_context.memory_transcript_segments_synced:]
    memory_context.memory_transcript_segments_synced = 0
    memory_context.processing_memory = None