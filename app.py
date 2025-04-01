from flask import Flask, render_template, request, redirect, url_for, session, flash
import os
import sqlite3
import uuid
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy
app = Flask(__name__)

app.config['UPLOAD_FOLDER'] = 'static/uploads'
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads')
app.secret_key = os.urandom(24)  

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session: 
            return redirect(url_for('login'))  
        return f(*args, **kwargs)  
    return decorated_function


def get_db_connection():
    conn = sqlite3.connect('database.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row  
    return conn

def create_db():
    conn = get_db_connection()
    
def create_db():
    conn = get_db_connection()
    conn.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL UNIQUE,
        password TEXT NOT NULL,
        username TEXT NOT NULL UNIQUE,
        nickname TEXT NOT NULL,
        profile_photo TEXT,
        bio TEXT,
        is_admin BOOLEAN NOT NULL DEFAULT 0)''')

    conn.execute('''CREATE TABLE IF NOT EXISTS images (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT NOT NULL,
        user_id INTEGER NOT NULL,
        description TEXT,
        likes INTEGER DEFAULT 0,
        FOREIGN KEY(user_id) REFERENCES users(id))''')

    conn.execute('''CREATE TABLE IF NOT EXISTS likes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        image_id INTEGER NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(image_id) REFERENCES images(id),
        UNIQUE(user_id, image_id)  -- Aynı kullanıcı aynı resmi iki kez beğenemesin
    )''')


    conn.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL,
            receiver_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(sender_id) REFERENCES users(id),
            FOREIGN KEY(receiver_id) REFERENCES users(id)
        )
    ''')

    conn.execute('''
        CREATE TABLE IF NOT EXISTS followers (
            follower_id INTEGER NOT NULL,
            followed_id INTEGER NOT NULL,
            PRIMARY KEY(follower_id, followed_id),
            FOREIGN KEY(follower_id) REFERENCES users(id),
            FOREIGN KEY(followed_id) REFERENCES users(id)
        )
    ''')

    conn.commit()
    conn.close()





ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def generate_unique_filename(prefix, original_filename):
    extension = original_filename.rsplit('.', 1)[1].lower()  
    unique_filename = f"{prefix}_{uuid.uuid4().hex}.{extension}"  
    return unique_filename

@app.route('/')
def index():
    conn = get_db_connection()
    images = conn.execute('''
        SELECT images.id, images.filename, images.description, images.likes, images.user_id, users.nickname, users.profile_photo
        FROM images
        JOIN users ON images.user_id = users.id
    ''').fetchall()

    user_id = session.get('user_id')
    liked_images = []
    if user_id:
        liked_images = [row['image_id'] for row in conn.execute(
            'SELECT image_id FROM likes WHERE user_id = ?', (user_id,)
        ).fetchall()]
    conn.close()
    return render_template('index.html', images=images, current_user_id=user_id, liked_images=liked_images)

@app.route('/messages', methods=['GET', 'POST'])
@login_required
def messages():
    user_id = session['user_id']  
    conn = get_db_connection()

    messages = conn.execute('''
        SELECT messages.*, users.nickname AS sender_nickname 
        FROM messages 
        JOIN users ON messages.sender_id = users.id 
        WHERE messages.receiver_id = ?
        ORDER BY messages.timestamp DESC
    ''', (user_id,)).fetchall()

    users = conn.execute('SELECT id, nickname FROM users WHERE id != ?', (user_id,)).fetchall()

    conn.close()
    return render_template('messages.html', messages=messages, users=users,user_id=session['user_id'])

@app.route('/send_message', methods=['POST'])
@login_required
def send_message():
    sender_id = session['user_id']
    receiver_id = request.form['receiver_id']
    message = request.form['message']

    if not message.strip():
        flash("Message cannot be empty.")
        return redirect(url_for('messages'))

    conn = get_db_connection()
    conn.execute('''
        INSERT INTO messages (sender_id, receiver_id, message) 
        VALUES (?, ?, ?)
    ''', (sender_id, receiver_id, message))
    conn.commit()
    conn.close()

    flash("Message sent successfully!")
    return redirect(url_for('messages'))

@app.route('/messages/<int:user_id>', methods=['GET'])
@login_required
def view_messages(user_id):
    current_user_id = session['user_id']
    if current_user_id != user_id:
        return "Yetkiniz yok!", 403

    conn = get_db_connection()
    received_messages = conn.execute('''
        SELECT messages.message, messages.timestamp, users.nickname AS sender
        FROM messages
        JOIN users ON messages.sender_id = users.id
        WHERE messages.receiver_id = ?
        ORDER BY messages.timestamp DESC
    ''', (user_id,)).fetchall()

    sent_messages = conn.execute('''
        SELECT messages.message, messages.timestamp, users.nickname AS receiver
        FROM messages
        JOIN users ON messages.receiver_id = users.id
        WHERE messages.sender_id = ?
        ORDER BY messages.timestamp DESC
    ''', (user_id,)).fetchall()
    conn.close()

    return render_template(
        'messages.html',
        received_messages=received_messages,
        sent_messages=sent_messages
    )


