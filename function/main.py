import os
import requests
import flask
import functions_framework
from urllib.parse import urlparse, parse_qs
from contextlib import suppress
from bs4 import BeautifulSoup
from youtube_transcript_api import YouTubeTranscriptApi
from langchain_openai.llms import OpenAI
from dotenv import load_dotenv


load_dotenv()


def get_youtube_video_id(url, ignore_playlist=False):
    query = urlparse(url)
    if query.hostname == "youtu.be":
        return query.path[1:]
    if query.hostname in {"www.youtube.com", "youtube.com", "music.youtube.com"}:
        if not ignore_playlist:
            with suppress(KeyError):
                return parse_qs(query.query)["list"][0]
        if query.path == "/watch":
            return parse_qs(query.query)["v"][0]
        if query.path[:7] == "/watch/":
            return query.path.split("/")[1]
        if query.path[:7] == "/embed/":
            return query.path.split("/")[2]
        if query.path[:3] == "/v/":
            return query.path.split("/")[2]


def get_youtube_video_title(url):
    r = requests.get(url)
    soup = BeautifulSoup(r.text, features="html.parser")
    link = soup.find_all(name="title")[0]
    title = str(link)
    title = title.replace("<title>", "")
    title = title.replace("</title>", "")
    return title


def get_youtube_video_transcript(url):
    video_id = get_youtube_video_id(url)
    segments = YouTubeTranscriptApi.get_transcript(video_id)
    text_segments = [segment["text"] for segment in segments]
    transcript = " ".join(text_segments)
    return transcript


def get_prompt(title, transcript, additional_instructions):
    template = """
    You're an assistant that summarizes Youtube videos based on their title and their transcript.

    Hint: Use the title to correct potential typos in the transcript.

    ADDITIONAL INSTRUCTIONS: {additional_instructions}

    TITLE: {title}

    TRANSCRIPT: {transcript}
    """
    prompt = template.format(
        title=title,
        transcript=transcript,
        additional_instructions=additional_instructions,
    )
    return prompt


def summarize_youtube_video(url, additional_instructions):
    transcript = get_youtube_video_transcript(url)
    title = get_youtube_video_title(url)
    llm = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    prompt = get_prompt(title, transcript, additional_instructions)
    summary = llm.predict(prompt)
    data = {
        "url": url,
        "title": title,
        "summary": summary,
        "transcript": transcript,
    }
    return data


@functions_framework.http
def main(request: flask.Request):
    if request.method == "POST":
        url = request.form.get("url")
        additional_instructions = request.form.get("additional_instructions")
        data = summarize_youtube_video(url, additional_instructions)
        return flask.jsonify(data)
    else:
        return "Method Not Allowed", 40()
