from flask import Flask, request, jsonify, render_template, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from datetime import datetime
import os
from functools import wraps

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'default_secret_key')
DATABASE = 'bookings.db'

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

class User(UserMixin):
    def __init__(self, id, username, email, password):
        self.id = id
        self.username = username
        self.email = email
        self.password = password

@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE userID = ?', (user_id,)).fetchone()
    conn.close()
    if user:
        return User(id=user['userID'], username=user['username'], email=user['email'], password=user['password'])
    return None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/about')
def about():
    return render_template('about.html')

# Custom login required decorator
def login_required_with_flash(message):
    def decorator(func):
        @wraps(func)
        def decorated_view(*args, **kwargs):
            if not current_user.is_authenticated:
                flash(message, 'warning')
                return redirect(url_for('login'))
            return func(*args, **kwargs)
        return decorated_view
    return decorator

@app.route('/contact', methods=['GET', 'POST'])
@login_required_with_flash('Please log in to access the contact form.')
def contact():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        message = request.form['message']

        conn = get_db_connection()
        conn.execute(
            'INSERT INTO inquiries (name, email, message, userID) VALUES (?, ?, ?, ?)',
            (name, email, message, current_user.id)
        )
        conn.commit()
        conn.close()

        flash('Your message has been sent successfully!', 'success')
        return redirect(url_for('about'))
    
    return redirect(url_for('about'))


@app.route('/wedding-packages')
def wedding_packages():
    conn = get_db_connection()
    packages = conn.execute('SELECT * FROM packages WHERE type = ?', ('wedding',)).fetchall()
    conn.close()
    return render_template('wedding_packages.html', packages=packages)

@app.route('/birthday-packages')
def birthday_packages():
    conn = get_db_connection()
    packages = conn.execute('SELECT * FROM packages WHERE type = ?', ('birthday',)).fetchall()
    conn.close()
    return render_template('birthday_packages.html', packages=packages)

@app.route('/packages')
def get_packages():
    event_type = request.args.get('event_type')
    conn = get_db_connection()
    packages = conn.execute('SELECT * FROM packages WHERE type = ?', (event_type,)).fetchall()
    conn.close()
    packages_list = [dict(row) for row in packages]
    return jsonify({'packages': packages_list})

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data['username']
    email = data['email']
    password = data['password']

    conn = get_db_connection()
    existing_user = conn.execute('SELECT * FROM users WHERE username = ? OR email = ?', (username, email)).fetchone()
    
    if existing_user:
        conn.close()
        return jsonify({'success': False, 'message': 'User already exists'}), 400

    hashed_password = generate_password_hash(password, method='pbkdf2:sha256')

    conn.execute(
        'INSERT INTO users (username, email, password) VALUES (?, ?, ?)',
        (username, email, hashed_password)
    )
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'User registered successfully'}), 200

@app.route('/check_auth', methods=['GET'])
def check_auth():
    if current_user.is_authenticated:
        return jsonify({'is_authenticated': True})
    else:
        return jsonify({'is_authenticated': False})

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data['username']
    password = data['password']

    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    conn.close()

    if user and check_password_hash(user['password'], password):
        user_obj = User(id=user['userID'], username=user['username'], email=user['email'], password=user['password'])
        login_user(user_obj)
        return jsonify({'success': True, 'message': 'Login successful'}), 200
    else:
        return jsonify({'success': False, 'message': 'Invalid credentials'}), 401

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/bookings', methods=['POST'])
@login_required
def create_booking():
    data = request.get_json()
    
    # Debugging: log the received data
    app.logger.debug("Received data: %s", data)

    event_type = data.get('event_type')
    event_date = data.get('event_date')
    event_time = data.get('event_time')
    attendees = data.get('attendees')
    location = data.get('location')
    package_id = data.get('package')

    if event_type not in ['birthday', 'wedding']:
        return jsonify({'success': False, 'message': 'Invalid event type'})

    try:
        datetime.strptime(event_date, '%Y-%m-%d')
    except ValueError:
        return jsonify({'success': False, 'message': 'Invalid date format'})

    try:
        datetime.strptime(event_time, '%H:%M')
    except ValueError:
        return jsonify({'success': False, 'message': 'Invalid time format'})

    try:
        attendees = int(attendees)
        if attendees <= 0:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Number of attendees must be a positive integer'})
    
    # Additional checks for package_id
    if package_id is None or package_id == '':
        return jsonify({'success': False, 'message': 'Package ID is required'})
    
    try:
        package_id = int(package_id)
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Package ID must be an integer'})

    conn = get_db_connection()
    package = conn.execute('SELECT * FROM packages WHERE packageID = ?', (package_id,)).fetchone()
    if not package:
        conn.close()
        return jsonify({'success': False, 'message': 'Invalid package ID'})
    
    max_attendees = package['max_attendees']
    if attendees > max_attendees:
        conn.close()
        return jsonify({
            'success': False,
            'message': f'Maximum number of attendees for this package is {max_attendees}.'
            }), 400

    
    conn.execute(
        'INSERT INTO bookings (event_type, event_date, event_time, attendees, location, userID, packageID) VALUES (?, ?, ?, ?, ?, ?, ?)',
        (event_type, event_date, event_time, attendees, location, current_user.id, package_id)
    )
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'Booking created successfully!'})

