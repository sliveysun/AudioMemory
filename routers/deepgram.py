import os
from typing import Callable, List
from deepgram import DeepgramClient, DeepgramClientOptions, LiveTranscriptionEvents
from deepgram.clients.live.v1 import LiveOptions, LiveClient

tencent_asr_secret_key: str = os.environ.get("DEEPGRAM_API_KEY")
tencent_asr_secret_id: str = os.environ.get("DEEPGRAM_OPTIONS")

def get_deepgram_client(update_transcript_callback: Callable, stream_id: int, language: str, 
            sample_rate: int, codec: str, channels: int, preseconds: int = 0):
    print(f'Processing audio: {language}, {sample_rate}, {codec}, {channels}, {preseconds}')
    client = DeepgramClient(os.getenv('DEEPGRAM_API_KEY'), DeepgramClientOptions(options={"keepalive": "true"}))

    def on_message(self, result, **kwargs):
        sentence = result.channel.alternatives[0].transcript
        if not sentence:
            return

        transcript_segments = _combine_words(result.channel.alternatives[0].words, preseconds)
        update_transcript_callback(transcript_segments, stream_id)

    def on_error(self, error, **kwargs):
        print(f"Deepgram Error: {error}")

    print("Connecting to Deepgram")
    return _connect_to_deepgram(client, on_message, on_error, language, sample_rate, codec, channels)

def _combine_words(words, preseconds: int):
    segments = []
    for word in words:
        is_user = word.speaker == 0 and preseconds > 0
        if word.start < preseconds:
            continue

        if not segments or segments[-1]['speaker'] != f"SPEAKER_{word.speaker}":
            segments.append({
                'speaker': f"SPEAKER_{word.speaker}",
                'start': word.start - preseconds,
                'end': word.end - preseconds,
                'text': word.punctuated_word,
                'is_user': is_user,
                'person_id': None,
            })
        else:
            segments[-1]['text'] += f" {word.punctuated_word}"
            segments[-1]['end'] = word.end - preseconds

    return segments

def _connect_to_deepgram(client, on_message, on_error, language: str, sample_rate: int, 
                            codec: str, channels: int) -> LiveClient:
    try:
        dg_connection = client.listen.live.v("1")
        dg_connection.on(LiveTranscriptionEvents.Transcript, on_message)
        dg_connection.on(LiveTranscriptionEvents.Error, on_error)

        options = LiveOptions(
            punctuate=True,
            no_delay=True,
            endpointing=100,
            language=language,
            interim_results=False,
            smart_format=True,
            profanity_filter=False,
            diarize=True,
            filler_words=False,
            channels=channels,
            multichannel=channels > 1,
            model='nova-2-general',
            sample_rate=sample_rate,
            encoding='linear16' if codec in ('pcm8', 'pcm16') else 'opus'
        )

        result = dg_connection.start(options)
        print('Deepgram connection started:', result)
        return dg_connection
    except Exception as e:
        raise ConnectionError(f'Could not open Deepgram socket: {e}')