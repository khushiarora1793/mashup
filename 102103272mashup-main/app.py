from flask import Flask, request, render_template, redirect, url_for
from flask_mail import Mail, Message
import os
from celery import Celery
from pytube import Search
from moviepy.editor import AudioFileClip
from pydub import AudioSegment

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


app = Flask(__name__)
app.config['CELERY_BROKER_URL'] = 'redis://localhost:6379/0'
app.config['CELERY_RESULT_BACKEND'] = 'redis://localhost:6379/0'
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USERNAME'] = 'aryankhannachd@gmail.com'
app.config['MAIL_PASSWORD'] = ''
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True

mail = Mail(app)
celery = Celery(app.name, broker=app.config['CELERY_BROKER_URL'])
celery.conf.update(app.config)


@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        singer_name = request.form['singer_name']
        number_of_videos = int(request.form['number_of_videos'])
        duration_of_videos = int(request.form['duration_of_videos'])
        email = request.form['email']

        # Send to background task
        process_and_email.delay(singer_name, number_of_videos, duration_of_videos, email)

        return redirect(url_for('success'))
    return render_template('index.html')


@app.route('/success')
def success():
    return 'The processing has started, you will receive an email once it is completed.'


@celery.task
def process_and_email(singer_name, number_of_videos, duration_of_videos, email):
    logger.info(f"Starting process for {singer_name} with {number_of_videos} videos.")
    download_dir = "downloaded_videos"
    try:
        os.makedirs(download_dir, exist_ok=True)
        # logger.info(f"We are here baby.")
        s = Search(singer_name)
        videos = s.results[:number_of_videos]

    except Exception as e:
        logger.error(f"Failed to search or create directory: {e}")
        return

    audio_clips = []

    for i, video in enumerate(videos):
        try:
            video_stream = video.streams.filter(only_audio=True).first()
            video_stream.download(download_dir, filename=f"{singer_name}_{i}.mp4")

            video_path = os.path.join(download_dir, f"{singer_name}_{i}.mp4")
            audio_clip = AudioFileClip(video_path)
            audio_clip = audio_clip.subclip(0, duration_of_videos)
            audio_clip_path = video_path.replace(".mp4", ".mp3")
            audio_clip.write_audiofile(audio_clip_path, codec='mp3')
            audio_clips.append(AudioSegment.from_mp3(audio_clip_path))
            logger.info(f"Processed video {i + 1} for {singer_name}.")
        except Exception as e:
            logger.error(f"Failed to process video {i + 1}: {e}")
            continue  # Skip to the next video if there's an error

    if not audio_clips:
        logger.error("No videos were processed successfully.")
        return

    try:
        merged_audio = audio_clips[0]
        for clip in audio_clips[1:]:
            merged_audio += clip

        output_file_name = f"{singer_name}_merged.mp3"
        merged_audio.export(output_file_name, format="mp3")
        logger.info("Merged audio file created successfully.")
    except Exception as e:
        logger.error(f"Failed to merge audio clips: {e}")
        return

    # Email the file
    try:
        with app.app_context():
            msg = Message(subject="Your merged audio file",
                          sender=app.config['MAIL_USERNAME'],
                          recipients=[email],
                          body="Find attached the merged audio file.")
            with open(output_file_name, 'rb') as fp:
                msg.attach(output_file_name, "audio/mp3", fp.read())
            mail.send(msg)
            logger.info(f"Email sent to {email}.")
    except Exception as e:
        logger.error(f"Failed to send email: {e}")



