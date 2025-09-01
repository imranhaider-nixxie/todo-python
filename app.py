from flask import Flask, render_template, request, redirect, url_for, session, flash
import psycopg2
from werkzeug.security import generate_password_hash, check_password_hash
from openai import OpenAI
import os
import json
from dateutil.parser import parse as parse_date
from datetime import datetime

app = Flask(__name__)
app.secret_key = "your_secret_key_here"  # needed for sessions
# ------------------ OpenAI Client ------------------
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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
# ------------------ AI Task Parser ------------------

def ai_parse_task(user_input):
    """
    Convert natural language todo into a Python dict with:
    task (concise), category (meaningful), priority (low/medium/high/urgent), due_date (ISO).
    """
    prompt = f"""
    You are an expert personal assistant and task manager.
    Take this user's todo: "{user_input}"
    
    1. Rewrite the task in a concise, actionable way (task field).
    2. Assign a suitable category from: Work, Personal, Shopping, Health, Study, Finance (category field).
    3. Assign priority intelligently: low, medium, high, urgent (priority field).
    4. Determine due_date in ISO format YYYY-MM-DD if a date or time can be inferred, otherwise null.
    
    Only respond with valid JSON, never use 'default' or placeholders.
    Example output:
    {{
        "task": "Finish project report",
        "category": "Work",
        "priority": "high",
        "due_date": "2025-08-30"
    }}
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )

    text = response.choices[0].message.content

    # Convert JSON safely
    try:
        todo_data = json.loads(text)
    except Exception as e:
        print("JSON parse error:", e)
        todo_data = {}

    # Normalize task
    task_desc = todo_data.get("task") or user_input
    todo_data["task"] = task_desc

    # Validate category
    valid_categories = ["Work", "Personal", "Shopping", "Health", "Study", "Finance"]
    category = todo_data.get("category", "").strip()
    if category not in valid_categories:
        todo_data["category"] = "Personal"

    # Validate priority
    valid_priorities = ["low", "medium", "high", "urgent"]
    priority = todo_data.get("priority", "").strip().lower()
    if priority not in valid_priorities:
        todo_data["priority"] = "medium"
    todo_data["priority"] = priority

    # Validate due_date
    due_date = todo_data.get("due_date")
    if due_date:
        try:
            parsed_date = parse_date(str(due_date), fuzzy=True)
            todo_data["due_date"] = parsed_date.date().isoformat()
        except:
            todo_data["due_date"] = None
    else:
        # Try to infer from user input
        try:
            parsed_date = parse_date(user_input, fuzzy=True, default=datetime.today())
            if parsed_date.date() >= datetime.today().date():
                todo_data["due_date"] = parsed_date.date().isoformat()
            else:
                todo_data["due_date"] = None
        except:
            todo_data["due_date"] = None

    return todo_data


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
            flash("Error: " + str(e), "danger")
    
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
    cur.execute("""
        SELECT id, task, status, priority, category, due_date
        FROM todos
        WHERE user_id = %s
        ORDER BY id;
    """, (user_id,))
    todos = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("index.html", todos=todos)

@app.route("/add", methods=["POST"])
@login_required
def add():
    user_input = request.form.get("task")
    if user_input:
        todo_data = ai_parse_task(user_input)
        task_desc = todo_data.get("task")
        category = todo_data.get("category")
        priority = todo_data.get("priority")
        due_date = todo_data.get("due_date")

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO todos (task, user_id, category, priority, due_date)
            VALUES (%s, %s, %s, %s, %s)
        """, (task_desc, session["user_id"], category, priority, due_date))
        conn.commit()
        cur.close()
        conn.close()
        flash("Task added with AI-powered category, priority, and due date!", "success")
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
    flash("Task done successfully ✅", "success")
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
    flash("Task undone successfully ✅", "success")
    return redirect(url_for("index"))

@app.route("/edit/<int:task_id>", methods=["POST"])
@login_required
def edit(task_id):
    new_task_input = request.form.get("task")
    if new_task_input:
        # Use AI to parse the edited task
        todo_data = ai_parse_task(new_task_input)
        task_desc = todo_data.get("task", new_task_input)
        category = todo_data.get("category", "General")
        priority = todo_data.get("priority", "medium")
        due_date = todo_data.get("due_date")

        # Update the database
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE todos 
            SET task = %s, category = %s, priority = %s, due_date = %s 
            WHERE id = %s AND user_id = %s
        """, (task_desc, category, priority, due_date, task_id, session["user_id"]))
        conn.commit()
        cur.close()
        conn.close()

        flash("Task updated with AI enhancements ✅", "success")
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
    flash("Task deleted ❌", "info")
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(debug=True)
