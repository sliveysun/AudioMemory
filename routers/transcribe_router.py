from fastapi import APIRouter, WebSocketDisconnect
from fastapi.websockets import WebSocket
from .websocket_handler import handle_websocket
from routers.asr_client import TencentASRClient
from .tencent_asr import get_tencent_asr_client
import asyncio
import aiofiles
import os
import subprocess
import time


router = APIRouter()

@router.websocket("/listen")
async def websocket_endpoint(
    websocket: WebSocket,
    uid: str,
    language: str = 'cn',
    sample_rate: int = 16000,
    codec: str = 'pcm8',
    channels: int = 1,
    include_speech_profile: bool = False,
    new_memory_watch: bool = False
):
    await handle_websocket(
        websocket, uid, language, sample_rate, codec, channels,
        include_speech_profile, new_memory_watch = False
    )
    # = '57119dfa-4ed3-4509-832b-5d32d9337b15',

    #await handle_websocket2(websocket)

async def handle_websocket2(websocket):

    await websocket.accept()
    print("WebSocket connection accepted")
    
    await websocket.send_text("fixed:we are in the handle_websocket2\n")

    session_id = "127493"
    webm_file_path = f"{session_id}.webm"

    loop = asyncio.get_event_loop()
    def sentence_changed(msg):
        try:
            asyncio.run_coroutine_threadsafe(websocket.send_text("ongoing:" + msg), loop)
            #await websocket.send(msg)
        except Exception as e:
            print(f"Exception during sentence_changed: {e}")
        except RuntimeError as e:
            print(f"Can not send message event, error: {e}")
            
    def sentence_end(msg):
        print(f"sentence_end: {msg}")
        try:
            asyncio.run_coroutine_threadsafe(websocket.send_text("fixed:" + msg), loop)
            #websocket.send(msg)
        except Exception as e:
            print(f"Exception during sentence_changed: {e}")
        except RuntimeError as e:
            print(f"Can not send message event, error: {e}")
        
    asr_client = TencentASRClient(sentence_changed, sentence_end)
    #asr_client = get_tencent_asr_client(sentence_changed, sentence_end)
    
    # 启动 ffmpeg 进程，通过管道将 WebM 音频流转换为 WAV
    process = subprocess.Popen(
        ['ffmpeg', '-i', 'pipe:0', '-f', 's16le', '-ar', '16000', '-ac', '1', 'pipe:1'],
        stdin=subprocess.PIPE,  # WebSocket 数据传输到 ffmpeg stdin
        stdout=subprocess.PIPE,  # 从 stdout 中读取转换的 WAV 数据
        stderr=subprocess.PIPE,  # 可选：捕获 stderr 以调试 FFmpeg 错误
        bufsize=10**8  # 设置较大的缓冲区
    )
    
    
    print(f"Recording session started for UID: {session_id}")
    is_connected = True
    
    async def write_to_ffmpeg():
        async with aiofiles.open(webm_file_path, mode='wb') as f:
            try:
                while True:
                    data = await websocket.receive_bytes()
                    process.stdin.write(data)
                    await asyncio.sleep(0)  # 显式让出控制权
                    process.stdin.flush()
                    #await f.write(data)
            except WebSocketDisconnect:
                print("WebSocket disconnected")
            except Exception as e:
                print(f"Exception during write to ffmpeg: {e}")
            finally:
                nonlocal is_connected
                is_connected = False
                process.stdin.close()  # 通知 ffmpeg 没有更多数据了

    async def read_wav_output():
        try:
            while is_connected:
                wav_data = await asyncio.to_thread(process.stdout.read, 4096)  # 异步读取
                if not wav_data:
                    print("No more WAV data")
                    break
                asr_client.stream_audio(wav_data, 0)
        except WebSocketDisconnect:
            print("WebSocket disconnected")
        except Exception as e:
            print(f"Exception during WAV output read: {e}")
 
    await asyncio.gather(read_wav_output(), write_to_ffmpeg())

    print(f"Recording saved as {webm_file_path}") 