def init_db():
    with app.app_context():
        conn = get_db_connection()
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                userID INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                event_date TEXT NOT NULL,
                event_time TEXT NOT NULL,
                attendees INTEGER NOT NULL,
                location TEXT NOT NULL,
                userID INTEGER NOT NULL,
                packageID INTEGER,
                FOREIGN KEY (userID) REFERENCES users (userID),
                FOREIGN KEY (packageID) REFERENCES packages (packageID)
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS packages (
                packageID INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                type TEXT NOT NULL,
                image TEXT NOT NULL,
                max_attendees INTEGER NOT NULL DEFAULT 100
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS inquiries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                message TEXT NOT NULL,
                userID INTEGER NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (userID) REFERENCES users (userID)
            )
        ''')
        
        conn.commit()
        conn.close()

def add_packages():
    with app.app_context():
        conn = get_db_connection()
        existing_packages = conn.execute('SELECT COUNT(*) FROM packages').fetchone()[0]
        
        
        if existing_packages == 0:
            conn.executescript('''
                INSERT INTO packages (name, description, type, image, max_attendees) VALUES
                ('Classic Elegance Package', '<ul><li><b>Venue:</b> Grand Ballroom</li><li><b>Catering:</b> 4-course gourmet meal with wine</li><li><b>Decorations:</b> Classic floral arrangements and elegant lighting</li><li><b>Music:</b> Live band for 5 hours</li><li><b>Photography:</b> Full-day coverage</li><li><b>Additional Services:</b> Bridal suite, valet parking</li><li><b>Price:</b> $10,000</li></ul>', 'wedding', 'classic_elegance_package.jpg', 150),
                ('Intimate Ceremony Package', '<ul><li><b>Venue:</b> Private Garden</li><li><b>Catering:</b> 3-course meal with champagne toast</li><li><b>Decorations:</b> Minimalist floral decor and candles</li><li><b>Music:</b> Solo musician for ceremony</li><li><b>Photography:</b> 4-hour coverage</li><li><b>Additional Services:</b> Wedding planner, transportation for couple</li><li><b>Price:</b> $5,000</li></ul>', 'wedding', 'intimate_ceremony_package.jpg', 40),
                ('Destination Wedding Package', '<ul><li><b>Venue:</b> Beach Resort</li><li><b>Catering:</b> Seafood buffet with tropical cocktails</li><li><b>Decorations:</b> Tropical floral arrangements and tiki torches</li><li><b>Music:</b> Steel drum band</li><li><b>Photography:</b> Full-day coverage with sunset photo shoot</li><li><b>Additional Services:</b> Accommodation for couple, welcome dinner</li><li><b>Price:</b> $20,000</li></ul>', 'wedding', 'destination_wedding_package.jpg', 80),
                ('Deluxe Package', '<ul><li><b>Venue:</b> Seaside Villa</li><li><b>Catering:</b> 5-course meal with seafood and wine pairings</li><li><b>Decorations:</b> Customized floral arrangements, centerpieces, and elegant lighting</li><li><b>Music:</b> String quartet for ceremony and DJ for reception</li><li><b>Photography:</b> Full-day coverage with two photographers</li><li><b>Videography:</b> Full-day coverage with drone footage</li><li><b>Additional Services:</b> On-site wedding coordinator, luxury transportation for bride and groom</li><li><b>Price:</b> $15,000</li></ul>', 'wedding', 'deluxe_package.jpg', 100),
                ('Rustic Charm Package', '<ul><li><b>Venue:</b> Countryside Barn</li><li><b>Catering:</b> Farm-to-table buffet with dessert bar</li><li><b>Decorations:</b> Rustic decor with wildflowers, mason jar centerpieces, and string lights</li><li><b>Music:</b> Live folk band for 4 hours</li><li><b>Photography:</b> 6-hour coverage with digital and printed albums</li><li><b>Videography:</b> 4-hour coverage</li><li><b>Additional Services:</b> Hayride for guests, fire pit with s''mores station</li><li><b>Price:</b> $7,000</li></ul>', 'wedding', 'rustic_charm_package.jpg', 120),
                ('Fairytale Package', '<ul><li><b>Venue:</b> Castle or Historic Estate</li><li><b>Catering:</b> 6-course gourmet meal with premium wine and champagne</li><li><b>Decorations:</b> Extravagant floral arrangements, chandeliers, and drapery</li><li><b>Music:</b> Orchestra for ceremony and live band for reception</li><li><b>Photography:</b> Full-day coverage with videography and drone shots</li><li><b>Additional Services:</b> Horse-drawn carriage, fireworks display, luxury accommodation for the couple</li><li><b>Price:</b> $25,000</li></ul>', 'wedding', 'fairytale_package.jpg', 200),
                
                ('Kids Fun Package', '<ul><li><b>Venue:</b> Indoor Play Center</li><li><b>Catering:</b> Pizza, snacks, and cake</li><li><b>Decorations:</b> Themed decorations (e.g., superheroes, princesses)</li><li><b>Entertainment:</b> Clown or magician, games</li><li><b>Party Favors:</b> Goodie bags with toys and candy</li><li><b>Price:</b> $500</li></ul>', 'birthday', 'kids_fun_package.jpg', 25),
                ('Teen Bash Package', '<ul><li><b>Venue:</b> Private Party Room</li><li><b>Catering:</b> Buffet with snacks and soft drinks</li><li><b>Decorations:</b> Modern decor with a theme of choice</li><li><b>Entertainment:</b> DJ and dance floor, photo booth</li><li><b>Party Favors:</b> Customized items (e.g., T-shirts, hats)</li><li><b>Price:</b> $1,200</li></ul>', 'birthday', 'teen_bash_package.jpg', 50),
                ('Adult Celebration Package', '<ul><li><b>Venue:</b> Banquet Hall</li><li><b>Catering:</b> 3-course meal with wine and cocktails</li><li><b>Decorations:</b> Elegant decor with centerpieces</li><li><b>Entertainment:</b> Live band or DJ, karaoke</li><li><b>Additional Services:</b> Bartender, event coordinator</li><li><b>Price:</b> $3,000</li></ul>', 'birthday', 'adult_celebration_package.jpg', 100),
                ('Outdoor Adventure Package', '<ul><li><b>Venue:</b> Adventure Park</li><li><b>Catering:</b> BBQ picnic with snacks and cake</li><li><b>Decorations:</b> Outdoor-themed decorations and banners</li><li><b>Entertainment:</b> Guided adventure activities (zip-lining, rock climbing)</li><li><b>Party Favors:</b> Adventure gear (e.g., hats, water bottles)</li><li><b>Price:</b> $1,500</li></ul>', 'birthday', 'outdoor_adventure_package.jpg', 40),
                ('Spa Day Package', '<ul><li><b>Venue:</b> Luxury Spa</li><li><b>Catering:</b> Light refreshments and birthday cake</li><li><b>Decorations:</b> Relaxing spa-themed decor with flowers and candles</li><li><b>Entertainment:</b> Spa treatments (massages, facials, manicures) for guests</li><li><b>Additional Services:</b> Personalized bathrobes for each guest</li><li><b>Price:</b> $2,000</li></ul>', 'birthday', 'spa_day_package.jpg', 20),
                ('Movie Night Package', '<ul><li><b>Venue:</b> Private Theater or Home Setup</li><li><b>Catering:</b> Popcorn, snacks, soft drinks, and cake</li><li><b>Decorations:</b> Movie-themed decor with posters and banners</li><li><b>Entertainment:</b> Screening of favorite movies or a new release</li><li><b>Additional Services:</b> Red carpet entrance, photo ops with themed props</li><li><b>Price:</b> $800</li></ul>', 'birthday', 'movie_night_package.jpg', 30);
            ''')
            conn.commit()
        conn.close()


import re

def regex_findall(value, pattern):
    return re.findall(pattern, value)


app.jinja_env.filters['regex_findall'] = regex_findall


if __name__ == '__main__':
    init_db()
    add_packages()
    app.run(debug=True)
