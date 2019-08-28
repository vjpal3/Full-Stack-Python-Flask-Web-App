import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
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
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    user_id = session["user_id"]
    rows = db.execute("SELECT symbol, SUM(shares) as no_of_shares from portfolio where user_id = ? GROUP BY symbol", user_id)
    stocks = []

    for row in rows:
        # Get stock data from API
        stockData = lookup(row["symbol"])
        stockData["shares"] = row["no_of_shares"]
        stocks.append(stockData)

        # Add the total value of each holding
        grandTotal += stockData["price"] * stockData["shares"]

    # Get user's available cash
    cash = db.execute("Select cash from users where id = ?", user_id)
    # Add to the total, the available cash user has
    grandTotal += cash[0]["cash"]
    return render_template("index.html", stocks=stocks, cash=cash[0]["cash"], grandTotal=grandTotal)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")

        if not symbol:
            return apology("Please enter Symbol", 403)
        elif not shares:
            return apology("Please enter number of Shares", 403)

        try:
            shares = int(shares)
            if shares < 0:
               return apology("Please enter positive number of Shares", 403)

        except ValueError:
            return apology("Please enter positive number of Shares", 403)

        # Get stock's information from api
        result = lookup(symbol)
        # Check if symbol is valid
        if not result:
            return apology("Invalid Symbol", 400)

        user_id = session["user_id"]
        rows = db.execute("SELECT cash FROM users WHERE id = ?", (user_id))
        if not rows:
           return apology("Database error", 404)

        cash = rows[0]["cash"]

        totalPrice = shares * result["price"]
        if cash < totalPrice:
            return apology("Sorry! your acccount dosen't have enough cash", 400)

        # Insert data into user's portfolio
        sql = "INSERT INTO portfolio (user_id, symbol, price, shares) values( ?, ?, ?, ?)"
        db_insert = db.execute(sql, (user_id, result["symbol"], result["price"], shares ))
        if not db_insert:
            return apology("Database error", 404)

        # Update user's cash
        db_update = db.execute("UPDATE users set cash = ? WHERE id = ?", (cash - totalPrice, user_id))
        if not db_update:
            return apology("Database error", 404)

        flash("Bought!")
        return redirect("/")

    # user selected the link to buy shares of a perticular company on home page
    else:
        symbol = request.args.get("symbol")
        return render_template("buy.html", symbol=symbol)


@app.route("/check", methods=["GET"])
def check():
    """Return true if username available, else false, in JSON format"""
    username = request.args.get("username")
    if not username:
        return apology("Username required!", 403)

    # Query database for username
    result = db.execute("SELECT username FROM users WHERE username = :username", username=username)

    if not result:
        return jsonify(True)

    return jsonify(False)


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    user_id = session["user_id"]
    transactions = db.execute("SELECT symbol, shares, price, transacted FROM portfolio WHERE user_id = ? ORDER BY symbol ASC", user_id)
    return render_template("history.html", transactions=transactions)


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
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

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
        symbol = request.form.get("symbol")
        result = lookup(symbol)

        if not result:
            return apology("Invalid Symbol", 400)

        return render_template("quoted.html", result=result)

    #user reached route via GET
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    # User reached route via POST
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        password2 = request.form.get("confirmation")

        if not username:
            return apology("Username required!", 403)
        elif not password:
            return apology("Passsword required!", 403)
        elif not password == password2:
            return apology("Passwords do not match!", 403)

        hash = generate_password_hash(password);

        result = db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)", username=username, hash=hash)

        if not result:
            return apology("Username already exists! Please choose another username.")

        # Get user id of newly registered user
        rows = db.execute("SELECT id from users where username = :username", username=username)

        # Login the newly registered user
        session["user_id"] = rows[0]["id"]

        flash('Registered Successfully!')
        return redirect("/")
    # User reached route via GET
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    user_id = session["user_id"]

    # User reached here after posting form data
    if request.method == "POST":
        selectedSymbol = request.form.get("symbol")
        shares = request.form.get("shares")

        if not selectedSymbol:
            return apology("Missing symbol", 400)
        elif not shares:
            return apology("Please enter number of Shares", 400)

        try:
            shares = int(shares)
            if shares < 0:
               return apology("Please enter positive number of Shares", 400)
        except ValueError:
            return apology("Please enter positive number of Shares", 400)

        # Check if the user has that many shares to sell
        usersShares = db.execute("SELECT SUM(shares) as no_of_shares from portfolio where user_id = ? and symbol = ? GROUP BY symbol", user_id, selectedSymbol)
        if usersShares[0]["no_of_shares"] < shares:
            return apology("Sorry! Too many shares")

        stockData = lookup(selectedSymbol)
        totalPrice = shares * stockData["price"]

        # Enter the sale tranction into user's portfolio, the sold shares as negative value
        shares *= -1
        sql = "INSERT INTO portfolio (user_id, symbol, price, shares) values( ?, ?, ?, ?)"
        db_insert = db.execute(sql, (user_id, stockData["symbol"], stockData["price"], shares ))
        if not db_insert:
            return apology("Database error", 404)

        cashData = db.execute("SELECT cash FROM users WHERE id = ?", (user_id))
        if not cashData:
           return apology("Database error", 404)

        cash = cashData[0]["cash"]

        # Update user's cash
        db_update = db.execute("UPDATE users set cash = ? WHERE id = ?", (cash + totalPrice, user_id))
        if not db_update:
            return apology("Database error", 404)

        flash("Sold!")
        return redirect("/")

    else:
        symbolParam = request.args.get("symbol")
        symbols = []

        if not symbolParam:
            symbolsData = db.execute("SELECT symbol from portfolio where user_id = ? GROUP BY symbol", user_id)            
            for symbol in symbolsData:
                symbols.append(symbol["symbol"])

        # user selected the link to sell shares of a perticular company on home page
        else:
            symbols.append(symbolParam)
        return render_template("sell.html", symbols=symbols)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
