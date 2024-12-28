import asyncio
import uuid
import time
from fastapi.websockets import WebSocket
from starlette.websockets import WebSocketState
from .memory_management import (
    setup_memory_context, create_processing_memory,
    try_flush_new_memory_with_lock
)
from .deepgram import get_deepgram_client
from .tencent_asr import get_tencent_asr_client
from models.message_event import MessageEvent

class WebSocketHandler:
    def __init__(self, websocket: WebSocket, uid: str, language: str, sample_rate: int,
                 codec: str, channels: int, include_speech_profile: bool, enable_memory_watching: bool):
        self.websocket = websocket
        self.uid = uid
        self.language = language
        self.sample_rate = sample_rate
        self.codec = codec
        self.channels = channels
        self.enable_memory_watching = enable_memory_watching
        self.session_id = str(uuid.uuid4())
        self.websocket_active = True
        self.websocket_close_code = 1001
        self.memory_transcript_segments = []

        self.memory_context = None

        self.include_speech_profile = include_speech_profile
        self.deepgram_client = None
        self.deepgram_client2 = None
        self.speech_profile_duration

    async def send_initial_file(data: List[List[int]], transcript_socket):
        print('Sending initial file')
        start = asyncio.get_event_loop().time()
        for chunk in data:
            transcript_socket.send(bytes(chunk))
            await asyncio.sleep(0.00005)  # Small delay to prevent overwhelming the transcriber
        print(f'Initial file sent in {asyncio.get_event_loop().time() - start:.2f} seconds')

    async def setup_audio_processing(self):
        duration = 0

        try:
            if self.language == 'en' and self.codec == 'opus' and self.include_speech_profile:
                speech_profile = get_user_speech_profile(uid)
                duration = get_user_speech_profile_duration(uid)
                print('speech_profile', len(speech_profile), duration)
                if duration:
                    duration *= 2
            else:
                speech_profile, duration = [], 0

            self.speech_profile_duration = duration
            self.deepgram_client = get_deepgram_client(update_transcript_callback, 1,
                                            self.language, self.sample_rate, self.codec, self.channels,
                                            preseconds = duration)

            if duration:
                self.deepgram_client2 = get_deepgram_client(update_transcript_callback, 2,
                                            self.language, self.sample_rate, self.codec, self.channels)                            

                await send_initial_file(speech_profile, deepgram_client)

        except Exception as e:
            print(f"Initial processing error: {e}")
            raise

    async def handle(self):
        print('websocket_endpoint', self.uid, self.language, self.sample_rate, self.codec,
              self.channels, self.include_speech_profile, self.new_memory_watch)

        try:
            await self.websocket.accept()
        except RuntimeError as e:
            print(e)
            return

        await setup_audio_processing(
            self.uid, self.language, self.sample_rate, self.codec,
            self.channels, self.include_speech_profile
        )
        self.memory_context = setup_memory_context(
            self.uid, self.session_id, self.new_memory_watch
        )

        try:
            if self.new_memory_watch:
                heartbeat_task = asyncio.create_task(self.heartbeat())
                receive_audio_task = asyncio.create_task(self.receive_audio())
                memory_watching_task = asyncio.create_task(self.memory_watching())
                await asyncio.gather(receive_audio_task, memory_watching_task, heartbeat_task)
            else:
                heartbeat_task = asyncio.create_task(self.heartbeat())
                receive_audio_task = asyncio.create_task(self.receive_audio())
                await asyncio.gather(receive_audio_task, heartbeat_task)

        except Exception as e:
            print(f"Error during WebSocket operation: {e}")
        finally:
            self.websocket_active = False

            if self.enable_memory_watching:
                await try_flush_new_memory_with_lock(self.memory_context, time_validate=False)

            if self.websocket.client_state == WebSocketState.CONNECTED:
                try:
                    await self.websocket.close(code=self.websocket_close_code)
                except Exception as e:
                    print(f"Error closing WebSocket: {e}")

    def process_segments(self, segments: list[dict]):
        token = notification_db.get_token_only(self.uid)  # TODO: Optimize token retrieval
        trigger_realtime_integrations(self.uid, token, segments)

    def _merge_segments(segments, new_segments):
        """Combines consecutive segments from the same speaker 
        or consecutive user segments if they are close enough in time."""

        if not new_segments:
            return segments

        # Index of the last segment in `segments` that might need merging.
        last_mergeable_index = len(segments) - 1

        for segment in new_segments:
            if (last_mergeable_index >= 0 and 
                _should_merge(segments[last_mergeable_index], segment, 
                              max_gap=30 if last_mergeable_index != -1 else 0)):
                segments[last_mergeable_index]["text"] += f' {segment["text"]}'
                segments[last_mergeable_index]["end"] = segment["end"]
            else:
                segments.append(segment)
                last_mergeable_index += 1

        return segments

    def _should_merge(seg1, seg2, max_gap=0):
        """Checks if two segments should be merged based on speaker and time gap."""
        return ((seg1["speaker"] == seg2["speaker"] or 
                 (seg1["is_user"] and seg2["is_user"])) and 
                (seg2["start"] - seg1["end"] < max_gap))

    async def update_transcript_callback(self, new_segments, stream_id):
        if not new_segments or len(new_segments) == 0:
            return

        await self.websocket.send_json(segments)
        #asyncio.create_task(self.process_segments(segments))

        # memory segments
        # Warn: need double check should we still seperate the memory and speech profile stream or not?
        if self.enable_memory_watching:
            _merge_segments(self.memory_transcript_segments, new_segments)

            # Sync processing transcript, periodly
            #if processing_memory and len(self.memory_transcript_segments) % 3 == 0:
            #    processing_memory_synced = len(self.memory_transcript_segments)
            #    processing_memory.transcript_segments = list(
            #        map(lambda m: TranscriptSegment(**m), self.memory_transcript_segments))
            #    processing_memories_db.update_processing_memory(self.uid, processing_memory.id, processing_memory.dict())

    async def memory_watching(self):
        try:
            while self.enable_memory_watching and self.websocket_active:
                print(f"memory watch, uid: {self.uid}, session: {self.session_id}")
                await asyncio.sleep(5)

                await try_flush_new_memory_with_lock(self.memory_context)

        except WebSocketDisconnect:
            print("WebSocket disconnected")
        except Exception as e:
            print(f"Error during memory watching: {e}")

    async def heartbeat(self):
        try:
            while True:
                await asyncio.sleep(10)
                if self.websocket.client_state == WebSocketState.CONNECTED:
                    await self.websocket.send_json({"type": "ping"})
                else:
                    break
        except WebSocketDisconnect:
            print("WebSocket disconnected")
        except Exception as e:
            print(f'Heartbeat error: {e}')
        finally:
            self.websocket_active = False

    async def send_message_event(self, msg: MessageEvent):
        print(f"Message: {msg.to_json()}")
        try:
            await self.websocket.send_json(msg.to_json())
            return True
        except WebSocketDisconnect:
            print("WebSocket disconnected")
        except RuntimeError as e:
            print(f"Can not send message event, error: {e}")
        return False

    async def receive_audio(self):
        timer_start = time.time()
        try:
            while self.websocket_active:
                data = await self.websocket.receive_bytes()

                self.stream_audio_to_deepgram(data, timer_start)
                self.stream_audio_to_buffer(data)

        except Exception as e:
            print(f'Could not process audio: error {e}')
        finally:
            self.memory_context['websocket_active'] = False
            self.deepgram_client.finish()
            if self.deepgram_client2:
                self.deepgram_client2.finish()

    def stream_audio_to_deepgram(self, data, timer_start):
        audio_buffer = bytearray()
        audio_buffer.extend(data)
        elapsed_seconds = time.time() - timer_start
        if elapsed_seconds > self.speech_profile_duration or not self.deepgram_client2:
            self.deepgram_client.send(audio_buffer)
            if self.deepgram_client2:
                print('Killing socket2')
                self.deepgram_client2.finish()
                self.deepgram_client2 = None
        else:
            self.deepgram_client2.send(audio_buffer)

    def stream_audio_to_buffer(self, data):
        if self.enable_memory_watching:
            self.memory_context['processing_audio_frames'].append(data)
# Usage
async def handle_websocket(websocket: WebSocket, uid: str, language: str, sample_rate: int, 
                            codec: str, channels: int, include_speech_profile: bool, 
                            new_memory_watch: bool):    
    handler = WebSocketHandler(websocket, uid, language, sample_rate, codec, channels, include_speech_profile, new_memory_watch)
    await handler.handle()