@app.route('/upload', methods=['POST'])
@login_required
def upload_file():
    if 'file' not in request.files:
        return redirect(request.url)
    
    file = request.files['file']
    description = request.form.get('description', '')
    if file and allowed_file(file.filename):
        original_filename = secure_filename(file.filename)
        filename = generate_unique_filename("image", original_filename)

        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        
        conn = get_db_connection()
        conn.execute('INSERT INTO images (filename, user_id, description) VALUES (?, ?, ?)', 
                     (filename, session['user_id'], description))
        conn.commit()
        conn.close()
        return redirect(url_for('index'))
    return "Dosya yüklenemedi"




@app.route('/update_profile', methods=['GET', 'POST'])
@login_required
def update_profile():
    user_id = session['user_id'] 
    conn = get_db_connection()

    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()

    if request.method == 'POST':
        nickname = request.form['nickname']
        bio = request.form['bio']
        file = request.files.get('profile_photo')
        if file and allowed_file(file.filename):
            extension = os.path.splitext(file.filename)[1] 
            filename = f"profile_{uuid.uuid4().hex}{extension}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        else:
            filename = user['profile_photo']  

        conn.execute('UPDATE users SET nickname = ?, bio = ?, profile_photo = ? WHERE id = ?',
                     (nickname, bio, filename, user_id))
        conn.commit()
        conn.close()

        flash("Profil başarıyla güncellendi.")
        return redirect(url_for('profile', user_id=user_id))

    conn.close()
    return render_template('update_profile.html', user=user)



@app.route('/like/<int:image_id>', methods=['POST'])
@login_required
def like_image(image_id):
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))

    conn = get_db_connection()

    existing_like = conn.execute(
        'SELECT * FROM likes WHERE user_id = ? AND image_id = ?',
        (user_id, image_id)
    ).fetchone()

    if existing_like:
        conn.close()
        return "Bu fotoğrafı zaten beğendiniz!", 400  

    conn.execute('INSERT INTO likes (user_id, image_id) VALUES (?, ?)', (user_id, image_id))
    conn.execute('UPDATE images SET likes = likes + 1 WHERE id = ?', (image_id,))
    conn.commit()
    conn.close()

    return redirect(url_for('index'))

@app.route('/follow/<int:followed_id>', methods=['POST'])
@login_required
def follow_user(followed_id):
    follower_id = session['user_id']
    if follower_id == followed_id:
        return "Kendinizi takip edemezsiniz!", 400
    conn = get_db_connection()

    conn.execute('INSERT OR REPLACE INTO followers (follower_id, followed_id) VALUES (?, ?)', (follower_id, followed_id))
    conn.commit()
    
    if conn.execute('SELECT * FROM followers WHERE follower_id = ? AND followed_id = ?', (followed_id, follower_id)).fetchone():
        conn.execute('INSERT INTO friends (sender_id, receiver_id, status) VALUES (?, ?, "accepted")', (follower_id, followed_id))
        conn.commit()
    
    conn.close()
    return redirect(url_for('index'))

@app.route('/profile/<int:user_id>')
def profile(user_id):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    
    images = conn.execute('SELECT * FROM images WHERE user_id = ?', (user_id,)).fetchall()
    
    followers = conn.execute('SELECT users.nickname FROM followers JOIN users ON followers.follower_id = users.id WHERE followed_id = ?', (user_id,)).fetchall()
    following = conn.execute('SELECT users.nickname FROM followers JOIN users ON followers.followed_id = users.id WHERE follower_id = ?', (user_id,)).fetchall()

    followers_count = conn.execute('''
        SELECT COUNT(*) FROM followers WHERE followed_id = ?
    ''', (user_id,)).fetchone()[0]

    conn.close()
    return render_template('profile.html', user=user, images=images, followers=followers, following=following, followers_count=followers_count)


@app.route('/profile')
@login_required
def my_profile():
    return redirect(url_for('profile', user_id=session['user_id']))

@app.route('/delete/<filename>', methods=['GET'])
@login_required
def delete_file(filename):
    try:
        conn = get_db_connection()

        photo = conn.execute(
            'SELECT * FROM images WHERE filename = ? AND user_id = ?',
            (filename, session['user_id'])
        ).fetchone()

        if not photo:
            conn.close()
            return "Bu fotoğrafı silme yetkiniz yok!", 403

        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.exists(file_path):
            os.remove(file_path)

        conn.execute('DELETE FROM images WHERE filename = ?', (filename,))
        conn.commit()
        conn.close()
        return redirect(url_for('index'))
    except Exception as e:
        return f"Fotoğraf silinirken bir hata oluştu: {e}", 500

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['pwd']
        nickname = request.form['nickname']  
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')

        file = request.files.get('profile_photo') 
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        else:
            filename = 'basic_p.png'  

        conn = get_db_connection()
        conn.execute('''
            INSERT INTO users (username, email, password, nickname, profile_photo) 
            VALUES (?, ?, ?, ?, ?)
        ''', (username, email, hashed_password, nickname, filename))
        conn.commit()
        conn.close()

        flash('Kayıt başarılı! Giriş yapabilirsiniz.')
        return redirect(url_for('login'))

    return render_template('register.html')



@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['pwd']
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        conn.close()
        if user and check_password_hash(user['password'], password): 
            session['user_id'] = user['id']
            return redirect(url_for('index'))  
        else:
            return "Hatalı giriş", 401
    return render_template('login.html')

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    create_db()
    app.run(debug=True)