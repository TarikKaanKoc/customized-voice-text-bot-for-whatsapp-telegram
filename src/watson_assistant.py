import os
from dotenv import load_dotenv
from datetime import datetime
from ibm_watson import AssistantV2, ApiException
from ibm_cloud_sdk_core.authenticators import IAMAuthenticator
from audio_services import process_audio_tts
from db import update_conversation_shift, update_context_variables

########################
# Setting Environment Variables and setting up services
load_dotenv() # This is used to enable loading environment variables from the
              # .env file
WA_API_KEY            = os.getenv('WA_API_KEY')
WA_ID                 = os.getenv('WA_ID')
WA_SERVICE_URL        = os.getenv('WA_SERVICE_URL')
DEFAULT_ERROR_MESSAGE = str(
    os.getenv('DEFAULT_ERROR_MESSAGE')).replace("_"," ")

# Configuring and authenticating Watson Assistant
assistant = AssistantV2(
    version='2021-11-27',
    authenticator=IAMAuthenticator(WA_API_KEY))
assistant.set_service_url(WA_SERVICE_URL)

# Setting the media response types of Watson Assistant
media_response = ["audio", "video", "image"]

def create_session_ID():
    try:
        session_ID = assistant.create_session(
            WA_ID
            ).get_result()["session_id"]
        return session_ID
    except ApiException as ex:
        print("WA Method failed with status code "
             + str(ex.code) + ": " + ex.message)

def cleaning_text_formatting(text):
    return ((str(text).replace("_", "")).replace("*", "")).replace("\n", " ")

def filtering_answers_to_return(
    response, user_ID, session_ID, message_is_audio, timestamp):
    if len(response) > 1:
        answers_to_return = []
        all_answers       = []
        for answer in response:
            if answer["response_type"] == "text":
                if message_is_audio:
                    phrase     = cleaning_text_formatting(answer["text"])
                    audio_link = process_audio_tts(user_ID, phrase)
                    all_answers.extend([phrase, audio_link, answer["text"]])
                    answers_to_return.extend([audio_link, answer["text"]])

                else:
                    all_answers.append(answer["text"])
                    answers_to_return.append(answer["text"])

            elif answer["response_type"] in media_response:
                all_answers.append(answer["source"])
                answers_to_return.append(answer["source"])

        update_conversation_shift(
            user_ID, session_ID, 'chatbot', 
            all_answers, timestamp)
            
        return answers_to_return

    elif len(response) == 1:
        if response[0]["response_type"] == "text":
            all_answers       = []
            answers_to_return = []

            if message_is_audio:
                phrase     = cleaning_text_formatting(response[0]["text"])
                audio_link = process_audio_tts(user_ID, phrase)
                all_answers.extend([phrase, audio_link, response[0]["text"]])
                answers_to_return.extend([audio_link, response[0]["text"]])
            else:
                all_answers.append(response[0]["text"])
                answers_to_return.append(response[0]["text"])

            update_conversation_shift(
                user_ID, session_ID, 'chatbot',
                all_answers, timestamp)
            return answers_to_return

        elif response[0]["response_type"] in media_response:
            update_conversation_shift(
                user_ID, session_ID, 'chatbot',
                response[0]["source"], timestamp)
            return response[0]["source"]
    else:
        update_conversation_shift(
            user_ID, session_ID, 'chatbot',
            DEFAULT_ERROR_MESSAGE, timestamp)
        return DEFAULT_ERROR_MESSAGE

def assistant_conversation(message, user_ID, session_ID, message_is_audio):
    try:
        conversation = assistant.message(
            WA_ID,
            session_ID,
            input = {
                        'text': message,
                        'options': {
                            'return_context': True
                        }
                    }
        ).get_result()
        timestamp = datetime.now().utcnow().strftime("%d-%m-%Y_%H:%M:%S:%f")

        if 'user_defined' in conversation['context']['skills']['main skill']:
            context_variables = (
                conversation['context']['skills']['main skill']['user_defined'])
            update_context_variables(
                str(user_ID), session_ID, context_variables)
        
        response = conversation['output']['generic']
        return filtering_answers_to_return(response, user_ID, 
                                           session_ID, message_is_audio, 
                                           timestamp)
    except ApiException as ex:
        if ex.code == 404:
            new_session_ID = create_session_ID()
            return assistant_conversation(
                message, user_ID, new_session_ID, message_is_audio)
        else:
            return("WA Method failed with status code "
                   + str(ex.code) + ": " + ex.message)