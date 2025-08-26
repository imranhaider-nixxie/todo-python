from flask import Flask, render_template, request, redirect, url_for, session, flash
import psycopg2
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "your_secret_key_here"  # needed for sessions

# Database configuration
DB_NAME = "todo_db"
DB_USER = "postgres"
DB_PASS = "haider"
DB_HOST = "localhost"
DB_PORT = "5433"

def get_db_connection():
    conn = psycopg2.connect(
        dbname=DB_NAME, user=DB_USER, password=DB_PASS,
        host=DB_HOST, port=DB_PORT
    )
    return conn

# --------------------- User Authentication ---------------------

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, password FROM users WHERE username = %s", (username,))
        user = cur.fetchone()
        cur.close()
        conn.close()

        if user and check_password_hash(user[1], password):
            session["user_id"] = user[0]
            session["username"] = username
            return redirect(url_for("index"))
        else:
            flash("Invalid username or password", "danger")
    
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        first_name = request.form.get("first_name")
        last_name = request.form.get("last_name")
        email = request.form.get("email")
        username = request.form.get("username")
        password = request.form.get("password")

        hashed_password = generate_password_hash(password)

        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO users (first_name, last_name, email, username, password)
                VALUES (%s, %s, %s, %s, %s)
            """, (first_name, last_name, email, username, hashed_password))
            conn.commit()
            cur.close()
            conn.close()

            flash("Registration successful. Please login.", "success")
            return redirect(url_for("login"))
        except Exception as e:
            print("Error:", e)  # Debugging
            flash("Username or email already exists!", "danger")
    
    return render_template("register.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# --------------------- TODO Routes ---------------------

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

@app.route("/todos")
@login_required
def index():
    user_id = session["user_id"]
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, task, status FROM todos WHERE user_id = %s ORDER BY id;", (user_id,))
    todos = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("index.html", todos=todos)

@app.route("/add", methods=["POST"])
@login_required
def add():
    task = request.form.get("task")
    if task:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO todos (task, user_id) VALUES (%s, %s)", (task, session["user_id"]))
        conn.commit()
        cur.close()
        conn.close()
    return redirect(url_for("index"))

@app.route("/done/<int:task_id>")
@login_required
def done(task_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE todos SET status = TRUE WHERE id = %s AND user_id = %s", (task_id, session["user_id"]))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for("index"))

@app.route("/undone/<int:task_id>")
@login_required
def undone(task_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE todos SET status = FALSE WHERE id = %s AND user_id = %s", (task_id, session["user_id"]))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for("index"))

@app.route("/edit/<int:task_id>", methods=["POST"])
@login_required
def edit(task_id):
    new_task = request.form.get("task")
    if new_task:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE todos SET task = %s WHERE id = %s AND user_id = %s", (new_task, task_id, session["user_id"]))
        conn.commit()
        cur.close()
        conn.close()
    return redirect(url_for("index"))

@app.route("/delete/<int:task_id>")
@login_required
def delete(task_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM todos WHERE id = %s AND user_id = %s", (task_id, session["user_id"]))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(debug=True)
