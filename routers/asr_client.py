from abc import ABC, abstractmethod
from typing import List
from .deepgram import get_deepgram_client
from .tencent_asr import get_tencent_asr_client

class ASRClient(ABC):
    @abstractmethod
    def setup(self):
        pass

    @abstractmethod
    def disconnect(self):
        pass

    @abstractmethod
    def stream_audio(self, data, timer_start):
        pass


class TencentASRClient(ASRClient):
    def __init__(self, sentence_changed_callbacck, sentence_end_callback):
        self.tencent_asr_client = get_tencent_asr_client(sentence_changed_callbacck, sentence_end_callback)

    async def setup(self):
        pass
        
    def disconnect(self):
        self.tencent_asr_client.stop()

    def stream_audio(self, data, timer_start):
        self.tencent_asr_client.write(data)


class DeepgramClient(ASRClient):
    def __init__(self, update_transcript_callback, language: str, 
            sample_rate: int, codec: str, channels: int, include_speech_profile: bool = False):
        self.language = language
        self.codec = codec
        self.include_speech_profile = include_speech_profile
        self.speech_profile_duration = 0
        self.deepgram_client = get_deepgram_client(update_transcript_callback, 1,
                                        language, sample_rate, codec, channels,
                                        preseconds = duration)
        self.deepgram_client2 = get_deepgram_client(update_transcript_callback, 2,
                                        language, sample_rate, codec, channels) 

    async def send_initial_file(self, data: List[List[int]]):
        print('Sending initial file')
        start = asyncio.get_event_loop().time()
        for chunk in data:
            self.deepgram_client.send(bytes(chunk))
            await asyncio.sleep(0.00005)  # Small delay to prevent overwhelming the transcriber
        print(f'Initial file sent in {asyncio.get_event_loop().time() - start:.2f} seconds')

    async def setup(self):
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
            if duration:                          
                await send_initial_file(speech_profile)
            else:
                self.deepgram_client2.finish()
                self.deepgram_client2 = None

        except Exception as e:
            print(f"Initial processing error: {e}")
            raise

    def disconnect(self):
        self.deepgram_client.finish()
        if self.deepgram_client2:
            self.deepgram_client2.finish()

    def stream_audio(self, data, timer_start):
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