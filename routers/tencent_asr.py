import os
from datetime import datetime
import json
from libs.tencent.common import credential
from libs.tencent.asr import speech_recognizer

tencent_asr_app_id: str = os.environ.get("TENCENT_ASR_APPID")
tencent_asr_secret_key: str = os.environ.get("TENCENT_ASR_SECRET_KEY")
tencent_asr_secret_id: str = os.environ.get("TENCENT_ASR_SECRET_ID")

ENGINE_MODEL_TYPE = "16k_zh"


def get_tencent_asr_client(sentence_changed_callbacck, sentence_end_callback):
    listener = TencentASRListener(sentence_changed_callbacck, sentence_end_callback)
    credential_var = credential.Credential(tencent_asr_secret_id, tencent_asr_secret_key)
    recognizer = speech_recognizer.SpeechRecognizer(
        tencent_asr_app_id, credential_var, ENGINE_MODEL_TYPE,  listener)
    recognizer.set_filter_modal(1)
    recognizer.set_filter_punc(1)
    recognizer.set_filter_dirty(1)
    recognizer.set_voice_format(1)
    recognizer.set_word_info(1)
    #recognizer.set_nonce("12345678")
    recognizer.set_convert_num_mode(1)
    recognizer.set_need_vad(1)
    #recognizer.set_vad_silence_time(600)
    recognizer.start()


    print("Connecting to Tencent ASR service")
    return recognizer

class TencentASRListener(speech_recognizer.SpeechRecognitionListener):
    def __init__(self, sentence_changed_callbacck, sentence_end_callback):
        self.sentence_changed_callbacck = sentence_changed_callbacck
        self.sentence_end_callback = sentence_end_callback

    def on_recognition_start(self, response):
        print("%s|%s|OnRecognitionStart\n" % (
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"), response['voice_id']))

    def on_sentence_begin(self, response):
        pass
        #rsp_str = json.dumps(response, ensure_ascii=False)
        #print("%s|%s|OnRecognitionSentenceBegin, rsp %s\n" % (
        #    datetime.now().strftime("%Y-%m-%d %H:%M:%S"), response['voice_id'], rsp_str))

    def on_recognition_result_change(self, response):
        if response and "result" in response and "voice_text_str" in response["result"]:
            sentence = response["result"]["voice_text_str"]
        
        if not sentence:
            return

        try:
            self.sentence_changed_callbacck(sentence)
        except Exception as e:
            print(f"got exception in result change : {e}")
        
        #rsp_str = json.dumps(response, ensure_ascii=False)
        #print("%s|%s|OnResultChange, rsp %s\n" % (datetime.now().strftime(
        #    "%Y-%m-%d %H:%M:%S"), response['voice_id'], rsp_str))

    def on_sentence_end(self, response):
        if not response or "result" not in response:
            return

        result = response["result"]
        if "voice_text_str" not in result or "start_time" not in result or "end_time" not in result:
            return

        segment = {
            "start" : result["start_time"],
            "end" : result["end_time"],
            "text" : result["voice_text_str"],
            "is_user" : False
        }
        
        try:
            self.sentence_end_callback(segment)
        except Exception as e:
            print(f"got exception in sentence end : {e}")

        #rsp_str = json.dumps(response, ensure_ascii=False)
        #print("%s|%s|OnSentenceEnd, rsp %s\n" % (datetime.now().strftime(
        #    "%Y-%m-%d %H:%M:%S"), response['voice_id'], rsp_str))

    def on_recognition_complete(self, response):
        print("%s|%s|OnRecognitionComplete\n" % (
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"), response['voice_id']))

    def on_fail(self, response):
        rsp_str = json.dumps(response, ensure_ascii=False)
        print(f"Tencent ASR Error: {rsp_str}")
        print("%s|%s|OnFail,message %s\n" % (datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"), response['voice_id'], rsp_str))