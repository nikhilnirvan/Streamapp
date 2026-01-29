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

# Spotify credentials
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI", "http://localhost:8080/spotify_callback")

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

# Token management
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
# ROUTES
# -------------------------------

@app.route("/")
def index():
    token_info = get_saved_token()
    user_name = None
    spotify_info = None

    if token_info:
        try:
            sp = Spotify(auth=token_info["access_token"])
            spotify_info = sp.current_user()
            user_name = spotify_info.get("display_name")
        except Exception as e:
            print("Error fetching Spotify user:", e)

    html = """
    <html>
    <head><title>Spotify Artist Search App</title></head>
    <body style="font-family:sans-serif; padding:20px;">
    <h2>Spotify Artist Dashboard</h2>

    {% if spotify %}
        <p>Welcome, <b>{{ spotify['display_name'] }}</b>!</p>
        <img src="{{ spotify['images'][0]['url'] if spotify['images'] else '' }}" width="120"/><br>
        <p><a href="/logout">Log out</a></p>
        <hr/>
        <h3>Search Artist:</h3>
        <form action="/search" method="get">
            <input type="text" name="artist_name" placeholder="Enter artist name" required style="padding:6px;width:250px;">
            <input type="submit" value="Search" style="padding:6px;">
        </form>
        <p>or view directly by ID: <code>/artist_stats/&lt;artist_id&gt;</code></p>
    {% else %}
        <a href="/login_spotify">Connect Spotify</a>
    {% endif %}
    </body></html>
    """
    return render_template_string(html, spotify=spotify_info, user_name=user_name)

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
    auth_url = sp_oauth.get_authorize_url()
    print("Redirect URI in use:", REDIRECT_URI)
    return redirect(auth_url)

# Callback
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

# Search route
@app.route("/search")
def search_artist():
    token_info = get_saved_token()
    if not token_info:
        return redirect("/")

    artist_name = request.args.get("artist_name", "")
    if not artist_name:
        return redirect("/")

    sp = Spotify(auth=token_info["access_token"])
    results = sp.search(q=f"artist:{artist_name}", type="artist", limit=1)

    if not results["artists"]["items"]:
        return f"<p>No artist found for '{artist_name}'.</p><a href='/'>⬅ Back</a>"

    artist = results["artists"]["items"][0]
    artist_id = artist["id"]
    return redirect(f"/artist_stats/{artist_id}")

# Artist stats route
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

@app.route("/logout")
def logout():
    clear_token()
    return redirect("/")

# Run Flask + Webview
def start_flask():
    app.run(host="0.0.0.0", port=8080, debug=True, use_reloader=False)

if __name__ == "__main__":
    threading.Thread(target=start_flask, daemon=True).start()
    time.sleep(1)
    webview.create_window("Spotify Artist Search App", "http://localhost:8080", width=900, height=700)
    webview.start()
