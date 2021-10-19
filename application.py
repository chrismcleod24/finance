import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True


# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
# if not os.environ.get("API_KEY"):
# raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    user = session.get("user_id")

    stock = db.execute("SELECT * FROM buy WHERE id=? AND totalShares > 0 GROUP BY symbol ORDER BY time DESC", user)

    cash = db.execute("SELECT cash FROM users WHERE id=?", user)
    cash = round(cash[0]['cash'], 2)

    # total = cash + all stocks worth
    total = db.execute("SELECT total FROM users WHERE id=?", user)
    total = total[0]['total']
    total = cash

    # loop through all unique stocks get needed values and update db with current prices
    for row in stock:
        symbol = row['symbol']

        currentPrice = lookup(row['symbol'])
        currentPrice = currentPrice['price']

        worth = row['worth']

        worth = round(currentPrice * row['totalShares'], 2)

        total = round(total + row['worth'], 2)

        db.execute("UPDATE buy SET currentPrice=?, worth=? WHERE symbol=? AND id=?", currentPrice, worth, symbol, user)
        db.execute("UPDATE users SET total=? WHERE id=?", total, user)

    return render_template("index.html", stock=stock, cash=cash, total=total)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":

        user = session.get("user_id")

        symbol = lookup(request.form.get("symbol"))
        if not lookup(request.form.get("symbol")):
            return apology("must provide symbol", 403)

        shares = int(request.form.get("shares"))
        if shares < 1:
            return apology("must provide positive number of shares", 403)

        totalShares = db.execute(
            "SELECT totalShares FROM buy WHERE id = ? AND symbol = ? ORDER BY time DESC", user, symbol['symbol'])

        if len(totalShares) < 1:
            totalShares = 0

        else:
            totalShares = totalShares[0]['totalShares']

        totalShares = totalShares + shares

        cash = db.execute("SELECT cash FROM users WHERE id = ?", user)
        cash = cash[0]['cash']
        price = symbol['price']
        cost = round(price * shares, 2)

        if cash < cost:
            return apology("broke boy alert", 403)

        cash = round(cash - cost, 2)

        worth = totalShares * symbol['price']

        # total = cash + all stocks worth
        total = cash
        ownedStocks = db.execute("SELECT * FROM buy WHERE id=? GROUP BY symbol", user)

        # find total of all owned stocks
        for row in ownedStocks:
            total += round(row['worth'])

        db.execute("UPDATE users SET cash=?, total=? WHERE id=?", cash, total, user)
        db.execute(
            "INSERT INTO buy (symbol, price, id, shares, cost, totalShares, name, worth, currentPrice) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", symbol['symbol'], price, user, shares, cost, totalShares, symbol['name'], worth, symbol['price'])
        db.execute("UPDATE buy SET totalShares=? WHERE symbol=? AND id=?", totalShares, symbol['symbol'], user)

        return redirect("/")

    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    user = session.get("user_id")

    stock = db.execute("SELECT * FROM buy WHERE id=? ORDER BY time DESC", user)

    return render_template("history.html", stock=stock)


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
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
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
    """Get stock quote."""
    if request.method == "POST":
        symbol = lookup(request.form.get("symbol"))

        return render_template("quoted.html", symbol=symbol)

    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":

        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        usernamecheck = db.execute("SELECT * FROM users WHERE username = :username", username=username)

        if len(usernamecheck) > 0:
            return apology("Username already taken", 403)

        if password != confirmation:
            return apology("password does not match", 403)

        pwhash = generate_password_hash(request.form.get("password"))
        db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", username, pwhash)

        return redirect("/login")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    # get users owned stocks and display owned stocks in drop down
    user = session.get("user_id")
    stocks = db.execute("SELECT * FROM buy WHERE id=? AND totalShares > 0 GROUP BY symbol", user)

    # when form is submitted put shares as negative int and update totalShares, worth and users total
    if request.method == "POST":
        selected_stock = request.form.get("symbol")
        shares_sold = int(request.form.get("shares"))
        live_stock = lookup(request.form.get("symbol"))

        selected_stock = db.execute("SELECT * FROM buy WHERE id=? AND symbol=? GROUP BY symbol", user, selected_stock)
        cash = db.execute("SELECT cash FROM users WHERE id=?", user)

        total_shares = selected_stock[0]['totalShares']

        cost = live_stock['price'] * shares_sold
        sold_shares_value = shares_sold * live_stock['price']

        if shares_sold > selected_stock[0]['totalShares']:
            return apology("Need more stonks", 403)

        shares_sold = 0 - shares_sold
        total_shares += shares_sold

        # calculate new totalShares and worth
        worth = total_shares * live_stock['price']
        # update users cash the total updates when index renders
        cash = cash[0]['cash'] + sold_shares_value

        db.execute(
            "INSERT INTO buy (symbol, price, id, shares, cost, totalShares, name, worth, currentPrice) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", live_stock['symbol'], live_stock['price'], user, shares_sold, cost, total_shares, live_stock['name'], worth, live_stock['price'])
        db.execute("UPDATE buy SET totalShares=? WHERE id=? AND symbol=?", total_shares, user, live_stock['symbol'])
        db.execute("UPDATE users SET cash=? WHERE id=?", cash, user)

        return redirect("/")

    return render_template("sell.html", stocks=stocks)


@app.route("/reset", methods=["GET", "POST"])
def reset():
    """Reset password"""
    if request.method == "POST":

        username = request.form.get("username")
        password = request.form.get("new-password")
        confirmation = request.form.get("confirmation")

        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("new-password"):
            return apology("must provide password", 403)

        usernamecheck = db.execute("SELECT * FROM users WHERE username = :username", username=username)

        if username not in usernamecheck[0]['username']:
            return apology("invalid username", 403)

        if password != confirmation:
            return apology("password does not match", 403)

        pwhash = generate_password_hash(password)
        db.execute("UPDATE users SET hash=? WHERE username=?", pwhash, username)

        return redirect("/login")

    else:
        return render_template("reset.html")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
