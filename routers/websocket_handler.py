import asyncio
import uuid
import time
import traceback
from fastapi.websockets import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState
from .memory_management import (
    setup_memory_context, create_processing_memory,
    try_flush_new_memory_with_lock
)
from models.message_event import MessageEvent
from .asr_client import TencentASRClient
from .audio_processor import AudioProcessor
import subprocess
import json

from persistqueue import Queue


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
        self.websocket_active = True
        self.websocket_close_code = 1001
        self.memory_transcript_segments = []
        self.session_id = str(uuid.uuid4())
        self.timer_start = time.time()

        self.audio_processor = AudioProcessor(channels, sample_rate)

        self.memory_context = None
        self.include_speech_profile = include_speech_profile
        self.asr_client = None
        self.loop = None
        self.is_client_socket_connected = asyncio.Event()
        self.queue = Queue('./data/queue/transcript_segments_queue')

    async def handle(self):
        try:
            await self.websocket.accept()
        except RuntimeError as e:
            print(e)
            return

        self.loop = asyncio.get_event_loop()

        self.asr_client = TencentASRClient(self.sentence_changed_callback, self.sentence_end_callback)
        await self.asr_client.setup()

        #self.memory_context = setup_memory_context(self, self.uid, self.language)

        try:
            if self.enable_memory_watching:
                #heartbeat_task = asyncio.create_task(self.heartbeat())
                receive_audio_task = asyncio.create_task(self.receive_audio())
                memory_watching_task = asyncio.create_task(self.memory_watching())
                #await asyncio.gather(receive_audio_task, memory_watching_task, heartbeat_task)
                await asyncio.gather(receive_audio_task, memory_watching_task)
            else:
                #heartbeat_task = asyncio.create_task(self.heartbeat())
                receive_audio_task = asyncio.create_task(self.receive_audio())
                #await asyncio.gather(receive_audio_task, heartbeat_task)
                await asyncio.gather(receive_audio_task)

        except Exception as e:
            print(f"Error during WebSocket operation: {e}")
        finally:
            self.websocket_active = False

            if self.enable_memory_watching:
                await try_flush_new_memory_with_lock(self.memory_context, should_validate_time=False)

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

    def sentence_changed_callback(self, sentence):
        if not sentence or len(sentence) == 0:
            return

        asyncio.run_coroutine_threadsafe(self.websocket.send_text("ongoing:" + sentence), self.loop)

    def sentence_end_callback(self, segment):
        if not segment:
            return

        print(f"setence end : {segment}")
        asyncio.run_coroutine_threadsafe(self.websocket.send_text("fixed:" + segment["text"]), self.loop)

        segment["session_id"] = self.session_id
        segment["timer_start"] = self.timer_start

        self.queue.put(json.dumps(segment))
        #self.memory_context.memory_transcript_segments.append(segment)

    async def memory_watching(self):
        try:
            while self.enable_memory_watching and self.websocket_active:
                print(f"memory watch, uid: {self.uid}")
                await asyncio.sleep(5)

                await try_flush_new_memory_with_lock(self.memory_context)

        except WebSocketDisconnect:
            print("WebSocket disconnected")
        except Exception as e:
            print(f"Error during memory watching: {e}")
            traceback.print_exc() # Print callstack for other exceptions

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

    async def write_to_ffmpeg(self, process):
        try:
            while True:
                #print("-----------read audio from client loop-----------")
                data = await self.websocket.receive_bytes()
                process.stdin.write(data)
                await asyncio.sleep(0)  # 显式让出控制权
                process.stdin.flush()


        except WebSocketDisconnect:
            print("WebSocket disconnected")
        except Exception as e:
            print(f"Exception during write to ffmpeg: {e}")
        finally:
            self.is_client_socket_connected.clear()
            self.audio_processor.stop_processing()
            process.stdin.close()  # 通知 ffmpeg 没有更多数据了
            print("write_to_ffmpeg exit")

            self.asr_client.disconnect()
            print("asr_client.disconnect done")

    async def read_wav_output(self, process):
        try:
            count = 0
            while self.is_client_socket_connected.is_set():
                print("-----------send audio to asr loop {count}-----------")
                count += 1
                wav_data = await asyncio.to_thread(process.stdout.read, 4096 * 2)  # 异步读取

                if not wav_data:
                    print("No more WAV data")
                    break
                self.asr_client.stream_audio(wav_data, 0)
                
                self.audio_processor.buffer.extend(wav_data)

        except WebSocketDisconnect:
            print("WebSocket disconnected")
        except Exception as e:
            print(f"Exception during WAV output read: {e}")
        finally:
            print("read_wav_output exit")

    async def receive_audio(self):
        # 启动 ffmpeg 进程，通过管道将 WebM 音频流转换为 WAV
        process = subprocess.Popen(
            ['ffmpeg', '-i', 'pipe:0', '-f', 's16le', '-ar', '16000', '-ac', '1', 'pipe:1'],
            stdin=subprocess.PIPE,  # WebSocket 数据传输到 ffmpeg stdin
            stdout=subprocess.PIPE,  # 从 stdout 中读取转换的 WAV 数据
            stderr=subprocess.PIPE,  # 可选：捕获 stderr 以调试 FFmpeg 错误
            bufsize=10**8  # 设置较大的缓冲区
        )

        self.is_client_socket_connected.set()
        self.audio_processor.start_processing();

        await asyncio.gather(self.read_wav_output(process),
                            self.write_to_ffmpeg(process),
                            self.audio_processor.save_to_wav_file_periodically())

# Usage
async def handle_websocket(websocket: WebSocket, uid: str, language: str, sample_rate: int, 
                            codec: str, channels: int, include_speech_profile: bool, 
                            new_memory_watch: bool):    
    handler = WebSocketHandler(websocket, uid, language, sample_rate, codec, channels, include_speech_profile, new_memory_watch)
    await handler.handle()