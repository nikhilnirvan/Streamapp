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

# Home page
@app.route("/")
def index():
    token_info = get_saved_token()
    spotify_info = None
    top_tracks = []

    if token_info:
        try:
            sp = Spotify(auth=token_info["access_token"])
            spotify_info = sp.current_user()
            top_tracks = sp.current_user_top_tracks(limit=5)["items"]
        except Exception as e:
            spotify_info = None

    html = """
    <html>
    <head><title>Spotify Stats Viewer</title></head>
    <body style="font-family:sans-serif; padding:20px;">
    <h2>Spotify Stats App</h2>
    {% if spotify %}
      <p><b>Logged in as:</b> {{ spotify['display_name'] }}</p>
      <img src="{{ spotify['images'][0]['url'] if spotify['images'] else '' }}" width="120"/><br><br>
      <p>Followers: {{ spotify['followers']['total'] }}</p>
      <p><a href="{{ spotify['external_urls']['spotify'] }}" target="_blank">View Profile on Spotify</a></p>
      <hr/>
      <h3>Your Top Tracks:</h3>
      <ul>
        {% for t in top_tracks %}
          <li>{{ t['name'] }} — {{ t['artists'][0]['name'] }}</li>
        {% endfor %}
      </ul>
      <hr/>
      <a href="/logout">Log out</a>
    {% else %}
      <a href="/login_spotify">Connect to Spotify</a>
    {% endif %}
    </body></html>
    """
    return render_template_string(html, spotify=spotify_info, top_tracks=top_tracks)

# Start Spotify login
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

# Spotify callback
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

# Logout
@app.route("/logout")
def logout():
    clear_token()
    return redirect("/")

# Save / Get token helpers
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


# Example API endpoint to get artist details
@app.route("/api/spotify/artist/<artist_id>")
def get_artist(artist_id):
    token_info = get_saved_token()
    if not token_info:
        return jsonify({"error": "not logged in"}), 401
    sp = Spotify(auth=token_info["access_token"])
    artist = sp.artist(artist_id)
    return jsonify(artist)

# Run Flask + open webview
def start_flask():
    app.run(host="0.0.0.0", port=8080, debug=True, use_reloader=False)

if __name__ == "__main__":
    threading.Thread(target=start_flask, daemon=True).start()
    time.sleep(1)
    webview.create_window("Spotify Stats App", "http://localhost:8080", width=900, height=700)
    webview.start()
