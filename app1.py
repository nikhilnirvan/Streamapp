import os
import sqlite3
import time
import threading
import webview
from flask import Flask, redirect, request, session, render_template_string, jsonify
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv

# Load environment variables
from dotenv import load_dotenv
load_dotenv()


app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "dev_secret")

# Spotify credentials from .env
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI", "http://localhost:8080/spotify_callback")

print("Spotify ID:", SPOTIFY_CLIENT_ID)
print("Spotify Secret:", SPOTIFY_CLIENT_SECRET)

# Database setup
DB = "spotify_users.sqlite"
def init_db():
    with sqlite3.connect(DB) as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            spotify_access TEXT,
            spotify_refresh TEXT,
            spotify_expires_at INTEGER
        )""")
init_db()

# Helper functions for token management
def save_token(token_info):
    with sqlite3.connect(DB) as conn:
        conn.execute("DELETE FROM users")
        conn.execute("INSERT INTO users (spotify_access, spotify_refresh, spotify_expires_at) VALUES (?, ?, ?)",
                     (token_info['access_token'], token_info['refresh_token'], token_info['expires_at']))
        conn.commit()

def get_saved_token():
    with sqlite3.connect(DB) as conn:
        cur = conn.execute("SELECT spotify_access, spotify_refresh, spotify_expires_at FROM users LIMIT 1")
        row = cur.fetchone()
        if row:
            return {"access_token": row[0], "refresh_token": row[1], "expires_at": row[2]}
        return None

def clear_token():
    with sqlite3.connect(DB) as conn:
        conn.execute("DELETE FROM users")
        conn.commit()

# -------------------------------
# Routes
# -------------------------------

@app.route("/")
def index():
    token_info = get_saved_token()
    artist_info = None
    top_tracks = []
    user_name = None
    artist_id = os.getenv("ARTIST_ID")  # 👈 Use your artist ID from .env

    if token_info:
        try:
            sp = Spotify(auth=token_info["access_token"])
            user = sp.current_user()
            user_name = user.get("display_name")

            if artist_id:
                artist_info = sp.artist(artist_id)
                top_tracks = sp.artist_top_tracks(artist_id)["tracks"]
            else:
                # fallback to search by display name if artist_id not set
                results = sp.search(q=f"artist:{user_name}", type="artist", limit=1)
                if results["artists"]["items"]:
                    artist_info = results["artists"]["items"][0]
                    artist_id = artist_info["id"]
                    top_tracks = sp.artist_top_tracks(artist_id)["tracks"]

        except Exception as e:
            print("Error fetching artist data:", e)

    html = """
    <html>
    <head><title>Spotify Artist Stats App</title></head>
    <body style="font-family:sans-serif; padding:20px;">
    <h2>Spotify Artist Dashboard</h2>

    {% if artist %}
        <h3>Welcome, {{ user_name }}</h3>
        <img src="{{ artist['images'][0]['url'] if artist['images'] else '' }}" width="150"/><br><br>
        <p><b>Artist:</b> {{ artist['name'] }}</p>
        <p><b>Followers:</b> {{ artist['followers']['total'] }}</p>
        <p><b>Popularity:</b> {{ artist['popularity'] }} / 100</p>
        <p><b>Genres:</b> {{ ', '.join(artist['genres']) }}</p>
        <p><a href="{{ artist['external_urls']['spotify'] }}" target="_blank">View on Spotify</a></p>
        <hr/>
        <h3>Top Tracks:</h3>
        <ul>
        {% for t in top_tracks %}
          <li>{{ t['name'] }} — Popularity: {{ t['popularity'] }}</li>
        {% endfor %}
        </ul>
        <hr/>
        <a href="/logout">Log out</a>
    {% elif user_name %}
        <p>Welcome, {{ user_name }}. No artist profile found for your name.</p>
        <p>You can manually view an artist by adding their ID to the URL:</p>
        <p><code>/artist_stats/&lt;artist_id&gt;</code></p>
        <a href="/logout">Log out</a>
    {% else %}
        <a href="/login_spotify">Connect Spotify</a>
    {% endif %}
    </body></html>
    """
    return render_template_string(html, artist=artist_info, top_tracks=top_tracks, user_name=user_name)

# Spotify login
@app.route("/login_spotify")
def login_spotify():
    sp_oauth = SpotifyOAuth(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scope="user-read-private user-read-email user-top-read",
        cache_path=None
    )
    print("Redirect URI in use:", REDIRECT_URI)
    auth_url = sp_oauth.get_authorize_url()
    return redirect(auth_url)

# Callback from Spotify
@app.route("/spotify_callback")
def spotify_callback():
    code = request.args.get("code")
    if not code:
        return "Error: no code returned", 400

    sp_oauth = SpotifyOAuth(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scope="user-read-private user-read-email user-top-read",
        cache_path=None
    )
    token_info = sp_oauth.get_access_token(code, as_dict=True)
    save_token(token_info)
    return redirect("/")

@app.route("/logout")
def logout():
    clear_token()
    return redirect("/")

# Manual artist stats route
@app.route("/artist_stats/<artist_id>")
def artist_stats(artist_id):
    token_info = get_saved_token()
    if not token_info:
        return "You must connect to Spotify first.", 401

    sp = Spotify(auth=token_info["access_token"])
    artist = sp.artist(artist_id)
    top_tracks_data = sp.artist_top_tracks(artist_id)["tracks"]

    html = f"""
    <html>
    <head><title>{artist['name']} - Stats</title></head>
    <body style="font-family:sans-serif; padding:20px;">
    <h2>{artist['name']}</h2>
    <img src="{artist['images'][0]['url'] if artist['images'] else ''}" width="150"/><br>
    <p><b>Followers:</b> {artist['followers']['total']:,}</p>
    <p><b>Popularity:</b> {artist['popularity']} / 100</p>
    <p><b>Genres:</b> {', '.join(artist['genres'])}</p>
    <p><a href="{artist['external_urls']['spotify']}" target="_blank">Open on Spotify</a></p>
    <hr/>
    <h3>Top Tracks:</h3>
    <ul>
    {''.join([f"<li>{t['name']} — Popularity: {t['popularity']}</li>" for t in top_tracks_data])}
    </ul>
    <a href="/">⬅ Back</a>
    </body></html>
    """
    return html

# Run Flask + Webview
def start_flask():
    app.run(host="0.0.0.0", port=8080, debug=True, use_reloader=False)

if __name__ == "__main__":
    threading.Thread(target=start_flask, daemon=True).start()
    time.sleep(1)
    webview.create_window("Spotify Artist Stats App", "http://localhost:8080", width=900, height=700)
    webview.start()
