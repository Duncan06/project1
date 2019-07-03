import os
import requests

from flask import Flask, session, flash, redirect, render_template, request, url_for, jsonify
from flask_session import Session
from passlib.apps import custom_app_context as pwd_context
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

app = Flask(__name__, template_folder='../../scripts/project1')

# Check for environment variable
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL is not set")

# Configure session to use filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Set up database
engine = create_engine(os.getenv("DATABASE_URL"))
db = scoped_session(sessionmaker(bind=engine))

user_id = None

@app.route("/", methods=["GET"])
def index():

    if "user_id" in session:

        user_id = session["user_id"]

    if request.method == "GET":

        return render_template("index.html")

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "GET":
        return render_template("login.html")

    if request.method == 'POST':
        if not request.form.get("username"):
            return render_template("error.html", message="Must provide username.")
        if not request.form.get("password"):
            return render_template("error.html", message="Must provide password.")
        # query database for username
        user = db.execute("SELECT username, password, id FROM users WHERE username = :username", {"username":request.form.get("username")}).fetchone()

        # ensure username exists and password is correct
        for users in user:
            if users is None or not pwd_context.verify(request.form.get("password"), user["password"]):
                return render_template("error.html", message="Invalid username and/or password")
        # remember which user has logged in
        session["user_id"] = user["id"]

        # redirect user to home page
        return redirect(url_for("index"))

@app.route("/logout")
def logout():

    if "user_id" not in session:

        return render_template("error.html", message="You must login first.")

    try:
        session.pop("user_id", None)

    except KeyError:
        return render_template("error.html", message="You must be logged in first.")

    return render_template("index.html", message="You have successfully logged out.")

@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user."""

    if request.method == "GET":
        return render_template("register.html")

    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # ensure username was submitted
        if not request.form.get("username"):
            return render_template("error.html", message="Must provide username")

        # ensure password was submitted
        elif not request.form.get("password"):
            return render_template("error.html", message="Must provide password")

        elif not request.form.get("confirm password"):
            return render_template("error.html", message="Please confirm password")

        elif request.form.get("password") != request.form.get("confirm password"):
            return render_template("error.html", message="passwords must match")
        hashed = pwd_context.hash(request.form.get("password"))
        result = db.execute("INSERT INTO users (username, password) VALUES (:username, :hash)", {"username": request.form.get("username"), "hash": hashed})
        if not result:
            return render_template("error.html", message="Username already taken")
        db.commit()
        return render_template("index.html", message="Successfully registered.")
    else:
        return render_template("error.html", message="Must register to login")

@app.route("/search", methods=["GET", "POST"])
def search():
    """search for books"""

    if request.method == "GET":

        if "user_id" not in session:

            return render_template("error.html", message="You must login first.")

        else:

            return render_template("search.html")

    if request.method == "POST":
        if session["user_id"] != None:

            search = request.form.get("info")

            if search == "":
                return render_template("search.html", message="No results found.")

            results = db.execute("SELECT * FROM books WHERE isbn LIKE :search OR UPPER(title) LIKE :search OR UPPER(author) LIKE :search LIMIT 10",
                {"search": "%" + search.upper() + "%"}).fetchall()

            return render_template("search.html", results=results)


@app.route("/search/<int:book_id>", methods=["GET", "POST"])
def info(book_id):
    """show details of selection"""

    book = db.execute("SELECT * FROM books WHERE id = :book_id", {"book_id":book_id}).fetchone()

    if book is None:
        return render_template("error.html", message="No such book with this id.")

    #GoodReads API
    res = requests.get("https://www.goodreads.com/book/review_counts.json", params={"key": "qYVQdZbwzlpNz3XKprOLPQ", "isbns": book.isbn})

    #Set default values for data if none received.
    data = {"ratings_count": None, "average_rating": None}

    #If status code success
    if res.status_code ==  200:
        data = res.json()["books"][0]


    if request.method == "POST":

        if not request.form.get("review"):
            return render_template("error.html", message="Please submit a review first.")

        user_id = session["user_id"]

        rating = request.form.get("rating")

        review = request.form.get("review")

        user = db.execute("SELECT username FROM users WHERE id = :user_id", {"user_id":user_id}).fetchone()[0]

        if db.execute("SELECT id FROM reviews WHERE user_id = :user_id AND book_id = :book_id", {"user_id":user_id, "book_id": book_id}).fetchone() is None:

            db.execute("INSERT INTO reviews (user_id, book_id, rating, review, username) VALUES (:user_id, :book_id, :rating, :review, :username)",
                {"user_id":user_id, "book_id":book_id, "rating":rating, "review":review, "username":user})

        else:
            db.execute("UPDATE reviews SET review = :review, rating = :rating WHERE user_id = :user_id AND book_id = :book_id",
                {"user_id":user_id, "book_id":book_id, "rating":rating, "review":review})

        db.commit()

    posts = db.execute("SELECT review, rating, username FROM reviews WHERE book_id = :book_id", {"book_id":book_id}).fetchall()

    return render_template("info.html", posts=posts, book=book, data=data)


@app.route("/api/<isbn>")
def book_api(isbn):

    book = db.execute("SELECT * FROM books WHERE isbn = :isbn", {"isbn":isbn}).fetchone()

    if book is None:
        return jsonify ({"error": "Invalid book isbn."}), 422

    userdata = db.execute("SELECT rating FROM reviews WHERE book_id = :id", {"id":book.id}).fetchall()

    count = 0

    total = 0

    for user in userdata:
            count += 1
            total += user.rating

    avg = total/count

    return jsonify ({
        "title": book.title,
        "author": book.author,
        "year": book.year,
        "isbn": book.isbn,
        "ratings_count": count,
        "average_score": avg
    })
