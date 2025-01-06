import requests
import base64
import json
import time
import random
import azure.cognitiveservices.speech as speechsdk
from io import BytesIO
from pydub import AudioSegment
from openai import AzureOpenAI
from flask import Flask, jsonify, render_template, request, make_response
from dotenv import load_dotenv 
import os

app = Flask(__name__)

# Load environment variables from .env file
load_dotenv()

subscription_key = os.getenv('SUBSCRIPTION_KEY')
openai_api = os.getenv('OPENAI_API')
whisper_api_key = os.getenv('WHISPER_API_KEY')
region = "southeastasia"
language = "en-US"
voice = "Microsoft Server Speech Text to Speech Voice (en-US, JennyNeural)"
whisper_url = "https://enfluent-eastus2.openai.azure.com/openai/deployments/enfluent-whisper/audio/translations?api-version=2024-06-01"

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/gettoken", methods=["POST"])
def gettoken():
    fetch_token_url = 'https://%s.api.cognitive.microsoft.com/sts/v1.0/issueToken' %region
    headers = {
        'Ocp-Apim-Subscription-Key': subscription_key
    }
    response = requests.post(fetch_token_url, headers=headers)
    access_token = response.text
    return jsonify({"at":access_token})



@app.route("/ackaud", methods=["POST"])
def ackaud():
    f = request.files['audio']
    audioFile = f
    audio_stream = BytesIO(f.read())

    # Whisper API Request using the in-memory file
    whisper_response = requests.post(
        url=whisper_url,
        files={"file": ("audio_wh.wav", audio_stream, f.content_type)},
        headers={"api-key": whisper_api_key}
    )
    
    if whisper_response.status_code != 200:
        print(f"Whisper API Error: {whisper_response.status_code} - {whisper_response.text}")
        return {"error": "Whisper API transcription failed"}, 500
    whisper_result = whisper_response.json()
    referenceText = whisper_result.get("text", "")
    print(referenceText)
    audio_stream.seek(0)
    #referenceText = "wake up to reality. nothing goes as planned"
    # Convert the uploaded file to WAV format with PCM encoding and 16kHz sample rate for pronunciation assessment
    try:
        # Load the audio file into a pydub AudioSegment
        audio_pron = AudioSegment.from_file(audio_stream)
        audio_pron = audio_pron.set_frame_rate(16000).set_channels(1).set_sample_width(2)

        # Export the audio as WAV to an in-memory file
        wav_buffer = BytesIO()
        audio_pron.export(wav_buffer, format="wav")
        wav_buffer.seek(0)
    except Exception as e:
        return {"error": f"Audio conversion failed: {str(e)}"}, 500

    #  build pronunciation assessment parameters
    pronAssessmentParamsJson = json.dumps({
        "ReferenceText": referenceText,
        "GradingSystem": "HundredMark",
        "Dimension": "Comprehensive",
        "EnableMiscue": True
    })
    pronAssessmentParamsBase64 = base64.b64encode(bytes(pronAssessmentParamsJson, 'utf-8'))
    pronAssessmentParams = str(pronAssessmentParamsBase64, "utf-8")

    # build request
    pronun_url = "https://%s.stt.speech.microsoft.com/speech/recognition/conversation/cognitiveservices/v1?language=%s&usePipelineVersion=0" % (region, language)
    headers_pronun = { 'Accept': 'application/json;text/xml',
                'Connection': 'Keep-Alive',
                'Content-Type': 'audio/wav; codecs=audio/pcm; samplerate=16000',
                'Ocp-Apim-Subscription-Key': subscription_key,
                'Pronunciation-Assessment': pronAssessmentParams,
                'Transfer-Encoding': 'chunked',
                'Expect': '100-continue' }

    def get_chunk(audio_source, chunk_size=1024):
        while True:
            #time.sleep(chunk_size / 32000) # to simulate human speaking rate
            chunk = audio_source.read(chunk_size)
            if not chunk:
                break
            yield chunk

    response_pronun = requests.post(url=pronun_url, data=get_chunk(wav_buffer), headers=headers_pronun)
    if response_pronun.status_code != 200:
        print(f"Pronunciation API Error: {response_pronun.status_code} - {response_pronun.text}")
        return {"error": f"Pronunciation API call failed with status {response_pronun.status_code}"}, 500

    response_pronun = response_pronun.json()
    audioFile.close()
    pronunScore = response_pronun["NBest"][0]["PronScore"]
    print(pronunScore)

    client = AzureOpenAI(
    azure_endpoint = "https://enfluent-eastus2.openai.azure.com/",  # Your Azure OpenAI endpoint
    api_key=openai_api,  # Your Azure OpenAI API key
    api_version="2023-03-15-preview"
    )


    # Sending a request to the Azure OpenAI API to evaluate grammar and lexical resources
    response = client.chat.completions.create(
        model="enfluent-gpt-4o",  # Use the correct model deployed on your Azure environment
        messages=[
            {"role": "system", "content": "You are a language expert. Your task is to evaluate the grammar and lexical resources of the provided text. and given the pronunciation score, determine the IELTS band score."},
            {"role": "user", "content": f"I would like you to evaluate the IELTS bad score for whole speech based on the grammar and lexical resources aspect of the following speech transcript:\n\n{pronunScore}\n\n and following pronunciation of out of 100\n\n{referenceText}\n\n and output only a single value of the IELTS band score. possible output values are 0, 0.5, 1, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5, 5.5, 6, 6.5, 7, 7.5, 8.0, 8.5, 9, 9.5"  }
        ]
    )
    print(response)

    ielts_band_score = response.choices[0].message.content.strip()

    # print(whisper_result)
    # print(response_pronun)
    return {
        "whisper_result": whisper_result,
        "pronunciation_result": response_pronun,
        'IELTS_band_score': ielts_band_score
    }




