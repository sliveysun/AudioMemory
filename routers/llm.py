import os
from openai import OpenAI
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field

from models.chat import Message
from models.facts import Fact
from models.memory import Structured, MemoryPhoto, CategoryEnum, Memory
from models.plugin import Plugin
from models.transcript_segment import TranscriptSegment
from .facts import get_prompt_facts

import tencentcloud.common.exception.tencent_cloud_sdk_exception as TencentCloudSDKException
from tencentcloud.common import credential
from tencentcloud.nlp.v20190408 import nlp_client, models

client = OpenAI(
  api_key=os.environ.get('TENCENT_HUNYUAN_API_KEY'),  # this is also the default, it can be omitted
  base_url=os.environ.get("TENCENT_HUNYUAN_API_BASE")
)

# **********************************************
# ************* MEMORY PROCESSING **************
# **********************************************

def call_openai_embedding(text: str):
    """Helper function to call OpenAI's chat model directly"""
    response = client.embeddings.create(
        model="hunyuan-embedding",  # You can change this to the model you would like to use
        input=text
    )
    return response.data[0].embedding

def call_openai_chat(prompt: str):
    """Helper function to call OpenAI's chat model directly"""
    response = client.chat.completions.create(
        model="hunyuan-pro",  # You can change this to the model you would like to use
        messages=[
            {"role": "user", "content": prompt}
        ]
    )
    #print(f"response.choices[0].message.content : {response.choices[0].message.content}")
    return response.choices[0].message.content

def generate_embedding(content: str) -> List[float]:
    return call_openai_embedding(content)
    #return call_openai_chat(content)

def should_discard_memory(transcript: str) -> bool:
    if len(transcript.split(' ')) > 100:
        return False
    
    prompt = f'''
    You will be given a conversation transcript, and your task is to determine if the conversation is worth storing as a memory or not.
    It is not worth storing if there are no interesting topics, facts, or information, in that case, output {{'discard': False/True}}
    
    Transcript: ```{transcript}```
    '''
    
    try:
        response = call_openai_chat(prompt)
        result = eval(response)  # Assuming the response is in the form of a dict like {'discard': True/False}
        return result.get('discard', False)
    
    except Exception as e:
        print(f'Error determining memory discard: {e}')
        return False


def get_transcript_structure(transcript: str, started_at: datetime, language_code: str) -> Structured:
    prompt = f'''
    Your task is to provide structure and clarity to the recording transcription of a conversation.
    The conversation language is {language_code}. Use Chinese for your response.
    
    For the title, use the main topic of the conversation.
    For the overview, condense the conversation into a summary with the main topics discussed, make sure to capture the key points and important details from the conversation.
    For the action items, include a list of commitments, specific tasks or actionable next steps from the conversation. Specify which speaker is responsible for each action item. 
    For the category, classify the conversation into one of the available categories.
    For Calendar Events, include a list of events extracted from the conversation, that the user must have on his calendar. For date context, this conversation happened on {started_at}.
    
    Ensure that:
    - Boolean values are formatted as Python `True` or `False` (not `true` or `false`).

    Transcript: ```{transcript}```

    The response is in the form of a dict to match python class Structured which is defined below.

    class CategoryEnum(str, Enum):
        personal = 'personal'
        education = 'education'
        health = 'health'
        finance = 'finance'
        legal = 'legal'
        philosophy = 'philosophy'
        spiritual = 'spiritual'
        science = 'science'
        entrepreneurship = 'entrepreneurship'
        parenting = 'parenting'
        romance = 'romantic'
        travel = 'travel'
        inspiration = 'inspiration'
        technology = 'technology'
        business = 'business'
        social = 'social'
        work = 'work'
        sports = 'sports'
        politics = 'politics'
        literature = 'literature'
        history = 'history'
        other = 'other'

    class ActionItem(BaseModel):
        description: str
        completed: bool = False

    class Event(BaseModel):
        title: str
        description: str
        start: datetime
        duration: int = Field(description="The duration of the event in minutes", default=30)
        created: bool = False

    class Structured(BaseModel):
        title: str
        overview: str
        emoji: str
        category: CategoryEnum
        action_items: List[ActionItem]
        events: List[Event]

    '''
    
    try:
        print(f"transcript: {transcript}")
        response = call_openai_chat(prompt)
        print(f"response: {response}")
        result = eval(response)  # Assuming the response is in the form of a dict like {'title': ..., 'overview': ..., 'category': ...}
        print(f"result: {result}")
        return Structured(**result)
    
    except Exception as e:
        print(f'Error structuring transcript: {e}')
        return None



class SummaryOutput(BaseModel):
    summary: str = Field(description="The extracted content, maximum 500 words.")


