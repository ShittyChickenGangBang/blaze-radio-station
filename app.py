from flask import Flask, Response, stream_template
import os
import random
import time
import threading
import io
from elevenlabs.client import ElevenLabs
from elevenlabs import save
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

# Env vars from Railway
ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY')
VOICE_ID = os.getenv('VOICE_ID')
SPOTIFY_PLAYLIST_URL = os.getenv('SPOTIFY_PLAYLIST_URL')

# ElevenLabs client
client = ElevenLabs(api_key=ELEVENLABS_API_KEY) if ELEVENLABS_API_KEY else None

# Fallback 80s tracks (replace with real MP3s in /static/music/ if uploaded)
fallback_tracks = [
    {"artist": "Van Halen", "name": "Jump", "duration": 240},  # seconds
    {"artist": "Def Leppard", "name": "Pour Some Sugar on Me", "duration": 285},
    {"artist": "Bon Jovi", "name": "Livin' on a Prayer", "duration": 260},
    {"artist": "Journey", "name": "Don't Stop Believin'", "duration": 250},
    {"artist": "Mötley Crüe", "name": "Kickstart My Heart", "duration": 270}
]

# Load Spotify playlist or fallback
def load_tracks():
    tracks = fallback_tracks
    if SPOTIFY_PLAYLIST_URL:
        try:
            sp = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials())
            playlist_id = SPOTIFY_PLAYLIST_URL.split('/playlist/')[1].split('?')[0]
            results = sp.playlist_tracks(playlist_id)
            tracks = [{"artist": item['track']['artists'][0]['name'], "name": item['track']['name'], "duration": item['track']['duration_ms'] // 1000} for item in results['items'][:10]]  # Limit for demo
        except Exception as e:
            print(f"Spotify error: {e} - Using fallback")
    random.shuffle(tracks)
    return tracks

tracks = load_tracks()

# Blaze's 1986 banter lines (full prompt baked in)
blaze_lines = [
    "Crank it up, dudes! This is Blaze Baxter on 102.7 The Blaze—totally righteous rock all night!",
    "Killer set from the Rock-Copter! Traffic's bodacious down at the mall—play that Van Halen loud!",
    "Fake caller alert: 'Blaze, spin some Journey for my Trans Am!' You got it, caller 69!",
    "Time check: It's 8:15, weather's sunny with a chance of headbanging. Win Bon Jovi tickets—call 555-ROCK!",
    "This one goes to eleven! 102.7 WBLZ, where the fringe flies and the aviators shine indoors.",
    "Commercial break: Get your leather jacket at Leather World—fringe included! Back to the rock!"
]

def generate_tts(text):
    if not client or not VOICE_ID:
        return AudioSegment.silent(duration=3000)  # Fallback silence
    audio = client.generate(
        text=text,
        voice=VOICE_ID,
        model="eleven_turbo_v2",
        voice_settings={"stability": 0.5, "similarity_boost": 0.75, "style": 0.4, "use_speaker_boost": True}
    )
    audio_bytes = io.BytesIO()
    save(audio, audio_bytes)
    audio_bytes.seek(0)
    return AudioSegment.from_file(audio_bytes, format="mp3")

from pydub import AudioSegment  # For mixing

# Background thread for radio queue
current_audio_bytes = b''
audio_lock = threading.Lock()

def radio_loop():
    global current_audio_bytes
    song_idx = 0
    while True:
        track = tracks[song_idx % len(tracks)]
        # Generate random Blaze banter
        banter = random.choice(blaze_lines) + f" Up next: {track['artist']} - {track['name']}—crank it!"
        tts_audio = generate_tts(banter)
        
        # Simulate song (upload real MP3s to /static/music/{artist}-{name}.mp3 for prod)
        try:
            song_path = f"static/music/{track['artist']}-{track['name']}.mp3"
            song_audio = AudioSegment.from_file(song_path)
        except:
            song_audio = AudioSegment.silent(duration=track['duration'] * 1000)
        
        # Mix: TTS fade-in + song + short fade-out to next
        mixed = tts_audio.fade_out(500).append(song_audio.fade_in(500)).fade_out(1000)
        with audio_lock:
            current_audio_bytes = mixed.export(format="mp3").read()
        
        # Wait for "playtime"
        time.sleep(track['duration'] + 5)  # + buffer
        song_idx += 1

# Start loop
threading.Thread(target=radio_loop, daemon=True).start()

@app.route('/stream.mp3')
def stream():
    def generate():
        while True:
            with audio_lock:
                if current_audio_bytes:
                    yield current_audio_bytes
            time.sleep(0.5)
    return Response(generate(), mimetype='audio/mpeg', headers={
        'Content-Disposition': 'inline; filename="blaze.mp3"',
        'Cache-Control': 'no-cache',
        'Transfer-Encoding': 'chunked'
    })

@app.route('/')
def home():
    return '''
    <h1>🔥 102.7 The Blaze is LIVE! 🔥</h1>
    <p>Blaze Baxter's 1986 album-rock station—crank it worldwide!</p>
    <audio controls autoplay loop>
        <source src="/stream.mp3" type="audio/mpeg">
        Your browser doesn't support audio—use VLC: <a href="/stream.mp3">Direct Stream</a>
    </audio>
    <p>Tune in on phone: Open VLC → Network → Paste your stream URL.</p>
    '''

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
