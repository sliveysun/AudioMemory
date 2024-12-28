import datetime
import asyncio
import os
import time
import wave
from silero_vad import load_silero_vad, read_audio, get_speech_timestamps

class AudioProcessor:
    def __init__(self, channels, sample_rate, save_interval=60, 
                vad_threshold=0.5, audio_data_path="./data/audio/"):
        self.is_client_socket_connected = asyncio.Event()
        self.buffer = bytearray()  # 当前用于接收数据的缓冲区
        self.save_buffer = bytearray()  # 用于保存数据的缓冲区
        self.save_interval = save_interval  # 设置保存文件的时间间隔（秒）
        self.sample_rate = sample_rate # 16000  # 采样率（Hz）
        self.channels = channels # 1  # 声道数（1 = 单声道, 2 = 立体声）
        self.sample_width = 2  # 采样深度，2 表示 16 bit（每个样本 2 字节）
        self.audio_data_path = audio_data_path  # 保存音频文件的路径
        self.vad_threshold = vad_threshold  # VAD 阈值
        self.model = load_silero_vad()

        directory = os.path.dirname(self.audio_data_path)
        if not os.path.exists(directory):
            os.makedirs(directory)
    
    def push_audio_data(self, data):
        self.buffer.extend(data)

    def vad(self, file_path):
        wav = read_audio(file_path)
        speech_timestamps = get_speech_timestamps(wav, self.model)
        return True if speech_timestamps else False

    async def save_to_wav_file_periodically(self):
        """定期将缓冲区中的音频数据保存为 WAV 格式文件"""
        print("start save_to_wav_file_periodically")
        while self.is_client_socket_connected.is_set():
            try:
                # 获取当前时间的时间戳
                dt = datetime.datetime.now()

                # 将 datetime 对象格式化为 '12:14:25.123' 这样的字符串格式（带毫秒）
                timestamp = dt.strftime('%H_%M_%S.%f')[:-3]  # 只保留前三位毫秒数

                await asyncio.sleep(self.save_interval)  # 等待指定的时间间隔

                # 使用 swap 技术来避免锁定：只交换缓冲区
                self.buffer, self.save_buffer = self.save_buffer, self.buffer
                filename = f"audio_{timestamp}.wav.tmp"  # 保存为 .wav 文件
                file_path = self.audio_data_path + filename
                self.save_wav_file(file_path, self.save_buffer)

                # 检查文件是否包含有效语音
                if self.vad(file_path):
                    # 如果有语音活动，将文件重命名为最终的 .wav 文件
                    final_filename = f"audio_{timestamp}.wav"
                    final_file_path = self.audio_data_path + final_filename
                    os.rename(file_path, final_file_path)  # 重命名文件
                    print(f"Renamed file {file_path} to {final_file_path}")
                else:
                    # 如果没有语音活动，创建一个 .empty 文件作为占位
                    empty_filename = f"audio_{timestamp}.empty"
                    empty_file_path = self.audio_data_path + empty_filename

                    # 创建空的 .empty 文件
                    with open(empty_file_path, 'w') as empty_file:
                        empty_file.write('')  # 写入空内容

                    print(f"Created empty file {empty_file_path} to indicate VAD processing with no speech.")

                    # 如果没有语音活动，删除临时文件
                    os.remove(file_path)  # 删除文件
                    print(f"Deleted file {file_path} due to lack of speech")

                # 清空保存缓冲区
                self.save_buffer.clear()
            except Exception as e:
                print(f"got exception : {e}")

        print("end save_to_wav_file_periodically")

    def save_wav_file(self, filename, audio_data):
        """将音频数据保存为指定的 WAV 文件"""
        with wave.open(filename, 'wb') as wf:
            # 设置 WAV 文件的头部信息
            wf.setnchannels(self.channels)  # 设置声道数
            wf.setsampwidth(self.sample_width)  # 设置采样深度（16-bit = 2 字节）
            wf.setframerate(self.sample_rate)  # 设置采样率
            # 写入音频数据
            wf.writeframes(audio_data)
        print(f"Saved audio data to {filename}")
    
    def start_processing(self):
        """启动音频处理"""
        self.is_client_socket_connected.set()
        #asyncio.create_task(self.save_to_wav_file_periodically())

    def stop_processing(self):
        """停止音频处理"""
        self.is_client_socket_connected.clear()