def chunk_extraction(segments: List[TranscriptSegment], topics: List[str]) -> str:
    content = TranscriptSegment.segments_as_string(segments)
    prompt = f'''
    You are an experienced detective, your task is to extract the key points of the conversation related to the topics you were provided.
    You will be given a conversation transcript of a low quality recording, and a list of topics.

    Include the most relevant information about the topics, people mentioned, events, locations, facts, phrases, and any other relevant information.
    It is possible that the conversation doesn't have anything related to the topics, in that case, output an empty string.

    Conversation:
    {content}

    Topics: {topics}
    '''.strip()

    try:
        response = call_openai_chat(prompt)
        result = eval(response)  # Assuming the response is a dict with 'summary'
        return result.get('summary', "")
    
    except Exception as e:
        print(f'Error extracting chunk: {e}')
        return ""

# **************************************************
# ************* RETRIEVAL (EMOTIONAL) **************
# **************************************************

def retrieve_memory_context_params(memory: Memory) -> List[str]:
    transcript = memory.get_transcript(False)
    if len(transcript) == 0:
        return []

    prompt = f'''
    Based on the current transcript of a conversation.

    Your task is to extract the correct and most accurate context in the conversation, to be used to retrieve more information.
    Provide a list of topics in which the current conversation needs context about, in order to answer the most recent user request.

    Conversation:
    {transcript}
    '''.strip()

    try:
        response = call_openai_chat(prompt)
        result = eval(response)  # Assuming the response is a dict with 'topics'
        return result.get('topics', [])
    
    except Exception as e:
        print(f'Error retrieving memory context params: {e}')
        return []


# **********************************
# ************* FACTS **************
# **********************************

def new_facts_extractor(uid: str, segments: List[TranscriptSegment]) -> List[Fact]:
    user_name, facts_str = get_prompt_facts(uid)
    print(f"prompt facts : {facts_str}")

    content = TranscriptSegment.segments_as_string(segments, user_name=user_name)
    if not content or len(content) < 100:  # less than 100 chars, probably nothing
        return []

    prompt = f'''
        You are an experienced detective, whose job is to create detailed profile personas based on conversations.

        You will be given a low-quality audio recording transcript of a conversation or something {user_name} listened to, and a list of existing facts we know about {user_name}.
        Your task is to determine **new** facts, preferences, and interests about {user_name}, based on the transcript.

        Make sure these facts are:
        - Relevant, and are not repetitive or similar to the existing facts we know about {user_name}. It is preferred to have breadth rather than too much depth on specifics.
        - Each fact must be formatted as a valid JSON string that follows the structure of the `Fact` object.
        - The `content` field must be in the same language as the Conversation.
        - Each fact must include both `content` (which describes the fact) and `category` (which classifies the fact into one of the categories: hobbies, lifestyle, interests, habits, work, skills, or other).
        - Use a format like `{{"content": "{user_name} 喜欢在周末打网球 or {user_name} likes play tennis in weekend。", "category": "hobbies"}}` for each fact.
        - The `category` field must be one of the valid categories: **hobbies, lifestyle, interests, habits, work, skills, or other**. The category names must be in **English**.
        - Non sex assignable: do not use gendered pronouns such as "he", "she", "his", or "her", as we don't know if {user_name} is male or female.
        - Only include **new** facts, and ensure they are **not** repetitive or similar to the existing facts.

        This way we can create a more accurate profile.

        ### Output Format:
        - You **must** return the result as a **valid JSON** object in the following format:
        {{
            "facts": [
                {{
                    "content": "Fact 1 about {user_name}",
                    "category": "hobbies"
                }},
                {{
                    "content": "Fact 2 about {user_name}",
                    "category": "interests"
                }},
                {{
                    "content": "Fact 3 about {user_name}",
                    "category": "other"
                }}
            ]
        }}

        - If no new facts are found, return:
        {{
            "facts": []
        }}

        Existing Facts that were: {facts_str}

        Conversation:
        {content}
    '''.strip()

    try:
        response = call_openai_chat(prompt)
        print(f"response:{response}")
        result = eval(response)  # Assuming the response is a dict with 'facts'
        facts_data = result.get('facts', [])
        facts = [Fact(**fact_data) for fact_data in facts_data]
        return facts
    
    except Exception as e:
        print(f'Error extracting new facts: {e}')
        return []


