import os
import uuid
from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView
from flask_admin.form import ImageUploadField

# --- MONKEY PATCH FOR Pillow 10.0+ ---
# Flask-Admin uses an attribute 'ANTIALIAS' that was removed in Pillow 10.
# We are adding it back here to maintain compatibility.
from PIL import Image
if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.LANCZOS
# --- END MONKEY PATCH ---

# --- App Configuration ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///movies.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- Configuration for Image Uploads ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.config['POSTER_UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'static/uploads/posters/')
app.config['AVATAR_UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'static/uploads/avatars/')
os.makedirs(app.config['POSTER_UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['AVATAR_UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- Database Models ---
class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rating = db.Column(db.Integer, nullable=False)
    text = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    movie_id = db.Column(db.Integer, db.ForeignKey('movie.id'))

# --- Association Tables ---
user_genre_preferences = db.Table('user_genre_preferences',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('genre_id', db.Integer, db.ForeignKey('genre.id'), primary_key=True)
)
user_liked_movies = db.Table('user_liked_movies',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('movie_id', db.Integer, db.ForeignKey('movie.id'), primary_key=True)
)
user_language_preferences = db.Table('user_language_preferences',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('language_id', db.Integer, db.ForeignKey('language.id'), primary_key=True)
)
movie_genres = db.Table('movie_genres',
    db.Column('movie_id', db.Integer, db.ForeignKey('movie.id'), primary_key=True),
    db.Column('genre_id', db.Integer, db.ForeignKey('genre.id'), primary_key=True)
)
movie_languages = db.Table('movie_languages',
    db.Column('movie_id', db.Integer, db.ForeignKey('movie.id'), primary_key=True),
    db.Column('language_id', db.Integer, db.ForeignKey('language.id'), primary_key=True)
)
user_watchlist = db.Table('user_watchlist',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('movie_id', db.Integer, db.ForeignKey('movie.id'), primary_key=True)
)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    has_completed_survey = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)
    bio = db.Column(db.Text, nullable=True)
    avatar_path = db.Column(db.String(200), nullable=False, default='default.jpg')
    
    reviews = db.relationship('Review', backref='author', lazy='dynamic')
    preferred_genres = db.relationship('Genre', secondary=user_genre_preferences, backref='preferring_users')
    liked_movies = db.relationship('Movie', secondary=user_liked_movies, backref='liking_users')
    preferred_languages = db.relationship('Language', secondary=user_language_preferences, backref='preferring_users_lang')
    watchlist = db.relationship('Movie', secondary=user_watchlist, backref='watchlisted_by')

    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)

class Movie(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    overview = db.Column(db.Text, nullable=True)
    poster_path = db.Column(db.String(200), nullable=False, default='default_poster.jpg', server_default='default_poster.jpg')
    rating = db.Column(db.Float, nullable=True)
    reviews = db.relationship('Review', backref='movie', lazy='dynamic')
    genres = db.relationship('Genre', secondary=movie_genres, backref='movies_in_genre')
    languages = db.relationship('Language', secondary=movie_languages, backref='movies_in_lang')

class Genre(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    
    def __str__(self):
        return self.name

    def __repr__(self):
        return self.name

class Language(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    
    def __str__(self):
        return self.name
        
    def __repr__(self):
        return self.name

# --- ADMIN PANEL SETUP (Updated for Image Uploads) ---
def unique_poster_namegen(obj, file_data):
    ext = os.path.splitext(file_data.filename)[1]
    safe_title = secure_filename(obj.title.lower().replace(' ', '_'))
    unique_id = uuid.uuid4().hex[:6]
    return f"{safe_title}_{unique_id}{ext}"

class SecureAdminView(ModelView):
    def is_accessible(self):
        return current_user.is_authenticated and current_user.is_admin
    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('login'))

class MovieAdminView(SecureAdminView):
    form_columns = ['title', 'overview', 'poster_path', 'rating', 'genres', 'languages']
    
    form_overrides = {
        'poster_path': ImageUploadField
    }
    form_args = {
        'poster_path': {
            'label': 'Movie Poster',
            'base_path': app.config['POSTER_UPLOAD_FOLDER'],
            'url_relative_path': 'uploads/posters/',
            'namegen': unique_poster_namegen,
            'allowed_extensions': ('jpg', 'jpeg', 'png', 'gif'),
            'max_size': (800, 1200, True),
            # 'thumbnail_size': (100, 150, True),
        }
    }

admin = Admin(app, name='CineSuggest Admin', template_mode='bootstrap4')
admin.add_view(SecureAdminView(User, db.session))
admin.add_view(MovieAdminView(Movie, db.session)) # Using the custom view
admin.add_view(SecureAdminView(Genre, db.session))
admin.add_view(SecureAdminView(Language, db.session))
admin.add_view(SecureAdminView(Review, db.session))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Flask Routes ---
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template("index.html")

@app.route('/dashboard')
@login_required
def dashboard():
    languages = Language.query.order_by(Language.name).all()
    return render_template("dashboard.html", languages=languages)

@app.route('/genres/<language_name>')
@login_required
def genres_by_language(language_name):
    language = Language.query.filter_by(name=language_name).first_or_404()
    genres = Genre.query.join(Movie.genres).join(Movie.languages).filter(Language.id == language.id).distinct().order_by(Genre.name).all()
    return render_template('genres_by_language.html', genres=genres, language=language)

@app.route('/movies/<language_name>/<int:genre_id>')
@login_required
def movies_by_genre_and_lang(language_name, genre_id):
    language = Language.query.filter_by(name=language_name).first_or_404()
    genre = Genre.query.get_or_404(genre_id)
    movies = Movie.query.join(Movie.genres).join(Movie.languages).filter(Genre.id == genre.id, Language.id == language.id).all()
    return render_template('genre_movies.html', movies=movies, genre=genre, language=language)

@app.route('/movie/<int:movie_id>', methods=['GET', 'POST'])
@login_required
def movie_detail(movie_id):
    movie = Movie.query.get_or_404(movie_id)
    user_review = movie.reviews.filter_by(user_id=current_user.id).first()
    if request.method == 'POST':
        if user_review:
            flash('You have already reviewed this movie. You can edit your existing review.', 'error')
            return redirect(url_for('movie_detail', movie_id=movie_id))
        rating = request.form.get('rating')
        text = request.form.get('review_text')
        if not rating:
            flash('You must provide a rating.', 'error')
            return redirect(url_for('movie_detail', movie_id=movie_id))
        new_review = Review(rating=int(rating), text=text, user_id=current_user.id, movie_id=movie.id)
        db.session.add(new_review)
        db.session.commit()
        flash('Your review has been submitted!', 'success')
        return redirect(url_for('movie_detail', movie_id=movie_id))
    reviews = movie.reviews.order_by(Review.timestamp.desc()).all()
    return render_template('movie_detail.html', movie=movie, reviews=reviews, user_review=user_review)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'error')
            return redirect(url_for('register'))
        new_user = User(username=username)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        flash('Account created! Please complete the survey to get started.', 'success')
        return redirect(url_for('survey'))
    return render_template("register.html")

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            if not user.has_completed_survey:
                flash('Welcome! Please complete the survey to get recommendations.', 'info')
                return redirect(url_for('survey'))
            return redirect(url_for('dashboard'))
        flash('Invalid username or password.', 'error')
    return render_template("login.html")

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/survey', methods=['GET', 'POST'])
@login_required
def survey():
    if request.method == 'POST':
        lang_ids = request.form.getlist('languages')
        current_user.preferred_languages = Language.query.filter(Language.id.in_(lang_ids)).all()
        genre_ids = request.form.getlist('genres')
        current_user.preferred_genres = Genre.query.filter(Genre.id.in_(genre_ids)).all()
        movie_ids = request.form.getlist('liked_movies')
        current_user.liked_movies = Movie.query.filter(Movie.id.in_(movie_ids)).all()
        current_user.has_completed_survey = True
        db.session.commit()
        flash('Your preferences have been saved!', 'success')
        return redirect(url_for('recommendations'))

    all_genres = Genre.query.order_by(Genre.name).all()
    all_languages = Language.query.order_by(Language.name).all()
    popular_movies = Movie.query.order_by(Movie.rating.desc()).limit(20).all()
    return render_template("survey.html", popular_movies=popular_movies, all_genres=all_genres, all_languages=all_languages)

@app.route('/recommendations')
@login_required
def recommendations():
    if not current_user.has_completed_survey:
        flash('Please complete the survey to get recommendations.', 'info')
        return redirect(url_for('survey'))
    user_pref_genre_ids = {genre.id for genre in current_user.preferred_genres}
    user_pref_lang_ids = {lang.id for lang in current_user.preferred_languages}
    seed_movie_genre_ids = {genre.id for movie in current_user.liked_movies for genre in movie.genres}
    liked_movie_ids = {movie.id for movie in current_user.liked_movies}
    candidate_movies = Movie.query.join(Movie.languages).filter(Language.id.in_(user_pref_lang_ids)).all()
    recommendations_scores = {}
    for movie in candidate_movies:
        if movie.id in liked_movie_ids:
            continue
        score = 0
        movie_genre_ids = {genre.id for genre in movie.genres}
        direct_matches = user_pref_genre_ids.intersection(movie_genre_ids)
        score += len(direct_matches) * 10
        indirect_matches = seed_movie_genre_ids.intersection(movie_genre_ids)
        score += len(indirect_matches) * 5
        if score > 0:
            recommendations_scores[movie] = score
    sorted_recommendations = sorted(recommendations_scores.items(), key=lambda item: item[1], reverse=True)
    return render_template("recommendations.html", recommendations=sorted_recommendations)

@app.route('/watchlist/toggle/<int:movie_id>', methods=['POST'])
@login_required
def toggle_watchlist(movie_id):
    movie = Movie.query.get_or_404(movie_id)
    if movie in current_user.watchlist:
        current_user.watchlist.remove(movie)
        flash(f'"{movie.title}" removed from your watchlist.', 'success')
    else:
        current_user.watchlist.append(movie)
        flash(f'"{movie.title}" added to your watchlist.', 'success')
    db.session.commit()
    return redirect(url_for('movie_detail', movie_id=movie_id))

@app.route('/watchlist')
@login_required
def watchlist():
    watchlist_movies = current_user.watchlist
    return render_template('watchlist.html', watchlist_movies=watchlist_movies)

@app.route('/profile/<username>')
@login_required
def profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    reviews = user.reviews.order_by(Review.timestamp.desc()).all()
    return render_template('profile.html', user=user, reviews=reviews)

@app.route('/review/edit/<int:review_id>', methods=['GET', 'POST'])
@login_required
def edit_review(review_id):
    review = Review.query.get_or_404(review_id)
    if review.author != current_user:
        abort(403)
    if request.method == 'POST':
        review.rating = request.form['rating']
        review.text = request.form['review_text']
        db.session.commit()
        flash('Your review has been updated!', 'success')
        return redirect(url_for('movie_detail', movie_id=review.movie_id))
    return render_template('edit_review.html', review=review)

@app.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if request.method == 'POST':
        current_user.bio = request.form.get('bio')
        if 'avatar' in request.files:
            file = request.files['avatar']
            if file.filename != '':
                ext = os.path.splitext(file.filename)[1]
                unique_filename = secure_filename(current_user.username + '_' + uuid.uuid4().hex[:8] + ext)
                file_path = os.path.join(app.config['AVATAR_UPLOAD_FOLDER'], unique_filename)
                file.save(file_path)
                current_user.avatar_path = unique_filename
        db.session.commit()
        flash('Your profile has been updated!', 'success')
        return redirect(url_for('profile', username=current_user.username))
    return render_template('edit_profile.html')

# --- CLI Commands ---
@app.cli.command("init-db")
def init_db_command():
    db.create_all()
    print("Initialized the database.")

@app.cli.command("create-admin")
def create_admin_command():
    username = input("Enter admin username: ")
    password = input("Enter admin password: ")
    user = User.query.filter_by(username=username).first()
    if user:
        user.is_admin = True
        print(f"Existing user '{username}' updated to admin.")
    else:
        new_admin = User(username=username, is_admin=True, has_completed_survey=True)
        new_admin.set_password(password)
        db.session.add(new_admin)
        print(f"New admin user '{username}' created.")
    db.session.commit()

@app.cli.command("seed-mock-data")
def seed_mock_data_command():
    print("Deleting old data...")
    Review.query.delete()
    db.session.execute(user_genre_preferences.delete())
    db.session.execute(user_liked_movies.delete())
    db.session.execute(user_language_preferences.delete())
    db.session.execute(user_watchlist.delete())
    db.session.execute(movie_genres.delete())
    db.session.execute(movie_languages.delete())
    Movie.query.delete()
    User.query.delete()
    Genre.query.delete()
    Language.query.delete()
    
    print("Seeding new mock data...")
    lang_en = Language(name='English')
    lang_hi = Language(name='Hindi')
    lang_gu = Language(name='Gujarati')
    g_action = Genre(name='Action')
    g_comedy = Genre(name='Comedy')
    g_scifi = Genre(name='Sci-Fi')
    g_drama = Genre(name='Drama')
    g_crime = Genre(name='Crime')
    db.session.add_all([lang_en, lang_hi, lang_gu, g_action, g_comedy, g_scifi, g_drama, g_crime])
    
    m1 = Movie(title='The Dark Knight', overview='The Joker wreaks havoc on Gotham.', poster_path='the_dark_knight.jpg', rating=9.0)
    m2 = Movie(title='Inception', overview='A thief who steals corporate secrets through dream-sharing technology.', poster_path='inception.jpg', rating=8.8)
    m3 = Movie(title='3 Idiots', overview='Two friends are searching for their long lost companion.', poster_path='3_idiots.jpg', rating=8.4)
    m4 = Movie(title='Lagaan', overview='A small village in Victorian India stakes their future on a game of cricket.', poster_path='lagaan.jpg', rating=8.1)
    m5 = Movie(title='Chhello Divas', overview='The lives of eight friends and their journey of growing up.', poster_path='chhello_divas.jpg', rating=8.5)
    m6 = Movie(title='Hellaro', overview='A group of women from the Kutch region of Gujarat express themselves through garba.', poster_path='hellaro.jpg', rating=8.2)
    
    m1.genres.extend([g_action, g_drama, g_crime]); m1.languages.append(lang_en)
    m2.genres.extend([g_action, g_scifi]); m2.languages.append(lang_en)
    m3.genres.extend([g_drama, g_comedy]); m3.languages.append(lang_hi)
    m4.genres.append(g_drama); m4.languages.append(lang_hi)
    m5.genres.extend([g_comedy, g_drama]); m5.languages.append(lang_gu)
    m6.genres.append(g_drama); m6.languages.append(lang_gu)
    
    db.session.add_all([m1, m2, m3, m4, m5, m6])
    db.session.commit()
    print("Mock data has been seeded successfully!")

if __name__ == '__main__':
    app.run(debug=True)