@app.route("/gettts", methods=["POST"])
def gettts():
    reftext = request.form.get("reftext")
    # Creates an instance of a speech config with specified subscription key and service region.
    speech_config = speechsdk.SpeechConfig(subscription=subscription_key, region=region)
    speech_config.speech_synthesis_voice_name = voice

    offsets=[]

    def wordbound(evt):
        offsets.append( evt.audio_offset / 10000)

    speech_synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=None)
    speech_synthesizer.synthesis_word_boundary.connect(wordbound)

    result = speech_synthesizer.speak_text_async(reftext).get()
    # Check result
    if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        #print("Speech synthesized for text [{}]".format(reftext))
        #print(offsets)
        audio_data = result.audio_data
        #print(audio_data)
        #print("{} bytes of audio data received.".format(len(audio_data)))
        
        response = make_response(audio_data)
        response.headers['Content-Type'] = 'audio/wav'
        response.headers['Content-Disposition'] = 'attachment; filename=sound.wav'
        # response.headers['reftext'] = reftext
        response.headers['offsets'] = offsets
        return response
        
    elif result.reason == speechsdk.ResultReason.Canceled:
        cancellation_details = result.cancellation_details
        print("Speech synthesis canceled: {}".format(cancellation_details.reason))
        if cancellation_details.reason == speechsdk.CancellationReason.Error:
            print("Error details: {}".format(cancellation_details.error_details))
        return jsonify({"success":False})

@app.route("/getttsforword", methods=["POST"])
def getttsforword():
    word = request.form.get("word")

    # Creates an instance of a speech config with specified subscription key and service region.
    speech_config = speechsdk.SpeechConfig(subscription=subscription_key, region=region)
    speech_config.speech_synthesis_voice_name = voice

    speech_synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=None)

    result = speech_synthesizer.speak_text_async(word).get()
    # Check result
    if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:

        audio_data = result.audio_data
        response = make_response(audio_data)
        response.headers['Content-Type'] = 'audio/wav'
        response.headers['Content-Disposition'] = 'attachment; filename=sound.wav'
        # response.headers['word'] = word
        return response
        
    elif result.reason == speechsdk.ResultReason.Canceled:
        cancellation_details = result.cancellation_details
        print("Speech synthesis canceled: {}".format(cancellation_details.reason))
        if cancellation_details.reason == speechsdk.CancellationReason.Error:
            print("Error details: {}".format(cancellation_details.error_details))
        return jsonify({"success":False})

if __name__ == "__main__":
    app.run(debug=True)