'''

class DiscardMemory(BaseModel):
    discard: bool = Field(description="If the memory should be discarded or not")

class SpeakerIdMatch(BaseModel):
    speaker_id: int = Field(description="The speaker id assigned to the segment")


def get_plugin_result(transcript: str, plugin: Plugin) -> str:
    prompt = f''
    Your are an AI with the following characteristics:
    Name: {plugin.name}, 
    Description: {plugin.description},
    Task: {plugin.memory_prompt}

    Note: It is possible that the conversation you are given, has nothing to do with your task, \
    in that case, output an empty string. (For example, you are given a business conversation, but your task is medical analysis)

    Conversation: ```{transcript.strip()}```,

    Output your response in plain text, without markdown.
    ''

    try:
        return call_openai_chat(prompt)
    except Exception as e:
        print(f'Error getting plugin result: {e}')
        return ''


# *******************************************
# ************* POSTPROCESSING **************
# *******************************************


# **************************************************
# ************* EXTERNAL INTEGRATIONS **************
# **************************************************

def summarize_experience_text(text: str) -> Structured:
    prompt = f''
    The user sent a text of their own experiences or thoughts, and wants to create a memory from it.

    For the title, use the main topic of the experience or thought.
    For the overview, condense the descriptions into a brief summary with the main topics discussed, make sure to capture the key points and important details.
    For the category, classify the scenes into one of the available categories.
    
    Text: ```{text}```
    ''
    
    response = call_openai_chat(prompt)
    return Structured(**eval(response))


# ****************************************
# ************* CHAT BASICS **************
# ****************************************
def initial_chat_message(uid: str, plugin: Optional[Plugin] = None) -> str:
    user_name, facts_str = get_prompt_facts(uid)
    if plugin is None:
        prompt = f''
        You are an AI with the following characteristics:
        Name: Friend, 
        Personality/Description: A friendly and helpful AI assistant that aims to make your life easier and more enjoyable.
        Task: Provide assistance, answer questions, and engage in meaningful conversations.
        
        You are made for {user_name}, {facts_str}

        Send an initial message to start the conversation, make sure this message reflects your personality, \
        humor, and characteristics.

        Output your response in plain text, without markdown.
        ''
    else:
        prompt = f''
        You are an AI with the following characteristics:
        Name: {plugin.name}, 
        Personality/Description: {plugin.chat_prompt},
        Task: {plugin.memory_prompt}
        
        You are made for {user_name}, {facts_str}

        Send an initial message to start the conversation, make sure this message reflects your personality, \
        humor, and characteristics.

        Output your response in plain text, without markdown.
        ''
    prompt = prompt.replace('    ', '').strip()
    return llm.invoke(prompt).content

def obtain_emotional_message(uid: str, memory: Memory, context: str, emotion: str) -> str:
    user_name, facts_str = get_prompt_facts(uid)
    transcript = memory.get_transcript(False)
    prompt = f"""
    You are a thoughtful and encouraging Friend. 
    Your best friend is {user_name}, {facts_str}
    
    {user_name} just finished a conversation where {user_name} experienced {emotion}.
    
    You will be given the conversation transcript, and context from previous related conversations of {user_name}.
    
    Remember, {user_name} is feeling {emotion}.
    Use what you know about {user_name}, the transcript, and the related context, to help {user_name} overcome this feeling \
    (if bad), or celebrate (if good), by giving advice, encouragement, support, or suggesting the best action to take.
    
    Make sure the message is nice and short, no more than 20 words.
    
    Conversation Transcript:
    {transcript}

    Context:
    ```
    {context}
    ```
    """.strip()

    try:
        response = call_openai_chat(prompt)
        return response  # Assuming the response is directly the emotional message
    except Exception as e:
        print(f'Error obtaining emotional message: {e}')
        return ""


def qa_rag(uid: str, context: str, messages: List[Message], plugin: Optional[Plugin] = None) -> str:
    conversation_history = Message.get_messages_as_string(
        messages, use_user_name_if_available=True, use_plugin_name_if_available=True
    )
    user_name, facts_str = get_prompt_facts(uid)

    plugin_info = ""
    if plugin:
        plugin_info = f"Your name is: {plugin.name}, and your personality/description is '{plugin.description}'.\nMake sure to reflect your personality in your response.\n"

    prompt = f"""
    You are an assistant for question-answering tasks. 
    You are made for {user_name}, {facts_str}
    
    Use what you know about {user_name}, the following pieces of retrieved context and the chat history to continue the chat.
    If you don't know the answer, just say that there's no available information about it. Use three sentences maximum and keep the answer concise.
    If the message doesn't require context, it will be empty, so follow-up the conversation casually.
    If there's not enough information to provide a valuable answer, ask the user for clarification questions.
    {plugin_info}
    
    Chat History:
    {conversation_history}

    Context:
    ```
    {context}
    ```
    Answer:
    """.strip()

    try:
        response = call_openai_chat(prompt)
        return response  # Assuming the response is directly the answer
    except Exception as e:
        print(f'Error during QA: {e}')
        return ""


'''
