import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash
import datetime

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    user_id = session["user_id"]

    trades_db = db.execute(
        "SELECT symbol, SUM(shares) as shares FROM trades WHERE id = ? AND type = 'buy' GROUP BY symbol", user_id)
    cash_db = db.execute("SELECT cash FROM users WHERE id = ?", user_id)
    cash = cash_db[0]["cash"]
    total = cash

    for row in trades_db:
        stock_details = lookup(row["symbol"])
        row["symbol"] = stock_details["symbol"]
        row["price"] = stock_details["price"]
        row["total_value"] = stock_details["price"] * row["shares"]

        total += row["total_value"]

    return render_template("index.html", db=trades_db, cash=cash, total=total)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    if request.method == "GET":
        return render_template("buy.html")
    else:
        symbol = request.form.get("symbol")
        stock_details = lookup(symbol)
        try:
            quantity = int(request.form.get("shares"))
        except ValueError:
            return apology("invalid quantity", 400)

        if not symbol:
            return apology("please provide a stock", 400)
        elif stock_details == None:
            return apology("stock does not exist", 400)
        elif quantity < 1:
            return apology("quantity must be more than 0", 400)

        user_id = session["user_id"]
        cost = quantity * stock_details["price"]
        all_cash = db.execute("SELECT cash FROM users WHERE id = ? ", user_id)
        user_cash = all_cash[0]["cash"]

        if cost > user_cash:
            return apology("Not enough cash!", 403)
        else:
            upd_cash = user_cash - cost
            db.execute("UPDATE users SET cash = ? WHERE id = ?", upd_cash, user_id)

            date = datetime.datetime.now()

            db.execute("INSERT INTO trades (id, symbol, shares, price, date, type) VALUES (? , ? , ? , ?, ?, ?)",
                       user_id, symbol, quantity, stock_details["price"], date, "buy")
            flash(f"{quantity} {symbol} Bought!")

            return redirect("/")


@app.route("/history")
@login_required
def history():
    user_id = session["user_id"]
    trades_db = db.execute("SELECT * FROM trades WHERE id = ?", user_id)

    return render_template("history.html", db=trades_db)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get(
                "username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    if request.method == "GET":
        return render_template("quote.html")
    else:
        if not request.form.get("symbol"):
            return apology("please provide a stock to quote", 400)

        stock_details = lookup(request.form.get("symbol"))

        if stock_details == None:
            return apology("stock does not exist", 400)

        return render_template("quoted.html", symbol=stock_details["symbol"], price=stock_details["price"])


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        if not username:
            return apology("must provide username", 400)

        elif not password:
            return apology("must provide password", 400)

        elif not confirmation:
            return apology("please verify password", 400)

        elif password != confirmation:
            return apology("passwords must match", 400)

        hash = generate_password_hash(password)
        try:
            new_user = db.execute(
                "INSERT INTO users (username, hash) VALUES (? , ?)", username, hash)
        except:
            return apology("username already exists", 400)
        session["user_id"] = new_user

        return redirect("/")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    if request.method == "GET":
        user_id = session["user_id"]
        sym_db = db.execute("SELECT symbol FROM trades WHERE id = ? GROUP BY symbol", user_id)

        return render_template("sell.html", db=sym_db)

    else:
        user_id = session["user_id"]
        symbol = request.form.get("symbol")
        try:
            quantity = int(request.form.get("shares"))
        except ValueError:
            return apology("invalid sell quantity", 400)
        stock_details = lookup(symbol)
        stock_db = db.execute("SELECT * FROM trades WHERE id = ? AND symbol = ?", user_id, symbol)

        if not symbol:
            return apology("input a valid stock", 400)

        if quantity < 1:
            return apology("invalid sell quantity", 400)

        owned_shares = stock_db[0]["shares"]
        if quantity > owned_shares:
            return apology("insufficient shares to sell", 400)

        # update cash of sold stock
        cash_db = db.execute("SELECT cash FROM users WHERE id=?", user_id)
        curr_cash = cash_db[0]["cash"]
        stock_value = stock_details["price"] * quantity
        cash = curr_cash + stock_value

        db.execute("UPDATE users SET cash = ? WHERE id = ?", cash, user_id)

        # update quantity of remaining shares, delete raw if quantity 0
        remaining_shares = owned_shares - quantity
        if remaining_shares != 0:
            db.execute("UPDATE trades SET shares = ? WHERE symbol = ? AND id = ?",
                       remaining_shares, symbol, user_id)
        else:
            db.execute("DELETE FROM trades WHERE symbol = ? AND id = ?", symbol, user_id)

        # update history
        date = datetime.datetime.now()

        db.execute("INSERT INTO trades (id, symbol, shares, price, date, type) VALUES (? , ? , ? , ?, ?, ?)",
                   user_id, symbol, quantity, stock_details["price"], date, "sell")
        flash(f"{quantity} {symbol} Sold!")

        return redirect("/")


@app.route("/change", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "GET":
        return render_template("change.html")
    else:
        user_id = session["user_id"]
        password = request.form.get("password")
        newpassword = request.form.get("newpassword")
        confirmation = request.form.get("confirmation")

        if not password:
            return apology("please enter password", 403)
        elif not newpassword:
            return apology("please enter new password", 403)
        elif not confirmation:
            return apology("please retype new password", 403)
        elif newpassword != confirmation:
            return apology("new password does not match!", 403)
        elif password == newpassword:
            return apology("new and old password are the same!", 403)

        hash = generate_password_hash(newpassword)
        db.execute("UPDATE users SET hash = ? WHERE id = ?", hash, user_id)
        flash("Password Changed!")

        return redirect("/")
